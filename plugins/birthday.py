import logging
import discord
import asyncio
import re
import json

from classes.plugin import Plugin

from decorators import command, bg_task, Task
from util import has_permission, DATE_FORMAT, clean_string
from datetime import date, datetime, timedelta
from dateutil.rrule import rrule, YEARLY

from typing import Dict, List, Tuple

log = logging.getLogger('pedantbot')


class Birthdays(Plugin):
    plugin_name = "birthdays"
    required = True
    owner_manage = True

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)
        self.failed_servers = []

    async def get_birthday(self, user: discord.User):
        storage = self.db.redis
        
        if isinstance(user, discord.User):
            user_id = user.id
        else:
            user_id = str(user)

        ts = await storage.get("Birthdays:global:birthday.{}".format(user_id))
        dt = None 

        if ts:
            try:
                dt = date.fromtimestamp(float(ts))
            except:
                pass

        return dt

    async def get_birthdays(self, server, on = None, after = None, before = None) \
            -> Dict[datetime, List[discord.Member]]:
        storage = self.db.redis
        known_users = await storage.keys("Birthdays:global:birthday.*")
        permissions = json.loads(await storage.get("Birthdays.{}:permissions".format(server.id)) or "{}")
        print(permissions)
        today = date.today()

        if on is not None:
            cast = type(on)
        elif before is not None:
            cast = type(before)
        elif after is not None:
            cast = type(after)
        else:
            cast = datetime

        birthdays = {}
        for key in known_users:
            match = re.match(r"^Birthdays:global:birthday\.(.*)$", key)
            if match:
                user_id = match.group(1)
            else:
                continue

            if server is None:
                member = await self.client.get_user_info(user_id)
            else:
                member = server.get_member(user_id)

            if member is not None:
                if not permissions.get(member.id, True):
                    continue

                dt = cast.fromtimestamp(float(await storage.get(key)))
                ty = cast(today.year, dt.month, dt.day)

                if dt is None:
                    continue

                if on is not None and not ty == on:
                    continue
                if after is not None and ty < after:
                    continue
                if before is not None and ty > before:
                    continue

                if dt not in birthdays:
                    birthdays[dt] = []
                    
                birthdays[dt].append(member)

        return birthdays

    @staticmethod
    def ordinal(n):
        return "{:.0f}{}".format(n,"tsnrhtdd"[(n/10%10!=1)*(n%10<4)*n%10::4])

    @command(pattern="^!(bdd|birthdaydisable)",
             description="disable birthday announcements",
             usage="!birthdaydisable")
    async def disable_brithdays(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        storage = self.db.redis

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{}, you do not have permission to enable/disable birthday announcements.\n"
                "Requires `manage_server`.".format(user.mention)
            )
            return

        await storage.srem("Birthdays:global:daily_announce_enabled", server.id)
        await storage.srem("Birthdays:global:weekly_announce_enabled", server.id)

        await self.client.send_message(channel, "Birthdays will no longer be announced in this server.")

    @command(pattern="^!(bde|birthdayenable)(?: <#[0-9]*?>)?",
             description="enable birthday announcements",
             usage="!birthdayenable #birthdays")
    async def enable_birthdays(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        storage = self.db.redis

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{}, you do not have permission to enable/disable birthday announcements.\n"
                "Requires `manage_server`.".format(user.mention)
            )
            return

        await storage.sadd("Birthdays:global:daily_announce_enabled", server.id)
        await storage.sadd("Birthdays:global:weekly_announce_enabled", server.id)

        if len(message.channel_mentions) < 1:
            message.channel_mentions = [channel]

        for chan in message.channel_mentions:
            try:
                await self.client.send_message(chan, "Birthday announcements will be sent in this channel.")
                await storage.set("Birthdays:{}:announce_channel".format(server.id), chan.id)
                await self.client.add_reaction(message, '👍')
                return
            except discord.errors.Forbidden:
                await self.client.send_message(channel, "{}, I cannot send messages in that channel".format(user.mention))
            except:
                pass
            

    @command(pattern="^!birthdays(?: (all))?$",
             description="list birthdays in this server",
             usage="!birthdays")
    async def list_birthdays(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        storage = self.db.redis
        known_users = await storage.keys("Birthdays:global:birthday.*")

        if user.id == "154542529591771136" and args[0] == "all":
            birthdays = await self.get_birthdays(None)
        else:
            birthdays = await self.get_birthdays(server)

        embed = discord.Embed(
            title="Birthdays in {}".format(server.name),
            colour=discord.Colour.gold()
        )

        now = datetime.now()
        today = now.date()

        from dateutil.rrule import rrule, YEARLY

        def d(dt):
            rule = rrule(YEARLY, dtstart=dt)
            return rule.after(now)

        for dt in sorted(birthdays.keys(), key=d):
            born = dt
            members = birthdays.get(dt, [])
            dt = d(dt).date()

            age = dt.year - born.year

            delta = dt - today
            days = delta.days

            if days < -7:
                dt = date(today.year + 1, dt.month, dt.day)
                delta = dt - today
                days = delta.days
                age = dt.year - born.year

            if dt == today:
                until = "today"
            elif days < 0:
                if days == -1:
                    until = "yesterday"
                else:
                    until = "{} days ago".format(abs(days))
            else:
                if days == 1:
                    until = "tomorrow"
                else:
                    if days > 40:
                        fmt = "{} months, {} days".format(days//31, days)
                    until = "in {} days".format(days)

            embed.add_field(
                name="{} ({})".format(dt.strftime(DATE_FORMAT), until),
                value='\n'.join("{}'s {}".format(member.mention, self.ordinal(age)) for member in members),
                inline=False
            )

        await self.client.send_message(channel, embed=embed)


    @command(pattern="^!birthday$",
             description="show your birthday",
             usage="!birthday")
    async def show_birthday(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        dt = await self.get_birthday(user)

        if dt is None:
            await self.client.send_message(channel, "{}, you have not set your birthday!\nDo so with the `!setbirthday DD/MM/YYYY` command.".format(user.mention))
            return
        else:
            if date.today() == dt:
                await self.client.send_message(channel, "{}, today is your birthday!".format(user.mention))
            else:
                await self.client.send_message(channel, "{}, your birthday is listed as `{}`.\nYou can change it with `!setbirthday DD/MM/YYYY`".format(user.mention, dt.strftime(DATE_FORMAT)))

    @command(pattern="^!(?:cb|clearbirthday)(?: (.*))?$",
             description="reset birthday",
             usage="!clearbirthday")
    async def clear_birthday(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member
 
        storage = self.db.redis

        member = None
        if args[0]:
            member = server.get_member_named(args[0]) or await self.client.get_user_info(args[0])
            if member is None:
                await self.client.send_message(channel, "Could not find user")
        else:
            member = user

        if not user in [member, (await self.client.application_info()).owner]:
            await self.client.send_message(
                channel,
                "{}, you do not have permission to clear other users' birthdays.\n"
                "Requires `bot_owner`.".format(user.mention)
            )
            return

        await storage.delete("Birthdays:global:birthday.{}".format(member.id))
        await self.client.send_message(channel, "{}, `{}`'s birthday was reset.".format(user.mention, str(member)))

    @command(pattern="^!(?:sb|setbirthday) ([^ ]*)$",
             description="set your birthday",
             usage="!setbirthday DD/MM/YYYY")
    async def set_birthday(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        storage = self.db.redis
        dt = None

        parts = re.match(r"([0-9]{1,2})\/([0-9]{1,2})\/([0-9]{4})", args[0])
        try:
            day = int(parts.group(1))
            month = int(parts.group(2))
            year = int(parts.group(3))

            dt = datetime(year, month, day)
        except:
            await self.client.send_message(channel, "{}, Invalid date format, please use a valid date the form `DD/MM/YYYY`)".format(user.mention))
            return

        timestamp = dt.timestamp()
        await storage.set("Birthdays:global:birthday.{}".format(user.id), timestamp)
        await self.client.send_message(channel, "{}, your birthday was set to `{}`".format(user.mention, dt.strftime(DATE_FORMAT)))

    @command(pattern="^!(?:sb|setbirthday) ([^ ]*) (.*)$",
             description="set someone else's birthday",
             usage="!setbirthday DD/MM/YYYY <name or id>")
    async def set_other_birthday(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member
  
        storage = self.db.redis

        if not user == (await self.client.application_info()).owner:
            await self.client.send_message(
                channel,
                "{}, you do not have permission to change other users' birthdays.\n"
                "Requires `bot_owner`.".format(user.mention)
            )

            return

        member = server.get_member_named(args[1]) or await self.client.get_user_info(args[1])

        parts = re.match(r"([0-9]{1,2})[\/-]([0-9]{1,2})[\/-]([0-9]{4})", args[0])
        if parts:
            try:
                day = int(parts.group(1))
                month = int(parts.group(2))
                year = int(parts.group(3))

                dt = datetime(year, month, day)
            except:
                await self.client.send_message(channel, "{}, Invalid date format, please use a valid date the form `DD/MM/YYYY`)")
                return

            timestamp = dt.timestamp()
            await storage.set("Birthdays:global:birthday.{}".format(member.id), timestamp)
            await self.client.send_message(channel, "Set `{}`'s birthday as `{}`".format(str(member), dt.strftime(DATE_FORMAT)))

    @command(pattern="^!(?:b|birthday) opt (in|out)$",
             description="set someone else's birthday",
             usage="!birthday opt [in|out]")
    async def birthday_opt_in(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        storage = await self.get_storage(server)

        announcement_permission = args[0] == "in"
        message = "will" if announcement_permission else "will not"

        permissions = json.loads(await storage.get("permissions") or "{}")
        permissions[user.id] = announcement_permission

        await storage.set("permissions", json.dumps(permissions))
        await self.client.send_message(
            channel,
            "{}, your birthday {} be announced in this server from now on.".format(
                user.mention, message
            ))

    @command(pattern="^!age real$",
             description="view the ages of users in this server",
             usage="!age real")
    async def user_ages(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        today = datetime.today()
        birthdays = await self.get_birthdays(server)
        members = []
        for dt, _members in birthdays.items():
            if dt > today:
                continue
            for member in _members:
                members.append((member, dt))

        def age(dt):
            return today.year - dt.year

        string = ''
        members = sorted(members, key=lambda x: -age(x[1]))
        for n, birthday in enumerate(members[:20]):
            member, dt = birthday
            member.name = clean_string(member.name)
            string += '{n:>2}.  {user}: {age} on `{date}`\n'.format(
                n=n + 1,
                user=member.mention,
                age=age(dt),
                date=dt.strftime(DATE_FORMAT)
            )

        embed = discord.Embed(
            title="Age of users in {server.name}".format(server=message.server),
            color=discord.Colour.blue(),
            description=string
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    # background tasks

    @bg_task(Task.HOURLY)
    async def weekly_announcement(self):
        storage = self.db.redis
        now = datetime.now()
        today = now.date()

        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)

        if now.hour < 7:
            wait = (datetime(now.year, now.month, now.day, 7) - now).total_seconds()
            if wait <= 3600:
                log.info("Weekly: Waiting for 7am ({:,.0f}s)".format(wait))
                await asyncio.sleep(wait)
            else:
                return

        last_check_ts = 0
        try:
            last_check_ts = float(await storage.get("Birthdays:global:last_check_weekly"))
            pass
        except:
            pass

        last_check = date.fromtimestamp(last_check_ts or 0)

        if last_check < today:
            log.info("Checking weekly birthdays (w/c {})".format(monday.strftime(DATE_FORMAT)))
            servers = await storage.smembers("Birthdays:global:weekly_announce_enabled") or []
            if len(servers) == 0:
                log.info("Weekly announcement disabled in all servers")

            for server_id in servers:
                server = self.client.get_server(server_id)
                if not server:
                    continue

                announce_channel = await storage.get("Birthdays:{}:announce_channel".format(server_id))
                try:
                    channel = server.get_channel(announce_channel)
                    if channel:
                        body = ""
                        birthdays = await self.get_birthdays(server, after=monday, before=sunday)

                        if not birthdays:
                            continue

                        for dt, members in birthdays.items():
                            age = today.year - dt.year
                            bd = date(today.year, dt.month, dt.day)

                            body += "{} will be **{:.0f}** on **{}**\n".format(
                                ', '.join(m.mention for m in members),
                                age,
                                bd.strftime("%A")
                            )

                        embed = discord.Embed(title="Upcoming birthdays this week", description=body, colour=discord.Colour.gold())
                        await self.client.send_message(channel, embed=embed)
                except Exception as e:
                    log.warning("Weekly birthday announcement failed in server {}".format(server_id))
                    log.exception(e)

            await storage.set("Birthdays:global:last_check_weekly", datetime(*sunday.timetuple()[:6]).timestamp())
        else:
            log.info("Already checked weekly birthdays (w/c {})".format(monday.strftime(DATE_FORMAT)))


    @bg_task(3600)
    async def daily_announcement(self):
        storage = self.db.redis
        now = datetime.now()
        today = now.date()
 
        if now.hour < 7:
            wait = (datetime(now.year, now.month, now.day, 7) - now).total_seconds()
            if wait <= 3600:
                log.info("Daily: Waiting for 7am ({:,.0f}s)".format(wait))
                await asyncio.sleep(wait)
            else:
                return

        last_check_ts = 0
        try:
            last_check_ts = float(await storage.get("Birthdays:global:last_check_daily"))
            pass
        except:
            pass

        last_check = date.fromtimestamp(last_check_ts or 0)
 
        if last_check < today or self.failed_servers:
            log.info("Checking daily birthdays ({})".format(today.strftime(DATE_FORMAT)))
            servers = []
            if last_check < today:
                servers.extend(await storage.smembers("Birthdays:global:daily_announce_enabled") or [])
            if self.failed_servers:
                servers.extend(self.failed_servers)

            log.info("Will announce birthdays in {} servers.".format(len(servers)))

            self.failed_servers = []

            if len(servers) == 0:
                log.info("Daily announcement disabled in all servers")
 
            for server_id in servers:
                server = self.client.get_server(server_id)
                if not server:
                    log.warn("Server {} not found".format(server_id))
                    continue
 
                announce_channel = await storage.get("Birthdays:{}:announce_channel".format(server_id))
                if announce_channel is None:
                   continue

                try:
                    channel = server.get_channel(announce_channel)
                    if channel:
                        body = "Happy Birthday today!\n"
                        birthdays = await self.get_birthdays(server, on=today)

                        if not birthdays:
                            continue 

                        for dt, members in birthdays.items():
                            age = today.year - dt.year
 
                            body += "{} will be **{:.0f}** today!\n".format(
                                ', '.join(m.mention for m in members),
                                age
                            )
 
                        try:
                            await self.client.send_message(channel, body)
                        except Exception as e:
                            log.exception(e)
                            self.failed_servers.add(server_id)
                except Exception as e:
                    log.warning("Could not announce birthdays in server {}".format(server_id))
                    log.exception(e)

            await storage.set("Birthdays:global:last_check_daily", now.timestamp())
        else:
            log.info("Already checked daily birthdays ({})".format(last_check.strftime(DATE_FORMAT)))

