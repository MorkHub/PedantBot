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

@register('ping','[<host> [count]]',rate=5)
async def ping(message,*args):
    """Test latency by receiving a ping message"""
    await client.send_message(message.channel, MESG.get('ping','Pong.'))

@register('ip', admin=True)
async def ip(message,*args,admin=True):
    """Looks up external IP of the host machine"""
    response = urllib.request.urlopen('https://api.ipify.org/')
    IP_address = response.read().decode('utf-8')

    await client.send_message(message.channel, MESG.get('ip_addr','IP address: `{0}`').format(IP_address))

@register('speedtest',admin=True,rate=5)
async def speedtest(message):
    """Run a speedtest from the bot's LAN."""

    st = pyspeedtest.SpeedTest(host='speedtest.as50056.net')
    msg = await client.send_message(message.channel, MESG.get('st_start','Speedtest ...'))

    try:
        ping = str(round(st.ping(),1))
        logger.info(' -> ping: ' + ping + 'ms')
        msg = await client.edit_message(msg, MESG.get('st_ping','Speedtest:\nping: {}ms ...').format(ping))

        down = str(round(st.download()/1024/1024,2))
        logger.info(' -> download: ' + down + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_down','Speedtest:\nping: {0}ms,  up: {1}MB/s ...').format(ping,down))

        up = str(round(st.upload()/1024/1024,2))
        logger.info(' -> upload: ' + up + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_up','Speedtest:\nping: {0}ms,  up: {1}MB/s, down: {2}MB/s').format(ping,down,up))

    except Exception as e:
        logger.exception(e)
        await client.edit_message(msg, msg.content + MESG.get('st_error','Error.'))

@register('oauth','<OAuth client ID>')
async def oauth_link(message,*args):
    """Get OAuth invite link"""
    logger.info('OAuth')
    if len(message.content.split()) > 2:
        return False

    client_id = args[0] if len(args) == 1 else None

    await client.send_message(message.channel, discord.utils.oauth_url(client_id if client_id else client.user.id, permissions=discord.Permissions.all(), server=None, redirect_uri=None))

@register('pedant','<term>',rate=5)
@register('define','<term>',rate=5)
async def define(message, *args):
    """Search for a wikipedia page and show summary"""
    if not args:
        return False

    term = args[0]
    search = term
    content = None
    found = False

    logger.info('Finding definition: "' + term + '"')

    if term in special_defs:
        logger.info(' -> Special def')
        content = special_defs[term.lower()]
        if content.startswith('wiki:'):
            term = content[5:]
            content = None
        else:
            found = True

    try:
        if not found:
            arts = wikipedia.search(term)
            if len(arts) == 0:
                logger.info(' -> No results found')
                await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                return
            else:
                logger.info(' -> Wiki page')
                try:
                    content = wikipedia.summary(arts[0], chars=750)
                except wikipedia.DisambiguationError as de:
                    logger.info(' -> ambiguous wiki page')
                    content = wikipedia.summary(de.options[0], chars=750)

        logger.info(' -> Found stuff')
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(term),
                              description=''.join([x for x in content if x in ALLOWED_EMBED_CHARS]),
                              color=colour(message)
                             )

        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))

@register('random',rate=5)
async def random_wiki(message,*args):
    """Retrieve a random WikiPedia article"""
    logger.info('Finding random article')
    term = wikipedia.random(pages=1)

    logger.info(' -> Found: ' + term)
    embed = discord.Embed(title='Random article',
                            type='rich',
                            url='https://en.wikipedia.org/wiki/'+term,
                            description=''.join(x for x in wikipedia.summary(term, chars=450) if x in ALLOWED_EMBED_CHARS),
                            color=colour(message)
                         )
    embed.set_thumbnail(url='https://en.wikipedia.org/static/images/project-logos/enwiki.png')
    embed.set_author(name=term)
    embed.set_footer(text='Requested: random')

    await client.send_message(message.channel, embed=embed)

@register('perms',admin=True)
async def perms(message,*args):
    """List permissions available to this  bot"""
    member = message.server.get_member(message.mentions[0].id if len(message.mentions) > 0 else client.user.id)
    perms = message.channel.permissions_for(member)
    perms_list = [' '.join(w.capitalize() for w in x[0].split('_')).replace('Tts','TTS') for x in perms if x[1]]

    await client.send_message(message.channel, '**Perms for {0} [{2.value}]:**\n```{1}```'.format(member.name,'\n'.join(perms_list),perms))

@register('shrug')
async def shrug(message,*args):
    """Send a shrug: mobile polyfill"""
    embed = discord.Embed(title=message.author.name+' sent something:',description='¯\_(ツ)_/¯',color=colour(message),timestamp=datetime.now())
    await client.send_message(message.channel,embed=embed)

@register('wrong')
async def wrong(message,*args):
    """Send the WRONG! image"""
    embed = discord.Embed(title='THIS IS WRONG!',color=colour(message))
    embed.set_image(url='http://i.imgur.com/CMBlDO2.png')

    await client.send_message(message.channel,embed=embed)

@register('thyme')
async def thyme(message,*args):
    """Send some thyme to your friends"""
    embed = discord.Embed(title='Thyme',timestamp=message.edited_timestamp or message.timestamp,color=colour(message))
    embed.set_image(url='http://shwam3.altervista.org/thyme/image.jpg')
    embed.set_footer(text='{} loves you long thyme'.format(message.author.name))

    await client.send_message(message.channel,embed=embed)

@register('grid','<x> <y>',rate=1)
async def emoji_grid(message,*args):
    """Display a custom-size grid made of server custom emoji"""
    try:
        x = int(args[0]); y = int(args[1])
    except ValueError:
        x,y = 0,0

    x,y = min(x,12),min(y,4)

    emoji = message.server.emojis
    string = '**{}x{} Grid of {} emoji:**\n'.format(x,y,len(emoji))

    for i in range(y):
        for j in range(x):
            temp = emoji[randrange(len(emoji))]
            temp_emoji = '<:{}:{}> '.format(temp.name,temp.id)
            if len(string) + len(temp_emoji) <= 2000:
                string += temp_emoji
        if i < y-1:
            string += '\n'

    await client.send_message(message.channel,string)

@register('showemoji')
async def showemoji(message,*args):
    """Displays all available custom emoji in this server"""
    await client.send_message(message.channel,' '.join(['{}'.format('<:{}:{}>'.format(emoji.name,emoji.id),emoji.name) for emoji in message.server.emojis]))

@register('bigger','<custom server emoji>')
async def bigger(message,*args):
    """Display a larger image of the specified emoji"""
    logger.info('Debug emoji:')
    await client.send_typing(message.channel)

    try:
        thisEmoji = args[0]
    except:
        return False

    if thisEmoji:
        logger.info(' -> ' + thisEmoji)

    useEmoji = None
    for emoji in message.server.emojis:
        if str(emoji).lower() == thisEmoji.lower():
            useEmoji = emoji

    emoji = useEmoji
    if useEmoji != None:
        logger.info(' -> id: ' + emoji.id)
        logger.info(' -> url: ' + emoji.url)

        embed = discord.Embed(title=emoji.name,color=colour(message))
        embed.set_image(url=emoji.url)
        embed.set_footer(text='ID #'+emoji.id)

        await client.send_message(message.channel,embed=embed)
    else:
        await client.send_message(message.channel,MESG.get('emoji_unsupported','Unsupported emoji.').format(message.server.name))

@register('avatar','@<mention user>',rate=1)
async def avatar(message,*args):
    """Display a user's avatar"""
    if len(message.mentions) < 1:
        return False

    user = message.mentions[0]
    name = user.nick or user.name
    avatar = user.avatar_url or user.default_avatar_url

    embed = discord.Embed(title=name,type='rich',colour=colour(message))
    embed.set_image(url=avatar)
    embed.set_footer(text='ID: #{}'.format(user.id))
    await client.send_message(message.channel,embed=embed)

@register('vote','"<vote question>" <sequence of emoji responses>',rate=30)
async def vote(message,*args):
    """Initiate a vote using Discord Message Reactions."""
    logger.info(message.author.name + ' started a vote')

    await client.send_typing(message.channel)
    stuff = ' '.join(args)

    try:
        q, question = re.findall('(["\'])([^\\1]*)\\1',stuff)[0]
    except:
        return False

    allowedReactions = str(stuff[len(q+question+q)+1:]).replace('  ',' ').split()

    if len(allowedReactions) < 1:
        return False

    logger.info(' -> "' + question + '"')
    logger.info(' -> %s' % ', '.join(allowedReactions))

    msg = await client.send_message(message.channel, MESG.get('vote_title','"{0}" : {1}').format(question,allowedReactions))
    digits = MESG.get('digits',['0','1','2','3','4','5','6','7','8','9'])

    for e in allowedReactions:
        await client.add_reaction(msg, e)
    for i in range(30,0,-1):
        tens = round((i - (i % 10)) / 10)
        ones = i % 10
        num = (digits[tens] if (tens > 0) else '') + ' ' + digits[ones]

        await client.edit_message(msg,msg.content + MESG.get('vote_timer','Time left: {0}').format(num))
        await asyncio.sleep(1)

    await client.edit_message(msg,msg.content + MESG.get('vote_ended','Ended.'))
    msg = await client.get_message(msg.channel,msg.id)

    reacts = []
    validReactions = 0

    if len(msg.reactions) == 0:
        await client.send_message(msg.channel,MESG.get('vote_none','No valid votes.'))
        logger.info(' -> no winner')

    else:
        for reaction in msg.reactions:
            if reaction.emoji in allowedReactions:
                if reaction.count > 1:
                    reacts.append((reaction.emoji,reaction.count -1))
                    validReactions += 1

        if validReactions == 0:
            await client.send_message(msg.channel,MESG.get('vote_none','No valid votes.'))
            logger.info(' -> no winner')

        else:
            reacts = sorted(reacts, key=lambda x: x[1])
            reacts.reverse()

            await client.send_message(msg.channel,MESG.get('vote_win','"{0}", Winner: {1}').format(question,reacts[0][0],graph=graph.draw(msg.reactions,height=5,find=lambda x: x.count-1)))
            logger.info(' -> %s won' % reacts[0][0])

@register('quote','[quote id]',rate=2)
async def quote(message,*args):
    """Embed a quote from https://themork.co.uk/quotes"""
    logger.info('Quote')

    id = args[0]

    cnx = MySQLdb.connect(user='readonly', db='my_themork')
    cursor = cnx.cursor()

    query = ("SELECT * FROM `q2` WHERE `id`='{}' ORDER BY RAND() LIMIT 1".format(id))
    cursor.execute(query)

    if cursor.rowcount < 1:
        query = ("SELECT * FROM `q2` ORDER BY RAND() LIMIT 1")
        cursor.execute(query)

    for (id,quote,author,date,_,_) in cursor:
        embed = discord.Embed(title='TheMork Quotes',
                                description=quote,
                                type='rich',
                                url='https://themork.co.uk/quotes/?q='+ str(id),
                                timestamp=datetime(*date.timetuple()[:-4]),
                                color=colour(message)
        )
        embed.set_thumbnail(url='https://themork.co.uk/assets/main.png')
        embed.set_author(name=author)
        embed.set_footer(text='Quote ID: #' + str(id))

        await client.send_message(message.channel,embed=embed)

        break
    cursor.close()
    cnx.close()

@register('abuse','<channel> <content>',admin=True)
@register('sendmsg','<channel> <content>',admin=True)
async def abuse(message,*args):
    """Harness the power of Discord"""
    if len(args) < 2:
        return False

    channel = args[0]
    if channel == 'here':
        channel = message.channel.id
    msg = ' '.join(args[1::])

    try:
        await client.send_message(client.get_channel(channel),msg)
    except Exception as e:
        await client.send_message(message.channel,MESG.get('abuse_error','Error.'))

@register('fkoff',admin=True)
@register('restart',admin=True)
async def fkoff(message,*args):
    """Restart the bot"""
    logger.info('Stopping')
    await client.send_message(message.channel, MESG.get('shutdown','Shutting down.'))

    await client.logout()

    try:
        sys.exit()
    except Exception as e:
        logger.exception(e)
        pass

"""Utility functions"""
def colour(message=None):
    """Return user's primary role colour"""
    try:
        if message:
            return sorted([x for x in message.author.roles if x.colour != discord.Colour.default()], key=lambda x: -x.position)[0].colour
    except:
        pass

    return discord.Colour.default()

async def log_exception(e,location=None):
    """Log exceptions nicely"""
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

"""Import definition overrides"""
special_defs = {}
if os.path.isfile(CONF.get('dir_pref','/home/shwam3/')+'special_defs.txt'):
    with open(CONF.get('dir_pref','/home/shwam3/')+'special_defs.txt') as file:
        for line in file:
            if line.find(':') < 0:
                continue
            line = line.split(':',1)
            special_defs[line[0].lower()] = line[1].replace('\n','')

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
