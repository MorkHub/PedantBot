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

    @command(pattern="^\?(?:help|\?)$",
             description="get help",
             usage="?help")
    async def list_plugins(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        body = "Use `?help <topic>` to find specific help.\n\n"
        for plugin in await self.client.plugin_manager.get_all(server):
            body += "**{plugin.__class__.__name__}**: {plugin.plugin_name}\n".format(plugin=plugin)

        embed = discord.Embed(
            title="Plugins available in {}".format(server),
            description=body,
            colour=discord.Color.green()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^\?help (.+)$",
             description="get help",
             usage="?help <plugin>")
    async def plugin_help(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        body = ""
        plugin = discord.utils.find(lambda p: p.__class__.__name__.lower() == args[0].lower(), self.client.plugins)  # type: Plugin
        if not plugin:
            await self.client.send_message(
                channel,
                "No plugin found by that name"
            )
            return

        for command_name, func in plugin.commands.items():
            cmd = func.info.get('name', command_name)
            description = func.info.get('description', 'No description')
            body += "`{cmd}`: {desc}\n".format(cmd=cmd, desc=description)

        embed = discord.Embed(
            title="{}: commands".format(plugin.__class__.__name__),
            description=body,
            colour=discord.Color.blue()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )
