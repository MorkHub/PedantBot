import re
import logging
import asyncio
import discord
from util import has_permission, truncate

from functools import wraps

log = logging.getLogger('pedantbot')


def command(pattern: str = "", db_name: str = None, description: str = "", usage: str = "",
            cooldown: int = 0, global_cooldown: int = 0,
            require_role: str = None, banned_role: str = None,
            requires_permissions: discord.Permissions = None):
    def actual_decorator(func):
        name = func.__name__
        cmd_name = "/" + name
        prog = re.compile(pattern or cmd_name)
        is_nsfw = hasattr(func, 'nsfw') and func.nsfw is not False

        @wraps(func)
        async def wrapper(self, message: discord.Message):
            match = prog.match(message.content)
            if not match:
                return

            server = message.server
            channel = message.channel
            args = match.groups()

            storage = await self.get_storage(server)

            channel_disabled = await storage.get("channel_disabled:{}".format(message.channel.id))
            if channel_disabled == "1":
                return

            if wrapper.nsfw and "nsfw" not in channel.name or \
                    (hasattr(channel, 'nsfw') and channel.nsfw is not True):
                return

            if cooldown:
                check = await storage.get("cooldown:{}:{}".format(db_name or name, message.author))
                if check:
                    return
                await storage.set("cooldown:{}:{}".format(db_name or name, message.author), 1, expire=cooldown)

            if global_cooldown:
                check = await storage.get("global_cooldown:{}".format(db_name or name))
                if check:
                    return
                await storage.set("global_cooldown:{}".format(db_name or name), 1, expire=global_cooldown)

            if requires_permissions:
                if not has_permission(server.me, requires_permissions):
                    await self.client.send_message(
                        channel,
                        "I do not have permission for that.\nRequires `{}`.".format(requires_permissions)
                    )
                    return

            if require_role:
                role = await storage.get('role:{}'.format(require_role))
                if role not in [x.id for x in message.author.roles]:
                    return

            if banned_role:
                if banned_role in [x.id for x in message.author.roles]:
                    return

            log.info("{}#{}@{} >> {}".format(
                message.author.name,
                message.author.discriminator,
                message.server.name,
                truncate(message.clean_content, 100)
            ))

            await func(self, message, args)
            added = await self.client.db.redis.incr('pedant3.stats:command_uses:{}'.format(
                wrapper.info.get('name', 'unknown')
            ))
            if added:
                await self.client.db.redis.sadd('pedant3.stats:commands', wrapper.info.get('name', 'unknown'))

        wrapper._db_name = db_name or func.__name__
        wrapper._is_command = True
        wrapper.nsfw = is_nsfw

        if usage:
            command_name = usage
        else:
            command_name = "/" + func.__name__

        wrapper.info = {
            "name": command_name,
            "description": description
        }

        return wrapper
    return actual_decorator


def bg_task(sleep_time):
    def actual_decorator(func):
        @wraps(func)
        async def wrapper(self):
            await self.client.wait_until_ready()
            while True:
                try:
                    await func(self)
                except Exception as e:
                    log.info("Error while executing {}. Retrying in {} seconds".format(
                        func.__name__,
                        sleep_time
                    ))
                    log.exception(e)

                await asyncio.sleep(sleep_time)

        wrapper._bg_task = True
        return wrapper
    return actual_decorator


def nsfw(func):
    func.nsfw = True
    return func
