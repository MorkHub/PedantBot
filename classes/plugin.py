import inspect
import logging

import discord
from classes.storage import Storage

log = logging.getLogger('pedantbot')

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from classes.pedant import Pedant
    from classes.database import Db

class PluginMount(type):
    def __init__(cls, *_):
        """called whenever a Plugin class is imported"""
        if not hasattr(cls, 'plugins'):
            cls.plugins = []
        else:
            cls.plugins.append(cls)


class Plugin(object, metaclass=PluginMount):
    plugin_name = None
    required = False
    default = True
    owner_manage = False
    config_vars = {}

    def __init__(self, client):
        """
        Plugin class exposing all Discord API events to plugins

        :param client: Pedant | discord.Client
        """
        self.client = client  # type: Pedant
        self.db = client.db  # type: Db
        self.commands = {}
        self.bg_tasks = {}

        for (name, member) in inspect.getmembers(self):
            if hasattr(member, '_is_command'):
                self.commands[member.__name__] = member
            if hasattr(member, '_bg_task'):
                self.bg_tasks[member.__name__] = member
                self.client.loop.create_task(member())

        log.debug('Registered {} commands'.format(
            len(self.commands)
        ))

    async def get_storage(self, server: discord.Guild) -> Storage:
        server_id = server.id
        paired = await self.client.db.redis.get('Admin.global:paired_server:{}'.format(server_id))
        if paired:
            server_id = paired

        return await self.client.db.get_storage(self, server_id)

    async def on_ready(self):
        pass

    async def _on_message(self, message: discord.Message):
        for command_name, func in self.commands.items():
            await func(message)
        await self.on_message(message)

    async def on_message(self, message: discord.Message):
        pass

    async def on_message_edit(self, before, after):
        pass

    async def on_message_delete(self, message):
        pass

    async def on_channel_create(self, channel):
        pass

    async def on_channel_update(self, before, after):
        pass

    async def on_channel_delete(self, channel):
        pass

    async def on_member_join(self, member):
        pass

    async def on_member_remove(self, member):
        pass

    async def on_member_update(self, before, after):
        pass

    async def on_server_join(self, server):
        pass

    async def on_server_remove(self, server):
        pass

    async def on_server_update(self, before, after):
        pass

    async def on_server_role_create(self, role):
        pass

    async def on_server_role_delete(self, role):
        pass

    async def on_server_role_update(self, before, after):
        pass

    async def on_voice_state_update(self, before, after):
        pass

    async def on_member_ban(self, member):
        pass

    async def on_member_unban(self, member):
        pass

    async def on_typing(self, channel, user, when):
        pass
