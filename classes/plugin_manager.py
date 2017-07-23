from classes.plugin import Plugin
from decorators import *
from util import *

log = logging.getLogger('pedantbot')

class PluginManager:

    def __init__(self, client: discord.Client):
        self.client = client
        self.db = client.db
        self.client.plugins = []
        self.default_enabled = []

    def load(self, plugin: Plugin.__class__):
        log.debug('Loading plugin {}.'.format(plugin.__name__))
        plugin_instance = plugin(self.client)
        self.client.plugins.append(plugin_instance)
        self.default_enabled.append(plugin.__name__)
        log.info('Plugin {} loaded.'.format(plugin.__name__))

    def load_all(self):
        for plugin in Plugin.plugins:
            self.load(plugin)

    async def get_all(self, server: discord.Server):
        enabled_plugins = await self.db.redis.smembers('plugins_enabled:{}'.format(server.id))
        if not enabled_plugins:
            patch = True
        else:
            patch = False

        plugins = []
        for plugin_name in self.default_enabled:
            plugin = discord.utils.find(lambda p: p.__class__.__name__ == plugin_name, self.client.plugins)
            if not plugin:
                continue
            plugin_name = plugin.__class__.__name__

            if plugin_name in enabled_plugins:
                pass
            elif patch and plugin.default:
                pass
            elif plugin.required:
                pass
            else:
                continue

            if patch or plugin.required:
                await self.db.redis.sadd('plugins_enabled:{}'.format(server.id), plugin_name)

            plugins.append(plugin)
        return plugins

    async def set_plugin_state(self, plugin_name, server, state=None):
        errors = []
        if not plugin_name:
            return "No plugin name specified."
        else:
            plugin = discord.utils.find(lambda p: p.__class__.__name__.lower() == plugin_name.lower(), self.client.plugins)
            if not plugin:
                return "No plugin found by that name."
            elif plugin.required:
                return "You cannot enable/disable required plugins."
            plugin_name = plugin.__class__.__name__

        mode = "disabled" if state is False else "enabled"
        if not errors:
            func = self.db.redis.srem if state is False else self.db.redis.sadd
            enabled = await func("plugins_enabled:{}".format(server.id), plugin_name)
            if not enabled:
                return "Plugin already {}.".format(mode)

            return "Plugin, `{}`, {} for server, `{}`.".format(
                plugin.__class__.__name__,
                mode,
                server
            )

        return "Not {}".format(mode)