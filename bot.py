#!/usr/bin/python3
from util import redis_address

"""Start Plugins"""
from plugins.admin import Admin
from plugins.commands import Commands
from plugins.define import Define
from plugins.fun import Fun
from plugins.help import Help
from plugins.info import Info
from plugins.levels import Levels
from plugins.music import Music
from plugins.reminders import Reminders
from plugins.test import Test
from plugins.time import Time
from plugins.utility import Utility
from plugins.birthday import Birthdays
"""End Plugins"""

VERSION = '3.1.1'

def main():
    import logging
    import os
    import time

    token = os.getenv('TOKEN')
    shard = os.getenv('SHARD_ID') or '0'
    shard_count = os.getenv('SHARD_COUNT') or '1'
    redis_url = redis_address(os.getenv('REDIS_ADDRESS') or '')

    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s]:%(levelname)s:pedantbot#{}: %(message)s'.format(shard),
        datefmt="%d-%b-%Y %H:%M:%S"
    )

    log = logging.getLogger("pedantbot")
    log.info("Starting...")

    try:
        from classes.pedant import Pedant

        if token is None:
            tokens = []
            try:
                with open("tokens.txt", "r") as file:
                    tokens = file.read().split("\n")
            except:
                pass
            finally:
                if tokens:
                    token = tokens[0]
                else:
                    raise ValueError("required env variable 'TOKEN' not found.")

        if not shard.isnumeric():
            raise ValueError("'SHARD_ID' must be of type 'int'")

        if not shard_count.isnumeric():
            raise ValueError("'SHARD_COUNT' must be of type 'int'")

        if int(shard) >= int(shard_count):
           raise ValueError("'SHARD_ID' must be less than 'SHARD_COUNT'")

        if redis_url is None or \
            len(redis_url) != 2 or \
            not 0 < redis_url[1] < 65535:
            raise ValueError("'REDIS_ADDRESS' is invalid")

        bot = Pedant(
            shard_id=int(shard),
            shard_count=int(shard_count),
            redis_url=redis_url
        )

        bot.run(token)
    except Exception as e:
        log.exception(e)
        exit(1)

    log.warn("Restarting in 5 seconds...")
    time.sleep(5)


if __name__ == "__main__":
    main()
