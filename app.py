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

@register('remindme','in <number of> [seconds|minutes|hours]')
async def remindme(message,*args):
    if len(args) < 3:
        return False

    if args[0] != 'in' or int(args[1]) <= 0:
        return False

    invoke_time = int(time.time())

    logger.info('Set reminder')
    await client.send_typing(message.channel)

    reminder_msg = ' '.join(args[2::])
    is_cancelled = False
    split = reminder_msg.split(' ',1)
    unit = split[0]
    unit_specified = True
    reminder_if_unit = split[1] if len(split) > 1 else None

    _s = ['seconds','second','sec','secs']
    _m = ['minutes','minute','min','mins']
    _h = ['hours'  ,'hour'  ,'hr' ,'hrs' ]
    _d = ['days'   ,'day'   ,'d'         ]

    if unit in _s:
        unit_mult = 1
    elif unit in _m:
        unit_mult = 60
    elif unit in _h:
        unit_mult = 3600
    elif unit in _d:
        unit_mult = 3600 * 24
    else:
        unit_mult = 60
        unit_specified = False

    if not reminder_if_unit and not unit_specified:
        return False

    if reminder_if_unit and unit_specified:
        reminder_msg = reminder_if_unit

    if not reminder_msg:
        return False

    remind_delta = int(args[1]) * unit_mult
    remind_timestamp = invoke_time + remind_delta

    if remind_delta <= 0:
        await client.send_message(message.channel, MESG.get('reminder_illegal','Illegal argument'))
        return

    reminder = {'user_name':message.author.display_name, 'user_mention':message.author.mention, 'invoke_time':invoke_time, 'time':remind_timestamp, 'channel_id':message.channel.id, 'message':reminder_msg, 'task':None, 'is_cancelled':is_cancelled}
    reminders.append(reminder)
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
    await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime(dateFormat))

    if remind_delta > 15:
        save_reminders()

@register('reminders',rate=1)
async def list_reminders(message,*args):
    logger.info('Listing reminders')

    msg = 'Current reminders:\n'

    for rem in reminders:
        try:
            msg += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' at ' + datetime.fromtimestamp(rem['time']).strftime(dateFormat) + ': ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')
        except:
            msg += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' in ' + str(rem['time']) + ' seconds: ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')

    if len(reminders) == 0:
        msg += 'No reminders'

    await client.send_message(message.channel, msg)

@register('cancelreminder','<reminder id>')
async def cancel_reminder(message,*args):
    if len(args) != 1:
        return

    logger.info('Cancel reminder')

    invoke_time = int(args[0])

    reminder = get_reminder(invoke_time)
    reminder['is_cancelled'] = True
    reminder['task'].cancel()

    await client.send_message(message.channel,MESG.get('reminder_cancel','Reminder #{1[invoke_time]}for {0} cancelled.').format(datetime.fromtimestamp(rem['time'])).strftime(dateFormat),reminder)

@register('editreminder', '<reminder ID> <message|timestamp> [data]',rate=3)
async def edit_reminder(message,*args):
    """Edit scheduled reminders"""
    logger.info('Edit reminder')

    invoke_time = int(args[0])

    reminder = get_reminder(invoke_time)

    if not reminder:
        await client.send_message(message.channel, 'Invalid reminder ID `{0}`'.format(invoke_time))
        return

    try:
        if args[1].lower() in ['message','msg']:
            reminder['message'] = ' '.join(args[2::])

        elif args[1].lower() in ['timestamp','time','ts']:
            reminder['time'] = int(args[2])

        else:
            return False
    except:
        return False

    reminder['task'].cancel()
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    await client.send_message(message.channel, 'Reminder re-scheduled')

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

"""Reminders system"""
def get_reminder(invoke_time):
    """Returns reminder with specified invoke_time"""
    invoke_time = int(invoke_time)
    for rem in reminders:
        if rem['invoke_time'] == invoke_time:
            return rem

    return None

async def do_reminder(client, invoke_time):
    """Schedules and executes reminder"""
    cancel_ex = None
    try:
        reminder = get_reminder(invoke_time)
        wait = reminder['time']-int(time.time())
        if wait > 0:
            await asyncio.sleep(wait)
        else:
            chan = client.get_channel(reminder['channel_id'])
            await client.send_message(chan, 'The next reminder in channel ' + chan.name + ' is delayed by approximately ' + str(math.ceil(-wait/60.0)) + ' minutes, this is due to a bot fault')

        #get again to sync
        reminder = get_reminder(invoke_time)
        reminder['cancelled'] = True
        logger.info('Reminder ready')
        logger.info(' -> ' + reminder['user_mention'] + ': ' + reminder['message'])

        await client.send_message(client.get_channel(reminder['channel_id']), reminder['user_mention'] + ': ' + reminder['message'])
    except asyncio.CancelledError as e:
        cancel_ex = e
        reminder = get_reminder(invoke_time)
        if reminder['cancelled']:
            logger.info(' -> reminder ' + str(invoke_time) + ' cancelled')
            await client.send_message(client.get_channel(reminder['channel_id']), 'Reminder for '+reminder['user_name']+' in '+str(reminder['time']-int(time.time()))+' secs cancelled')
        else:
            logger.info(' -> reminder ' + str(invoke_time) + ' removed')

    if reminder['cancelled']:
        reminders.remove(reminder)

    save_reminders()

    if cancel_ex:
        raise cancel_ex

"""Exit procedure"""
@atexit.register
def save_reminders():
    """Save all in-memory reminders to file"""
    str = ''
    rems = []
    for rem in reminders[:]:
        rems.append({'user_name':rem['user_name'], 'user_mention':rem['user_mention'], 'invoke_time':rem['invoke_time'], 'time':rem['time'], 'channel_id':rem['channel_id'], 'message':rem['message'], 'is_cancelled':rem['is_cancelled']})
    for rem in rems:
        rem['task'] = None
        str += json.dumps(rem, sort_keys=True, skipkeys=True) + '\n'
    with open(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt', 'w') as file:
        file.write(str)

"""Load reminders from file into memory"""
reminders = []
if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt'):
    with open(CONF.get('dir_pref','/home/shwam3/')+'reminders.txt') as file:
        for line in file:
            try:
                reminders.append(json.loads(line))
            except json.decoder.JSONDecodeError as e:
                logger.error('JSON Error:')
                logger.exception(e)

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
