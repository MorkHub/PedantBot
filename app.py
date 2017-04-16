#!/usr/bin/env python3

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
import re#eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee
import string
import sys
import time
import traceback
import urllib
import subprocess
import calendar as cal
from random import randrange
import glob
import io
from PIL import Image,ImageDraw,ImageFont
import textwrap
import struct
import gtts
import requests

"""Dependencies"""
import discord
import taglib
import morkpy.graph as graph
from morkpy.postfix import calculate
from morkpy.scale import scale
import pyspeedtest
import MySQLdb
import wikipedia, wikia
import urbandict

"""Initialisation"""
from pedant_config import CONF,SQL,MESG
last_message_time = {}
reminders = []
ALLOWED_EMBED_CHARS = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~'
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
        f.owner = kwargs.get('owner', False)
        f.rate = kwargs.get('rate',0)
        f.hidden = kwargs.get('hidden',False)
        f.invokes = {}
        f.alias_for = kwargs.get('alias',False)
        f.typing = kwargs.get('typing',True)

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
    logger.info(' ->    Name: '+ client.user.name)
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

    client.voice = None

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

                if command_name in commands:
                    cmd = commands[command_name]
                else:
                    asyncio.ensure_future(do_record(message))
                    return False

                last_used = cmd.invokes.get(message.author.id,False)
                datetime_now = datetime.now()

                try:
                    await client.delete_message(message)
                except:
                    pass

                if not last_used or (last_used < datetime_now - timedelta(seconds=cmd.rate)):
                    cmd.invokes[message.author.id] = datetime_now

                    if cmd.typing:
                        await client.send_typing(message.channel)
                    if not (cmd.owner or cmd.admin) or (cmd.owner and isowner(message.author)) or (cmd.admin and (isadmin(message.author) or isowner(message.author))):
                        executed = await cmd(message,*command_args)
                        if executed == False:
                            msg = await client.send_message(message.channel,MESG.get('cmd_usage','USAGE: {}.usage').format(cmd))
                            asyncio.ensure_future(message_timeout(msg, 40))
                    else:
                        msg = await client.send_message(message.channel,MESG.get('nopermit','{0.author.mention} Not allowed.').format(message))
                        asyncio.ensure_future(message_timeout(msg, 40))
                else:
                    # Rate-limited
                    pass

            except Exception as e:
                logger.exception(e)
                msg = await client.send_message(message.channel,MESG.get('error','Error in `{1}`: {0}').format(e,command_name))
                asyncio.ensure_future(message_timeout(msg, 40))
        else:
            pass

    except Exception as e:
        logger.error('error in on_message')
        logger.exception(e)
        await log_exception(e, 'on_message')

async def toggle_deafen(user):
    """toggles mute/deafen every few seconds"""
    await asyncio.sleep(randrange(7,15))

    try:
        await client.server_voice_state(user,mute=not user.voice.mute,deafen=not user.voice.deaf)
        logger.info(' -> Toggled {} to {},{}'.format(user,'muted' if user.voice.mute else 'unmuted','deafened' if user.voice.deaf else 'undeafened'))
        sleepies[user.id] = asyncio.ensure_future(toggle_deafen(user))
    except:
        t = sleepies.get(user.id,False)
        if t:
            t.cancel()
        pass

sleepies = {}
@client.event
async def on_voice_state_update(before,after):
    roles = []
    def bed_role(role=None):
        if not role:
            return False
        return role.name == "gotobed"

    for server in client.servers:
        roles += list(filter(bed_role, server.roles))

    if 0 < datetime.now().hour < 7 and not set(after.roles).isdisjoint(roles):
        if after.voice != None and (before.voice == None or before.voice.voice_channel != after.voice.voice_channel) and not after.id in sleepies:
            logger.info(' -> doing the thing for {}'.format(after))
            sleepies[after.id] = asyncio.ensure_future(toggle_deafen(after))

"""Commands"""
@register('test','[list of parameters]',owner=False,rate=1)
async def test(message,*args):
    """Print debug output"""
    debug = '**Debug Output**```py\n'

    def get_embed(embed):
        temp = {}
        for param in ['type','title','description','url','footer','image','video','author']:
            try:
                temp[param] = embed.get(param,None)
            except:
                pass
        return temp

    if len(args) > 0:
        debug += '\n\nargs = {}'.format(args)
    if len(message.attachments) > 0:
        debug += '\n\nmessage.attachments = {}'.format(message.attachments)
    if len(message.embeds) > 0:
        debug += '\nmessage.embeds = {}'.format(e.to_dict() for e in message.embeds)
    debug += "\ncolor = '{}'".format(str(message.author.color))
    debug += '```'
    msg = await client.send_message(message.channel,debug)
    await client.add_reaction(msg,'🚫')
    def react(reaction,user):
        return user != client.user
    await client.wait_for_reaction(emoji='🚫',message=msg,check=react)
    await client.delete_message(msg)

@register('report')
async def issues(message,*args):
    """get url to report bugs"""
    await client.send_message(message.channel,"Please post bug reports on GitHub.\n__https://github.com/MorkHub/PedantBot/issues__")

@register('info',rate=5)
async def bot_info(message,*args):
    """Print information about the Application"""
    me = await client.application_info()
    owner = me.owner
    embed = discord.Embed(title=me.name,description=me.description,color=message.author.color,timestamp=discord.utils.snowflake_time(me.id))
    embed.set_thumbnail(url=me.icon_url)
    embed.set_author(name=owner.name,icon_url=owner.avatar_url or owner.default_avatar_url)
    embed.set_footer(text="Client ID: {}".format(me.id))

    await client.send_message(message.channel,embed=embed)
@register('msg','<message ID>',owner=True)
async def get_msg(message,*args):
   """get info about a message"""
   if len(args) < 1: return False
   msg = await client.get_message(message.channel,args[0])

   embed = discord.Embed(title="Message info",description="Date: {}\nContent: {:.100}".format(msg.timestamp.strftime('%d %B %Y @ %I:%M%p'),msg.content))
   await client.send_message(message.channel,embed=embed)

@register('git')
async def git(message,*args):
    """Get the github URL for this bot"""
    me = await client.application_info()
    embed = discord.Embed(title='MorkHub/PedantBot on GitHub',color=message.author.color,description=me.description,url='https://github.com/MorkHub/PedantBot')
    embed.set_author(name='MorkHub',url='https://github.com/MorkHub/')
    embed.set_thumbnail(url=me.icon_url)

    await client.send_message(message.channel,embed=embed)

@register('hlep','[command name]',alias='help',rate=3)
@register('man','[command name]',alias='help',rate=3)
@register('help','[command name]',rate=3)
async def help(message,*args):
    """Display help message(s), optionally append command name for specific help"""
    command_name = ' '.join(args)
    if args == ():
        admin_commands = ''; standard_commands = ''
        for command_name,cmd in sorted(commands.items(),key=lambda x: (x[1].owner,x[0])):
            if cmd.alias_for == False and not cmd.hidden:
                if cmd.owner:
                    admin_commands += '{0.usage}'.format(cmd) + "\n"
                else:
                    standard_commands += '{0.usage}'.format(cmd) + "\n"

        embed = discord.Embed(title="Command Help",color=message.author.color,description='Prefix: {0}\nUSAGE: {0}command <required> [optional]\nFor more details: {0}help [command] '.format(CONF.get('cmd_pref','/')))
        embed.add_field(name='Standard Commands',value='```{:.1000}```'.format(standard_commands),inline=True)
        if message.author.id in CONF.get('owners',[]):
          embed.add_field(name='Admin Commands',value='```{:.400}```'.format(admin_commands),inline=True)
        embed.add_field(name='Discord Help',value='If you need help using Discord, the Help Center may be useful for you.\nhttps://support.discordapp.com/')

        msg = await client.send_message(message.channel,embed=embed)
        asyncio.ensure_future(message_timeout(msg,120))
    else:
        try:
            cmd = commands[command_name]
            embed = discord.Embed(title="__Help for {0.command_name}__".format(cmd),color=message.author.color)
            embed.add_field(name="Usage",value='```'+cmd.usage+'```')
            embed.add_field(name="Description",value=cmd.__doc__)
            msg = await client.send_message(message.channel,embed=embed)
            asyncio.ensure_future(message_timeout(msg, 60))
        except KeyError as e:
            logger.exception(e)
            msg = await client.send_message(message.channel,MESG.get('cmd_notfound','`{0}` not found.').format(command_name))
            asyncio.ensure_future(message_timeout(msg, 20))

@register('info',rate=5)
async def bot_info(message,*args):
    """Print information about the Application"""
    me = await client.application_info()
    owner = me.owner
    embed = discord.Embed(title=me.name,description=me.description,color=message.author.color,timestamp=discord.utils.snowflake_time(me.id))
    embed.set_thumbnail(url=me.icon_url)
    embed.set_author(name=owner.name,icon_url=owner.avatar_url or owner.default_avatar_url)
    embed.set_footer(text="Client ID: {}".format(me.id))

    await client.send_message(message.channel,embed=embed)
@register('setnick',rate=10,owner=True)
async def setnick(message,*args):
    """Set bot nickname"""
    nickname = ''.join(args)
    member = message.server.get_member(client.user.id)
    try:
        await client.change_nickname(member,nickname)
        member = message.server.get_member(client.user.id)
        await client.send_message(message.channel,'Nickname successfully changed to `{}`'.format(member.nick or member.name))
    except:
        await client.send_message(message.channel,'Failed to change nickname!')

@register('remindme','in <number of> [seconds|minutes|hours|days]')
async def remindme(message,*args):
    if len(args) < 3:
        return False

    word_units = {'couple':(2,2),'few':(2,4),'some':(3,5), 'many':(5,15), 'lotsa':(10,30)}

    if args[0] != 'in' or (not args[1] in word_units and int(args[1]) <= 0):
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

    if args[1] in word_units:
        args[1] = randrange(*word_units[args[1]])

    remind_delta = int(args[1]) * unit_mult
    remind_timestamp = invoke_time + remind_delta

    if remind_delta <= 0:
        msg = await client.send_message(message.channel, MESG.get('reminder_illegal','Illegal argument'))
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    reminder = {'user_name':message.author.display_name, 'user_mention':message.author.mention, 'invoke_time':invoke_time, 'time':remind_timestamp, 'channel_id':message.channel.id, 'message':reminder_msg, 'task':None, 'is_cancelled':is_cancelled}
    reminders.append(reminder)
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
    msg = await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p')))
    asyncio.ensure_future(message_timeout(msg, 60))

    if remind_delta > 15:
        save_reminders()

@register('reminders',rate=1)
async def list_reminders(message,*args):
    logger.info('Listing reminders')

    msg = 'Current reminders:\n'
    reminders_yes = ''; reminders_no = ''

    for rem in reminders:
        try:
            if not message.server.get_channel(rem['channel_id']): continue
        except: continue

        try: date = datetime.fromtimestamp(rem['time']).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p'))
        except: date = str(rem['time'])

        if not rem.get('is_cancelled',False):
            n=datetime.now()
            c=(datetime.fromtimestamp(rem['time'])-n)
            s=c.days*86400+c.seconds
            d=(s//(86400*365),s//86400,s//3600,s//60,s)
            for i in range(5):
                if d[i] > 0:
                    x = i
                    break
            u=['year','day','hour','minute','second']
            m="{} {}{} remaining".format(d[x],u[x],'s' if d[x] > 1 else '')

            current_reminders += ''.join([x for x in (rem['user_mention'] + ' at ' + date + ' ({})'.format(m) + ': ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)\n') if x in ALLOWED_EMBED_CHARS or x == '\n'])

    embed = discord.Embed(title="Reminders in {}".format(message.server.name),color=message.author.color,description='No reminders set' if len(current_reminders == 0) else discord.Embed.Empty)
    embed.set_footer(icon_url=message.server.icon_url,text='{:.16} | PedantBot Reminders'.format(message.server.name))
    if len(current_reminders) > 0:
        embed.add_field(name='__Current Reminders__',value='{:.1000}'.format(reminders_yes))

    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 90))

@register('cancelreminder','<reminder id>')
async def cancel_reminder(message,*args):
    """Cancel an existing reminder"""
    global reminders
    if len(args) != 1:
        return

    logger.info('Cancel reminder')

    invoke_time = int(args[0])

    try:
        reminder = get_reminder(invoke_time)
        reminder['is_cancelled'] = True
        reminder['task'].cancel()
    except:
        msg = await client.send_message(message.channel,'Reminder not found.')
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    msg = await client.send_message(message.channel,'Reminder #{0[invoke_time]}: `"{0[message]}"` removed.'.format(reminder))
    asyncio.ensure_future(message_timeout(msg, 20))
    reminders = [x for x in reminders if x['invoke_time'] != invoke_time]

@register('editreminder', '<reminder ID> <message|timestamp> [data]',rate=3)
async def edit_reminder(message,*args):
    """Edit scheduled reminders"""
    logger.info('Edit reminder')

    invoke_time = int(args[0])

    reminder = get_reminder(invoke_time)

    if not reminder:
        msg = await client.send_message(message.channel, 'Invalid reminder ID `{0}`'.format(invoke_time))
        asyncio.ensure_future(message_timeout(msg, 20))
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

    msg = await client.send_message(message.channel, 'Reminder re-scheduled')
    asyncio.ensure_future(message_timeout(msg, 40))

@register('ping','[<host> [count]]',rate=5)
async def ping(message,*args):
    """Test latency by receiving a ping message"""
    await client.send_message(message.channel, MESG.get('ping','Pong.'))

@register('ip', owner=True)
async def ip(message,*args,owner=True):
    """Looks up external IP of the host machine"""
    response = urllib.request.urlopen('https://api.ipify.org/')
    IP_address = response.read().decode('utf-8')

    output = subprocess.run("ip route | awk 'NR==2 {print $NF}'", shell=True, stdout=subprocess.PIPE, universal_newlines=True)

    embed = discord.Embed(title="IP address for {user.name}".format(user=client.user),color=message.author.color)
    try:
        embed.add_field(name='Internal',value='```'+output.stdout+'```')
    except Exception as e:
        logger.exception(e)
    embed.add_field(name='External',value='```'+IP_address+'```')

    await client.send_message(message.channel, embed=embed)

@register('speedtest',owner=True,rate=5)
async def speedtest(message):
    """Run a speedtest from the bot's LAN."""
    st = pyspeedtest.SpeedTest(host='speedtest.as50056.net')
    msg = await client.send_message(message.channel, MESG.get('st_start','Speedtest ...'))

    try:
        ping = str(round(st.ping(),1))
        logger.info(' -> ping: ' + ping + 'ms')
        msg = await client.edit_message(msg, MESG.get('st_ping','Speedtest:\nping: {0}ms ...').format(ping))

        down = str(round(st.download()/1024/1024,2))
        logger.info(' -> download: ' + down + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_down','Speedtest:\nping: {0}ms,  down: {1}MB/s ...').format(ping,down))

        up = str(round(st.upload()/1024/1024,2))
        logger.info(' -> upload: ' + up + 'Mb/s')
        msg = await client.edit_message(msg, MESG.get('st_up','Speedtest:\nping: {0}ms,  down: {1}MB/s, up: {2}MB/s').format(ping,down,up))

    except Exception as e:
        logger.exception(e)
        msg = await client.edit_message(msg, msg.content + MESG.get('st_error','Error.'))
        asyncio.ensure_future(message_timeout(msg, 20))

@register('oauth','[OAuth client ID]')
async def oauth_link(message,*args):
    """Get OAuth invite link"""
    logger.info('OAuth')
    if len(args) > 3:
        return False

    appinfo = await client.application_info()
    client_id = args[0] if len(args) > 0 else appinfo.id
    server_id = args[1] if len(args) > 1 else None

    msg = await client.send_message(message.channel, discord.utils.oauth_url(client_id if client_id else client.user.id,
        permissions=discord.Permissions(permissions=1848765527),
        redirect_uri=None))
    asyncio.ensure_future(message_timeout(msg, 120))

@register('invites')
async def get_invite(message,*args):
    """List active invite link for the current server"""
    active_invites = await client.invites_from(message.server)

    revoked_invites   = ['~~{0.url}: `{0.channel}` created by `{0.inviter}`~~ '.format(x) for x in active_invites if x.revoked]
    unlimited_invites = [  '{0.url}: `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age == 0 and x not in revoked_invites]
    limited_invites   = [  '{0.url}: `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age != 0 and x not in revoked_invites]

    embed = discord.Embed(title='__Invite links for {0.name}__'.format(message.server),
        color=message.author.color)
    if unlimited_invites:
        embed.add_field(name='Unlimited Invites',value='\n'.join(unlimited_invites))
    if limited_invites:
        embed.add_field(name='Temporary/Finite Invites', value='\n'.join(limited_invites))
    if revoked_invites:
        embed.add_field(name='Revoked Invites', value='\n'.join(revoked_invites))

    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('watta','<term>',rate=5,alias='define')
@register('pedant','<term>',rate=5,alias='define')
@register('define','<term>',rate=5)
async def define(message, *args):
    """Search for a wikipedia page and show summary"""
    if not args:
        return False

    term = ' '.join(args)
    search = term
    content = None
    found = False

    logger.info('Finding definition: "' + term + '"')

    if term == 'baer':
        await client.send_message(message.channel,'Definition for `baer`:\n```More bae than aforementioned article```')
        return

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
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.info(' -> Wiki page')
                try:
                    content = wikipedia.page(arts[0])
                except wikipedia.DisambiguationError as de:
                    logger.info(' -> ambiguous wiki page')
                    content = wikipedia.page(de.options[0])

        logger.info(' -> Found stuff')
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(search.title()),
                              url=content.url,
                              description=''.join([x for x in content.summary[:1000] + bool(content.summary[1000:]) * '...' if x in ALLOWED_EMBED_CHARS]),
                              color=message.author.color,
                              timestamp=message.timestamp,
                             )
        embed.set_footer(text='Wikipedia',icon_url='https://en.wikipedia.org/static/apple-touch/wikipedia.png')
        if len(content.images) > 0:
            embed.set_thumbnail(url=content.images[0])

        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))

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
                            color=message.author.color
                         )
    embed.set_thumbnail(url='https://en.wikipedia.org/static/images/project-logos/enwiki.png')
    embed.set_author(name=term)
    embed.set_footer(text='Requested: random')

    await client.send_message(message.channel, embed=embed)

@register('runescape','<term>',rate=5)
async def define(message, *args):
    """Search for a runescape wiki page and show summary"""
    if not args:
        return False

    term = ' '.join(args)
    search = term
    content = None
    found = False

    logger.info('Finding definition: "' + term + '"')

    try:
        if not found:
            arts = wikia.search('runescape',term)
            if len(arts) == 0:
                logger.info(' -> No results found')
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.info(' -> Wikia page')
                try:
                    content = wikia.page('runescape',arts[0])
                except wikia.DisambiguationError as de:
                    logger.info(' -> ambiguous wiki page')
                    content = wikia.page('runescape',de.options[0])

        logger.info(' -> Found stuff')
        embed = discord.Embed(title=''.join([x for x in content.title if x in ALLOWED_EMBED_CHARS] or 'No title found.'),
                              url=re.sub(' ','%20',content.url),
                              description='{:.1600}'.format(''.join([x for x in content.summary if x in ALLOWED_EMBED_CHARS]) or 'No description found.'),
                              color=message.author.color,
                              timestamp=message.timestamp,
                             )
        embed.set_footer(text='Runescape Wiki',icon_url='http://vignette3.wikia.nocookie.net/runescape2/images/6/64/Favicon.ico')
        if len(content.images) >= 1:
            embed.set_thumbnail(url=content.images[0])

        await client.send_message(message.channel,embed=embed)
    except AttributeError:
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(term),
                              description=''.join([x for x in content if x in ALLOWED_EMBED_CHARS]),
                              color=message.author.color,
                              timestamp=message.timestamp,)
        embed.set_footer(text='PedantBot Definitions',icon_url=client.user.avatar_url or client.user.avatar_default_url)
        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('urban',rate=3)
async def urban(message,*args):
    """Lookup a term/phrase on urban dictionary"""
    definition = None; msg = None
    definitions = urbandict.define(' '.join(args))
    if len(definitions) > 1:
        embed = discord.Embed(title="Multiple definitions for __{}__".format(' '.join(args)),color=message.author.color,timestamp=message.timestamp)
        embed.set_footer(text='Urban Dictionary',icon_url='http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png')
        for i in range(min(5,len(definitions))):
            _def = definitions[i]
            embed.add_field(name="`[{}]` **{}**".format(i,_def.get('word','none').title().replace('\n','')),value='```{:.200}```'.format(_def.get('def','no definition found')))

        msg = await client.send_message(message.channel,embed=embed)
        res = await client.wait_for_message(20,author=message.author,channel=message.channel,check=lambda m: m.content.isnumeric() and int(m.content) < len(definitions))
        if res:
            await client.delete_message(res)
            definition = definitions[int(res.content)]

    if not definition:
        definition = definitions[0]

    for i in definition:
        definition[i] = re.sub(r'/\n+/','\\n',definition[i])

    embed = discord.Embed(title=''.join([x for x in definition['word'].title() if x in ALLOWED_EMBED_CHARS]), color=message.author.color, url='http://www.urbandictionary.com/define.php?term='+re.sub(' ','%20',definition['word']),description=definition.get('def','no definition found'),timestamp=message.timestamp)
    embed.set_footer(text='Urban Dictionary',icon_url='http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png')
    if re.sub('\n','',definition['example']) != '':
        embed.add_field(name='Example',value=definition.get('example','No example found'))

    if msg:
        await client.edit_message(msg,embed=embed)
    else:
        await client.send_message(message.channel,embed=embed)

@register('imdb',rate=5,alias="ombd")
@register('omdb',rate=5)
async def imdb_search(message,*args):
    """Search OMDb for a film"""
    term = ' '.join(args).strip().lower()
    raw = urllib.request.urlopen('http://sg.media-imdb.com/suggests/{0[0]}/{0}.json'.format(term.replace(' ','%20'))).read().decode('utf8')
    result = json.loads(re.sub('imdb\${}\((.*)\)'.format(term.replace(' ','_')),'\\1',raw))

    if not 'd' in result:
        await client.send_message(message.channel,'No results for `{}`'.format(term))
        return

    movies = list(filter(lambda r: re.match('[a-z]{2}[\d]{7}',r['id']),result['d']))
    movie = None; msg = None

    if len(movies) > 1:
        embed = discord.Embed(title="Multiple results for __{}__".format(term),color=message.author.color,timestamp=message.timestamp)
        embed.set_footer(text="The Open Movie Database",icon_url="http://ia.media-imdb.com/images/G/01/imdb/images/logos/imdb_fb_logo-1730868325._CB522736557_.png")
        for i in range(min(5,len(movies))):
            _movie = movies[i]
            embed.add_field(inline=False,name="[{}] __{} - **{}** *[{}]*__".format(i,_movie.get('q','Unkown Type').title(),_movie.get('l','Unknown Title'),_movie.get('y','Unknown Year')),value='**Starring:** {:.200}'.format(_movie.get('s','cast unavailable')))

        msg = await client.send_message(message.channel,embed=embed)
        res = await client.wait_for_message(20,author=message.author,channel=message.channel,check=lambda m: m.content.isnumeric() and int(m.content) < len(movies))
        if res:
            await client.delete_message(res)
            movie = movies[int(res.content)]

    if not movie:
        movie = movies[0]

    movie = json.loads(urllib.request.urlopen('https://www.omdbapi.com/?i={}&tomatoes=true'.format(movie['id'])).read().decode('utf8'))
    for key in movie:
        if movie[key] == 'N/A' or movie[key] == '':
            movie[key] = None

    try:
        embed = discord.Embed(title="{} ({})".format(movie['Title'] or 'Unknown Title',movie['Year'] or 'Unknown Year'),description=movie['Plot'] or 'Plot Unavailable',url='http://www.imdb.com/title/{}/'.format(movie['imdbID']),color=message.author.color)
        embed.set_footer(text="The Open Movie Database",icon_url="http://ia.media-imdb.com/images/G/01/imdb/images/logos/imdb_fb_logo-1730868325._CB522736557_.png")
        if movie['Poster']:
            embed.set_image(url=movie['Poster'])
        if 'Genre' in movie:
            embed.add_field(name="Genres",value=movie['Genre'].replace(', ','\n'))
        if 'Actors' in movie:
            embed.add_field(name="Cast",value="{}".format(movie['Actors'].replace(', ','\n')))
        ratings = ''
        for service in [('Metacritic','Metascore','%'),('Rotten Tomatoes','tomatoMeter','%'),('IMDb','imdbRating','/10')]:
            if service[1] in movie and movie[service[1]]:
                ratings += '{}: `{}{}`\n'.format(service[0],str(movie[service[1]]),service[2])
        if ratings:
            embed.add_field(name="Reviews",value=ratings)
    except:
        pass

    if 'embed' in locals() and embed:
        if msg:
            await client.edit_message(msg,embed=embed)
        else:
            await client.edit_message(msg,embed=embed)


@register('shrug')
async def shrug(message,*args):
    """Send a shrug: mobile polyfill"""
    embed = discord.Embed(title=message.author.name+' sent something:',description='¯\_(ツ)_/¯',color=message.author.color,timestamp=datetime.now())
    await client.send_message(message.channel,embed=embed)

@register('wrong')
async def wrong(message,*args):
    """Send the WRONG! image"""
    embed = discord.Embed(title='THIS IS WRONG!',color=message.author.color)
    embed.set_image(url='http://i.imgur.com/CMBlDO2.png')

    await client.send_message(message.channel,embed=embed)

@register('notwrong')
async def wrong(message,*args):
    """Send CORRECT! image"""
    embed = discord.Embed(title='THIS IS NOT WRONG!',color=message.author.color)
    embed.set_image(url='https://i.imgur.com/nibZI2D.png')

    await client.send_message(message.channel,embed=embed)

@register('thyme')
async def thyme(message,*args):
    """Send some thyme to your friends"""
    embed = discord.Embed(title='Thyme',timestamp=message.edited_timestamp or message.timestamp,color=message.author.color)
    embed.set_image(url='http://shwam3.altervista.org/thyme/image.jpg')
    embed.set_footer(text='{} loves you long thyme'.format(message.author.nick or message.author.name))

    await client.send_message(message.channel,embed=embed)

@register('grid','<width> <height>',rate=1)
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

@register('emojis','[server ID]',alias='showemoji')
@register('showemoji','[server ID]')
async def showemoji(message,*args):
    """Displays all available custom emoji in this server"""
    server = message.server
    if len(args) > 0:
        try:
            server = client.get_server(args[0])
            if not (isowner(message.author) or server.get_member(message.author.id)):
                server = message.server
            emojis = ' '.join(['<:{0.name}:{0.id}>'.format(emoji) if server==message.server else '`<:{0.name}:{0.id}>`'.format(emoji) for emoji in server.emojis])
        except:
            await client.send_message(message.channel,message.author.mention + ' You provided an invalid server ID.')
            return

    if not 'emojis' in locals():
        emojis = ' '.join(['<:{0.name}:{0.id}>'.format(emoji) if server==message.server else '`<:{0.name}:{0.id}>`'.format(emoji) for emoji in server.emojis])
        
    await client.send_message(message.channel,'Emoji in __{}__\n'.format(server.name) + emojis)

@register('bigly','<custom server emoji>',alias='bigger')
@register('bigger','<custom server emoji>')
async def bigger(message,*args):
    """Display a larger image of the specified emoji"""
    logger.info('Debug emoji:')

    if len(args) < 1:
        return False

    logger.info(args)
    id = re.findall(r'<:[^:]+:([^:>]+)>',args[0])[0]

    useEmoji = None
    for emoji in client.get_all_emojis():
        if emoji.id == id:
            useEmoji = emoji
                
    emoji = useEmoji
    if useEmoji != None:
        logger.info(' -> id: ' + emoji.id)
        logger.info(' -> url: ' + emoji.url)

        embed = discord.Embed(title=emoji.name,color=message.author.color)
        embed.set_image(url=emoji.url)
        embed.set_footer(text='{emoji.id}'.format(emoji=emoji),icon_url=emoji.server.icon_url or client.user.avatar_url)

        await client.send_message(message.channel,embed=embed)
    else:
        msg = await client.send_message(message.channel,MESG.get('emoji_unsupported','Unsupported emoji.').format(message.server.name))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('avatar','@<mention user>',rate=1)
async def avatar(message,*args):
    """Display a user's avatar"""
    if len(message.mentions) < 1:
        return False

    user = message.mentions[0]
    name = user.nick or user.name
    avatar = user.avatar_url or user.default_avatar_url
    avatar = re.sub('https:\/\/discordapp.com\/api\/users\/([^\/]+)\/avatars\/([^\/]+)\.jpg','https://images.discordapp.net/avatars/\g<1>/\g<2>.gif',avatar)

    embed = discord.Embed(title=name,type='rich',colour=message.author.color,url=avatar)
    embed.set_image(url=avatar)
    embed.set_footer(text='ID: #{}'.format(user.id))
    await client.send_message(message.channel,embed=embed)

@register('serveravatar', rate=5)
async def serveravatar(message,*args):
    """Show the avatar for the current server"""
    server = message.server
    avatar = server.icon_url
    embed = discord.Embed(title='Image for {server.name}'.format(server=server), color=message.author.color)
    embed.set_image(url=avatar)

    await client.send_message(message.channel,embed=embed)

@register('elijah')
async def elijah(message,*args):
    """elijah wood"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'elijah.gif')

@register('woop')
async def whooup(message, *args):
    """fingers or something"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'woop.gif')

@register('ree','[url true|false]',rate=5)
async def ree(message, *args):
    """reeeeeeeeeeeeeeeeeeeeeee"""
    if len(args) == 1:
        if args[0].lower() == 'true':
            await client.send_message(message.channel, 'http://i.imgur.com/y4d4iAO.gif')
    else:
        await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'ree.gif')

@register('aesthetic')
async def aesthetic(message,*args):
    """A E S T H E T I C"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'aesthetic.png')

@register('nice')
async def nice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'nice.png')

@register('ncie')
async def ncie(message,*args):
    """:point_right: :point_right: ncie"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'ncie.png')

@register('ncei')
async def nice(message,*args):
    """minkle is bad"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'ncei.png')

@register('nicenice')
async def nicenice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'nicenice.png')

@register('nicenicenice')
async def nicenicenice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'nicenicenice.gif')

@register('oh')
async def oh(message,*args):
    """*oh*"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'oh.png')

@register('java')
async def java(message,*args):
    """how many layers of abstraction are you on"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'java.png')

@register('g2a')
async def g2a_is_bad(message,*args):
    """g2a is bad kys"""
    await client.send_message(message.channel,"https://www.reddit.com/r/pcmasterrace/comments/5rm2f7/g2a_has_flaw_in_their_system_pointed_out_to_them/")

@register('cummies')
async def sex(message,*args):
    """cummies"""
    await client.send_message(message.channel,'https://open.spotify.com/album/1HDC77tWM1eN43XXLG7eZq')

@register('eww')
async def sex(message,*args):
    """terrible"""
    await client.send_file(message.channel,"eww.png")

@register('bbc')
async def bbc(message,*args):
    """oh fuck what now"""
    await client.send_file(message.channel,"bbc.png")

@register('doe')
async def doe(message,*args):
    """what you want doe"""
    await client.send_file(message.channel,"doe.png")

@register('say','<words>',typing=False)
async def tts(message,*args):
    """tts my dude"""
    if len(args) < 1:
        return False
    msg = ' '.join(args)
    gtts.gTTS(msg).save("tts.mp3")

    await join_voice(message)
    if client.voice:
        player = client.voice.create_ffmpeg_player('tts.mp3', after=lambda: disconn(client))
        player.volume = 0.5
        player.start()

@register('nut')
async def doe(message,*args):
    """nut"""
    await client.send_message(message.channel,"╲⎝⧹╲⎝⧹ :regional_indicator_n: :regional_indicator_u: :regional_indicator_t:  ⧸⎠╱⧸⎠╱")

@register('python')
async def python(message,*args):
    """python"""
    await client.send_file(message.channel,"python.png")

@register('shawn',alias='rain')
@register('rain')
async def rain(message,*args):
    """Heavy Rain"""
    shawns = ['http://ci.memecdn.com/8731766.jpg','https://i.ytimg.com/vi/rFhyZG-l5qY/maxresdefault.jpg','http://i.imgur.com/qQhNH8e.jpg']
    await client.send_message(message.channel,shawns[randrange(len(shawns))])

shawns = glob.glob("shawn*.mp3")
@register('x',typing=False)
async def press_x(message,*args):
    """Press (x) to SHAWN"""
    await join_voice(message)
    if client.voice:
        player = client.voice.create_ffmpeg_player(shawns[randrange(len(shawns))], after=lambda: disconn(client))
        player.volume = 0.5
        player.start()

@register('i\'m','<name>',alias='dad')
@register('im','<name>',alias='dad')
@register('iam','<name>',alias='dad')
@register('dad','<name>')
async def dad_joke(message,*args):
    """dad jokes my dude"""
    await client.send_message(message.channel,"Hi {:.20}, I am Dad. Nice to meet you.".format(' '.join(args)))

def get(url):
    return urllib.request.urlopen(urllib.request.Request(url,data=None,headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'}))

@register('needsmorejpeg','[JPEG quality 1-100]',rate=10)
async def jpeg(message,*args):
    """adds more jpeg to the last image the app can find"""
    messages = client.messages; messages.reverse()
    def image_embed(embed):
        return embed.get('type','') == 'image'
    def filtered_messages(msg):
        return msg.author != client.user
    quality = 1
    if len(args) > 0:
        if args[0].isnumeric():
            quality = int(args[0])
    if not 1 < quality < 100:
        quality = 1
    if True:
        #for msg in filter(filtered_messages,messages):
        async for msg in client.logs_from(message.channel,limit=50,reverse=False):
            try:
                images = list(filter(image_embed,msg.embeds))
                if filtered_messages(msg) and (len(msg.attachments) > 0 or len(images) > 0):
                    url = images[0].get('url','') if len(images) > 0 else msg.attachments[0]['proxy_url']
                    if (int(requests.head(url,headers={'Accept-Encoding': 'identity'}).headers['content-length']) / 1024 / 1024) >= 8:
                        await client.send_message(message.channel,'Image is too large.')
                        return
                    attachment = get(url)
                    content_type = attachment.headers.get_content_type()
                    if 'image' in content_type:
                        img_file = io.BytesIO(attachment.read())
                        img = Image.open(img_file)
                        outfile = os.path.join('tmp_{}.jpeg'.format(msg.id))
                        img.save(outfile,"JPEG",quality=quality)
                        await client.send_file(message.channel,'tmp_{}.jpeg'.format(msg.id))
                        return
            except:
                pass
    else:
        await client.send_m(message.channel,'No essages found (I can only read messages sent while I am connected.)')

@register('image','<text>',rate=5)
async def image_gen(message,*args):
    """draw image with words"""
    if len(args) < 1:
        return False

    input_text = ' '.join(args)
    image = generate_text_image(input_text,str(message.author.color))
    image.save('test.png','PNG')
    await client.send_file(message.channel,'test.png',content="**{}** sent this".format(message.author))

@register('bren','<url to image>',rate=10)
async def bren_think(message,*args):
    """creates an image of brendaniel thinking about things"""

    def image_embed(embed):
        return embed.get('type','') == 'image'
    def filtered_messages(msg):
        return msg.author != client.user

    if len(args) < 1:
        return False

    fg = Image.open(get(args[0]))
    bg = Image.open("bren.png")

    w,h = fg.size
    ratio = round(w/h)
    MAX = 180
    #w2,h2 = MAX,MAX*ratio
    w2,h2 = scale(w,h)

    fg2 = fg.resize((min(w2,MAX),min(MAX,h2)))
    draw = ImageDraw.Draw(bg)

    bg.paste(fg2,(120+round((MAX-w2)/2),110+round((MAX-h2)/2)))
    bg.save('bren_2.png','PNG')
    await client.send_file(message.channel,'bren_2.png',filename="bren thinking.png")

@register('rotato','<image url> [rotato amount]',rate=5)
async def rotato(message,*args):
    """rotate image"""
    if len(args) < 1:
        return False

    if len(args) > 1 and args[1].isnumeric():
        rotato = int(args[1])
    else:
        rotato = 180

    fg = Image.open(get(args[0]))
    fg.rotate(rotato).save("rotato.png","PNG")

    await client.send_file(message.channel,"rotato.png",filename="rotato.png")

@register('nicememe',owner=True,rate=5,typing=False)
async def nicememe(message,*args):
    """say nice meme"""
    try:
        client.voice = await client.join_voice_channel(message.server.get_channel(args[0]))
    except:
        pass

    if client.voice:
        player = client.voice.create_ffmpeg_player('/home/mark/Documents/pedant/nicememe.mp3', after=lambda: disconn(client))
        player.volume = 0.5
        player.start()

@register('s',owner=True,typing=False,alias='summon')
@register('summon',owner=True,typing=False)
async def summon(message,*args):
    """summon"""
    if not client.voice:
        for chan in message.server.channels:
            if chan.type == discord.ChannelType.voice and message.author in chan.voice_members:
                client.voice = await client.join_voice_channel(chan)
                break
        else:
            client.voice = await client.join_voice_channel(sorted([x for x in message.server.channels if x.type == discord.ChannelType.voice], key=lambda x: x.position)[0])

@register('d',owner=True,typing=False,alias='disconnect')
@register('disconnect',owner=True,typing=False)
async def disconnect(message,*args):
    """disconnect"""
    if client.voice:
        await client.voice.disconnect()
        client.voice = None

def disconn(clnt):
    if clnt.voice and CONF.get('voice_disconnect',True):
        asyncio.run_coroutine_threadsafe(clnt.voice.disconnect(), clnt.loop).result()
        clnt.voice = None

@register('play','<audio track>',typing=False)
async def play_audio(message,*args):
    """play audio in voice channel"""
    if len(args) < 1:
        files = glob.glob('sounds/*.mp3')
        embed = discord.Embed(title="Available Audio Files",description="```\n{}```".format('\n'.join(sorted([x.replace('sounds/','').replace('.mp3','') for x in files]))),color=message.author.color)
        await client.send_message(message.channel,embed=embed)
        return

    if not os.path.isfile(CONF.get('dir_pref','/home/shwam3/') + 'sounds/{}.mp3'.format(args[0])):
        await client.send_message(message.channel,'Audio track `{}` not found.'.format(args[0]))
        return

    track = taglib.File('sounds/{}.mp3'.format(args[0]))
    if track.length > 10 and not (isadmin(message.author) or isowner(message.author)):
        await client.send_message(message.channel,'Fuck off that\'s too long')
        return

    await join_voice(message)
    if client.voice:
        player = client.voice.create_ffmpeg_player(CONF.get('dir_pref','/home/shwam3/') + 'sounds/{}.mp3'.format(args[0]), after=lambda: disconn(client))
        player.volume = 0.75
        player.start()

@register('feshpince','<part #>',rate=5)
async def feshpince(message,*args):
    """Get feshpince up in this"""
    links = ['https://youtu.be/HeIkk6Yo0s8','https://youtu.be/Drqj67ImtxI']
    try:
        url = links[int(args[0]) - 1]
    except:
        url = links[0]

    await client.send_message(message.channel,url)

@register('lmgtfy',rate=5)
async def lmfgty(message,*args):
    """let me Google that for you"""
    path = urllib.parse.quote_plus(' '.join(args))
    await client.send_message(message.channel,'http://lmgtfy.com/?q='+path)

@register('skinnn','',rate=1,alias='skin')
@register('skinn','',rate=1,alias='skin')
@register('skin','',rate=1)
async def skinn_link(message,*args):
    logger.info('skinnn')
    await client.send_message(message.channel, 'https://twitter.com/4eyes_/status/805851294292381696')

@register('this')
async def oh(message,*args):
    """^"""
    await client.send_file(message.channel,CONF.get('dir_pref','/home/shwam3') + 'this.png')

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

    try:
        id = args[0]
    except:
        id = ''

    users = {'kush':'94897568776982528',
             'david b':'240904516269113344',
             'beard matt':'143529460744978432',
             'dawid':'184736498824773634',
             'jaime':'233244375285628928',
             'oliver barnwell':'188672208233693184',
             'orane':'100816656372097024',
             'william':'191332830519885824',
             'shwam3':'154543065594462208',
             'themork':'154542529591771136',
             'wensleydale':'154565902828830720',
             'minkle':'130527313673584640',
             'chris':'192671450388234240'
             }

    cnx = MySQLdb.connect(user='readonly', db='my_themork')
    cursor = cnx.cursor()

    query = ("SELECT * FROM `q2` WHERE `id`='{}' ORDER BY RAND() LIMIT 1".format(id))
    cursor.execute(query)

    if cursor.rowcount < 1:
        query = ("SELECT * FROM `q2` ORDER BY RAND() LIMIT 1")
        cursor.execute(query)

    for (id,quote,author,date,_,_) in cursor:
        if author.lower() in users:
            try:
                user = message.server.get_member(users[author.lower()])
                name = user.name
            except:
                user = await client.get_user_info(users[author.lower()])

        embed = discord.Embed(title='TheMork Quotes',
                                description=quote,
                                type='rich',
                                url='https://themork.co.uk/quotes/?q='+ str(id),
                                timestamp=datetime(*date.timetuple()[:-4]),
                                color=message.author.color
        )
        embed.set_thumbnail(url='https://themork.co.uk/assets/main.png')
        try:
            embed.set_author(name=user.display_name or user.name,icon_url=user.avatar_url or user.default_avatar_url)
        except:
            embed.set_author(name=author)
        embed.set_footer(text='Quote ID: #' + str(id))

        await client.send_message(message.channel,embed=embed)
        break

    cursor.close()
    cnx.close()

@register('cal')
async def calendar(message,*args):
    """Displays a formatted calendar"""
    today = datetime.now()
    embed = discord.Embed(title='Calender for {0.month}/{0.year}'.format(today),
        description='```\n{0}\n```'.format(cal.month(today.year,today.month)),
        color=message.author.color)
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))


@register('id','[DiscordTag#0000] [server ID]',owner=True)
async def get_user_id(message,*args):
    """get User ID by DiscordTag#0000"""
    if len(args) == 0:
        id = message.author.id
    if len(args) == 1:
        id = message.server.get_member_named(args[0]).id
    else:
        id = client.get_server(args[1]).get_member_named(args[0]).id

    await client.send_message(message.channel, "{}'s ID is `{}`".format(args[0] if len(args) > 0 else message.author, id))

@register('servers',owner=True)
async def connected_servers(message,*args):
    """Lists servers currently connected"""
    servers = ['•   **{server.name}** (`{server.id}`)'.format(server=x) for x in client.servers]

    embed = discord.Embed(title='Servers {0} is connected to.'.format(client.user),
                          colour=message.author.color,
                          description='\n'.join(servers))
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('channels',owner=True)
async def connected_channels(message,*args):
    """Displays a list of channels and servers currently available"""
    servers = [c for c in client.servers]

    currentServer = servers[0]
    currentIndex = servers.index(currentServer)

    embed = discord.Embed(title='Channels {user.name} is conected to. ({0})'.format(len(servers),user=client.user),
                          colour=message.author.color,
                          description='\n'.join([('•   **{channel.name}** (`{channel.id}`)'+('"{channel.topic}"' if x.topic and x.topic != "None" else '')).format(channel=x) for x in currentServer.channels if x.type == discord.ChannelType.text])
                         )
    embed.set_footer(text=('<- {} | '.format(servers[currentIndex -1].name) if currentIndex > 0 else '') + '{}'.format(currentServer.name) + (' |  {} ->'.format(servers[currentIndex + 1].name) if currentIndex < len(servers)-1 else ''))

    msg = await client.send_message(message.channel, embed=embed)
    await client.add_reaction(msg,'👈')
    await client.add_reaction(msg,'👉')
    await client.add_reaction(msg,'🚫')

    def check(reation,user):
        return user != client.user

    listening = True
    while listening:
        res = await client.wait_for_reaction(['👈','👉','🚫'],message=msg,check=check,timeout=30)
        if res:
            emoji = res.reaction.emoji
            await client.remove_reaction(msg,emoji,res.user)
            if emoji == '🚫':
                listening = False
                await client.delete_message(msg)
                return
            elif emoji == '👈':
                if currentIndex > 0:
                    currentIndex -= 1
                    currentServer = servers[currentIndex]
            elif emoji == '👉':
                if currentIndex < len(servers)-1:
                    currentIndex += 1
                    currentServer = servers[currentIndex]

            embed.title = "Channels in {server.name}".format(server=currentServer)
            embed.description = '\n'.join(['•   **{channel.name}** (`{channel.id}`) "{channel.topic}"'.format(channel=x) for x in currentServer.channels if x.type == discord.ChannelType.text])
            embed.set_footer(text=('Prev: {} | '.format(servers[currentIndex -1].name) if currentIndex > 0 else '') + 'Current: {}'.format(currentServer.name) + (' |  Next: {}'.format(servers[currentIndex + 1].name) if currentIndex < len(servers)-1 else ''))
            await client.edit_message(msg, embed=embed)
        else:
            listening = False
    try:
        await client.clear_reactions(msg)
    except:
        pass

@register('ranks',owner=True)
async def server_ranks(message,*args):
    """Displays a list of ranks in the server"""
    embed = discord.Embed(title='Ranks for {server.name}.'.format(server=message.server), colour=message.author.color)
    for role in message.server.roles:
        if not role.is_everyone:
            members = ['•   **{user.name}** (`{user.id}`)'.format(user=x) for x in message.server.members if role in x.roles]
            if len(members) > 0:
                embed.add_field(name='__{role.name}__ ({role.colour} `{role.id}`)'.format(role=role), value='\n'.join(members), inline=False)
    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('age',rate=10)
async def age(message,*args):
    """Get user's Discord age"""
    users = []
    if len(args) < 1:
        users = message.server.members
    else:
        for arg in args:
            if arg == 'me':
                users.append(message.author)
            else:
                users.append(await client.get_user_info(arg))

    for mention in message.mentions:
        users.append(mention)

    def age(user=discord.User()):
        return discord.utils.snowflake_time(user.id)

    string = ''
    users = sorted(users,key=age)
    for n,user in enumerate(sorted(users,key=age)):
        user.name = re.sub(r'([*_])',r'\\\1',user.name)
        string += '{n:>2}.  **{user}**:`{user.id}` joined on `{date}`\n'.format(n=n+1,user=user,date=age(user).strftime('%d %B %Y @ %I:%M%p'))

    embed = discord.Embed(title="Age of users in {server.name}".format(server=message.server),
        color=message.author.color,
        description=string)

    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('purge','[message limit]',rate=5)
async def purge(message,*args):
    """delete all messages"""
    deleted = []
    limit = 500
    if len(args) > 0 and args[0].isnumeric():
        limit = int(args[0])
    if isadmin(message.author) and message.server.id != '154543502313652224':
        try:
            deleted = await client.purge_from(message.channel,limit=limit)
        except:
            pass
        await client.send_message(message.channel,'Purged {} messages from {}.'.format(len(deleted),message.channel.mention))
    else:
        await client.send_message(message.channel,"Fuck off with that, you don't have permission to purge {}".format(message.channel.mention))

@register('clean','[number of messages]',owner=True,rate=10,typing=False)
async def clean(message,*args):
    """delete bot messages"""
    limit = 10
    if len(args) > 0:
        if args[0].isnumeric():
            limit = int(args[0])
    await client.purge_from(message.channel,check=lambda m: m.author == client.user,limit=limit)

@register('abuse','<channel> <content>',owner=True,alias='sendmsg')
@register('sendmsg','<channel> <content>',owner=True)
async def abuse(message,*args):
    """Harness the power of Discord"""
    if len(args) < 2:
        return False

    channel = args[0]
    if channel == 'here':
        channel = message.channel.id
    msg = ' '.join(args[1::])

    try:
        if channel == 'all':
            for chan in client.get_all_channels():
                await client.send_message(client.get_channel(chan),msg)
        else:
            await client.send_message(client.get_channel(channel),msg)
    except Exception as e:
        msg = await client.send_message(message.channel,MESG.get('abuse_error','Error.'))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('perms',owner=True)
async def perms(message,*args):
    """List permissions available to this  bot"""
    member = message.server.get_member(message.mentions[0].id if len(message.mentions) > 0 else client.user.id)
    perms = message.channel.permissions_for(member)
    perms_list = [' '.join(w.capitalize() for w in x[0].split('_')).replace('Tts','TTS') for x in perms if x[1]]

    msg = await client.send_message(message.channel, "**Perms for {user.name} in {server.name}:** ({1.value})\n```{0}```".format('\n'.join(perms_list),perms,user=member,server=message.server))
    asyncio.ensure_future(message_timeout(msg, 120))

@register('hole','@<mention users>',admin=True)
async def hole(message,*args):
    """move user to the hole"""
    hole = [x for x in message.server.channels if 'hole' in x.name.lower() and x.type == discord.ChannelType.voice]
    if len(hole) < 1:
        await client.send_message(message.channel,"There is no hole channel.")
        return
    elif len(hole) > 1:
        prompt =await client.send_message(message.channel,"There are multiple hole channels, please select one. ```{}```".format('\n'.join([str(i) + " " + hole[i].name for i in range(len(hole))])))
        res = await client.wait_for_message(author=message.author,channel=message.channel,check=lambda m: m.content.isnumeric() and 0 < int(m.content) < len(hole))
        channel = hole[int(res.content)]
        try:
            await client.delete_message(res)
            await client.delete_message(prompt)
        except: pass
    else:
        channel = hole[0]

    for user in message.mentions:
        channels = [x for x in message.server.channels if x.type == discord.ChannelType.voice and user in x.voice_members]
        if len(channels) < 1:
            await client.send_message(message.channel,"User is not in a voice channel.")
            return
        await client.move_member(user,channel)

@register('kick','@<mention users>',owner=True)
async def kick(message,*args):
    """Kicks the specified user from the server"""
    if len(message.mentions) < 1:
        return False

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    if not message.channel.permissions_for(message.server.get_member(client.user.id)).kick_members:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to kick users.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    members = []

    if not message.channel.is_private and message.channel.permissions_for(message.author).kick_members:
        for member in message.mentions:
            if member != message.author:
                try:
                    await client.kick(member)
                    members.append(member.name)
                except:
                    pass
            else:
                msg = await client.send_message(message.channel, message.author.mention + ', You should not kick yourself from a channel, use the leave button instead.')
                asyncio.ensure_future(message_timeout(msg, 40))
    else:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to kick users, or this is a private message channel.')
        asyncio.ensure_future(message_timeout(msg, 40))

    msg = await client.send_message(message.channel,'Successfully kicked user(s): `{}`'.format('`, `'.join(members)))
    asyncio.ensure_future(message_timeout(msg, 60))

@register('ban','@<mention users>',owner=True)
async def ban(message,*args):
    """Bans the specified user from the server"""
    if len(message.mentions) < 1:
        return False

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    if not message.channel.permissions_for(message.server.get_member(client.user.id)).ban_members:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to ban users.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    members = []

    if message.channel.permissions_for(message.author).ban_members:
        for member in message.mentions:
            if member != message.author:
                try:
                    await client.ban(member)
                    members.append(member.name)
                except:
                    pass
            else:
                msg = await client.send_message(message.channel, message.author.mention + ', You should not ban yourself from a channel, use the leave button instead.')
                asyncio.ensure_future(message_timeout(msg, 40))
    else:
        msg = await client.send_message(message.channel, message.author.mention + ', I do not have permission to ban users, or this is a private message channel.')
        asyncio.ensure_future(message_timeout(msg, 40))

    msg = await client.send_message(message.channel,'Successfully banned user(s): `{}`'.format('`, `'.join(members)))
    asyncio.ensure_future(message_timeout(msg, 30))

@register('bans',alias='bannedusers')
@register('bannedusers')
async def banned_users(message,*args):
    """List users that have been banned from this server"""
    bans = await client.get_bans(message.server)

    if message.channel.is_private:
        msg = await client.send_message(message.channel,'Users cannot be kicked/banned from private channels.')
        asyncio.ensure_future(message_timeout(msg, 40))
        return

    str = ''
    for user in bans:
        str += "• {0.mention} (`{0.name}#{0.discriminator}`): [`{0.id}`]\n".format(user)

    embed = discord.Embed(title="Banned users in {0.name}".format(message.server),color=message.author.color,description=str)
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 60))

@register('fkoff',owner=True,alias='restart',typing=False)
@register('restart',owner=True,typing=False)
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

@register('calc','<expression>',rate=1,alias='maths')
@register('maths','<expression>',rate=1)
async def do_calc(message,*args):
    """Perform mathematical calculation: numbers and symbols (+-*/) allowed only"""
    logger.info('Calc')

    if len(args) < 1:
        return False

    maths = ''.join(args)

    if (re.findall('[^0-9\(\)\/\*\+-\.]+',maths) != []):
        await client.send_message(message.channel, MESG.get('calc_illegal','Illegal chars in {0}').format(maths))

    else:
        logger.info(' -> ' + str(maths))
        try:
            ans = calculate(maths)
            await client.send_message(message.channel,'`{} = {}`'.format(maths,"The Universe, Life and Everything" if ans == 42 else ans))
        except Exception as e:
            logger.exception(e)
            await client.send_message(message.channel, MESG.get('maths_illegal','Error in {0}').format(maths))

@register('skinnn','',rate=1,alias='skin')
@register('skinn','',rate=1,alias='skin')
@register('skin','',rate=1)
async def skinn_link(message,*args):
    logger.info('skinnn')

    await client.send_message(message.channel, 'https://twitter.com/4eyes_/status/805851294292381696')

"""Utility functions"""
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

def isowner(user=discord.User()):
    """returns True if the user is in the list of sudoers"""
    return user.id in CONF.get("owners",[])

def isadmin(member):
    """returns True if the user is in the list of sudoers, or is an admin in the current server"""
    return member.server_permissions.administrator

def has_perm(permissions=discord.Permissions(),required=[]):
    """returns True if the supplied permissions contains the required"""
    if len(required) == 0: return True
    if type(required) == type(''): required = required.split(',')

    for permission in required:
        try:
            if not (permissions.__getattribute__(permission) or permissions.administrator): return False
        except:
            return False
    return True

async def message_timeout(message,timeout):
    """Deletes the specified message after the allotted time has passed"""
    if timeout > 0:
        await asyncio.sleep(timeout)

    await client.delete_message(message)

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

        #await client.send_message(client.get_channel(reminder['channel_id']), reminder['user_mention'] + ': ' + reminder['message'])
        try:
            chan = client.get_channel(reminder['channel_id'])
            user = chan.server.get_member(re.findall('<@!?([0-9]+)>',reminder['user_mention'])[0])
        except Exception as e:
            user = discord.User()
            user.name = "Unknown User"

        d = datetime.fromtimestamp(reminder['time'])
        embed = discord.Embed(title="Reminder for {}".format(d.strftime('%I:%M%p GMT+00')),description=reminder['message'],timestamp=d,color=user.color)
        embed.set_footer(text="PedantBot Reminders",icon_url=client.user.avatar_url or client.user.default_avatar_url)
        embed.set_author(name=user.nick or user.name,icon_url=user.avatar_url or user.default_avatar_url)
        await client.send_message(client.get_channel(reminder['channel_id']),reminder['user_mention'],embed=embed)
    except asyncio.CancelledError as e:
        cancel_ex = e
        reminder = get_reminder(invoke_time)
        if reminder['cancelled']:
            logger.info(' -> reminder ' + str(invoke_time) + ' cancelled')
            await client.send_message(client.get_channel(reminder['channel_id']), 'Reminder for '+reminder['user_name']+' in '+str(reminder['time']-int(time.time()))+' secs cancelled')
        else:
            logger.info(' -> reminder ' + str(invoke_time) + ' removed')
    except Exception as e:
        logger.exception(e)

    if reminder['cancelled']:
        reminders.remove(reminder)

    save_reminders()

    if cancel_ex:
        raise cancel_ex

async def join_voice(message):
    """join the nearest voice channel"""
    if not client.voice:
        for chan in message.server.channels:
            if chan.type == discord.ChannelType.voice and message.author in chan.voice_members:
                client.voice = await client.join_voice_channel(chan)
                break
        else:
            client.voice = await client.join_voice_channel(sorted([x for x in message.server.channels if x.type == discord.ChannelType.voice], key=lambda x: x.position)[0])
    return

def generate_text_image(input_text="",colour='#ffffff'):
    """returns Image with text in it"""
    if '\n' in input_text:
        wrap_text = input_text.splitlines()
    else:
        wrap_text = textwrap.wrap(input_text, width=30)
    current_h, pad = 10, 10
    colour = colour.replace('#','')

    MAX_W, MAX_H = 200, 200
    im = Image.new('RGBA', (MAX_W, MAX_H), (0, 0, 0, 255))
    draw = ImageDraw.Draw(im)
    font = ImageFont.truetype('FreeMono.ttf', 18)

    MAX_W = sorted([draw.textsize(x, font=font)[0] for x in wrap_text],key=lambda w: -w)[0] + pad
    MAX_H = (draw.textsize(wrap_text[0], font=font)[1]) * len(wrap_text) + 2*pad
    im = Image.new('RGB',(MAX_W+20, MAX_H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    def text_outline(draw,text="",x=0,y=0,fill="white",stroke="black",thickness=1):
        """draw text with stroke"""
        coords = [(x+thickness,y),(x-thickness,y),(x,y+thickness),(x,y-thickness)]
        for loc in coords:
            draw.text(loc,text,stroke,font)
        draw.text((x,y),text,fill,font)

    for line in wrap_text:
        w, h = draw.textsize(line, font=font)
        draw.text(((MAX_W - w + pad) / 2, current_h), line, font=font,fill=struct.unpack('BBB',bytes.fromhex(colour)))
        current_h += h

    return im

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
        #service = build('translate', 'v2', developerKey=CONF.get('gapi_key',''))
        client.run(token, bot=True)
        logging.shutdown()
    except Exception as e:
        logging.error(e)
