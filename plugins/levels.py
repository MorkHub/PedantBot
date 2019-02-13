import logging
from random import randint
import datetime

from classes.plugin import Plugin
from decorators import command
from util import *
import math

log = logging.getLogger('pedantbot')


class Levels(Plugin):
    plugin_name = "levels"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @staticmethod
    def xp_from_level(level):
        xp = 0
        for _level in range(1, level):
            xp += math.floor(_level + 300 * pow(2, _level / 7))
        
        return math.floor(xp / 4)

    @staticmethod
    def level_from_xp(xp):
        level = 1
        while Levels.xp_from_level(level + 1) < xp:
            level += 1
        return level

    async def on_message(self, message: discord.Message):
        server = message.server
        channel = message.channel
        user = message.author
        storage = await self.get_storage(server)

        if user.bot:
            return

        if await storage.get('player:{}:limited'.format(user.id)):
            return

        double_xp = bool(await storage.get('double_xp:global') or await storage.get('double_xp:{}'.format(channel.id)) or 0)

        added_xp = (len(message.content) / (len(message.content) + 5)) * 30 * (2 if double_xp else 1)
        xp = await storage.incrby('player:{}:xp'.format(user.id), int(added_xp)) or 0

        before = self.level_from_xp(int(xp - added_xp))
        after = self.level_from_xp(int(xp))

        await storage.sadd('players', user.id)
        await storage.set('player:{}:limited'.format(user.id), '1', expire=20)

        if after > before:
            announce = await storage.get('announce_enabled')
            if announce == '0':
                return

            await self.client.send_message(
                channel,
                "{user.mention} advanced a level! They are now **Level {level:,}**.".format(
                    user=user,
                    level=after
                )
            )

    @command(pattern="^!doublexp ([0-9]+)(?: (server))?$",
             description="enable bonus xp in this channel for n days",
             usage="!doublexp 2")
    async def doublexp(self, message, args):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, 'manage_server'):
            await client.send_message("no")
            return

        try:
            days = int(args[0])
        except:
            days = 1

        end = datetime.datetime.now() + datetime.timedelta(days=days)

        storage = await self.get_storage(server)
        if len(args) == 2 and args[1]:
            await storage.set('double_xp:{}'.format(channel.id), days * 24 * 3600)
        else:
            await storage.set('double_xp:global'.format(channel.id), days * 24 * 3600)

        try:
            await self.client.delete_message(message)
        except:
            pass
        await self.client.send_message(channel, "DOUBLE XP UNTIL {} !!".format(end.strftime(DATETIME_FORMAT)))

    @command(pattern="^!doublexp$",
             description="disable bonus xp",
             usage="!doublexp")
    async def disable_doublexp(self, message, args):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        if any([
                await storage.delete('double_xp:global'),
                await storage.delete('double_xp:{}'.format(channel.id))]):
            await self.client.send_message(channel, "DOUBLE XP ENDED.")

    @command(pattern="^!level shutup$",
             description="stop level announcements",
             usage="!level shutup")
    async def shutup(self, message: discord.Message, args: tuple=()):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, 'manage_server'):
            await client.send_message("no")
            return

        storage = await self.get_storage(server)
        await storage.set('announce_enabled', 0)

        await self.client.send_message("Level up announcements disabled for {}".format())

    @command(pattern="^!xp ?(.*)?$",
             description="get xp for user",
             usage="!xp [user]")
    async def user_xp(self, message: discord.Message, args: tuple=()):
        server = message.server
        channel = message.channel
        user = message.author

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
            return

        if target.bot:
            await self.client.send_message(
                channel,
                "Bots cannot earn experience."
            )
            return

        storage = await self.get_storage(server)
        xp = await storage.get('player:{}:xp'.format(target.id)) or 0
        level = self.level_from_xp(int(xp))
        next_level = self.xp_from_level(level + 1)

        await self.client.send_message(channel, "{user} is currently **level {level}** ({xp:,}/{next:,}) xp".format(
            user=target,
            xp=int(xp),
            level=level,
            next=next_level
        ))

    @command(pattern="^!skillcape",
             description="get a skillcape when you're level 99")
    async def get_skillcape(self, message: discord.Message, *_):
        server = message.server  # type: discord.Server
        channel = message.channel
        user = message.author
        storage = await self.get_storage(server)

        xp = int(await storage.get('player:{}:xp'.format(user.id)) or 0)
        lvl = self.level_from_xp(xp)
        if lvl >= 120:
            await self.client.send_message(channel, 'https://i.themork.co.uk/88220533c456.png')
        elif lvl >= 99:
            await self.client.send_message(channel, 'https://i.themork.co.uk/6cfc0a403220.png')

    @command(pattern="^!levels(?: all)?$",
             description="view leaderboards for this server",
             usage="!levels",
             global_cooldown=5)
    async def view_leaderboard(self, message: discord.Message, *_):
        server = message.server  # type: discord.Server
        channel = message.channel
        storage = await self.get_storage(server)

        users = []
        players = await storage.smembers('players')
        for user in players:
            user = server.get_member(user)
            if not user:
                continue

            xp = int(await storage.get('player:{}:xp'.format(user.id)) or 0)
            users.append((user, xp))

        pad = -sorted([-len(x[0].name) for x in users])[0]

        body = "```"
        biggest = None
        for n, (user, xp) in enumerate(sorted(users, key=lambda u: -u[1])[:10]):
            level = self.level_from_xp(int(xp))
            if not biggest:
                biggest = level

            body += "#{i:<2} {user:<{pad}} : {level:<{pad2},} ({xp:,}xp)\n".format(
                i=n+1,
                user=clean_string(user.name, remove="`"),
                xp=xp,
                level=level,
                pad=pad,
                pad2=len(str(biggest))
            )
        body += "```"

        embed = discord.Embed(
            title="Leaderboards for {}".format(server),
            description=body,
            colour=discord.Colour.gold()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

        # TODO: add rewards for levels
