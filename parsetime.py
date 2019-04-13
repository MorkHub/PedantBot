from datetime import datetime as dt, timedelta as td
import re





TIME_FORMAT = "%H:%M"
DATE_FORMAT = "%d-%b-%Y"
DATETIME_FORMAT = "{} @ {}".format(DATE_FORMAT, TIME_FORMAT)

split_exp  = re.compile(r"([^:]*)(?: *: *(.*))?")

year_exp   = re.compile(r"(?:([0-9]+)[ ]*(?:years?|y))")
month_exp  = re.compile(r"(?:([0-9]+)[ ]*(?:months?|mo))")
week_exp   = re.compile(r"(?:([0-9]+)[ ]*(?:weeks?|w))")
day_exp    = re.compile(r"(?:([0-9]+)[ ]*(?:days?|d))")
hour_exp   = re.compile(r"(?:([0-9]+)[ ]*(?:hours?|h))")
minute_exp = re.compile(r"(?:([0-9]+)[ ]*(?:min(?:ute)?s?|m))")
second_exp = re.compile(r"(?:([0-9]+)[ ]*(?:sec(?:ond)?s?|s))")


def parse(string = None):
    if string is None:
        string = input()
    time, message = split_exp.search(string).groups()

    days    = 0
    seconds = 0
    
    seconds += toInt(second_exp, time)
    seconds += toInt(minute_exp, time) * 60
    seconds += toInt(hour_exp,   time) * 3600
    
    days += toInt(day_exp,   time)
    days += toInt(week_exp,  time) * 7
    days += toInt(month_exp, time) * 30
    days += toInt(year_exp,  time) * 365
    
    return td(days=days, seconds=seconds), message


def toInt(expression, search):
    try:
        return int(expression.search(search).groups()[0])
    except:
        return 0

def init():
    import discord
    import logging
    import time

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("discord")

    client = discord.Client()

    try:
        logger = logging.getLogger('pedantbot')
    except Exception as e:
        print(e)


    """Respond to messages"""
    @client.event
    async def on_message(message):
        await client.wait_until_ready()

        if message.content.startswith("!dt"):
            try:
                delta, msg = parse(message.content[3:])
            except Exception as e:
                await client.send_message(message.channel, "Error: ```\n{}```".format(e))

            now = dt.now()
            then = now + delta
            
            await client.send_message(message.channel, "Will remind you at `{}`: ```\n{}```".format(then.strftime(DATETIME_FORMAT), msg))


"""Locate OAuth token"""
def get_token():
    token = 'MTY5MTEyMzU5OTM4MjkzNzYw.DhiDLg.pEtAoYJWD91QpBr-OEvQKkSlYIU'
    try:
        token = CONF.get('token',None)
        if not token:
            with open(CONF.get('dir_pref','./')+'tokens.txt') as file:
                token = file.read().splitlines()[0]
    except:
        pass

    return token

"""Run program"""
def main():
    init()

    try:
        token = get_token()
        client.run(token, bot=True)
        logging.shutdown()
    except Exception as e:
        logger.exception(e)

    logger.info("Waiting 5 seconds")
    time.sleep(3)


if __name__ == '__main__':
    main()
