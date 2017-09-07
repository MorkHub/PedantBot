# import discord
# import logging
import datetime

from classes.plugin import Plugin
from decorators import command
from util import *
from .time import Time

log = logging.getLogger('pedantbot')


class Commands(Plugin):
    plugin_name = 'user commands'

    async def response(self, string: str, message: discord.Message, args: tuple = ()):
        server = message.server
        channel = message.channel
        user = message.author

        tz = await Time.get_user_timezone(self.client, user.id)
        dt = datetime.datetime.now(tz=tz)

        response = printf(
            string,
            user=user.display_name,
            mention=user.mention,
            server=server,
            channel=channel.mention,
            time=dt.strftime(TIME_FORMAT),
            date=dt.strftime(DATE_FORMAT),
            datetime=dt.strftime(DATETIME_FORMAT),
        )

        if args:
            for arg in args:
                response = response.replace("%arg%", arg, 1)

        return response

    async def on_message(self, message):
        if message.author.bot:
            return
        if message.author.id == self.client.user.id:
            return

        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        commands = await storage.smembers('commands')

        trigger, args = find_match(commands, message.content)

        if trigger:
            template = await storage.get('command:{}'.format(trigger))
            response = await self.response(template, message, args)

            await  self.client.send_message(
                channel,
                response
            )

    @command(pattern=r'^!acr ("?)?([^"]*)\1 ("?)?([^"]*)\3$',
             description="add or edit a custom reaction",
             usage='!acr "<trigger>" "<response>"')
    async def add_command(self, message: discord.Message, args: tuple):
        if message.author.bot:
            return
        if message.author.id == self.client.user.id:
            return

        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_messages"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to add custom reactions in {server}.\n"
                "Requires `Manage Messages`.".format(
                    user=user,
                    server=server
                )
            )
            return

        storage = await self.get_storage(server)
        commands = await storage.smembers('commands')

        _, trigger, _, response = args
        trigger = trigger.lower()

        if trigger in commands:
            old = await storage.get('command:{}'.format(trigger))
            res = await confirm_dialog(
                self.client,
                channel=channel,
                user=user,
                title="That reaction already exists.",
                description="This will overwrite the existing response. Continue?\n"
                "```{} -> {}```".format(old, response),
                colour=discord.Color.red()
            )  # type: discord.Message

            if not res or res.content.lower() == 'n':
                return

        added = await storage.set('command:{}'.format(trigger), response)
        if added:
            await storage.sadd('commands', trigger)

        if added:
            await self.client.send_message(
                channel,
                "Reaction saved!"
            )

    @command(pattern='^!lcr$',
             description='list reactions for this server',
             usage='!lcr')
    async def list_reactions(self, message: discord.Message, args: tuple = ()):
        server = message.server
        channel = message.channel

        storage = await self.get_storage(server)
        commands = await storage.smembers('commands')

        body = ''.format(
            server=server
        )

        for n, _command in enumerate(commands):
            response = await storage.get('command:{}'.format(_command))
            response = response
            if not response:
                await storage.srem('commands', _command)

            body += "__#{}__ - *\"{:.100}\"* -> *\"{:.100}\"*\n".format(
                n,
                _command,
                str(response).replace('\n', '\\n')
            )

        embed = discord.Embed(
            title="Custom commands in {server}".format(
                server=server
            ),
            description=body
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern='^!dcr ([0-9]+)$',
             description="delete a custom reaction",
             usage="!dcr <ID>")
    async def delete_command(self, message: discord.Message, args: tuple):
        """
        :param message: discord.Message
        :param args: tuple[str]
        :return:
        """
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to delete custom reactions in {server}.\n"
                "Requires `Manage Messages`.".format(
                    user=user,
                    server=server
                )
            )
            return

        storage = await self.get_storage(server)
        commands = await storage.smembers('commands')

        if not args[0].isnumeric or int(args[0]) < 0 or int(args[0]) >= len(commands):
            await self.client.send_message(
                channel,
                "No command found by that ID"
            )
            return

        i = int(args[0])
        trigger = commands[i]
        response = await storage.get('command:{}'.format(trigger))
        res = await confirm_dialog(
            self.client,
            channel=channel,
            user=user,
            title="__Delete {}?__".format(trigger),
            description=response,
            colour=discord.Color.orange()
        )

        if not res:
            return

        if res.content.lower() == 'y':
            deleted = await storage.delete('command:{}'.format(trigger))
            if deleted:
                await storage.srem('commands', trigger)
                await self.client.send_message(
                    channel,
                    "Command `{}` deleted.".format(trigger)
                )
        else:
            await self.client.send_message(
                channel,
                "Cancelled, reaction not deleted."
            )
