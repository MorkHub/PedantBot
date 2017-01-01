#!/usr/bin/env python3

"""Dependencies"""
from datetime import date
from datetime import datetime,timedelta
from threading import Timer
import asyncio
import atexit
import base64
import json
import logging
import logging.handlers
import math
import os
import platform
import pprint
import re#eeee
import string
import sys
import time
import traceback
import urllib
from random import randrange

import discord
import graph
import pyspeedtest
import MySQLdb
import wikipedia, wikia

"""Initialisation"""
from pedant_config import CONF,MESG
last_message_time = {}
reminders = []

client = discord.Client()

"""Command registration framework"""
import functools,inspect
commands = {}
def register(command_name, *args, **kwargs):
    def w(fn):
        @functools.wraps(fn)
        def f(*args, **kwargs):
            return fn(*args, **kwargs)
        f.command_name = command_name
        f.usage = CONF.get('cmd_pref','/') + command_name + (' ' if args != () else '') + ' '.join(args)
        f.admin = kwargs.get('admin', False)
        f.rate = kwargs.get('rate',0)
        f.invokes = {}
        if not inspect.getsource(f) in [inspect.getsource(commands[x]) for x in commands]:
            commands[command_name] = f
        return f
    return w

"""Setup logging"""
try:
    logging.basicConfig(format=CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'),stream=sys.stdout)
    logger = logging.getLogger('pedantbot')
    logger.setLevel(logging.INFO)

    log_handler = logging.handlers.RotatingFileHandler(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__)), 'a', backupCount=5, delay=True)
    log_handler.setLevel(logging.DEBUG)

    err_log_handler = logging.StreamHandler(stream=sys.stderr)
    err_log_handler.setLevel(logging.WARNING)

    formatter = logging.Formatter(CONF.get('log_format','[%(asctime)s] [%(levelname)s] %(message)s'))
    log_handler.setFormatter(formatter)
    err_log_handler.setFormatter(formatter)


    if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+CONF.get('logfile','{}.log'.format(__file__))):
        log_handler.doRollover()

    logger.addHandler(log_handler)
    logger.addHandler(err_log_handler)

    logger.warn('Starting...')
except Exception as e:
    print(e)

"""Respond to events"""
@client.event
async def on_ready():
    logger.info('Version ' + CONF.get('VERSION','0.0.0'))
    logger.info('Logged in as:')
    logger.info(' ->	Name: '+ client.user.name)
    logger.info(' ->    ID: '+ client.user.id)

    logger.info('Setting reminders')
    try:
        for rem in reminders:
            if rem.get('is_cancelled', False):
                continue
            task = asyncio.ensure_future(do_reminder(client, rem['invoke_time']))
            rem['task'] = task

        asyncio.ensure_future(update_status())

        logger.info(' -> set ' + str(len(reminders)) + ' reminders')

        save_reminders()
    except:
        pass

"""Respond to messages"""
@client.event
async def on_message(message):
    await client.wait_until_ready()

    try:
        if message.author.id == client.user.id:
            return
        elif message.content.lower().startswith(CONF.get('cmd_pref','/')):
            try:
                inp = message.content.split(' ')
                command_name, command_args = inp[0][1::].lower(),inp[1::]
                cmd = commands[command_name]

                last_used = cmd.invokes.get(message.author.id,False)
                datetime_now = datetime.now()
                if not last_used or (last_used < datetime_now - timedelta(seconds=cmd.rate)):
                    cmd.invokes[message.author.id] = datetime_now
							                
                    try:
                        await client.delete_message(message)
                    except:
                        pass
                    await client.send_typing(message.channel)

                    if not cmd.admin or (cmd.admin and message.author.id in CONF.get('admins',[])):
                        executed = await cmd(message,*command_args)
                        if executed == False:
                            await client.send_message(message.channel,MESG.get('cmd_usage','USAGE: {}.usage').format(cmd))
                    else:
                        await client.send_message(message.channel,MESG.get('nopermit','{0.author.mention} Not allowed.').format(message))
                else:
                    # Rate-limited
                    pass
            except KeyError:
                await client.send_message(message.channel, MESG.get('cmd_notfound','`{0}` not found.').format(command_name))

            except Exception as e:
                await client.send_message(message.channel,MESG.get('error','Error: {0}').format(e))

    except Exception as e:
        logger.error('error in on_message')
        logger.exception(e)
        await log_exception(e, 'on_message')

"""Commands"""
@register('test','[list of parameters]',admin=False,rate=1)
async def test(message,*args):
    """Print debug output"""
    await client.send_message(message.channel,'```py\n'+str(args)+'\n```\n')

@register('help','[command name]',rate=3)
async def help(message,*args):
    """Display help message(s), optionally append command name for specific help"""
    command_name = ' '.join(args)
    if args == ():
        admin_commands = ''; standard_commands = ''
        for command_name,cmd in sorted(commands.items(),key=lambda x: (x[1].admin,x[0])):
            if cmd.admin:
                admin_commands += MESG.get('cmd_doc','{0.command_name}: {0.__doc__}').format(cmd) + "\n"
            else:
                standard_commands += MESG.get('cmd_doc','{0.command_name}: {0.__doc__}').format(cmd) + "\n"
        await client.send_message(message.channel,MESG.get('cmd_list','Commands:\n{0}\nAdmin Commands:\n{1}').format(standard_commands,admin_commands))
    else:
        try:
            cmd = commands[command_name]
            await client.send_message(message.channel,MESG.get('cmd_help','{0.command_name}:\n```{0.usage}: {0.__doc__}```').format(cmd))
        except KeyError:
            await client.send_message(message.channel,MESG.get('cmd_notfound','`{0}` not found.').format(command_name)) 

"""Log exceptions nicely"""
async def log_exception(e,location=None):
    try:
        exc = ''.join(traceback.format_exception(None, e, e.__traceback__).format(chain=True))
        exc = [exc[i:i+2000-6] for i in range(0, len(exc), 2000-6)]
        await client.send_message('257152358490832906', 'Error ' + ('in `{}`:'.format(location) if location else 'somewhere:'))
        for i,ex in enumerate(exc):
            await client.send_message('257152358490832906','```{:.1994}```'.format(ex))
    except:
        pass

"""Update bot status: "Playing Wikipedia: Albert Einstein"""
async def update_status():
    try:
        await client.change_presence(game=discord.Game(name='Wikipedia: ' + wikipedia.random(pages=1)),afk=False,status=None)
        await asyncio.sleep(60)
        asyncio.ensure_future(update_status())
    except:
        pass

"""Locate OAuth token"""
token = CONF.get('token',None)
if not token:
    with open(CONF.get('dir_pref','/home/shwam3/')+'tokens.txt') as file:
        token = file.read().splitlines()[0]

"""Run program"""
if __name__ == '__main__':
    try:
        client.run(token, bot=True)
        logging.shutdown()
    except Exception as e:
        logging.error(e)
