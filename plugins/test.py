# from util import *
import logging

from classes.server import Server
from classes.channel import Channel
from classes.user import User
from classes.embed import Embed
from classes.message import Message
from classes.plugin import Plugin
from decorators import *

log = logging.getLogger('pedantbot')


class Test(Plugin):
    plugin_name = "Test plugin"
    default = False

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @command(pattern='^!test(?: (.*))?$',
             description="get test data",
             usage='!test <something> <something>')
    async def list_args(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author

        await self.client.send_message(
            channel,
            "**{user}** message data: ```py\nraw = '{message}'\n" \
            "args = {args}\n" \
            "mentions = {mentions}\n" \
            "channel_mentions = {c_mentions}\n" \
            "msg = {dict}```".format(
                user=user,
                message=message.content,
                channel=channel,
                mentions=tuple(User(member) for member in message.mentions),
                c_mentions=tuple(Channel(chan) for chan in message.channel_mentions),
                args=args,
                dict=Message(message).to_dict(True)
            )
        )

    @command(pattern="^!pm ([0-9]+) (.*)$",
             description="bot will send you a private message and then delete it",
             usage="!pm <# of seconds> <message>")
    async def private_message(self, message: discord.Message, args: tuple):
        user = message.author
        channel = await self.client.start_private_message(user)
        text = args[1] or "blank message"
        delay = float(args[0] or 5)

        msg = await self.client.send_message(
            channel,
            text
        )

        await asyncio.sleep(delay)
        await self.client.delete_message(msg)

    @command(pattern='^!server$',
             description="get test data about the server",
             usage='!server')
    async def dump_server(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel

        dump = Server(server).to_json(True)
        await self.client.send_message(
            channel,
            "```json\n{:.1000}```".format(dump)
        )

    @command(pattern='^!channel ?(.*)?$',
             description="get test data about channel",
             usage='!channel [channel name]')
    async def dump_channel(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel

        name = args[0] if args[0] else channel.name
        chan = discord.utils.find(lambda c: c.name == name, server.channels)
        if not chan:
            return

        dump = Channel(chan).to_json()
        await self.client.send_message(
            channel,
            "```json\n{}```".format(dump)
        )

    @command(pattern='^!user  ?(.*)?$',
             description="get test data about user",
             usage='!user [name]')
    async def dump_member(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        name = args[0] if args[0] else user.name
        user = discord.utils.find(lambda u: u.name == name, server.members)
        if not user:
            return

        dump = User(user).to_json()
        await self.client.send_message(
            channel,
            "```json\n{}```".format(dump)
        )

    @command(pattern='^!role$',
             description="get test data about user's top role",
             usage='!role')
    async def dump_role(self, message: discord.Message, *_):
        channel = message.channel
        user = message.author

        dump = Role(user.top_role).to_json()
        await self.client.send_message(
            channel,
            "```json\n{}```".format(dump)
        )

    @command(pattern="^!embed (.*)",
             description="send an OEmbed JSON object",
             usage='!embed <JSON>')
    async def send_oembed(self, message: discord.Message, args: tuple):
        channel = message.channel
        user = message.author

        try:
            embed = Embed(args[0])
        except ValueError as e:
            await self.client.send_message(
                channel,
                e.args[0]
            )
            return

        await self.client.send_message(
            channel,
            "{user} here ur embed m8".format(user=user),
            embed=embed
        )

    @command(pattern="!emojitest",
             description="print test emoji",
             usage="!emojitest")
    async def list_test_emojis(self, message: discord.Message, *_):
        channel = message.channel
        types = "😀 😂 😍 🤑 😎 😡 👺 💀 👽 🤖 😹 🎅 🕵 🐶 🐱 🐻 🐼 🐷 🐮 🐸 🐔 🐧 🐝 🐟 🐬 🍄 🎃 🌎 🌞 ⚡ 🔥 ❄ 🌨  🍎 🍊 🍋 🍌 🍉 🍓 🍒 🍅 🌶 🍆 🍔 🧀 🍟 🍕 🍿 🍩 ⚽ 🏀 🏈 ⚾ 🏉 🎱 🏓 🏆 🏅 🎗 🚗 🚕 🚌 🏎 🚓 🚁 ✈ 💻 📱 🖥 🖨 🖱 📷 📽 💎 💳 💰";

        await self.client.send_message(
            channel,
            "```py\n['" + "','".join(types.split()) + "']```"
        )

    @nsfw
    @command(pattern="!lewd",
             description="it's lewd",
             usage="!lewd")
    async def lewd(self, message: discord.Message, *_):
        await self.client.send_message(
            message.channel,
            "L E W D"
        )