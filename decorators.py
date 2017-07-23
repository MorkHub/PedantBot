import re
import logging
import asyncio
import discord

from functools import wraps

log = logging.getLogger('pedantbot')


def command(pattern: str = "", db_name: str = None, description: str = "", usage: str = "",
            cooldown: int = 0, global_cooldown: int = 0):
    def actual_decorator(func):
        name = func.__name__
        cmd_name = "/" + name
        prog = re.compile(pattern or cmd_name)
        nsfw = hasattr(func, 'nsfw') and func.nsfw != False

        @wraps(func)
        async def wrapper(self, message: discord.Message):
            match = prog.match(message.content)
            if not match:
                return

            server = message.server
            channel = message.channel
            args = match.groups()

            storage = await self.get_storage(server)

            channel_disabled = await storage.get("cmd_disabled:{}".format(message.channel.id))
            if channel_disabled == "1":
                return

            if wrapper.nsfw and "nsfw" not in channel.name or \
                    (hasattr(channel, 'nsfw') and channel.nsfw != True):
                return

            if cooldown:
                check = await storage.get("cooldown:{}:{}".format(db_name or name,message.author))
                if check:
                    return
                await storage.set("cooldown:{}:{}".format(db_name or name, message.author), expire=cooldown)

            if global_cooldown:
                check = await storage.get("global_cooldown:{}".format(db_name or name))
                if check:
                    return
                await storage.set("global_cooldown:{}".format(db_name or name), expire=global_cooldown)

            log.info("{}#{}@{} >> {}".format(
                message.author.name,
                message.author.discriminator,
                message.server.name,
                message.clean_content[:100]
            ))

            await func(self, message, args)
            added = await self.client.db.redis.incr('pedant3.stats:command_uses:{}'.format(wrapper.info.get('name', 'unknown')))
            if added:
                await self.client.db.redis.sadd('pedant3.stats:commands',wrapper.info.get('name', 'unknown'))

        wrapper._db_name = db_name or func.__name__
        wrapper._is_command = True
        wrapper.nsfw = nsfw

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