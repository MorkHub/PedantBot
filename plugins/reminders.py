import json
import math
import time

import aioredis
import pytz
from dateutil import parser

from classes.plugin import Plugin
from decorators import *
from plugins.time import Time
from util import *

log = logging.getLogger('pedantbot')


class Reminder:
    def __init__(self, cls: Plugin, user: discord.Member, remind_time: datetime.datetime, channel: discord.Channel,
                 invoke_time=datetime.datetime.now(), message: str = "No message", is_cancelled: bool = False,
                 task: asyncio.Task = None, *_):
        self.plugin = cls
        self.client = cls.client
        self.channel = channel
        self.server = channel.server
        self.user = user
        self.time = remind_time
        self.invoke_time = invoke_time
        self.message = message
        self.is_cancelled = is_cancelled
        self.task = task
        self.save()

    def to_json(self):
        json_object = {
            "invoke_time": int(self.invoke_time.timestamp()),
            "time": int(self.time.timestamp()),
            "channel": self.channel.id,
            "user": self.user.id,
            "message": self.message,
            "is_cancelled": False,
        }

        string = json.dumps(json_object)
        return string

    async def update_timezone(self):
        tz = await Time.get_user_timezone(self.client, self.user.id)
        if self.time.tzinfo:
            self.time = tz.normalize(self.time)
        else:
            self.time = tz.localize(self.time)

    def save(self):
        if not hasattr(self.plugin, 'reminders'):
            self.plugin.reminders = {}
        self.plugin.reminders[str(self.invoke_time.timestamp())] = self

    async def _execute(self):
        client = self.plugin.client
        log.debug('Reminder #{} scheduled'.format(self.invoke_time))

        cancel_ex = None
        wait = int(self.time.timestamp() - time.time())

        try:
            if wait > 0:
                await asyncio.sleep(wait)
            else:
                await client.send_message(
                    self.channel,
                    "The next reminder in channel {chan} is delayed by approximately {delay} minutes.\n"
                    "this is due to a bot fault.".format(
                        chan=self.channel,
                        delay=math.ceil(-wait / 60.0))
                    )

            self.is_cancelled = True
            log.debug('Reminder ready')

            await self.update_timezone()

            embed = discord.Embed(
                description=self.message,
                timestamp=self.time,
                color=discord.Color.gold()
            )
            embed.set_footer(
                text="PedantBot Reminders",
                icon_url=client.user.avatar_url or client.user.default_avatar_url
            )
            embed.set_author(
                name="{}'s reminder for {}".format(
                    self.user.display_name,
                    self.time.strftime(DATETIME_FORMAT)
                ),
                icon_url=self.user.avatar_url or self.user.default_avatar_url

            )

            await client.send_message(
                self.channel,
                self.user.mention,
                embed=embed
            )
            await self.cancel()

        except asyncio.CancelledError as e:
            cancel_ex = e
            if self.is_cancelled:
                await client.send_message(
                    self.channel,
                    "Reminder for {user} in {time} seconds cancelled".format(
                        user=self.user,
                        time=int(self.time.timestamp() - time.time())
                    )
                )
            else:
                log.debug('  Reminder ' + str(self.invoke_time) + ' removed')
        except Exception as e:
            self.is_cancelled = False
            log.exception(e)

        if cancel_ex:
            raise cancel_ex

        if self.is_cancelled:
            await self.cancel()

        self.save()

    async def execute(self):
        db = await self.plugin.get_storage(self.server)  # type: aioredis.Redis
        added = await db.set("reminder:{}".format(self.invoke_time.timestamp()), self.to_json())
        if added:
            await db.sadd("reminders", self.invoke_time.timestamp())

        self.task = asyncio.ensure_future(self._execute())  # asyncio.Task
        self.save()

    async def cancel(self):
        db = await self.plugin.get_storage(self.server)  # type: aioredis.Redis
        await db.delete("reminder:{}".format(self.invoke_time.timestamp()))
        await db.srem("reminders", self.invoke_time.timestamp())

        self.task.cancel()


class Reminders(Plugin):
    plugin_name = "reminders"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)
        self.reminders = {}

    async def on_ready(self):
        for server in self.client.servers:
            storage = await self.get_storage(server)
            reminder_list = await storage.smembers('reminders')
            for invoke_time in reminder_list:
                reminder = await self.get_reminder(server, invoke_time)
                if reminder is None:
                    continue
                await reminder.execute()

    async def get_reminder(self, server: discord.Server, invoke_time: float) -> Reminder:
        """Returns reminder with specified invoke_time"""
        reminder = self.reminders.get(str(invoke_time))  # type: Reminder
        if reminder:
            await reminder.update_timezone()
            return reminder

        storage = await self.get_storage(server)
        reminder_json = json.loads(
            await storage.get('reminder:{}'.format(invoke_time)) or '{}'
        )

        try:
            channel = self.client.get_channel(reminder_json.get('channel'))
            server = channel.server
            user = server.get_member(reminder_json.get('user'))
            message = reminder_json.get('message')
            timestamp = reminder_json.get('time')
            cancelled = reminder_json.get('is_cancelled', False)
            tz = await Time.get_user_timezone(self.client, user.id)

            tm = None
            if timestamp:
                try:
                    tm = datetime.datetime.fromtimestamp(timestamp, tz=tz)
                except:
                    tm = None

            if not tm:
                tm = datetime.datetime.now(tz=tz)

            invoke_time = datetime.datetime.fromtimestamp(float(invoke_time), tz=tz)

            reminder = Reminder(
                self,
                user=user,
                remind_time=tm,
                channel=channel,
                invoke_time=invoke_time,
                message=message,
                is_cancelled=cancelled
            )
            return reminder

        except Exception as e:
            log.exception(e)
            log.warning("Reminder #{} could not be retrieved.".format(invoke_time))

    @staticmethod
    def get_multiplier(unit: str):
        units = [
            (1, "s", "sec", "secs", "second", "seconds"),
            (60, "m", "min", "mins", "minute", "minutes"),
            (3600, "h", "hr", "hrs", "hour", "hours"),
            (86400, "d", "day", "days"),
            (604800, "w", "wk", "wks", "week", "weeks")
        ]

        for t in units:
            if unit in t[1:]:
                return t[0]

        return None

    @command(pattern="^!reminder (.+?) (.+)$",
                description="schedule a reminder",
                usage="!reminder <time> <reminder>")
    async def remindme_in(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author
        errors = []

        reminder_deltatime, _ = parse_time(args[0])
        reminder_delta = remind_deltatime.total_seconds()

        label_safe = clean_string(args[1] or "no reason")

        if reminder_delta < 1:
            await self.client.send_message(
                channel,
                "**Reminder could not be scheduled:**\n" + '\n'.join(errors)
            )

        try:
            tz = await Time.get_user_timezone(self.client, user.id)

            now = datetime.datetime.now(tz=tz)
            date = now + datetime.timedelta(seconds=reminder_delta)
            date_str = date.strftime(DATETIME_FORMAT)

            invoke_time = int(time.time())
            remind_timestamp = invoke_time + remind_delta

            reminder = Reminder(
                self,
                user=user,
                remind_time=date,
                channel=channel,
                invoke_time=now,
                message=label
            )
        except Exception as e:
            await self.client.send_message(
                channel,
                "Could not create reminder: {}".format(e)
            )
            return

        self.client.loop.create_task(reminder.execute())

        embed = discord.Embed(
            title="Reminder set",
            desc=label_safe,
            timestamp=date.timestamp(),
            color=discord.Color.gold()
        )
        embed.set_author(name=user.name, icon_url=user.avatar_url or user.default_avatar_url)

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!remindme in (.+?)(?: (?:to|for) (.+))?$",
             description="schedule a reminder",
             usage="!remindme in <# of> <secs|mins|hours|days> to <reminder>")
    async def remindme_in(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author
        errors = []

        args = (' '.join(args)).split()

        quantity = args[0]
        unit = args[1]
        if len(args) == 3:
            label = args[2] or "no reason"
        else:
            label = "no reason"

        label_safe = clean_string(label)

        try:
            quantity = float(quantity)
        except:
            quantity = 0

        if quantity < 1:
            errors.append(" • `{}` is not a number, or is less than 1.".format(quantity))

        multiplier = self.get_multiplier(unit)
        if not multiplier:
            errors.append(" • `{}` is not a valid unit.".format(unit))

        if errors:
            await self.client.send_message(
                channel,
                "**Reminder could not be scheduled:**\n" + '\n'.join(errors)
            )
            return

        delay = quantity * multiplier

        try:
            tz = await Time.get_user_timezone(self.client, user.id)

            now = datetime.datetime.now(tz=tz)
            date = now + datetime.timedelta(seconds=delay)
            date_str = date.strftime(DATETIME_FORMAT)

            reminder = Reminder(
                self,
                user=user,
                remind_time=date,
                channel=channel,
                invoke_time=now,
                message=label
            )
        except Exception as e:
            await self.client.send_message(
                channel,
                "Could not create reminder: {}".format(e)
            )
            return

        self.client.loop.create_task(reminder.execute())

        await self.client.send_message(
            channel,
            "Will remind you to \"{label}\" {remaining}\n"
            "At __{date}__.".format(
                label=truncate(label_safe, 200),
                delay=delay,
                date=date_str,
                remaining=remaining_time(now, date)
            )
        )

    @command(pattern="^!remindme (?:at|on) (.*?) to (.+)$",
             description="schedule a reminder",
             usage="!remindme <at|on> <date|time> to <reminder>")
    async def remindme_at(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author

        label = args[1]
        label_safe = re.findall(r'^!remindme (?:at|on) (.*) ? to (.+)$', message.clean_content)[0][1]
        label_safe = clean_string(label_safe)

        try:
            parsed = parser.parse(args[0])
        except ValueError as e:
            await self.client.send_message(
                channel,
                "Could not set reminder: `{}`".format(clean_string(e))
            )
            return

        if parsed < datetime.datetime.now() + datetime.timedelta(seconds=10):
            res = await confirm_dialog(
                self.client,
                channel,
                user,
                "Reminder too early",
                description="The date/time provided is too early, would you like to schedule for tomorrow (`n`), "
                            "or a custom date (`c`)?\n```\n{}```".format(parsed.strftime(DATETIME_FORMAT)),
                options=('y', 'c', 'n')
            )

            if res is None or res.content.lower() == "n":
                return
            elif res.content.lower() == "c":
                def check(m: discord.Message):
                    try:
                        if not re.match("\d{4}-\d{2}-\d{2}", m.content):
                            return False
                        if parser.parse(m.content):
                            return True
                    except Exception:
                        return False

                prompt = await self.client.send_message(
                    channel,
                    "Please enter the date for your reminder in the following format: `yyyy-mm-dd`"
                )
                msg = await self.client.wait_for_message(
                    timeout=60,
                    author=user,
                    channel=channel,
                    check=check
                )
                await self.client.delete_messages([prompt, msg] if msg else prompt)
                new = parser.parse(msg.content)
                parsed = parsed.replace(new.year, new.month, new.day)
            else:
                parsed = parsed + datetime.timedelta(days=1)  # type: datetime.datetime

        tz = await Time.get_user_timezone(self.client, user.id)

        if parsed.tzinfo:
            date = tz.normalize(parsed.astimezone(pytz.utc))
        else:
            date = tz.localize(parsed)

        now = datetime.datetime.now(tz=tz)
        date_str = date.strftime(DATETIME_FORMAT)

        reminder = Reminder(
            self,
            user=user,
            remind_time=date,
            channel=channel,
            invoke_time=now,
            message=label
        )
        self.client.loop.create_task(reminder.execute())

        await self.client.send_message(
            channel,
            "Will remind you to \"{label}\" {remaining}\n"
            "At __{date}__.".format(
                label=truncate(label_safe, 200),
                date=date_str,
                remaining=remaining_time(now, date)
            )
        )

    @command(pattern="^!reminders ?(.*)$",
             description="list all your reminders, or all reminders in server",
             usage="!reminders <user|all>")
    async def list_reminders(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        if args[0] == "all":
            target = server
        else:
            target = await get_object(
                self.client,
                args[1],
                message,
                types=(discord.Member,)
            ) if args[0] else user

        if not target:
            await self.client.send_message(
                channel,
                "No user found by that name."
            )

        storage = await self.get_storage(server)
        reminders = await storage.smembers('reminders')

        body = ""

        tz = await Time.get_user_timezone(self.client, user.id)
        now = datetime.datetime.now(tz=tz)

        for invoke_time in reminders:
            reminder = await self.get_reminder(server, invoke_time)
            if not (target == reminder.user or target == server):
                continue

            body += " • `{id}` - {user} \"{message}\", {remaining}, at `{date}`\n".format(
                id=reminder.invoke_time.timestamp(),
                user=reminder.user,
                reminder=reminder,
                message=truncate(reminder.message, 200),
                remaining=remaining_time(now, reminder.time),
                date=reminder.time.strftime(DATETIME_FORMAT)
            )

        embed = discord.Embed(
            title="**Reminders for {}**\n".format(target),
            description=body or "No reminders found.".format(target),
            color=discord.Color.gold(),
        )
        embed.set_footer(
            icon_url=message.server.icon_url,
            text='{:.16} | PedantBot Reminders'.format(server.name)
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    # TODO: add edit command

    @command(pattern="^!cancelreminder (.*)$",
             description="cancel a reminder by ID",
             usage="!cancelreminder <id>")
    async def cancel_reminder(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        try:
            invoke_time = float(args[0])
        except:
            invoke_time = None

        if not invoke_time:
            await self.client.send_message(
                channel,
                "{user.mention}, invalid reminder ID was specified.\n"
                "No action was taken.".format(user=user)
            )
            return

        reminder = await self.get_reminder(server, args[0])
        if not reminder:
            await self.client.send_message(
                channel,
                "{user.mention} No reminder could be found for that ID.".format(user=user)
            )
            return

        if not (user == reminder.user or has_permission(user, 'manage_messages')):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to cancel other users' reminders.\n"
                "Requires `manage_messages`.".format(user=user)
            )
            return

        res = await confirm_dialog(
            self.client,
            channel=channel,
            user=user,
            title="Delete this reminder?",
            description="At {date} for {user}\n```{message}```".format(
                date=reminder.time.strftime(DATETIME_FORMAT),
                user=reminder.user,
                message=reminder.message
            ),
            colour=discord.Colour.red()
        )

        if not res:
            return
        if res.content == 'y':
            await reminder.cancel()
            await self.client.send_message(
                channel,
                "Reminder `{}` cancelled.".format(reminder.invoke_time.timestamp())
            )
        else:
            await self.client.send_message(
                channel,
                "Dialog cancelled, not action taken."
            )
