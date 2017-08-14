import logging
from random import randint

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
        points = 0
        for i in range(1, level + 1):
            diff = int(i * 5 ** (1.2*math.e))
            points += diff
        return points

    @staticmethod
    def level_from_xp(xp):
        level = 0
        while Levels.xp_from_level(level) < xp:
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

        xp = await storage.get('player:{}:xp'.format(user.id)) or 0
        before = self.level_from_xp(int(xp))
        xp = await storage.incrby('player:{}:xp'.format(user.id), randint(15, 25)) or 0
        after = self.level_from_xp(int(xp))

        await storage.sadd('players', user.id)
        await storage.set('player:{}:limited'.format(user.id), '1', expire=20)

        if after > before:
            announce = bool(await storage.get('announce_enabled') or '1')
            if not announce:
                return

            await self.client.send_message(
                channel,
                "{user.mention} advanced a level! They are now **Level {level:,}**.".format(
                    user=user,
                    level=after
                )
            )

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
        next_level = self.xp_from_level(level)

        await self.client.send_message(channel, "{user} is currently **level {level}** ({xp:,}/{next:,}) xp".format(
            user=target,
            xp=int(xp),
            level=level,
            next=next_level
        ))

    @command(pattern="^!levels$",
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