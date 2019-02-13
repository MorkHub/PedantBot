import logging

import aioredis
import pytz

from classes.plugin import Plugin
from decorators import *
from util import *

log = logging.getLogger('pedantbot')


class Time(Plugin):
    plugin_name = "user timezone storage"
    required = True
    owner_manage = True

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)
        self.default_timezone = pytz.timezone("Europe/London")

    @staticmethod
    async def get_user_timezone(client: discord.Client, user_id: str, fallback=True):
        db = client.db.redis  # type: aioredis.Redis
        timezone = await db.get('Time.global:{}'.format(user_id))

        if not (timezone or timezone in pytz.all_timezones):
            if fallback:
                return pytz.utc
            return None
        else:
            return pytz.timezone(timezone)

    async def set_user_timezone(self, user_id: str, tz: datetime.timezone):
        db = self.client.db.redis  # type: aioredis.Redis
        tz_name = str(tz)

        if tz_name in pytz.all_timezones:
            saved = await db.set('Time.global:{}'.format(user_id), tz_name)
            return saved
        else:
            return False

    // TODO: implement get_server_timezone

    @staticmethod
    async def get_server_timezone(server):
        #region = server.region  # type: discord.ServerRegion
        return pytz.UTC



    @staticmethod
    def check_timezone(timezone):
        timezone = search(timezone, pytz.all_timezones)

        if not timezone:
            return False

        tz = pytz.timezone(timezone)
        return tz

    @command(pattern="^!time(?: (.*))?$",
             description="show the local time for yourself or another user.",
             usage="!time [user]")
    async def show_local_time(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,)
        ) if args[0] else user

        if not target:
            await self.client.send_message(
                channel,
                "No user found by that name."
            )
            return

        tz = await self.get_user_timezone(self.client, target.id, False)
        if not tz:
            await self.client.send_message(
                channel,
                "No timezone could be found for {user}.\n"
                "You can set your timezone with `!timezone`\n"
                "E.g. `!timezone US/Central`".format(
                    user=target
                )
            )
            return

        dt = datetime.datetime.now(tz=tz)
        formatted = dt.strftime(DATETIME_FORMAT)

        await self.client.send_message(
            channel,
            "{user}'s local time is: `{time}`".format(
                user=target,
                time=formatted
            )
        )

    @command(pattern="^!timezone(?: ?(.*)?)$",
             description="set or view your timezone",
             usage="!timezone [timezone]")
    async def set_timezone(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author
        tz = await self.get_user_timezone(self.client, user.id, False)

        if not args[0].strip():
            if not tz:
                await self.client.send_message(
                    channel,
                    "No timezone could be found for you. UTC will be assumed.\n"
                    "You can set your timezone with `!timezone`\n"
                    "E.g. `!timezone US/Central`"
                )
                return

            await self.client.send_message(
                channel,
                "{user.mention}, your timezone is currently set to: `{tz}`".format(
                    user=user,
                    tz=tz
                )
            )
            return

        new_tz = self.check_timezone(args[0])
        if not new_tz:
            await self.client.send_message(
                channel,
                "`{tz}` was not recognised. Please enter a valid timezone.\n"
                "A list of all timezones can be found at the link below:\n"
                "**Timezones are case sentitive**\n"
                "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>".format(
                    tz=args[0]
                )
            )
            return

        if tz:
            desc = "This will change your timezone:\n```\n{old} -> {new}\n```"
        else:
            desc = "This will set your timezone:\n```\n{new}\n```"

        res = await confirm_dialog(
            self.client,
            channel,
            user,
            title="Update your timezone?",
            description=desc.format(
                old=tz,
                new=new_tz
            ),
            colour=discord.Color.orange()
        )

        if not res:
            return

        if res.content.lower() != 'y':
            await self.client.send_message(
                channel,
                "Action cancelled. Timezone not updated."
            )
            return

        added = await self.set_user_timezone(user.id, new_tz)
        if added:
            await self.client.send_message(
                channel,
                "Your timezone was set to: `{}`".format(new_tz)
            )
        else:
            await self.client.send_message(
                channel,
                "Your timezone could not be updated."
            )
