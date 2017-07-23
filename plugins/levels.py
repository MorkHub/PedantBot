import logging
from random import randint

from classes.plugin import Plugin
from decorators import command
from util import *

log = logging.getLogger('pedantbot')


class Levels(Plugin):
    plugin_name = "levels"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    async def on_message(self, message: discord.Message):
        server = message.server
        user = message.author
        storage = await self.get_storage(server)

        if user.bot:
            return

        if await storage.get('player:{}:limited'.format(user.id)):
            return

        await storage.incrby('player:{}:xp'.format(user.id), randint(15, 25))
        await storage.sadd('players', user.id)
        await storage.set('player:{}:limited'.format(user.id), '1', expire=20)

    @command(pattern="^!xp ?(.*)?$",
             description="get xp for user",
             usage="!xp [user]")
    async def user_xp(self, message: discord.Message, args: tuple=()):
        server = message.server
        channel = message.channel
        user = message.author

        if message.mentions:
            target = message.mentions[0]
        elif args[0]:
            target = server.get_member_named(args[0])
        else:
            target = user

        if not target:
            await self.client.send_message(
                channel,
                "No user found by that name."
            )
            return

        if user.bot:
            await self.client.send_message(
                channel,
                "Bots cannot earn experience."
            )
            return

        storage = await self.get_storage(server)
        xp = await storage.get('player:{}:xp'.format(target.id)) or 0

        await self.client.send_message(channel, "{user} currently has {xp:,} xp".format(
            user=target,
            xp=int(xp)
        ))

    @command(pattern="!levels",
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

        body = ""
        for n, (user, xp) in enumerate(sorted(users, key=lambda u: -u[1])[:10]):
            body += "#{i} - **{user}**: `{xp:,}` xp\n".format(
                i=n+1,
                user=clean_string(user.display_name, remove="`"),
                xp=xp
            )

        embed = discord.Embed(
            title="Leaderboards for {}".format(server),
            description=body,
            colour=discord.Colour.gold()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    # TODO: map xp to levels, exponential function

    # TODO: add rewards for levels