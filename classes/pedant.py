# import logging
# import os
import asyncio
import math

from classes.database import Db

from classes.plugin_manager import PluginManager
from util import *

log = logging.getLogger('pedantbot')


class Pedant(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.redis_url = kwargs.get("redis_url")
        self.db = Db(self.redis_url, self.loop)
        self.plugin_manager = PluginManager(self)
        self.plugin_manager.load_all()
        self.ping_interval = 10

    def run(self, *args):
        self.loop.run_until_complete(self.start(*args))

    async def start(self, *args, **kwargs):
        try:
            await super().start(*args, **kwargs)
        except KeyboardInterrupt:
            log.info('Shutting down...')
            await self.logout()

    async def ping(self):
        pass
    #     await self.wait_until_ready()
    #     while True:
    #         keep_alive = math.ceil(self.ping_interval * 1.3)

    #         if self.is_logged_in:
    #             await self.db.redis.setex('heartbeat:{}:ping'.format(self.shard_id), keep_alive, '1')
    #         else:
    #             await self.db.redis.setex('heartbeat:{}:ping'.format(self.shard_id), keep_alive, '0')

    #         await asyncio.sleep(3)

    async def on_ready(self):
        for plugin in self.plugins:
            self.loop.create_task(plugin.on_ready())

        me = await self.application_info()

        log.info('Client ready.')
        log.info('Logged in as:')
        log.info(' -> Client ID:   {}'.format(self.user.id))
        log.info(' -> Client User: {}'.format(self.user))
        log.info(' -> Invite URL:  {}'.format(discord.utils.oauth_url(
            me.id,
            permissions=discord.Permissions.all())
        ))

        self.loop.create_task(self.ping())

    async def on_message(self, message: discord.Message):
        # if message.channel.is_private:
        #     return
        if message.author.__class__ != discord.Member:
            return
        if message.author == self.user:
            return
        if message.author.bot:
            return

        server = message.guild
        if server is None:
            return

        if message.content.startswith((';enable ', ';disable ')) and \
                len(message.content.split(maxsplit=1)) == 2:
            channel = message.channel  # type: discord.TextChannel
            user = message.author  # type: discord.Member

            if not has_permission(user, "manage_server"):
                await self.send_message(
                    channel,
                    "{user.mention}, You cannot modify server settings.\n"
                    "Requires `manage_server`.".format(user=user)
                )
                return

            cmd, plugin_name = message.content.split(maxsplit=1)
            plugin_name = plugin_name.replace(" ", "_")
            plugin = discord.utils.find(
                lambda _plugin: _plugin.__class__.__name__.lower() == plugin_name.lower(),
                self.plugins
            )

            if plugin is None:
                await self.send_message(
                    channel,
                    "No such plugin: '{}'".format(
                        clean_string(plugin_name)
                    )
                )
                return

            if plugin.owner_manage:
                owners = await self.db.redis.smembers('owners') or []
                if int(user.id) not in owners:
                    await self.send_message(
                        channel,
                        "{user.mention}, only my owner(s) can manage that plugin.\n"
                        "Requires `bot_owner`.".format(
                            user=user
                        )
                    )
                    return

            state = cmd == ";enable"

            msg = await self.plugin_manager.set_plugin_state(plugin_name, server, state=state)

            await self.send_message(
                channel,
                msg
            )
            return

        enabled_plugins = await self.plugin_manager.get_all(server)

        if message.content.startswith((';enablecmd ', ';disablecmd ')) and \
                len(message.content.split(maxsplit=1)) == 2:
            channel = message.channel
            user = message.author

            if not has_permission(user, "manage_channels"):
                await self.send_message(
                    channel,
                    "{user.mention}, You cannot modify server settings.\n"
                    "Requires `manage_server`.".format(user=user)
                )
                return

            cmd_name = message.content.split(maxsplit=1)[1]
            cmds = []
            m = "disabled" if message.content.startswith(';disablecmd') else "enabled"
            for p in enabled_plugins:
                if cmd_name in p.commands:
                    f = self.db.redis.sadd if message.content.startswith(';disablecmd') else self.db.redis.srem
                    cmds.append(cmd_name)
                    await f('channel_disabled:{}'.format(channel.id), cmd_name)

            await self.send_message(
                channel,
                "{} commands: `{}`".format(m, ','.join(cmds))
            )

        for p in enabled_plugins:
            self.loop.create_task(p._on_message(message))

        try:
            await self.db.redis.incr('pedant3.stats:messages_received')
        except Exception as e:
            log.warning("Could not update stats.")
            log.exception(e)

    async def send_message(self, destination, content=None, *, tts=False, embed=None):
        dest = destination
        if isinstance(dest, discord.TextChannel):
            dest = dest.guild

        # if isinstance(dest, discord.PrivateChannel):
            # dest = dest.name or dest.user

        text = content or (embed.title or embed.description)
        if text:
            log.debug("Me@{} << {}".format(
                dest,
                truncate(text, 100)
            ))

        msg = await destination.send(content, tts=tts, embed=embed)

        try:
            await self.db.redis.incr('pedant3.stats:messages_sent')
        except Exception as e:
            log.warning("Could not update stats.")
            log.exception(e)

        return msg

    async def kick(self, member):
        _return = await super().kick(member)
        await self.db.redis.incr('pedant3.stats:kicked')
        return _return

    async def ban(self, member, delete_message_days=1):
        _return = await super().ban(member, delete_message_days=delete_message_days)
        await self.db.redis.incr('pedant3.stats:banned')
        return _return

    async def pin_message(self, message):
        _return = await super().pin_message(message)
        await self.db.redis.incr('pedant3.stats:pinned')
        return _return

    async def prune_members(self, server, *, days):
        pruned = await super().prune_members(server, days)
        await self.db.redis.incrby('pedant3.stats:pruned', pruned)
        return pruned

    async def purge_from(self, channel, *, limit=100, check=None, before=None, after=None, around=None):
        purged = await super().purge_from(channel, limit=limit, check=check, before=before, after=after, around=around)
        if purged:
            await self.db.redis.incrby('pedant3.stats:bulk_deleted', len(purged))
        return purged

    async def delete_message(self, message):
        deleted = await super().delete_message(message)
        if deleted:
            await self.db.redis.incr('pedant3.stats:deleted')
        return deleted

    async def delete_messages(self, messages):
        deleted = await super().delete_messages(messages)
        if deleted:
            await self.db.redis.incrby('pedant3.stats:bulk_deleted', len(deleted))
        return deleted

    async def send_file(self, destination, fp, *, filename=None, content=None, tts=False):
        _return = await super().send_file(destination, fp=fp, filename=filename, content=content, tts=tts)
        sent = await self.db.redis.incr('pedant3.stats:files_sent')
        return _return

    async def get_plugins(self, server):
        plugins = await self.plugin_manager.get_all(server)
        return plugins

    async def on_message_edit(self, before, after):
        server = before.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_message_edit(before, after))

    async def on_message_delete(self, message):
        server = message.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_message_delete(message))

    async def on_channel_create(self, channel):
        server = channel.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_channel_create(channel))

    async def on_channel_update(self, before, after):
        server = before.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_channel_update(before, after))

    async def on_channel_delete(self, channel):
        # if channel.is_private:
        #     return

        server = channel.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_channel_delete(channel))

    async def on_member_join(self, member):
        server = member.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_member_join(member))

    async def on_member_remove(self, member):
        server = member.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_member_remove(member))

    async def on_member_update(self, before, after):
        server = before.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_member_update(before, after))

    async def on_server_join(self, server):
        await self.db.redis.sadd('servers', server.id)

        log.info("Joined {}'s server: '{}'".format(
            clean_string(server.owner.name),
            clean_string(server.name)
        ))
        log.debug('Adding server {}\'s id to db'.format(server.id))
        await self.db.redis.set('server:{}:name'.format(server.id), server.name)
        if server.icon:
            await self.db.redis.set(
                'server:{}:icon'.format(server.id),
                server.icon
            )

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_server_join(server))

    async def on_server_update(self, before, after):
        for plugin in await self.plugin_manager.get_all(before):
            self.loop.create_task(plugin.on_server_update(before, after))

    async def on_server_remove(self, server):
        log.info("Leaving {} server: '{}!'".format(
            server.owner.name,
            server.name
        ))
        log.debug('Removing server {}\'s id from the db'.format(
            server.id
        ))
        await self.db.redis.srem('servers', server.id)

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_server_remove(server))

    async def on_server_role_create(self, role):
        server = role.guild

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_server_role_create(role))

    async def on_server_role_delete(self, role):
        server = role.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_server_role_delete(role))

    async def on_server_role_update(self, before, after):
        server = before.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_server_role_update(before, after))

    async def on_voice_state_update(self, before, after):
        server = before.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_voice_state_update(before, after))

    async def on_member_ban(self, member):
        server = member.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_member_ban(member))

    async def on_member_unban(self, member):
        server = member.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_member_unban(member))

    async def on_typing(self, channel, user, when):
        # if channel.is_private:
        #     return

        server = channel.guild
        if server is None:
            return

        for plugin in await self.plugin_manager.get_all(server):
            self.loop.create_task(plugin.on_typing(channel, user, when))
