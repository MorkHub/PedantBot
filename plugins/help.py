import logging

from classes.plugin import Plugin

from decorators import *

log = logging.getLogger('pedantbot')


class Help(Plugin):
    plugin_name = "help"
    required = True
    owner_manage = True

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @command(pattern="^[!?]help$",
             description="get help",
             usage="?help")
    async def list_plugins(self, message: discord.Message, args: tuple):
        server = message.guild  # type: discord.Guild
        channel = message.channel  # type: discord.TextChannel
        user = message.author  # type: discord.Member

        body = "Use `!help <topic>` to find specific help.\n\n"
        for plugin in sorted(await self.client.plugin_manager.get_all(server), key=lambda p: p.__class__.__name__):
            body += "**{plugin.__class__.__name__}**: {plugin.plugin_name}\n".format(plugin=plugin)

        embed = discord.Embed(
            title="Plugins available in {}".format(server),
            description=body,
            colour=discord.Color.green()
        )

        await channel.send(embed=embed)

    @command(pattern="^[!?]help (.+)$",
             description="get help",
             usage="?help <plugin>")
    async def plugin_help(self, message: discord.Message, args: tuple):
        server = message.guild  # type: discord.Guild
        channel = message.channel  # type: discord.TextChannel
        user = message.author  # type: discord.Member

        body = ""
        plugin = discord.utils.find(lambda p: p.__class__.__name__.lower() == args[0].lower(), self.client.plugins)  # type: Plugin
        if not plugin:
            await channel.send("No plugin found by that name")
            return

        storage = await self.get_storage(server)
        disabled_commands = await self.client.db.redis.smembers('channel_disabled:{}'.format(channel.id)) or {}

        for command_name, func in sorted(plugin.commands.items(), key=lambda f: f[1].info.get('name', f[0])):
            cmd = func.info.get('name', command_name)
            description = func.info.get('description', 'No description')
            body += "{e}`{cmd}`: {desc}{e}\n".format(name=command_name, cmd=cmd, desc=description, e='~~' if command_name in disabled_commands else '')

        embed = discord.Embed(
            title="{}: commands".format(plugin.__class__.__name__),
            description=body,
            colour=discord.Color.blue()
        )

        await channel.send(embed=embed)
