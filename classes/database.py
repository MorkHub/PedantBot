import logging

import aioredis

from classes.storage import Storage

log = logging.getLogger('pedantbot')

class Db(object):
    def __init__(self, redis_url, loop):
        self.loop = loop
        self.redis_url = redis_url
        self.loop.create_task(self.create())
        self.redis_address = redis_url
        self.redis = None  # type: aioredis.Redis

    async def create(self):
        self.redis = await aioredis.create_redis(
            self.redis_address,
            encoding='utf8'
        )  # type: aioredis.Redis

    async def get_storage(self, plugin, server_id) -> Storage:
        namespace = "{}.{}:".format(
            plugin.__class__.__name__,
            server_id
        )
        storage = Storage(namespace, self.redis)
        return storage