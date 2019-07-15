#!/usr/bin/env python3

from datetime import date
from datetime import datetime,timedelta
from dateutil.parser import parse
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
from random import randint,randrange,random
import glob
import io
from PIL import Image,ImageDraw,ImageFont
import textwrap
import struct
from gtts import gTTS
import requests
import customlogging
import hashlib
import html
from emoji import UNICODE_EMOJI

"""Dependencies"""
import discord
import taglib
import morkpy.graph as graph
from morkpy.postfix import calculate
from morkpy.scale import scale
from parsetime import parse as parse_time
import pyspeedtest
import MySQLdb
import wikipedia, wikia
import urbandictionary as ud
import aioredis

"""Initialisation"""
from pedant_config import CONF,SQL,MESG
SHARD_ID = int(os.environ.get('SHARD_ID',0))
SHARD_COUNT = int(os.environ.get('SHARD_COUNT',1))
last_message_time = {}
reminders = []
exceptions = [IndexError, KeyError, ValueError]
ALLOWED_EMBED_CHARS = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~'
client = discord.Client(shard_id=SHARD_ID,shard_count=SHARD_COUNT)
client.redis = None
GIPHY_API_KEY = "Kuyk7VmxxSw4Hu5K18RHY8Zj0dlnt8c7"

database = lambda: MySQLdb.connect(user='pedant', password='7XlMqXHCLfGomDHu', db='pedant')
pedant_db = database()

async def add_reaction(message, emoji):
    logger.info("Adding reaction {} to message: {}".format(repr(emoji), repr(message.id)))

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
    logger   = logging.getLogger('pedantbot')
    permlog  = logging.getLogger('sudo')
    auditlog = logging.getLogger('audit-log')
except Exception as e:
    print(e)


"""Respond to events"""

@client.event
async def on_error(e, *args, **kwargs):
    """log client errors"""
    logger.critical("Error occurred: '{}'".format(e))
    logger.critical('-- ' + '\n-- '.join(args))
    logger.critical('-- ' + '\n-- '.join(['{}:{}'.format(k,v) for k,v in kwargs.items()]))
    raise

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

        logger.info(' -> set ' + str(len(reminders)) + ' reminders')
        save_reminders()
    except Exception as e:
        logger.exception(e)

    try:
        client.users = set()
        for server in client.servers:
            for user in server.members:
                client.users.add( (user.id,str(user)) )
    except Exception as e:
        logger.exception(e)

    cursor = pedant_db.cursor()
    for server in client.servers:
        try: cursor.execute("INSERT IGNORE INTO `connected_servers` (`server_id`) VALUES (%s) ON DUPLICATE KEY UPDATE `server_id`=%s",(server.id,server.id))
        except: pass

    pedant_db.commit()
    cursor.close()

    client.redis = await aioredis.create_redis(('localhost',6379), encoding="utf8")
    asyncio.ensure_future(store_game('154698639812460544','154542529591771136'))
    asyncio.ensure_future(store_game('154698639812460544','154543065594462208'))
    asyncio.ensure_future(update_status(client))

    try:
       await client.redis.set('pedant.stats:servers', len(client.servers))
    except Exception as e:
       logger.warning('Could not update stats.')
       logger.exception(e)

    #client._send_message = client.send_message
    #client.send_message = send_message

async def send_message(destination, content=None, *, tts=False, embed=None):
    dest = destination
    if isinstance(dest, discord.Channel):
        dest = dest.server
    if isinstance(dest, discord.PrivateChannel):
        dest = dest.name or dest.user

    text = content or embed and (embed.title or embed.description) or ""
    if text:
        logger.debug("Me@{} << {}".format(
            dest,
            text[:100]
        ))

    msg = await client._send_message(destination, content, tts=tts, embed=embed)

    try:
        await client.redis.incr('pedant.stats:messages_sent')
    except Exception as e:
        logger.info("Could not update stats.")
        logger.exception(e)

    return msg

def logMessage(message):
    try:
        embeds = []
        for embed in message.embeds:
            em = "Embed"
            if embed.get('title'): em += " title=" + repr(embed.get('title'))
            if embed.get('description'): em += " desc=" + repr(embed.get('description'))

            embeds.append(em)

        logmsg = "{}#{}@{}: {}".format(message.server, message.channel, message.author, repr(message.clean_content))
        if embeds:
            logmsg += " embeds=[{}]".format(','.join(embeds))

        logger.info(logmsg)
    except Exception as e:
        pass


"""Respond to messages"""
@client.event
async def on_message(message):
    await client.wait_until_ready()

    if message.author == client.user:
        logMessage(message)

    try:
        if message.author.bot:
            return
        if message.author.id == client.user.id:
            return
        if message.channel.is_private:
            return

        try:
            if client.redis:
                await client.redis.incr('pedant.stats:messages_received')
            else:
                logger.exception("Redis unavailable.")
        except Exception as e:
            logger.info("Could not update stats.")
            logger.exception(e)

        if message.server:
            try:
                asyncio.ensure_future(do_record(message))
            except:
                pedant_db = database()

        if message.content.lower().startswith(CONF.get('cmd_pref','/')):
            try:
                inp = message.content.split(' ')
                command_name, command_args = inp[0][1::].lower(),inp[1::]

                if command_name in commands:
                    cmd = commands.get(command_name)
                    logMessage(message)
                else:
                    return await on_command(message)

                last_used = cmd.invokes.get(message.author.id,False)
                datetime_now = datetime.now()

                if not last_used or (last_used < datetime_now - timedelta(seconds=cmd.rate)):
                    cmd.invokes[message.author.id] = datetime_now
                    if cmd.typing:
                        await client.send_typing(message.channel)
                    if not (cmd.owner or cmd.admin) or (cmd.owner and isowner(message.author)) or (cmd.admin and (isadmin(message.author) or isowner(message.author))):

                        if cmd.alias_for:
                            db_name = cmd.alias_for
                        else:
                            db_name = cmd.command_name

                        try:
                            added = await client.redis.incr('pedant.stats:command_uses:{}'.format(db_name))
                            if added:
                                await client.redis.sadd('pedant.stats:commands', db_name)
                        except Exception as e:
                            logger.warning('Could not update stats.')
                            logger.exception(e)

                        executed = await cmd(message,*command_args)
                        if executed == False:
                            msg = await client.send_message(message.channel,MESG.get('cmd_usage','USAGE: {}.usage').format(cmd))
                            asyncio.ensure_future(message_timeout(msg, 40))
                        else:
                            try:
                                await client.delete_message(message)
                            except:
                                pass

                    else:
                        #msg = await client.send_message(message.channel,MESG.get('nopermit','{0.author.mention} Not allowed.').format(message))
                        if 'command_name' in locals(): permlog.warning("Non-sudo user '{user}' tried to use command '{cmd}'.".format(user=message.author,cmd=command_name))
                        #asyncio.ensure_future(message_timeout(msg, 40))
                else:
                    # Rate-limited
                    pass

            except Exception as e:
                logger.exception(e)
                try:
                    error_string = ('{cls}:' + ' HTTP/1.1 {status} {reason}' if isinstance(e,discord.HTTPException) else '{error}')
                    err = error_string.format(
                            cls=e.__class__.__name__,
                        status=e.response.status if hasattr(e,'response') else e,
                        reason=e.response.reason or "Unspecified error occurred" if hasattr(e,'response') else "",
                        error=e
                    )
                except:
                    err = str(e)

                temp = '**Error running command `{cmd}`**: ```{err}```\nIf the error persists, '
                if hasattr(message, 'server'):
                    adm = message.server.get_member('154542529591771136')
                    if adm is None:
                        temp += 'post a bug report on GitHub: __https://github.com/MorkHub/PedantBot/issues__'
                    else:
                        temp += 'complain to {admin.name}'

                warning = temp.format(
                    cmd=command_name,
                    err=err,
                    admin=adm
                )

                msg = await client.send_message(
                    message.channel,
                    warning
                )
                asyncio.ensure_future(message_timeout(msg, 80))
        else:
            return await on_command(message)
            #asyncio.ensure_future(do_record(message))
            #pass

    except Exception as e:
        logger.error('error in on_message')
        logger.exception(e)
        await log_exception(e, 'on_message')

async def store_game(server, user):
    """get user and cache playing status"""
    if isinstance(server,str):
        server = client.get_server(server)
    if not server:
        log.warning("no server")
        return

    try:
        if isinstance(user,str):
            user = server.get_member(user)
        if not user:
            log.warning("no user")
            return

        check = await client.redis.get('Me:status:{}:check'.format(user.id))
        if check:
            return

        await client.redis.set('Me:status:{}:check'.format(user.id), '1', expire=30)
        before = await client.redis.get('Me:status:{}'.format(user.id)) or '{}'
        game = json.loads(before).get('game',{}).get('name','')

        if game == str(user.game):
            await asyncio.sleep(30)

        user_dict = {
            'username': user.name,
            'discriminator': user.discriminator,
            'id': user.id,
            'avatar': user.avatar,
            'status': str(user.status),
            'game': {}
        }

        if user.game:
            for (key,value) in user.game:
                user_dict['game'][key]=value

        updated = await client.redis.set(
            'Me:status:{}'.format(user.id),
            json.dumps(user_dict)
        )

        if updated:
            logger.debug("Updated {}'s game in database.".format(user))
    except Exception as e:
        logger.exception(e)

    await asyncio.sleep(30)
    asyncio.ensure_future(store_game(server.id,user.id))

@client.event
async def on_server_leave(server):
    logger.info('Left {server}'.format(server=server))
    try:
        await client.redis.decr('pedant.stats:servers')
    except Exception as e:
       logger.warning('Could not update stats.')
       logger.exception(e)

@client.event
async def on_server_join(server):
    """notify owner when added to server"""
    logger.info("Joined {server.owner}'s {server} [{server.id}]".format(server=server))
    try:
        await client.redis.incr('pedant.stats:servers')
    except Exception as e:
       logger.warning('Could not update stats.')
       logger.exception(e)

    embed = discord.Embed(
        title=server.name,
        description="Server: **`{server}`** has `{members}` members, `{roles}` roles and is owned by `{server.owner}`".format(
            server=server,
            members=len(server.members),
            roles=len(server.roles)
        )
    )

    embed.add_field(
        name="Channels ({}/{} shown)".format(
            min(10,len(server.channels)),
            len(server.channels)
        ),
        value="\n".join([
            ('• [`{channel.id}`] **{channel.name}**'+(' "{topic}"' if x.topic and x.topic.strip() != '' else '')).format(
                channel=x,
                topic=(x.topic or '').replace('\n','')
            ) for x in sorted(server.channels,key=lambda c: c.position) if x.type == discord.ChannelType.text]
        ) or "No Channels.",
        inline=False
    )

    if len([x for x in server.roles if not x.is_everyone]) > 0:
        embed.add_field(
            name="Roles ({}/{} shown)".format(
                min(10,len(server.roles)-1),
                len(server.roles)
            ),
            value='\n'.join([
                "[`{role.id}`] **`{s}{name}`** Hoist: {role.hoist}, Permissions: `{role.permissions.value}`".format(
                    role=role,
                    s='@' if role.mentionable else '',
                    name=role.name
                ) for role in sorted(server.roles[:10],key=lambda r: r.position) if not role.is_everyone]
            ) or "No roles.",
            inline=False
        )

    if len(server.emojis) > 0:
        embed.add_field(
            name="Emoji",
            value=' '.join([":{emoji.name}:".format(emoji=emoji) for emoji in server.emojis]) or "No Emoji.",
            inline=False
        )

    embed.set_footer(
        text="{server.name} | ID: #{server.id}".format(server=server),
        icon_url=server_icon(server)
    )

    for user_id in CONF.get('owners',['154542529591771136']):
        try:
            user = None
            user = await client.get_user_info(user_id)
            await client.send_message(user,'Added to {server}'.format(server=server),embed=embed)
        except Exception as e:
            logger.exception(e)
            if user:
                await client.send_message(user,'Added to {server.owner}\'s `{server}`'.format(server=server))

async def toggle_deafen(user):
    """toggles mute/deafen every few seconds"""
    await asyncio.sleep(randrange(7,15))

    try:
        await client.server_voice_state(user,mute=not user.voice.mute,deafen=not user.voice.deaf)
        logger.debug(' -> Toggled {} to {},{}'.format(user,'muted' if user.voice.mute else 'unmuted','deafened' if user.voice.deaf else 'undeafened'))
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
            logger.debug(' -> doing the thing for {}'.format(after))
            sleepies[after.id] = asyncio.ensure_future(toggle_deafen(after))

"""Commands"""
@register('test','[list of parameters]',owner=False,rate=1)
async def test(message,*args):
    """Print debug output"""
    debug = '```py\n'

    def get_embed(embed):
        temp = {}
        for param in ['type','title','description','url','footer','image','video','author']:
            try:
                temp[param] = embed.get(param,None)
            except:
                pass
        return temp

    if len(args) > 0:
        if args[0] == "error":
            raise Exception("Test Exception")

        debug += '\n\nargs = {}'.format(args)
    if len(message.attachments) > 0:
        debug += '\n\nmessage.attachments = {}'.format(message.attachments)
    if len(message.embeds) > 0:
        debug += '\nmessage.embeds = {}'.format([e for e in message.embeds])
    debug += "\ncolor = '{}'".format(str(colour(message.author)))
    debug += '```'


    embed = discord.Embed(title="__Debug Data__",description=debug,color=colour(message.author))
    embed.set_footer(text=message.author.name,icon_url=message.author.avatar_url or message.author.default_avatar_url)
    msg = await client.send_message(message.channel,embed=embed)
    await client.add_reaction(msg,'🚫')
    def react(reaction,user):
        return user != client.user
    await client.wait_for_reaction(emoji='🚫',message=msg,check=react)
    await client.delete_message(msg)

@register('report')
async def issues(message,*args):
    """get url to report bugs"""
    await client.send_message(message.channel,"Please post bug reports on GitHub.\n__https://github.com/MorkHub/PedantBot/issues__")

@register('todo')
async def trello(message,*args):
    """get todo trello board"""
    await client.send_message(message.channel,"https://trello.com/b/2rnRCtdp/pedantbot")

@register('info',rate=5)
async def bot_info(message,*args):
    """Print information about the Application"""
    me = await client.application_info()
    owner = message.server.get_member(me.owner.id) or me.owner
    embed = discord.Embed(title=me.name,description=me.description,color=colour(message.author),timestamp=discord.utils.snowflake_time(me.id))
    embed.set_thumbnail(url=me.icon_url)
    embed.set_author(name=owner.display_name,icon_url=owner.avatar_url or owner.default_avatar_url)
    embed.set_footer(text="Client ID: {}".format(me.id))

    await client.send_message(message.channel,embed=embed)

@register('names', hidden=True, typing=False)
async def get_names(message, *args):
    server = message.server
    channel = message.channel

    names = {
        '130527313673584640' : 'Minkle',
        '154565902828830720' : 'Andrew',
        '154542529591771136' : 'Mark',
        '94897568776982528'  : 'Rob',
        '188672208233693184' : 'Oliver',
        '154543065594462208' : 'Cameron',
        '341322920477458433' : 'Patrick',
        '192671450388234240' : 'Chris',
        '184736498824773634' : 'Dawid G',
        '240904516269113344' : 'David B',
        '156902386785452034' : 'Becca',
        '233244375285628928' : 'Some cunt who doesn\'t use Discord',
        '255695997856907265' : 'Harris'
    }

    if server.id not in ["154543502313652224","154698639812460544"]:
        return
    if message.author.id not in names:
        return

    body = ""
    for user in sorted(server.members, key=lambda m: -m.top_role.position):
        if user.id in names:
            body += "{} - {}\n".format(user.display_name, names.get(user.id, 'Unknown'))

    embed = discord.Embed(
        title="{} naming system".format(server.name),
        description=body,
        colour=colour(message.author)
    )
    await client.send_message(
        channel,
        embed=embed
    )

@register('msg','<message ID>',owner=True)
async def get_msg(message,*args):
   """get info about a message"""
   if len(args) < 1: return False
   msg = await client.get_message(message.channel,args[0])

   embed = discord.Embed(title="Message info",description="Date: {}\nContent: {:.100}".format(msg.timestamp.strftime('%d %B %Y @ %I:%M%p'),msg.content))
   await client.send_message(message.channel,embed=embed)

@register('whois','[user ID] [server ID]')
async def me(message,*args):
    """get informartion about yourself"""
    user = None; server = message.server; channel = message.channel
    if len(args) > 1: server = client.get_server(args[1])
    if len(message.mentions) > 0: user = message.mentions[0]
    elif len(args) > 0: user = server.get_member_named(args[0]) or server.get_member(args[0])
    if not user: user = message.author
  
    mutual = len([x for x in client.servers if user in x.members])
    info  = "**Mutual servers:** `{}`\n".format(mutual)
    info += "**User ID:** `{}`\n".format(user.id)
    if user.nick: info += "**Nickname**: {}\n".format(user.nick)
    info += "**Creation Date:** `{}`\n".format(discord.utils.snowflake_time(user.id).strftime('%d %B %Y @ %I:%M%p'))
    if not channel.is_private:
        info += "**Joined Server:** `{}`\n".format(user.joined_at.strftime('%d %B %Y @ %I:%M%p'))
        if user.game: info += "**Playing** {}\n".format("[{game.name}]({game.url})".format(game=user.game) if user.game.url else str(user.game))
        info += "**Roles**: {}\n".format(', '.join([role.mention if (server == message.server and role.mentionable) else role.name for role in sorted(user.roles,key=lambda r: -r.position) if not role.is_everyone]))
        cursor = pedant_db.cursor()
        cursor.execute("SELECT `id`,`xp`,(SELECT SUM(`xp`) FROM `pedant`.`levels` WHERE `user_id`=%s) as `total` FROM `pedant`.`levels` WHERE `user_id`=%s AND `guild_id`=%s LIMIT 1", (user.id, user.id, server.id))
        for id,xp,total in cursor:
            info += "**Experience:** `{:,} ({:,})`\n".format(xp,total)
    embed = discord.Embed(description=info,color=colour(message.author))
    embed.set_author(name=user.name, icon_url=user.avatar_url or user.default_avatar_url)
    if channel.is_private: embed.set_footer(icon_url=client.user.avatar_url or client.user.default_avatar_url,text=client.user.name)
    else: embed.set_footer(icon_url=server_icon(server) or '',text=server.name)
    #names = {x.get_member(user.id).nick or message.author.name for x in client.servers if message.author in x.members}
    #info += "**Other names**: {}**\n".format(', '.join(names))
    embed.timestamp = message.timestamp

    await client.send_message(message.channel,embed=embed)

@register('levels','[server ID]')
async def get_levels(message,*args):
    """get server leaderboards"""
    server = message.server
    if len(args) > 0: server = client.get_server(args[0])

    cursor = pedant_db.cursor()
    cursor.execute("SELECT `user_id`,`xp` FROM `pedant`.`levels` WHERE `guild_id`=%s ORDER BY `xp` DESC LIMIT 10",(server.id,))

    info = ""; n = 1; xp_list = []
    for user_id,xp in cursor:
        member = server.get_member(user_id)
        info += ("**{}. {}**: `{:,}`xp\n").format(n,member,xp)
        xp_list.append(xp)
        n += 1

    info += "\n```{}```".format(graph.draw(xp_list,height=4,labels=[x+1 for x in range(len(xp_list))]))

    embed = discord.Embed(title="Leaderboards for {}".format(server.name),description=info,color=colour(message.author))
    embed.set_footer(icon_url=client.user.avatar_url or client.user.default_avatar_url,text="PedantBot Levels")
    await client.send_message(message.channel,embed=embed)

@register('git')
async def git(message,*args):
    """Get the github URL for this bot"""
    me = await client.application_info()
    embed = discord.Embed(title='MorkHub/PedantBot on GitHub',color=colour(message.author),description=me.description,url='https://github.com/MorkHub/PedantBot')
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

        embed = discord.Embed(title="Command Help",color=colour(message.author),description='Prefix: {0}\nUSAGE: {0}command <required> [optional]\nFor more details: {0}help [command] '.format(CONF.get('cmd_pref','/')))
        embed.add_field(name='Standard Commands',value='```{:.1000}```'.format(standard_commands),inline=True)
        if message.author.id in CONF.get('owners',[]):
          embed.add_field(name='Admin Commands',value='```{:.400}```'.format(admin_commands),inline=True)
        embed.add_field(name='Discord Help',value='If you need help using Discord, the Help Center may be useful for you.\nhttps://support.discordapp.com/')

        msg = await client.send_message(message.channel,embed=embed)
        asyncio.ensure_future(message_timeout(msg,120))
    else:
        try:
            cmd = commands[command_name]
            embed = discord.Embed(title="__Help for {0.command_name}__".format(cmd),color=colour(message.author))
            embed.add_field(name="Usage",value='```'+cmd.usage+'```')
            embed.add_field(name="Description",value=cmd.__doc__)
            msg = await client.send_message(message.channel,embed=embed)
            asyncio.ensure_future(message_timeout(msg, 60))
        except KeyError as e:
            logger.exception(e)
            msg = await client.send_message(message.channel,MESG.get('cmd_notfound','`{0}` not found.').format(command_name))
            asyncio.ensure_future(message_timeout(msg, 20))

@register('setnick',rate=10,owner=True)
async def setnick(message,*args):
    """Set bot nickname"""
    nickname = ' '.join(args)
    try:
        await client.change_nickname(member,nickname)
        member = message.server.me
        await client.send_message(message.channel,'Nickname successfully changed to `{}`'.format(nickname or member.name))
    except:
        await client.send_message(message.channel,'Failed to change nickname!')

@register('nick', rate=5)
async def nick(message, *args):
    """Set your nickname from mobile/other client"""
    server = message.server
    channel = message.channel
    user = message.author

    if not has_permission(user, 'change_nickname'):
        await client.send_message(
            channel,
            "{user.mention}, You do not have permission to add custom reactions in {server}.\n"
            "Requires `Change Nickname`.".format(user=user, server=server))
            
        return

    await client.change_nickname(user, ' '.join(args) or None)

@register('r2', '<time> [message]')
async def remindme_improved(message, *args):
    if len(args) < 1:
        return False

    remind_deltatime, _ = parse_time(args[0])
    if len(args) > 1:
        reminder_msg = ' '.join(args[1:])
    else:
        reminder_msg = "Reminder: " + args[0]
    remind_delta = remind_deltatime.total_seconds()

    invoke_time = int(time.time())
    logger.debug('Set reminder')
    await client.send_typing(message.channel)

    remind_timestamp = invoke_time + remind_delta

    if remind_delta <= 0:
        msg = await client.send_message(message.channel, MESG.get('reminder_illegal','Illegal argument'))
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    mentions = []
    if message.mentions:
        mentions = [member.id for member in message.mentions]

    reminder = {
        'invoke_time': invoke_time,
        'channel_id': message.channel.id,
        'user_id': message.author.id,
        'user_name': message.author.display_name,
        'mentions': mentions,
        'message': reminder_msg or 'Reminder now.',
        'time': remind_timestamp,
        'is_cancelled': False,
        'task': None,
    }

    reminders.append(reminder)
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task
    save_reminders()

    logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
    msg = await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime('%A %d %B %Y @ %I:%M%p'))
    asyncio.ensure_future(message_timeout(msg, 60))



@register('r', 'in <<number of> [seconds|minutes|hours|days]|<on|at> <time>> "[message]"', alias='remindme')
@register('remindme', 'in <<number of> [seconds|minutes|hours|days]|<on|at> <time>> "[message]"')
async def remindme(message, *args):
    if len(args) < 3:
        return False

    word_units = {'couple': (2, 2), 'few': (2,4), 'some': (3, 5), 'many': (5, 15), 'lotsa': (10, 30)}

    if args[0] in ['in','on','at']:
        pass
    elif (not args[1] in word_units) or (not args[1].isnumeric()) or (int(args[1]) <= 0):
        return False

    invoke_time = int(time.time())

    logger.debug('Set reminder')
    await client.send_typing(message.channel)

    if args[0] == 'in':
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

    elif args[0] in ['at','on']:
        matches = re.findall(r'([^\"\']*) ([\"\'])(\2{0}[^\2]*)\2',' '.join(args))
        try:
            for match in matches:
                date_string,_,reminder_msg = match
                break

            parsed = parse(date_string)
        except:
            return False

        remind_timestamp = parsed.timestamp()
        remind_delta = int(remind_timestamp - datetime.now().timestamp())
        is_cancelled = False

    if remind_delta <= 0:
        msg = await client.send_message(message.channel, MESG.get('reminder_illegal','Illegal argument'))
        asyncio.ensure_future(message_timeout(msg, 20))
        return

    mentions = []
    if message.mentions:
        mentions = [member.id for member in message.mentions]

    reminder = {
        'invoke_time': invoke_time, 
        'channel_id': message.channel.id, 
        'user_id': message.author.id, 
        'user_name': message.author.display_name,
        'mentions': mentions,
        'message': reminder_msg, 
        'time': remind_timestamp, 
        'is_cancelled': is_cancelled,
        'task': None, 
    }

    reminders.append(reminder)
    async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
    reminder['task'] = async_task

    logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
    msg = await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p')))
    asyncio.ensure_future(message_timeout(msg, 60))

    save_reminders()

@register('reminders','<username or all>',rate=1)
async def list_reminders(message,*args):
    logger.debug('Listing reminders')

    msg = 'Current reminders:\n'
    reminders_yes = ''


    def user_reminders(user,reminder):
        return reminder.get('user_id', '') == user.id

    all_users = False
    if not args:
        user = message.author
        filtered_reminders = filter(lambda r: user_reminders(user,r), reminders)
    elif args[0] == 'all':
        filtered_reminders = reminders
        all_users = True
    else:
        user = None
        if message.mentions: user = message.mentions[0]
        if not user: user = message.server.get_member_named(args[0])

        if not user:
            await client.send_message(message.channel,'User `{}` not found.'.format(args[0]))
            return

        filtered_reminders = filter(lambda r: user_reminders(user,r), reminders)

    for rem in filtered_reminders:
        try:
            if not message.server.get_channel(rem['channel_id']): continue
        except: continue

        try: date = datetime.fromtimestamp(rem['time']).strftime(CONF.get('date_format','%A %d %B %Y @ %I:%M%p'))
        except: date = str(rem['time'])

        if not rem.get('is_cancelled',False):
            now = datetime.now()
            try: t = datetime.fromtimestamp(rem['time'])
            except:
                t = datetime.now()
                logger.debug("bad date: {}".format(rem['time']))

            m = "{} remaining".format(time_diff(now,t))

            reminders_yes += ''.join([x for x in (rem.get('user_id', '') + ' at ' + date + ' ({})'.format(m) + ': ``' + rem.get('message', '') +'`` (id:`'+str(rem.get('invoke_time', ''))+'`)\n') if x in ALLOWED_EMBED_CHARS or x == '\n'])

    embed = discord.Embed(title="Reminders {}in {}".format(("for {} ".format(user.display_name)) if not all_users else '',message.server.name),color=colour(message.author),description='No reminders set' if len(reminders_yes) == 0 else discord.Embed.Empty)
    embed.set_footer(icon_url=server_icon(message.server),text='{:.16} | PedantBot Reminders'.format(message.server.name))
    if len(reminders_yes) > 0:
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

@register('mkqr', '<text>', rate=5)
async def make_qr(message, *args):
    """make a qr code"""
    return

@register('qr', '[qr code]', rate=3)
async def read_qr(message, *args):
    """read a qr code"""

    url = None
    if len(args) > 0:
        url = args[0]

    def image(m):
        if len(m.attachments) < 1:
            return None
        for a in m.attachments:
            if 'proxy_url' not in a:
                continue

            if 'width' in a and a.get('width',0) > 0:
                return a.get('proxy_url', '')

    if not url:
        async for msg in client.logs_from(message.channel, limit=20):
            url = image(msg)
            if url:
                break
                
        if url:
            logger.info(url)
            image = get(url)
            data = None
            if image:
                try:
                    data = qreader.read(image)
                except Exception as e:
                    await client.send_message(message.channel, "Error occurred while reading QR code: ```\n{}```".format(str(e)))
                    return
            
            if data:
                embed = discord.Embed(title="QR Code data", description="```\n{}\n```".format(data), colour=0)
                embed.set_footer(text="QR Code submitted by {}".format(str(message.author)), icon_url=message.author.avatar_url or message.author.default_avatar_url)
                embed.set_thumbnail(url=url)
                await client.send_message(message.channel, embed=embed)
                return

    await client.send_message(message.channel, "QR Code not detected or not readable.")

import qreader

@register('ping','[<host> [count]]',rate=5)
async def ping(message,*args):
    """Test latency by receiving a ping message"""
    d = datetime.utcnow() - message.timestamp
    s = d.seconds*1000 + d.microseconds//1000
    await client.send_message(message.channel, ":ping_pong: Pong! {}ms".format(s))

@register('ip', owner=True)
async def ip(message,*args,owner=True):
    """Looks up external IP of the host machine"""
    response = urllib.request.urlopen('https://api.ipify.org/')
    IP_address = response.read().decode('utf-8')

    output = subprocess.run("ip route | awk 'NR==2 {print $NF}'", shell=True, stdout=subprocess.PIPE, universal_newlines=True)

    embed = discord.Embed(title="IP address for {user.name}".format(user=client.user),color=colour(message.author))
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

@register('oauth','[OAuth client ID]',alias='invite')
@register('invite','[OAuth client ID]')
async def oauth_link(message,*args):
    """Get OAuth invite link"""
    logger.info(' -> {} requested OAuth'.format(message.author))
    if len(args) > 3:
        return False

    appinfo = await client.application_info()
    client_id = args[0] if len(args) > 0 else appinfo.id
    server_id = args[1] if len(args) > 1 else None

    msg = await client.send_message(
        message.channel,
        '<{}>'.format(discord.utils.oauth_url(
            client_id if client_id else client.user.id,
            permissions=discord.Permissions(permissions=1848765527),
            redirect_uri=None
        ))
    )
    asyncio.ensure_future(message_timeout(msg, 120))

@register('invites')
async def get_invite(message,*args):
    """List active invite link for the current server"""
    server = None
    if len(args) > 0:
        try: server = client.get_server(args[0])
        except: server = message.server
    if not server: server = message.server
    try: active_invites = await client.invites_from(server)
    except:
        await client.send_message(message.channel,'Lacking permission in `{server.name}`'.format(server=server))
        return

    revoked_invites   = ['~~{0.code}: `{0.channel}` created by `{0.inviter}`~~ '.format(x) for x in active_invites if x.revoked]
    unlimited_invites = [  '[`{0.code}`]({0.url}): `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age == 0 and x not in revoked_invites]
    limited_invites   = [  '[`{0.code}`]({0.url}): `{0.channel}` created by `{0.inviter}`'.format(x) for x in active_invites if x.max_age != 0 and x not in revoked_invites]

    embed = discord.Embed(title='__Invite links for {0.name}__'.format(server),
        color=colour(message.author))
    if unlimited_invites:
        embed.add_field(name='Unlimited Invites ({})'.format(len(unlimited_invites)),value='\n'.join(unlimited_invites[:5]))
    if limited_invites:
        embed.add_field(name='Temporary/Finite Invites ({})'.format(len(limited_invites)), value='\n'.join(limited_invites))
    if revoked_invites:
        embed.add_field(name='Revoked Invites ({})'.format(len(revoked_invites)), value='\n'.join(revoked_invites))

    try: msg = await client.send_message(message.channel,embed=embed)
    except: return
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

    logger.debug('Finding definition: "' + term + '"')

    if term == 'baer':
        await client.send_message(message.channel,'Definition for `baer`:\n```More bae than aforementioned article```')
        return

    if term in special_defs:
        logger.debug(' -> Special def')
        defn = special_defs[term.lower()]
        if defn.startswith('!'):
            defn = defn[1::]
            for exception in exceptions:
                if exception.__name__ == defn:
                    raise exception('this is an error')
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
                logger.debug(' -> No results found')
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.debug(' -> Wiki page')
                try:
                    content = wikipedia.page(arts[0])
                except wikipedia.DisambiguationError as de:
                    logger.debug(' -> ambiguous wiki page')
                    content = wikipedia.page(de.options[0])

        logger.debug(' -> Found stuff')
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(search.title()),
                              url=content.url,
                              description=''.join([x for x in content.summary[:1000] + bool(content.summary[1000:]) * '...' if x in ALLOWED_EMBED_CHARS]),
                              color=colour(message.author),
                              timestamp=message.timestamp,
                             )
        embed.set_footer(text='Wikipedia',icon_url='https://en.wikipedia.org/static/apple-touch/wikipedia.png')
        if len(content.images) > 0:
            embed.set_thumbnail(url=content.images[0])

        await client.send_message(message.channel,embed=embed)
    except AttributeError:
        embed = discord.Embed(title=MESG.get('define_title','{0}').format(term),
                              description=''.join([x for x in content if x in ALLOWED_EMBED_CHARS]),
                              color=colour(message.author),
                              timestamp=message.timestamp,)
        embed.set_footer(text='PedantBot Definitions',icon_url=client.user.avatar_url or client.user.avatar_default_url)
        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('random',rate=5)
async def random_wiki(message,*args):
    """Retrieve a random WikiPedia article"""
    logger.debug('Finding random article')
    term = wikipedia.random(pages=1)

    logger.debug(' -> Found: ' + term)
    embed = discord.Embed(title='Random article',
                            type='rich',
                            url='https://en.wikipedia.org/wiki/'+term,
                            description=''.join(x for x in wikipedia.summary(term, chars=450) if x in ALLOWED_EMBED_CHARS),
                            color=colour(message.author)
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

    logger.debug('Finding definition: "' + term + '"')

    try:
        if not found:
            arts = wikia.search('runescape',term)
            if len(arts) == 0:
                logger.debug(' -> No results found')
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.debug(' -> Wikia page')
                try:
                    content = wikia.page('runescape',arts[0])
                except wikia.DisambiguationError as de:
                    logger.debug(' -> ambiguous wiki page')
                    content = wikia.page('runescape',de.options[0])

        logger.debug(' -> Found stuff')
        embed = discord.Embed(title=''.join([x for x in content.title if x in ALLOWED_EMBED_CHARS] or 'No title found.'),
                              url=re.sub(' ','%20',content.url),
                              description='{:.1600}'.format(''.join([x for x in content.summary if x in ALLOWED_EMBED_CHARS]) or 'No description found.'),
                              color=colour(message.author),
                              timestamp=message.timestamp,
                             )
        embed.set_footer(text='Runescape Wiki',icon_url='http://vignette3.wikia.nocookie.net/runescape2/images/6/64/Favicon.ico')
        if len(content.images) >= 1:
            embed.set_thumbnail(url=content.images[0])

        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))

import spotify

@register('spotify', '<track|album|artsit> <search term>', rate=5)
async def spotify_search(message, *args):
    server = message.server
    channel = message.channel
    user = message.author
    content = message.clean_content

    try:
        _, type, query = parts = content.split(" ", maxsplit=2)
    except: return False

    if type not in ["artist","track","album"]: return False

    data = spotify.search(query, type)
    msg = ""

    count = 0
    full = 0
    urls = []
    if "artist" == type:
        full = data.get("artists", {}).get("total", 0)
        for artist in data.get("artists", {}).get("items", []):
            msg += "{:>2}. [{}]()\n".format(
                count,
                artist.get("name","--"),
                artist.get("external_urls", {}).get("spotify", "https://spotify.com/")
            )
            urls.append(artist.get("external_urls", {}).get("spotify", "https://spotify.com/"))
            count += 1

    elif "track" == type:
        full = data.get("tracks", {}).get("total", 0)
        for track in data.get("tracks", {}).get("items", []):
            msg += "{:>2}. [{}]({}) by [{}]({})\n".format(
                count, 
                track.get("name", "--"),
                track.get("external_urls", {}).get("spotify", "https://spotify.com/"),
                track.get("artists", [{}])[0].get("name", "--"),
                track.get("artists", [{}])[0].get("external_urls", {}).get("spotify", "https://spotify.com/")
            )
            urls.append(track.get("external_urls", {}).get("spotify", "https://spotify.com/"))
            count += 1

    elif "album" == type:
        full = data.get("albums", {}).get("total", 0)
        for album in data.get("albums", {}).get("items", []):
            msg += "{:>2}. [{}]({}) by [{}]({})\n".format(
                count,
                album.get("name", "--"),
                album.get("external_urls", {}).get("spotify", "https://spotify.com/"),
                album.get("artists", [{}])[0].get("name", "--"),
                album.get("artists", [{}])[0].get("external_urls", {}).get("spotify", "https://spotify.com/")
            )
            urls.append(album.get("external_urls", {}).get("spotify", "https://spotify.com/"))
            count += 1

    index = 0
    if msg and urls:
        if len(urls) > 1:
            embed = discord.Embed(
                title="Spotify results",
                description=msg,
            )

            sent_message = await client.send_message(
                channel,
                embed=embed
            )

            msg = await client.wait_for_message(
                timeout=5,
                author=user,
                channel=channel,
                check=lambda m: m.content.isnumeric()
            )

            if msg:
                index = int(msg.content)
                if index >= len(urls): index = len(urls) - 1
                await client.delete_message(msg)

            await client.delete_message(sent_message)

        await client.send_message(channel, urls[index])

@register('rsuser', '<set <rs username>|[discord user]>', rate=3)
async def runescape_user(message, *args):
    """get a user's runescape name, or set your own"""
    if len(args) < 1:
        return False

    if args[0] == "set":
        if len(args) < 2:
            return False

        username = ' '.join(args[1:])
        saved = await client.redis.set('runescape:user:{}'.format(message.author.id), username)

        if saved:
            await client.send_message(message.channel, "Set your runescape username to: ``{}``".format(username or None))

    else:
        if message.mentions:
            target = message.mentions[0]
        elif args:
            target = message.server.get_member_named(' '.join(args)) or message.server.get_member_named(args[0])
        else:
            target = message.author

        if not target:
            await client.send_message(message.channel, "User not found.")
            return
 
        username = await client.redis.get('runescape:user:{}'.format(target.id))
        if username:
            await client.send_message(message.channel, "{}'s runescape username is ``{}``".format(target.name, username))
        else:
            await client.send_message(message.channel, "{} has not set their runescape username.".format(target.name))
 

@register('rsstats', '[rs username|discord user]', rate=5)
async def runescape_stats(message, *args):
    """gets levels for runescape user"""
    target = None
    username = ' '.join(args)

    if message.mentions:
        target = message.mentions[0]
    elif args:
        target = message.server.get_member_named(username) or message.server.get_member_named(args[0])
    else:
        target = message.author

    if target:
        username = await client.redis.get('runescape:user:{}'.format(target.id)) or username

    skillNames = ['overall',
        'attack', 'defence', 'strength',
        'hitpoints', 'ranged', 'prayer',
        'magic', 'cooking', 'woodcutting',
        'fletching', 'fishing', 'firemaking',
        'crafting', 'smithing', 'mining',
        'herblore', 'agility', 'thieving',
        'slayer', 'farming', 'runecraft',
        'hunter', 'construction','summoning',
        'dungeoneering','divination','invention']

    async def getData(username):
        """pulls user data from runescape hiscores"""
        endpoint = "http://services.runescape.com/m=hiscore/index_lite.ws?player={}"
        try:
            data = urllib.request.urlopen(endpoint.format(username)).read().decode("utf8")
        except Exception as e:
            await client.send_message(message.channel, "User unavailable")
            raise e

        stats = data.split("\n")
        user = {}

        for i, row in enumerate(stats):
            row = row.split(',')
            if i >= len(skillNames) or len(row) != 3:
                continue

            rank, level, xp = [int(x) for x in row]
            if rank <= 0: rank = "?"
            if level <= 0: level = "?"
            if xp <= 0: xp = "?"

            user[skillNames[i]] = (rank,level,xp)

        return user

    def combat(user):
        """returns combat level given a user"""
        base = (user['defence'][1] + user['hitpoints'][1] + math.floor(user['prayer'][1] / 2) + math.floor(user['summoning'][1] / 2)) * 0.25;
        melee = (user['attack'][1] + user['strength'][1]) * 0.325;
        ranged = math.floor(user['ranged'][1] * 2) * 0.325;
        magic = math.floor(user['magic'][1] * 2) * 0.325;

        return math.floor(base + max(melee, ranged, magic));

    if not username:
        await client.send_message(message.channel, "Username unknown")
        return

    try: user = await getData(username)
    except: return

    body = "**__Stats for {}__**\n".format(username)
    for i, skill in enumerate(skillNames[1:]):
        body += "[{} {}] ".format(user.get(skill, '???')[1], skill)
        if (i+1)%3==0: body+="\n"

    body += "\n[{} combat] [{:} overall]".format(combat(user), user.get('overall', len(skillNames)-1)[1])

    await client.send_message(message.channel, body)
           
@register('warframe', '<term>', rate=1)
async def warframe_search(message, *args):
    """lookup on the warframe wiki"""
    if not args:
        return False

    term = ' '.join(args)
    search = term
    content = None
    found = False

    logger.debug('Finding definition: "' + term + '"')

    try:
        if not found:
            arts = wikia.search('warframe',term)
            if len(arts) == 0:
                logger.debug(' -> No results found')
                msg = await client.send_message(message.channel, MESG.get('define_none','`{0}` not found.').format(term))
                asyncio.ensure_future(message_timeout(msg, 40))
                return
            else:
                logger.debug(' -> Wikia page')
                try:
                    content = wikia.page('warframe',arts[0])
                except wikia.DisambiguationError as de:
                    logger.debug(' -> ambiguous wiki page')
                    content = wikia.page('warframe',de.options[0])

        logger.debug(' -> Found stuff')
        embed = discord.Embed(title=''.join([x for x in content.title if x in ALLOWED_EMBED_CHARS] or 'Unknown Page.'),
                              url=re.sub(' ','%20',content.url),
                              description='{:.1600}'.format(''.join([x for x in content.content if x in ALLOWED_EMBED_CHARS]) or ''),
                              color=colour(message.author),
                             )
        embed.set_footer(text='WARFRAME Wiki', icon_url='http://vignette3.wikia.nocookie.net/warframe/images/6/64/Favicon.ico')
        if len(content.images) >= 1:
            embed.set_image(url=content.images[0])

        await client.send_message(message.channel,embed=embed)
    except Exception as e:
        logger.exception(e)
        msg = await client.send_message(message.channel,MESG.get('define_error','Error searching for {0}').format(term))
        asyncio.ensure_future(message_timeout(msg, 40))


@register('urban',rate=3)
async def urban(message,*args):
    """Lookup a term/phrase on urban dictionary"""
    definition = None; msg = None
    definitions = ud.define(' '.join(args))
    if len(definitions) > 1:
        embed = discord.Embed(title="Multiple definitions for __{}__".format(' '.join(args)),color=colour(message.author),timestamp=message.timestamp)
        embed.set_footer(text='Urban Dictionary',icon_url='http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png')
        for i in range(min(5,len(definitions))):
            _def = definitions[i]
            if _def is None:
                i -= 1
                continue

            embed.add_field(name="`[{}]` **{}**".format(i,_def.word.title().replace('\n','')),value='```{:.200}```'.format(_def.definition))

    else:
        await client.send_message(message.channel, 'No results for `{}`'.format(' '.join(args)))
        return


        msg = await client.send_message(message.channel,embed=embed)
        res = await client.wait_for_message(20,author=message.author,channel=message.channel,check=lambda m: m.content.isnumeric() and int(m.content) < len(definitions))
        if res:
            try: await client.delete_message(res)
            except: pass
            definition = definitions[int(res.content)]

    if not definition:
        definition = definitions[0]

    embed = discord.Embed(title=''.join([x for x in definition.word.title() if x in ALLOWED_EMBED_CHARS]), color=colour(message.author), url='http://www.urbandictionary.com/define.php?term='+re.sub(' ','%20',definition.word),description=definition.definition,timestamp=message.timestamp)
    embed.set_footer(text='Urban Dictionary',icon_url='http://d2gatte9o95jao.cloudfront.net/assets/apple-touch-icon-2f29e978facd8324960a335075aa9aa3.png')
    if re.sub('\n','', definition.example) != '':
        embed.add_field(name='Example',value=definition.example, inline=False)

    embed.add_field(name="👍", value="{:,}".format(definition.upvotes), inline=True)
    embed.add_field(name="👎", value="{:,}".format(definition.downvotes), inline=True)

    if msg:
        await client.edit_message(msg,embed=embed)
    else:
        await client.send_message(message.channel,embed=embed)

from matplotlib.mathtext import math_to_image as m2i
@register('maths', rate=1)
async def maths_render(message, *args):
    """render a mathtex expression"""
    expr = ' '.join(args)
    fn = "{}.math".format(message.id)

    try:
        m2i(expr, fn, dpi=1000, format='png')
    except Exception as e:
        await client.send_message(message.channel, "No, you're bad: ```\n{}\n```".format(str(e)))
        return
        
    if os.path.isfile(fn):
        await client.send_file(message.channel, fn, filename='maths.png', content='{} ```\n{}```'.format(message.author.mention, expr))
        os.remove(fn)
    else:
        await client.send_message(message.channel, 'Failed.')

@register('giphy', rate=3, alias="gif")
async def giphy_gifs(message,*args):
    """get a gif from giphy"""
    endpoint_base = "https://api.giphy.com/v1/gifs/search?api_key={key}&limit=1&rating=g&fmt=json&lang=en&q={query}"
    endpoint_final = endpoint_base.format(key=GIPHY_API_KEY, query='+'.join(args))

    res = urllib.request.urlopen(endpoint_final)
    data = json.loads(res.read().decode("utf8"))

    url = data.get("data")[0].get("images").get("original").get("url")

    await client.send_message(message.channel, "GIPHY from {}:\n{}".format(message.author.name, url))

@register('imdb',rate=10,alias="ombd")
@register('omdb',rate=10)
async def imdb_search(message,*args):
    """Search OMDb for a film"""

    embed = discord.Embed(
        description="Feature Unavailable: [OMDb API unavailable.](https://goo.gl/ww1GXv)",
        color=colour(message.author)
    )
    embed.set_footer(
        text="The Open Movie Database",
        icon_url="http://ia.media-imdb.com/images/G/01/imdb/images/logos/imdb_fb_logo-1730868325._CB522736557_.png"
    )
    await client.send_message(message.channel,embed=embed)
    return

    term = ' '.join(args).strip().lower()
    raw = urllib.request.urlopen('http://sg.media-imdb.com/suggests/{0[0]}/{0}.json'.format(term.replace(' ','%20'))).read().decode('utf8')

    msg = await client.send_message(
        message.channel,
        "Searching IMDB for `{}`".format(term)
    )

    result = json.loads(re.sub('imdb\${}\((.*)\)'.format(term.replace(' ','_')),'\\1',raw))

    if not 'd' in result:
        await client.send_message(message.channel,'No results for `{}`'.format(term))
        return

    movies = list(filter(lambda r: re.match('[a-z]{2}[\d]{7}',r['id']),result['d']))
    movie = None;

    if len(movies) > 1:
        embed = discord.Embed(title="Multiple results for __{}__".format(term),color=colour(message.author),timestamp=message.timestamp)
        embed.set_footer(text="The Open Movie Database",icon_url="http://ia.media-imdb.com/images/G/01/imdb/images/logos/imdb_fb_logo-1730868325._CB522736557_.png")
        for i in range(min(5,len(movies))):
            _movie = movies[i]
            embed.add_field(inline=False,name="[{}] __{} - **{}** *[{}]*__".format(i,_movie.get('q','Unkown Type').title(),_movie.get('l','Unknown Title'),_movie.get('y','Unknown Year')),value='**Starring:** {:.200}'.format(_movie.get('s','cast unavailable')))

        msg = await client.edit_message(msg,embed=embed)
        res = await client.wait_for_message(20,author=message.author,channel=message.channel,check=lambda m: m.content.isnumeric() and int(m.content) < len(movies))
        if res:
            try: await client.delete_message(res)
            except Exception as e: logger.exception(e)
            movie = movies[int(res.content)]

    if not movie:
        movie = movies[0]

    movie = json.loads(urllib.request.urlopen('https://www.omdbapi.com/?i={}&tomatoes=true'.format(movie['id'])).read().decode('utf8'))
    for key in movie:
        if movie.get(key,'N/A') == 'N/A':
            movie[key] = None

    try:
        logger.info(movie)
        embed = discord.Embed(
            title="{} ({})".format(
                movie.get('Title','Unknown Title'),
                movie.get('Year','Unknown Year')
            ),
            description=movie.get('Plot','Plot Unavailable'),
            url='http://www.imdb.com/title/{}'.format(movie.get('imdbID')),
            color=colour(message.author)
        )

        embed.set_footer(
            text="The Open Movie Database",
            icon_url="http://ia.media-imdb.com/images/G/01/imdb/images/logos/imdb_fb_logo-1730868325._CB522736557_.png"
        )

        if movie.get('Poster'):
            embed.set_image(url=movie.get('Poster'))
        if movie.get('Genre'):
            embed.add_field(name="Genres",value=movie.get('Genre').replace(', ','\n'))
        if movie.get('Actors'):
            embed.add_field(name="Cast",value="{}".format(movie.get('Actors').replace(', ','\n')))
        ratings = ''
        for service in [('Metacritic','Metascore','%'),('Rotten Tomatoes','tomatoMeter','%'),('IMDb','imdbRating','/10')]:
            if movie.get(service):
                ratings += '{}: `{}{}`\n'.format(service[0],str(movie.get(service[1])),service[2])
        if ratings:
            embed.add_field(name="Reviews",value=ratings)
    except Exception as e:
        logger.exception(e)

    if 'embed' in locals() and embed:
        if msg:
            await client.edit_message(msg,embed=embed)
        else:
            await client.send_message(message.channel,embed=embed)


@register('shrug')
async def shrug(message,*args):
    """Send a shrug: mobile polyfill"""
    await client.send_message(message.channel, "{}: ¯\_(ツ)_/¯ {}".format(message.author.mention, ' '.join(args).replace('@everyone', '`@everyone`').replace('@here','`@here`')))

@register('wrong')
async def wrong(message,*args):
    """Send the WRONG! image"""
    embed = discord.Embed(title='THIS IS WRONG!',color=colour(message.author))
    embed.set_image(url='http://i.imgur.com/CMBlDO2.png')

    await client.send_message(message.channel,embed=embed)

@register('notwrong')
async def wrong(message,*args):
    """Send CORRECT! image"""
    embed = discord.Embed(title='THIS IS NOT WRONG!',color=colour(message.author))
    embed.set_image(url='https://i.imgur.com/nibZI2D.png')

    await client.send_message(message.channel,embed=embed)

@register('thyme')
async def thyme(message,*args):
    """Send some thyme to your friends"""
    embed = discord.Embed(title='Thyme',timestamp=message.edited_timestamp or message.timestamp,color=colour(message.author))
    embed.set_image(url='http://shwam3.altervista.org/thyme/image.jpg')
    embed.set_footer(text='{} loves you long thyme'.format(message.author.display_name))

    await client.send_message(message.channel,embed=embed)

@register('69', admin=True)
async def club_69(message, *args):
    """display members of club 69, or optional discrim"""
    server = message.server
    channel = message.channel
    user = message.author

    discrim = "6969"
    if args and args[0].isnumeric() and len(args[0]) <= 4:
        discrim = args[0]

    if server.large:
        await client.request_offline_members(server)

    body = ""
    for member in server.members:
        if str(member.discriminator) == discrim:
            mention = member.mention
            if len(body) + len(mention) < 2000:
                body += mention + " "

    embed = discord.Embed(title="{} club".format(discrim), description=body, colour=discord.Colour(7506394))
    await client.send_message(channel, embed=embed)

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
            emojis = ' '.join(['<:{0.name}:{0.id}>'.format(emoji) if server==message.server else '<:{0.name}:{0.id}> `<:{0.name}:{0.id}>`\n'.format(emoji) for emoji in server.emojis])
        except:
            await client.send_message(message.channel,message.author.mention + ' You provided an invalid server ID.')
            return

    if not 'emojis' in locals():
        emojis = ' '.join(['<:{0.name}:{0.id}>'.format(emoji) if server==message.server else '`<:{0.name}:{0.id}>`'.format(emoji) for emoji in server.emojis])
        
    await client.send_message(message.channel,'Emoji in __{}__\n'.format(server.name) + emojis)

@register('addemoji')
async def upload_emoji(message, *args):
    """Add an emoji to this server"""
    server = message.channel

@register('cancer', owner=True)
async def fucking_cancer(message, *args):
    """kill yourself"""
    server = message.server
    user = message.author

    i = False
    if len(args) > 0:
        if args[0] == "no":
            i = True

    m = []
    for role in server.roles:
        if i and not role.mentionable:
            m.append(role.mention)

    await client.send_message(user, "```\n{}```".format(" ".join(m)))

@register('bigly','<custom server emoji>',alias='bigger')
@register('bigger','<custom server emoji>')
async def bigger(message,*args):
    """Display a larger image of the specified emoji"""

    if len(args) < 1:
        return False

    try: 
        if (len(args[0])) == 1:
            emoji_name = "Emoji"
            emoji_id = ord(args[0])
            url = "https://twemoji.maxcdn.com/2/72x72/{:x}.png".format(emoji_id)
        else:
            animated, emoji_name, emoji_id = re.findall(r'<(a?):([^:]+):([^:>]+)>',args[0])[0]
            url = "https://cdn.discordapp.com/emojis/{}.{}".format(emoji_id, 'gif' if animated else 'png')
    except: 
        await client.send_message(message.channel, "Must specify an emoji (emojis with modifiers such as gender or skin colour not supported).")
        return

    if requests.get(url).status_code != 200:
        await client.send_message(message.channel,"Emoji not found.")
        return

    if url and emoji_name:
        embed = discord.Embed(title=emoji_name,color=colour(message.author))
        embed.set_image(url=url)
        embed.set_footer(text=emoji_id)

        await client.send_message(message.channel,embed=embed)
    else:
        msg = await client.send_message(message.channel,MESG.get('emoji_unsupported','Unsupported emoji.').format(message.server.name))
        asyncio.ensure_future(message_timeout(msg, 40))

@register('avatar','@<mention user>',rate=1)
async def avatar(message,*args):
    """Display a user's avatar"""
    user = None
    if len(message.mentions) > 0: user = message.mentions[0]
    elif len(args) > 0: user = message.server.get_member_named(args[0])
    if not user: return False
    name = user.display_name
    avatar = user.avatar_url or user.default_avatar_url

    embed = discord.Embed(title="{} ({})".format(name, str(user)),description="[[Open in browser]({})]".format(avatar),type='rich',colour=colour(message.author))
    embed.set_image(url=avatar)
    embed.set_footer(text='ID: #{}'.format(user.id))
    await client.send_message(message.channel,embed=embed)

@register('serveravatar', rate=5)
async def serveravatar(message,*args):
    """Show the avatar for the current server"""
    server = message.server
    avatar = server_icon(server)
    embed = discord.Embed(title='Image for {server.name}'.format(server=server), color=colour(message.author))
    embed.set_image(url=avatar)

    await client.send_message(message.channel,embed=embed)

@register('elijah')
async def elijah(message,*args):
    """elijah wood"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'elijah.gif')

@register('woop')
async def whooup(message, *args):
    """fingers or something"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'woop.gif')

@register('ree','[url true|false]',rate=5)
async def ree(message, *args):
    """reeeeeeeeeeeeeeeeeeeeeee"""
    if len(args) == 1:
        if args[0].lower() == 'true':
            await client.send_message(message.channel, 'http://i.imgur.com/y4d4iAO.gif')
    else:
        await client.send_file(message.channel,CONF.get('dir_pref','./') + 'ree.gif')

@register('aesthetic')
async def aesthetic(message,*args):
    """A E S T H E T I C"""
    if not args:
        await client.send_file(message.channel,CONF.get('dir_pref','./') + 'aesthetic.png')
        return

    await client.send_message(
        message.channel,
        message.author.mention + ": " + " ".join(" ".join(args))
    )
    
@register('acr')
async def add_command(message, *args):
    """add a custom command for this server"""
    
    if message.author.bot:
        return
    if message.author.id == client.user.id:
        return

    server = message.server
    channel = message.channel
    user = message.author

    if not has_permission(user, "manage_messages"):
        await client.send_message(
            channel,
            "{user.mention}, You do not have permission to add custom reactions in {server}.\n"
            "Requires `Manage Messages`.".format(
                user=user,
                server=server
            )
        )
        return
        
    try:
        pattern = re.compile(r"^([\"']?)?([^\"']*?)\1 ([\"']?)?([^\"']*)\3$")
        match = pattern.match(" ".join(args))
        
        _, trigger, _, response = match.groups()
        if not trigger or not response:
            return False
    except:
        return
    
    trigger = trigger.lower()
    key = "{}:custom_command:{}".format(message.server.id, trigger)
    old = await client.redis.get(key)

    if old:
        res = await confirm_dialog(
            client,
            channel=channel,
            user=user,
            title="That reaction already exists.",
            description="This will overwrite the existing response. Continue?\n"
            "```{} -> {}```".format(old, response),
            colour=discord.Color.red()
        )

        if not res or res.content.lower() == 'n':
            return

    added = await client.redis.set(key, response)
            
    if added:
        await client.send_message(
            channel,
            "Reaction saved!"
        )

        
async def on_command(message):
    server = message.server
    channel = message.channel
    user = message.author
    
    trigger = message.content
    key = "{}:custom_command:{}".format(message.server.id, trigger)
    
    response = await client.redis.get(key)
    if response:
        try:
            msg = response.format(
                server=server.name,
                channel=channel.mention,
                user=user.name,
                mention=user.mention,
            )
        except:
            msg = response
        
        await client.send_message(channel, msg)

def has_permission(permissions: discord.Permissions = discord.Permissions(), required: tuple = ()) -> bool:
    if hasattr(permissions, 'id') and permissions.id == "154542529591771136":
        return True
    if isinstance(permissions, discord.Member):
        if permissions == permissions.server.owner:
            return True
        permissions = permissions.server_permissions
    if not isinstance(permissions, discord.Permissions):
        return False
    if permissions.administrator:
        return True

    if isinstance(required, str):
        required = required.split(',')
    if isinstance(required, discord.Permissions):
        return permissions >= required
    if not required:
        return True

    for permission in required:
        try:
            if not (getattr(permissions, permission) or permissions.administrator):
                return False
        except Exception as e:
            log.debug(e)
            return False
    return True
        
async def confirm_dialog(client: discord.Client, channel: discord.Channel, user: discord.User,
                         title: str = "Are you sure?", description: str = "", options: tuple = ('y', 'n'),
                         author: dict = None, colour: discord.Color = discord.Color.default(), timeout=30):
    if not isinstance(client, discord.Client):
        raise ValueError("Client must be a discord client.")
    if not isinstance(channel, discord.Channel):
        raise ValueError("Channel must be a discord channel.")
    if not isinstance(user, discord.Member):
        raise ValueError("User must be a discord member.")
    if not isinstance(options, tuple):
        raise ValueError("Options provided must be None or a list.")

    opts = list(options)
    for n, value in enumerate(opts):
        opts[n] = str(value)

    embed = discord.Embed(
        title=title,
        description=description or discord.Embed.Empty,
        colour=colour
    )
    if author:
        embed.set_author(
            name=author.get('name', 'None'),
            icon_url=author.get('icon', '')
        )

    prompt = await client.send_message(
        channel,
        "Do you wish to continue? ({})".format(
            ' | '.join(opts),
        ),
        embed=embed
    )

    res = await client.wait_for_message(
        timeout,
        author=user,
        check=lambda m: m.clean_content.lower() in opts
    )  # type: discord.Message

    try:
        if res:
            await client.delete_messages([prompt, res])
        else:
            await client.delete_message(prompt)
    except Exception as e:
        log.exception(e)

    if not res:
        await client.send_message(
            channel,
            "Dialog timeout. Action cancelled."
        )
        return

    return res

    
@register('nice')
async def nice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'nice.png')

@register('ncie')
async def ncie(message,*args):
    """:point_right: :point_right: ncie"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'ncie.png')

@register('fingergloves')
async def gloves(message, *args):
    """:point_right: :point_right: ncie"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'fingerglovesnice.png')

@register('ncei')
async def nice(message,*args):
    """minkle is bad"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'ncei.png')

@register('nicenice')
async def nicenice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'nicenice.png')

@register('nicenicenice')
async def nicenicenice(message,*args):
    """:point_right: :point_right: nice"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'nicenicenice.gif')

@register('nicerer')
async def nicerer(message,*args):
    """:point_right: :point_right: nicerer"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'nicerer.png')

@register('ricknice')
async def ricknice(message, *args):
    """wubba lubba dub dub"""
    await client.send_file(message.channel,'ricknice.png')

#@register('consent',hidden=True)
#async def consent(message, *args):
#    """age of consent table"""
#    await client.send_message(message.channel, 'https://i.imgur.com/lb1pKXV.png')

@register('tite')
async def tite(message,*args):
    """tite"""
    await client.send_file(message.channel,'tite.png')

@register('walknice')
async def walknice(message,*args):
    """nice"""
    await client.send_message(message.channel, 'https://i.imgur.com/ZLyClkl.gif')

@register('useful')
async def useful(message,*args):
    """is this useful?"""
    await client.send_message(message.channel, 'https://i.imgur.com/rs6fP1D.png')

@register('no', owner=True)
async def randomBytes(message, *args):
    """AAaAAaaAA"""
    n = randint(8, 64)
    m = ""
    if args:
        if args[0].isnumeric():
            n = args[0]
            n = max(0, min(int(n), 1800))
            args = args[1:]
        if args:
            m = " ".join(args)

    await client.send_message(message.channel, m + " " + "".join(chr(randint(1,512)) for i in range(n)))

@register('aaa', '[length]')
async def aaa(message,*args):
    """AAaAAaaAA"""
    n = randint(5, 10)
    if args and args[0].isnumeric():
        n = args[0]
        n = max(0, min(int(n), 256))

    await client.send_message(message.channel, ''.join("A" if randint(0,1) else "a" for i in range(n)))

@register('oh')
async def oh(message,*args):
    """*oh*"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'oh.png')

@register('java')
async def java(message,*args):
    """how many layers of abstraction are you on"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'java.png')

@register('g2a')
async def g2a_is_bad(message,*args):
    """g2a is bad kys"""
    await client.send_message(message.channel,"https://redd.it/5rm2f7/")

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

@register('twice')
async def twice(message, *args):
    """twice, apparently"""
    await client.send_file(message.channel, "twice.png")

@register('doe')
async def doe(message,*args):
    """what you want doe"""
    await client.send_file(message.channel,"doe.png")

@register('pain')
async def pain(message,*args):
    """this man is in pain"""
    await client.send_file(message.channel,"pain.png")

@register('say','<words>',typing=False)
async def tts(message,*args):
    """tts my dude"""
    if len(args) < 1:
        return False
    msg = ' '.join(args)
    try:
        gTTS(msg).save("tts.mp3")

        voice = await join_voice(message)
        if voice:
            player = voice.create_ffmpeg_player('tts.mp3', after=lambda: disconn(client,message.server))
            player.volume = 0.5
            player.start()
    except Exception as e:
        await client.send_message(message.channel, "Couldn't create TTS. Try again later")
        logger.exception(e)

@register('nut')
async def doe(message,*args):
    """nut"""
    await client.send_message(message.channel,"╲⎝⧹╲⎝⧹ :regional_indicator_n: :regional_indicator_u: :regional_indicator_t:  ⧸⎠╱⧸⎠╱")

@register('python')
async def python(message,*args):
    """python"""
    await client.send_file(message.channel,"python.png")

@register('minkle')
async def minkle(message,*args):
    """i am minkle"""
    await client.send_file(message.channel,"minkle.png")

@register('concerned')
async def concerned(message,*args):
    """i am concerned"""
    await client.send_message(message.channel,"https://i.imgur.com/7XeV67N.png")

@register('nudes')
async def nudes(message,*args):
    """send nudes"""
    embed = discord.Embed(color=colour(message.author))
    embed.set_image(url='https://cdn.discordapp.com/attachments/304581721343393793/306484805938446338/sendnudes.png')
    await client.send_message(message.channel,embed=embed)

@register('theme')
async def show_theme(message,*args):
    """what theme bro"""
    embed = discord.Embed(color=colour(message.author))
    embed.set_image(url='https://themork.co.uk/theme.png')
    await client.send_message(message.channel,embed=embed)

@register('shawn',alias='rain')
@register('rain')
async def rain(message,*args):
    """Heavy Rain"""
    shawns = ['http://ci.memecdn.com/8731766.jpg','https://i.ytimg.com/vi/rFhyZG-l5qY/maxresdefault.jpg','http://i.imgur.com/qQhNH8e.jpg']
    await client.send_message(message.channel,shawns[randrange(len(shawns))])

@register('hello')
async def hello_gif(message,*args):
    """hello gif"""
    await client.send_message(message.channel,"https://i.imgur.com/pUlKlro.gif")

@register('sad')
async def sad_plus_one(message,*args):
    """Sad +1"""
    await client.send_file(message.channel, "sad.png")

shawns = glob.glob("shawn*.mp3")
@register('x',typing=False)
async def press_x(message,*args):
    """Press (x) to SHAWN"""
    voice = await join_voice(message)
    if voice:
        player = voice.create_ffmpeg_player(shawns[randrange(len(shawns))], after=lambda: disconn(client,message.server))
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

@register('jpeg','[JPEG quality 1-100]',rate=3,alias='needsmorejpeg')
@register('needsmorejpeg','[JPEG quality 1-100]',rate=3)
async def jpeg(message,*args):
    """adds more jpeg to the last image the app can find"""
    quality = 0
    if len(args) > 0:
        if args[0].isnumeric():
            quality = int(args[0])
    if not 0 < quality < 100:
        quality = 1

    img = await get_last_image(message.channel)
    if img:
        outfile = os.path.join('needsmore.jpeg')
        img.convert("RGB").save(outfile,"JPEG",quality=quality)
        await client.send_file(message.channel,'needsmore.jpeg')
        return
    else:
        await client.send_message(message.channel,'No images found in current channel.')

import imageio
@register('rgif', '<url>', rate=10)
async def random_gif(message, *args):
    """randomize a gif"""

    if len(args) < 1:
        return False

    url = ""
    req = None
    try:
        animated, name, emoji_id = re.findall(r'<(a?):([^:]+):([^:>]+)>',args[0])[0]
        url = "https://cdn.discordapp.com/emojis/{}.{}".format(emoji_id, 'gif' if animated else 'png')
        req = urllib.request.Request(url, headers={"User-Agent": "PedantBot v2.0"})
    except:
        url = str(args[0])
        req = urllib.request.Request(url, headers={"User-Agent": "PedantBot v2.0"})

    res = urllib.request.urlopen(req)
    if res.status != 200:
        await client.send_message(message.channel, "Image could not be downloaded")
        return

    info = res.info()
    if float(info.get("content-length") or 0) > 4000000:
        await client.send_message(message.channel, "File is too large, images must be under 4MB")
        return

    original = imageio.read(res.read())

    frames = []
    for f in original.iter_data():
        frames.append(f)

    with imageio.get_writer("random.gif", duration=0.1) as w:
        for f in sorted(frames, key=lambda a: random()):
            w.append_data(f)

    await client.send_file(message.channel, "random.gif")


import numpy
@register('red',rate=3)
async def needsmorered(message,*args):
    """makes it more red"""
    img = await get_last_image(message.channel)
    img = isolate_channel(img,0)
    img.save("morered.png","PNG")

    await client.send_file(message.channel,"morered.png")

@register('green',rate=3)
async def needsmoregreen(message,*args):
    """makes it more green"""
    img = await get_last_image(message.channel)
    img = isolate_channel(img,1)
    img.save("green.png","PNG")

    await client.send_file(message.channel,"green.png")

@register('blue',rate=3)
async def needsmoreblue(message,*args):
    """makes it more blue"""
    img = await get_last_image(message.channel)
    img = isolate_channel(img,2)
    img.save("blue.png","PNG")

    await client.send_file(message.channel,"blue.png")

@register('white', rate=3)
async def needsmorewhite(message,*args):
    """makes it more white"""
    width = randint(300, 800)
    height = min(500, int(max(width * 0.1, random() * width)))

    img = Image.new("RGB", (width, height), "WHITE")
    f = save(img, "PNG")

    await client.send_file(message.channel, f)


def save(image, format=None):
    stream = io.BytesIO()
    with stream as out:
        image.save(out, format)
        r = out.getvalue()

    return r

@register('collage')
async def make_collage(message,*args):
    """make one of those cancer collages"""
    img = await get_last_image(message.channel)
    x,y = img.size
    if not img: return

    bg = Image.new('RGBA', (x*2,y*2), (0, 0, 0, 255))
    bg.paste(img,(0,0))
    bg.paste(isolate_channel(img,0),(x,0))
    bg.paste(isolate_channel(img,1),(0,y))
    bg.paste(isolate_channel(img,2),(x,y))

    bg.save("collage.png","PNG")
    await client.send_file(message.channel,"collage.png")

@register('everyone')
async def everyone(message,*args):
    """ping everyone"""
    everyone = discord.utils.get(message.server.roles, is_everyone=True)
    if everyone:
        await client.send_message(message.channel, everyone.id)

@register('emoji','<text>')
async def cancer(message,*args):
    """converts your message to emoji"""
    msg = emoji_string(' '.join(args))
    await client.send_message(message.channel,"{}: {}".format(message.author.mention,msg))

@register('die', '<text>')
async def spoiler(message,*args):
    """spoiler all the things"""
    msg = ''.join('||{}||'.format(c) for c in ' '.join(args))
    await client.send_message(message.channel, msg)

@register('image','<text>',rate=5)
async def image_gen(message,*args):
    """draw image with words"""

    if message.content == "/image -f":
        fonts = {os.path.basename(x) for x in glob.glob("/bots/public/fonts/*")}
        embed = discord.Embed(title="Available fonts",description="```\n{}```".format('\n'.join(fonts)),colour=colour(message.author))

        await client.send_message(message.channel, embed=embed)
        return

    if len(args) < 1:
        return False

    args = list(args)

    font = None
    if len(args) > 1 and args[0].startswith("-f="):
        fn = args[0][3:]

        p = fn.split(":")
        fn = p.pop(0)

        pref = 'regular'
        if p:
            pref = p.pop(0)

        size = 18
        if p:
            part = p.pop(0)
            if part.isnumeric():
                size = int(part)

        size = min(100, size)

        font = try_load_font(fn, pref=pref, size=size)
        args.pop(0)

    transparent = False
    if "-T" in args:
        args.remove("-T")
        transparent = True

    input_text = ' '.join(args)
    image = generate_text_image(input_text,str(colour(message.author)),font=font,transparent=transparent)
    image.save('test.png','PNG')
    await client.send_file(message.channel,'test.png',content="{}".format(message.author.mention))

@register('bbren', alias='bren')
@register('bren','<url to image>',rate=10)
async def bren_think(message,*args):
    """creates an image of brendaniel thinking about things"""

    def image_embed(embed):
        return embed.get('type','') == 'image'
    def filtered_messages(msg):
        return msg.author != client.user

    if len(args) < 1:
        return False

    target = message.server.get_member_named(args[0])
    if target is not None:
        fg = Image.open(get(target.avatar_url or target.default_avatar_url))
    else:
        fg = Image.open(get(args[0]))

    bren = Image.open("bren.png").convert("RGBA")
    mask = Image.open("brenback.png").convert("L")

    out = []
    n = fg.n_frames if hasattr(fg, 'n_frames') else 1
    for i in range(n):
        fg.seek(i)
        bg = bren.copy()

        if message.content[1:].startswith('bbren'):
            fg2 = fg.resize((400, 370))
            masked = Image.new("RGBA", bren.size, color=(255, 255, 255))
            masked.paste(fg2, (10, 20))
            masked.putalpha(mask)

            bg.alpha_composite(
                masked
            )

        else:
            MAX = 180
            w2, h2 = scale(*fg.size)

            fg2 = fg.resize((min(w2, MAX), min(MAX, h2)))
            bg.alpha_composite(
                fg2.convert("RGBA"),
                (120 + round((MAX - w2) / 2), 110 + round((MAX - h2) / 2))
            )

        out.append(bg)

    fn = None
    ext = "png"
    if len(out) == 1:
        fn = tempfile()
        out[0].save(fn, "PNG")
    elif len(out) > 1:
        ext = "gif"
        fn = tempfile(ext)
        out[0].save(fn, "GIF", save_all=True, append_images=out[1:], loop=fg.info.get('loop', 0), duration=fg.info.get('duration', 20))

    await client.send_file(message.channel,fn,filename="bren_thinking.{}".format(ext))

    if os.path.isfile(fn):
        os.remove(fn)

@register('rotato','<image url> [rotato amount]',rate=5)
async def rotato(message,*args):
    """rotate image"""
    if len(args) < 1:
        return False

    if len(args) > 1 and args[1].isnumeric():
        rotato = int(args[1])
    else:
        rotato = 180

    try: fg = Image.open(get(args[0]))
    except:
        await client.send_message(message.channel,"I'm sorry {}, I can't let you rotato that image.".format(message.author.mention))
        return
    fg.rotate(rotato).save("rotato.png","PNG")

    await client.send_file(message.channel,"rotato.png",filename="rotato.png")

@register('nicememe',rate=5,typing=False)
async def nicememe(message,*args):
    """say nice meme"""
    user = message.author
    join = args[0].lower() != "s" if len(args) > 0 else True
    join_first = join and (isowner(user) or has_perm(user, "administrator"))

    voice = await join_voice(message, False)
    if voice:
        player = voice.create_ffmpeg_player('/home/mark/Documents/pedant/nicememe.mp3', after=lambda: disconn(client,message.server))
        player.volume = 0.5
        player.start()
    else:
        url = "http://nicememewebsitewebsitewebsitewebsitewebsitewebsitewebsite.website/"
        embed = discord.Embed(
            title=url,
            url=url
        )

        await client.send_message(
            message.channel,
            embed=embed
        )

@register('s',admin=True,typing=False,alias='summon')
@register('summon',admin=True,typing=False)
async def summon(message,*args):
    """summon"""
    if not client.voice_client_in(message.server):
        await join_voice(message)

@register('d',typing=False,alias='disconnect')
@register('disconnect',typing=False)
async def disconnect(message,*args):
    """disconnect"""
    voice = client.voice_client_in(message.server)
    if voice:
        await voice.disconnect()

def disconn(clnt,server):
    voice = clnt.voice_client_in(server)
    if voice:
        asyncio.run_coroutine_threadsafe(voice.disconnect(), clnt.loop).result()

@register('unmute', admin=True)
async def unmute_self(message, *args):
    """unmute self"""
    m = message.mentions
    if len(m) > 0 and message.author.id=='154542529591771136':
        member = m[0]
        await client.server_voice_state(member, mute=False, deafen=False)
        await client.send_message(message.channel, "yes")
    else:
        me = message.server.get_member(client.user.id)
        await client.server_voice_state(me, mute=False, deafen=False)
        


@register('new')
async def new_audio(message,*args):
    """list 5th (or nth) latest audio tracks for `/play`"""
    if len(args) > 0 and args[0].isnumeric(): limit = int(args[0])
    else: limit = 5
    t=datetime.now()
    files = sorted([(datetime.fromtimestamp(os.path.getmtime(x)),x) for x in glob.glob('sounds/*.mp3')], key=lambda f: t-f[0])[:limit]
    embed = discord.Embed(title="Recently Added Audio Files",description="Top {} latest audio files.\n```\n{}```".format(limit,'\n'.join([re.sub(r'sounds\/(.*)\.mp3','\\1',x[1]) for x in files])),color=colour(message.author))    

    await client.send_message(message.channel,embed=embed)

@register('play','<audio track>',typing=False)
async def play_audio(message,*args):
    """play audio in voice channel"""
    if len(args) < 1:
        files = glob.glob('sounds/*.mp3')
        embed = discord.Embed(title="Available Audio Files",description="**NOTE:** Audio tracks longer than 10 seconds require sudo\n",color=colour(message.author))

        tracks = []
        for f in files:
             name = re.sub(r'sounds\/(.*)\.mp3','\\1',f)
             try:
                 track = taglib.File(f)
                 logger.info('file {}'.format(json.dumps(track.tags)))
                 length = track.length
                 desc = track.tags['TITLE'][0]
                 category = track.tags['ALBUM'][0]
             except Exception as e:
                 desc, length, desc, category = name, 0, name, 'General'
                 logger.exception(e)

             tracks.append( (length,name,desc,category) )

        def sort(track):
            return ("aaaaaa" if track[3] == "General" else track[3].lower()),track[1]
        tracks = sorted(tracks,key=sort)
        pad = len(str(len(tracks)))

        msg = await client.send_message(message.channel,embed=embed)
        display = True; o = 0; pp = 25 # number of tracks per page
        pages = round(len(tracks)/pp//1)
        while display:
            tracklist = ""
            previous = ""
            m = ""
            embed.description = "**NOTE:** Audio tracks longer than 10 seconds require sudo\n"
            embed.set_footer(text="PedantBot Audio | {}/{}".format(o+1,pages+1),icon_url=client.user.avatar_url or client.user.default_avatar_url)
            embed.clear_fields()
            for n,track in enumerate(tracks[o*pp:(o+1)*pp]):
                length,name,desc,category = track

                tracklist += "[`{0}`], {1}\n".format(name,("< 0:01" if length < 1 else "{}:{:02.0f}".format(length//60,length%60)))
                if n == pp-1 or (o*pp+n+1) == len(tracks) or category != tracks[o*pp+n+1][3]:
                    embed.add_field(name=category,value=tracklist,inline=False)
                    tracklist = ""
                #tracklist += "{0} [{1[0]}:{1[1]}]\n".format(name,(length//60,length%60))

            embed.description += m
            await client.edit_message(msg,embed=embed)
            await client.add_reaction(msg,'👈');await client.add_reaction(msg,'👉');await client.add_reaction(msg,'🚫')

            def check(reation,user):
                return user != client.user

            listening = True
            res = await client.wait_for_reaction(['👈','👉','🚫'],message=msg,check=check,user=message.author,timeout=30)
            if res:
                emoji = res.reaction.emoji
                #await client.remove_reaction(msg,emoji,res.user)
                if emoji == '🚫':
                    diplay = False
                    await client.delete_message(msg)
                    return
                elif emoji == '👈':
                    if o > 0: o -= 1
                elif emoji == '👉':
                    if o+1 < len(tracks)/pp: o += 1

        return

    if not os.path.isfile(CONF.get('dir_pref','./') + 'sounds/{}.mp3'.format(args[0])):
        await client.send_message(message.channel,'Audio track `{}` not found.'.format(args[0]))
        return

    track = taglib.File('sounds/{}.mp3'.format(args[0]))
    if track.length > 10 and not (isadmin(message.author) or isowner(message.author)):
        await client.send_message(message.channel,'Fuck off that\'s too long')
        return

    try:
        await join_voice(message)
        voice = client.voice_client_in(message.server)
        if voice:
            player = voice.create_ffmpeg_player(CONF.get('dir_pref','./') + 'sounds/{}.mp3'.format(args[0]), after=lambda: disconn(client,message.server))
            player.volume = 0.75
            player.start()
    except Exception as e:
        logger.exception(e)
        await client.send_message(
            message.channel,
            "Could not play audio file: `{}.mp3`, reason: `{}` ".format(args[0], e.__class__.__name__)
        )

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
    logger.debug('skinnn')
    await client.send_message(message.channel, 'https://twitter.com/4eyes_/status/805851294292381696')

@register('this')
async def oh(message,*args):
    """^"""
    await client.send_file(message.channel,CONF.get('dir_pref','./') + 'this.png')

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

    allowedReactions = []
    args = re.split(r' +', stuff[len(q+question+q)+1:])

    logger.info(stuff)
    logger.info(stuff[len(q+question+q)+1:])
    logger.info(args)

    for arg in args:
        try:
            name, eid = re.findall(r'<:([^:]+):([^:>]+)>',arg)[0]
            emoji = discord.utils.get(client.get_all_emojis(), name=name, id=eid) or arg

            if not isinstance(emoji, discord.Emoji):
                if emoji not in UNICODE_EMOJI:
                    continue

            allowedReactions.append(emoji)
        except Exception as e:
            logger.warning("bad emojo: " + arg)
            logger.exception(e)
            continue

    if len(allowedReactions) < 2:
        await client.send_message(message.channel, 'Less than 2 valid emoji/emoji I understand.')
        return False

    logger.info(' -> "' + question + '"')
    logger.info(' -> %s' % ', '.join(str(e) for e in allowedReactions))

    msg = await client.send_message(message.channel, MESG.get('vote_title','"{0}" : {1}').format(question,list(str(e) for e in allowedReactions)))
    digits = MESG.get('digits',['0','1','2','3','4','5','6','7','8','9'])

    for e in allowedReactions:
        await client.add_reaction(msg, e)

    for i in range(10,0,-1):
        tens = round((i - (i % 10)) / 10)
        ones = i % 10
        num = (digits[tens] if (tens > 0) else '') + ' ' + digits[ones]

        await client.edit_message(msg,msg.content + MESG.get('vote_timer','Time left: {0}').format(num))
        await asyncio.sleep(1)

    await client.edit_message(msg,msg.content + MESG.get('vote_ended','Ended.'))
    msg = await client.get_message(msg.channel,msg.id)

    reacts = []
    validReactions = 0

    if len(msg.reactions) < 2:
        await client.send_message(msg.channel,MESG.get('vote_none','Not enough valid votes.'))
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
            winner = sorted(reacts, key=lambda x: -x[1])[0]

            output = graph.draw(reacts,height=5,find=lambda x: x[1])
            output += "\n" + ''.join([x[0] if len(str(x[0])) == 1 else str(reacts.index(x)) for x in reacts])

            await client.send_message(msg.channel,MESG.get('vote_win','"{0}", Winner: {1}').format(question, str(winner[0]), graph=output))
            logger.info(' -> %s won' % reacts[0][0])

quote_users = {'kush':'94897568776982528',
             'david b':'240904516269113344',
             'beard matt':'143529460744978432',
             'dawid':'184736498824773634',
             'jaime':'233244375285628928',
             'oliver':'188672208233693184',
             'orane':'100816656372097024',
             'william':'191332830519885824',
             'shwam3':'154543065594462208',
             'themork':'154542529591771136',
             'wensleydale':'154565902828830720',
             'minkle':'130527313673584640',
             'chris':'192671450388234240',
             'becca':'156902386785452034',
             'dmeta':'221976004745232385',
             'angus':'191596296971354113',
             'josh':'143095406249771009',
             'fistofvalor': '241769932054855690',
             'scott': '129337629299703808',
             'theironpredator': '228640982839721985',
             'anne': '339330915266461718',
             }

@register('scrote','[quote id]',rate=2,alias='quote')
@register('squote','[quote id]',rate=2,alias='quote')
@register('quote','[quote id]',rate=2)
async def quote(message,*args):
    """Embed a quote from https://themork.co.uk/quotes"""
    global quote_users
    logger.debug('Quote')

    try: id = args[0]
    except: id = ''

    cnx = MySQLdb.connect(user='readonly', db='my_themork')
    cursor = cnx.cursor()

    if id == "last":
        cursor.execute("SELECT id,quote,author,date FROM q2 ORDER BY id DESC LIMIT 1")
    else:
        try: cursor.execute("SELECT id,quote,author,date FROM `q2` WHERE `id`=%s ORDER BY RAND() LIMIT 1", (id,))
        except: cursor.execute("SELECT id,quote,author,date FROM `q2` ORDER BY RAND() LIMIT 1")

    if cursor.rowcount < 1:
        cursor.execute("SELECT id,quote,author,date FROM `q2` ORDER BY RAND() LIMIT 1")

    for (id,quote,author,date) in cursor:
        quote = html.unescape(quote)
        users = []
        for author in author.split(","):
            if author.lower() in quote_users:
                try:
                    user = message.server.get_member(quote_users[author.lower()])
                    name = user.name
                except: 
                    user = await client.get_user_info(quote_users[author.lower()])
                    
                if user:
                    users.append(user)

        if message.content.lower().startswith(CONF.get('cmd_pref','') + 's'):
            try:
                gtts.gTTS('{} said "{}"'.format(' and '.join(author.split(",")),quote), lang="en-uk").save("quote.mp3")
            except:
                await client.send_message(message.channel, "lol this command is broke come back later.")
                return

            try:
                await join_voice(message)
                voice = client.voice_client_in(message.server)
                if voice:
                    player = voice.create_ffmpeg_player('quote.mp3', after=lambda: disconn(client,message.server))
                    player.volume = 0.5
                    player.start()
                else:
                    await client.send_message(
                        message.channel,
                        "{} Could not join voice channel. (Are you connected?)".format(message.author.mention)
                    )
            except:
                await client.send_message(
                    message.channel,
                    "Could not read quote #{}".format(id)
                )
                return
        else:
            embed = discord.Embed(
                title='TheMork Quotes',
                description=quote,
                type='rich',
                url='https://themork.co.uk/quotes/?q='+ str(id),
                timestamp=datetime(*date.timetuple()[:-4]),
                color=colour(message.author)
            )
            try:
                embed.set_author(
                    name=', '.join(u.display_name for u in users),
                    icon_url=users[0].avatar_url or users[0].default_avatar_url
                )
            except: embed.set_author(name=author)
            embed.set_footer(text='Quote ID: #' + str(id),icon_url='https://themork.co.uk/assets/main.png')

            await client.send_message(message.channel,embed=embed)
        break

    cursor.close()
    cnx.close()

@register('quotemsg', '<message ID>', rate=2, alias='qm')
async def quote_message(message, *args):
    """quote a message"""
    server = message.server
    channel = message.channel
    user = message.author

    if not args:
        return False

    _message = None
    for chan in set([channel, *server.channels]):
        try: 
            _message = await client.get_message(chan, args[0])  # type: discord.Message
            break
        except (discord.Forbidden, discord.NotFound):
            continue
    if _message is None:
        await client.send_message(channel, "Message not found.")
        return

    embed = discord.Embed(
        color=_message.author.colour,
        description=_message.clean_content,
        timestamp=_message.timestamp
    )

    if _message.attachments:
        embed.set_image(url=_message.attachments[0].get('proxy_url'))
    elif _message.embeds and _message.embeds[0].get('type') == 'image':
        embed.set_image(url=_message.embeds[0].get('url'))
    elif _message.embeds and _message.embeds[0].get('type') == 'rich':
        embed.description += "\n`[Rich Embed not shown]`"

    embed.set_author(
        name=_message.author.name,
        icon_url=_message.author.avatar_url or _message.author.default_avatar_url
    )

    embed.set_footer(
        text="{}#{} | ID: {}".format(
            _message.server.name,
            _message.channel.name,
            _message.id
        ),
        icon_url=_message.server.icon_url
    )

    logger.info(embed.to_dict())

    await client.send_message(
        channel,
        "{user} quoted {sender}".format(user=user, sender=_message.author),
        embed=embed
    )

@register('qsearch','<search term(s)>')
async def search_quotes(message,*args):
    """search quotes by content"""
    global quote_users
    if len(args) < 1: return False
    term = ' '.join(args)
    term2 = "%{}%".format(term)

    cnx = MySQLdb.connect(user='readonly', db='my_themork')
    cursor = cnx.cursor()
    query = "SELECT `id`,`quote`,`author`,`date` FROM `q2` WHERE `quote` LIKE %s or `author` LIKE %s"
    cursor.execute(query, (term2, term2))

    embed = discord.Embed(title="Quotes matching '{}'".format(term),color=colour(message.author))
    msg = ""
    for (id,quote,author,date) in cursor:
        if cursor.rowcount == 1:
            if author.lower() in quote_users:
                try:
                    user = message.server.get_member(quote_users[author.lower()])
                    name = user.name
                except: user = await client.get_user_info(quote_users[author.lower()])

            embed = discord.Embed(title='TheMork Quotes',
                                description=quote,
                                type='rich',
                                url='https://themork.co.uk/quotes/?q='+ str(id),
                                timestamp=datetime(*date.timetuple()[:-4]),
                                color=colour(message.author)
            )
            try: embed.set_author(name=user.display_name,icon_url=user.avatar_url or user.default_avatar_url)
            except: embed.set_author(name=author)
            embed.set_footer(text='Quote ID: #' + str(id),icon_url='https://themork.co.uk/assets/main.png')
        else: msg += "[`#{0}`](https://themork.co.uk/quotes/{0}/) - \"{1:.75}\" - _{2:.32}_\n".format(id,quote,author)

    if cursor.rowcount > 1: embed.description = msg
    await client.send_message(message.channel,embed=embed)

    cursor.close()
    cnx.close()

@register('cal')
async def calendar(message,*args):
    """Displays a formatted calendar"""
    today = datetime.now()
    embed = discord.Embed(title='Calender for {0.month}/{0.year}'.format(today),
        description='```\n{0}\n```'.format(cal.month(today.year,today.month)),
        color=colour(message.author))
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 120))

@register('roll','<dice eg. 2d8+3>')
async def dice_roll(message,*args):
    """roll a die or dice"""
    args = list(args)
    name = []
    clean = []
    summary = False

    for arg in args:
        if arg.lower() == "-s":
            summary = True
            continue

        if not (
            arg[0].isnumeric() or
            arg[0] == 'd' and arg[1].isnumeric()
        ):
            name.append(arg)
        else:
            clean.append(arg)
    name = ' '.join(name)
    clean = ' '.join(clean)

    rolls = roll_dice(clean or "d20")
    if not rolls:
        await client.send_message(message.channel,"{}, you requested an invalid die/dice.".format(message.author.mention))
        return

    msg = ''
    for roll in rolls:
        if summary:
            msg += "• `{}` total: `{}` : `{}`\n".format(roll[0], repr(roll[1]), ', '.join(repr(x) for x in roll[2]))
        else:
            msg += "• `{}` total: `{}`\n".format(*roll)

    embed = discord.Embed(title="{} rolls {} {}.".format(message.author, len(rolls), name or ('die' if len(rolls) == 1 else 'dice')), description=msg, colour=colour(message.author), timestamp=message.timestamp)
    embed.set_footer(icon_url="https://themork.co.uk/wiki/images/4/4c/Dice.png",text="PedantBot Dice")

    await client.send_message(message.channel,embed=embed)

@register('shard')
async def get_shard(message,*args):
    """find out which shard is connected to the current server"""
    await client.send_message(message.channel,"**`{server}`** is connected to shard `{shard}/{shards}`".format(server=message.server,shard=SHARD_ID+1,shards=SHARD_COUNT))

@register('id','[DiscordTag#0000] [server ID]',owner=True)
async def get_user_id(message,*args):
    """get User ID by DiscordTag#0000"""
    if len(args) == 0:
        target  = message.author
    elif len(args) == 1:
        target = message.server.get_member_named(args[0]) or await client.get_user_info(args[0])
    elif len(args) == 2:
        target = client.get_server(args[1]).get_member_named(args[0])

    await client.send_message(message.channel, "{} ({})'s ID is `{}`".format(target.name, ' '.join(str(ord(x)) for x in target.name),target.id))

@register('servers',owner=True)
async def connected_servers(message,*args):
    """Lists servers currently connected"""

    #servers = ['•   __{owner.name}\'s__ **{server.name}** (`{server.id}`)'.format(owner=x.owner,server=x) for x in client.servers]

    #embed = discord.Embed(title='Servers {0} is connected to.'.format(client.user),
    #                      colour=colour(message.author),
    #                      description='\n'.join(servers))
    #msg = await client.send_message(message.channel,embed=embed)
    #asyncio.ensure_future(message_timeout(msg, 120))


    channel = message.channel

    body = ""
    displayed = 0

    PAGE_SIZE = 8
    pages = math.ceil(len(client.servers) / PAGE_SIZE)
    page = 0

    if args:
        page = int(args[0]) if args[0].isnumeric() else 0

    page = max(0, min(page, pages))

    frm = (page) * PAGE_SIZE
    to  = (page+1) * PAGE_SIZE

    for n, server in enumerate(client.servers):
        if n < frm:
            continue
        if n >= to:
            break
 
        temp = '•   __{0}\'s__ **{1}** ([{server.id}](https://themork.co.uk/code?code={server.id}))\n'.format(
            clean_string(server.owner.name),
            clean_string(server.name),
            server=server
        )
        if len(body) + len(temp) <= 1500:
            body += temp
        else:
            body += "{} more ...".format(len(client.servers) - displayed)
            break
 
    embed = discord.Embed(
        title='Servers {0} is connected to (pg. {1}/{2})'.format(client.user, page, pages-1),
        colour=discord.Colour.purple(),
        description=body
    )

    await client.send_message(
        channel,
        embed=embed
    )

@register('channels',owner=True)
async def connected_channels(message,*args):
    """Displays a list of channels and servers currently available"""
    servers = [c for c in client.servers]

    currentServer = servers[0]
    currentIndex = servers.index(currentServer)

    embed = discord.Embed(title='Channels {user.name} is conected to. ({0})'.format(len(servers),user=client.user),
                          colour=colour(message.author),
                          description="\n".join([('• [`{channel.id}`] **{channel.name}**'+(' "{topic}"' if x.topic and x.topic.strip() != '' else '')).format(channel=x,topic=(x.topic or '').replace('\n','')) for x in currentServer.channels if x.type == discord.ChannelType.text])
                         )
    embed.set_footer(text=('<- {:.24} | '.format(servers[currentIndex -1].name) if currentIndex > 0 else '') + '{:.24}'.format(currentServer.name) + (' |  {:.24} ->'.format(servers[currentIndex + 1].name) if currentIndex < len(servers)-1 else ''))
    if currentServer.icon_url: embed.set_thumbnail(url=currentServer.icon_url)

    msg = await client.send_message(message.channel, embed=embed)
    await client.add_reaction(msg,'👈')
    await client.add_reaction(msg,'👉')
    await client.add_reaction(msg,'🚫')

    def check(reation,user):
        return user != client.user

    listening = True
    while listening:
        res = await client.wait_for_reaction(['👈','👉','🚫'],message=msg,check=check,user=message.author,timeout=30)
        if res:
            emoji = res.reaction.emoji

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

            embed = discord.Embed(
                title="Channels in {server.name}".format(server=currentServer),
                colour=colour(message.author),
                description= '\n'.join(
                    ('• [`{channel.id}`] **{channel.name}**'+(' "{topic}"' if x.topic and x.topic.strip() != '' else '')).format(
                        channel=x,
                        topic=(x.topic or '').replace('\n','')
                    ) for x in currentServer.channels if x.type == discord.ChannelType.text
                )
            )

            embed.set_footer(
                text=('Prev: {:.24} | '.format(servers[currentIndex -1].name) if currentIndex > 0 else '') + 'Current: {:.24}'.format(currentServer.name) + (' |  Next: {:.24}'.format(servers[currentIndex + 1].name) if currentIndex < len(servers)-1 else '')
            )
            embed.set_thumbnail(url=currentServer.icon_url)
            await client.edit_message(msg, embed=embed)
        else:
            listening = False
    try:
        await client.clear_reactions(msg)
    except:
        pass

@register('botratio')
async def bot_ratio(message,*args):
    """list ratio of bots to humans"""
    server = message.server
    channel = message.channel
    user = message.author

    humans = 0; bots = 0
    for member in server.members:
        if member.bot: bots += 1
        else: humans += 1

    if humans > bots:
        short_string = "{server}'s human:bot ratio"
        string = "The ratio of humans to bots is: __{humans}:{bots}__\nThat means there is about {ratio:.1f}x as many humans as bots."
        ratio = humans / bots
        icon = "hooman"
    else:
        short_string = "{server}'s bot:human ratio"
        string = "The ratio of bots to humans is: __{bots}:{humans}__\nThat means there is about {ratio:.1f}x as many bots as humans."
        ratio = bots / humans
        icon = "robit"

    embed = discord.Embed(
        description=string.format(
            server=server,
            humans=humans,
            bots=bots,
            ratio=ratio
        ),
        colour=user.colour
    )
    embed.set_author(
        name=short_string.format(
            server=server
        ),
        icon_url=server.icon_url
    )
    embed.set_thumbnail(url='https://themork.co.uk/assets/{}.png'.format(icon))

    await client.send_message(
        channel,
        embed=embed
    )

@register('roles', '[user]', owner=True, alias='ranks')
@register('ranks', '[user] [page]', owner=True)
async def server_ranks(message,*args):
    """Displays a list of ranks in the server"""
    #embed = discord.Embed(colour=colour(message.author))
    #embed.set_author(name='Ranks for {server.name}.'.format(server=message.server), icon_url=message.server.icon_url)
    #for role in sorted(message.server.roles,key=lambda r: -r.position):
    #    if not role.is_everyone:
    #        members = ['•   **{user.name}** (`{user.id}`)'.format(user=x) for x in message.server.members if role in x.roles]
    #        if len(members) > 0:
    #            embed.add_field(name='__{role.name}__ ({role.colour} | `{role.id}`)'.format(role=role), value='\n'.join(members), inline=False)

    server = message.server
    channel = message.channel
    user = message.author

    target = server
    if message.mentions:
        target = message.mentions[0]
    elif args:
        target = server.get_member_named(args[0]) or server.get_member(args[0])
        if target is None and args[0].lower() == "server":
            target = server
    
    if target is None:
        await client.send_message(message.channel, "No user found.")
        return

    PAGE_SIZE = 12

    page = 1
    r = len(target.roles)
    pages = math.ceil(r / PAGE_SIZE)

    if len(args) > 1 and args[1].isnumeric:
        arg = int(args[1])
        if arg <= pages:
            page = arg

    start = PAGE_SIZE * (page-1)
    end = PAGE_SIZE * page + 1

    roles = sorted(target.roles, key=lambda r: -r.position)[start:end]

    pad = 0
    for role in roles:
        if role.is_everyone:
            continue

        size = len(role.name)
        if size > pad:
            pad = size

    members = {}
    for member in server.members:
        for role in member.roles:
            if role.is_everyone:
                continue

            if role.id not in members:
                members[role.id] = 0
            members[role.id] += 1

    msg = "Roles in {} (pg. {}/{})\n".format(target, page, pages)
    for role in roles:
        if role.is_everyone:
            continue

        msg += "`[{role.id}] {name:<{pad}} {role.colour} hoist: {role.hoist} ({members:,})`\n".format(
            pad=pad + 1,
            role=role,
            name=('@' if role.mentionable else '') + role.name,
            members=members.get(role.id, 0)
        )

    logger.info(msg)
    msg = await client.send_message(
        message.channel,
        msg
    )
    asyncio.ensure_future(message_timeout(msg, 180))

@register('members')
async def list_members(message,*args):
    """list the memebers in a server"""
    msg = ""
    if len(args) == 0: server = message.server
    else:
        server = client.get_server(args[0])
        if not server:
            await client.send_message(message.channel,"Could not found a server with that ID")
            return

    if len(args) > 1:
        try: page = int(args[1])
        except: page = 1
    else:
        page = 1

    for member in sorted(list(server.members)[page*10:(page+1)*11], key=lambda m: -m.top_role.position):
        msg += "• {role}**{member}** `{perms}`\n".format(member=re.sub(r'([`~*_])',r'\\\1',str(member)),perms=member.server_permissions.value,role="[`{}`] ".format(re.sub(r'([`~*_])',r'\\\1',str(member.top_role))) if not member.top_role.is_everyone else "")

    embed = discord.Embed(colour=colour(message.author), description=msg)
    embed.set_author(name="Members in {}".format(server),icon_url=server.icon_url)
    embed.set_footer(text="Page {}/{}".format(page, math.ceil(len(server.members)/10)))
    msg = await client.send_message(message.channel, embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('age', '[local]', rate=10)
async def age(message,*args):
    """Get user's Discord age"""
    users = message.server.members
    local = args[0] in ["local", "-local"] if args else False
    flip = local and args[0][0] == "-"
    now = datetime.now()

    def age(user=discord.User()):
        if (local and hasattr(user, 'joined_at')):
            return user.joined_at
        else:
            return discord.utils.snowflake_time(user.id)

    string = ''
    users = sorted([x for x in users if not x.bot], key=age)
    for n,user in enumerate(sorted(users,key=age)[:20]):
        user.name = re.sub(r'([`*_])',r'\\\1',user.name)
        if local:
            u = age(user)
            compare = (u - discord.utils.snowflake_time(message.server.id)) if flip else (now - u)
            string += '{n:>2}.  **{user}**: `{date}`\n'.format(n=n+1, user=user, date=diff(compare.total_seconds()))
        else:
            string += '{n:>2}.  **{user}**: joined Discord on `{date}`\n'.format(n=n+1, user=user, date=age(user).strftime('%d %B %Y @ %I:%M%p'))

    embed = discord.Embed(title="Age of users in {server.name}".format(server=message.server),
        color=colour(message.author),
        description=string)

    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 180))

@register('lastfm')
async def lastfm_week(message, *args):
    """View weekly last.fm charts"""
    pass


@register('purge','[message limit]',rate=5)
async def purge(message,*args):
    """delete all messages"""
    deleted = []
    limit = 500
    if len(args) > 0 and args[0].isnumeric():
        limit = int(args[0])
    if isadmin(message.author) or isowner(message.author) and message.server.id != '154543502313652224':
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

@register('status',owner=True)
async def set_status(message,*args):
    """set bot playing status"""
    if args[0] == "offline":
        msg = "Stealth mode engaged."
        await client.change_presence(game=None, status=discord.Status.offline)
        await client.send_message(message.channel, msg)
        return

    pattern = re.compile(r'^/status ?(?:([A-z]*?):([0-9])? )?(.*)$')
    args = pattern.match(message.clean_content).groups()

    text = args[2] or None
    if text.lower() == "none": text = None
    if text:
        status_type = args[0] or discord.Status.online
        game_type = int(args[1] or 0)
    else:
        status_type = None
        game_type = None

    current = message.server.me.game
    if text is current or (hasattr(current, 'name') and current.name == text):
        msg = "Status not changed."
        return
    elif text:
        msg = "Updated status: {}".format(text)
    else:
        msg = "Cleared status."

    if '{users' in text:
        logger.info("Updating user cache")
        client.users = set()
        for server in client.servers:
            if server.large:
                await client.request_offline_members(server)
            for user in server.members:
                client.users.add( (user.id,str(user)) )

    format_data = {
        'servers': len(client.servers),
        'users':   len(client.users),
        'shardid': SHARD_ID+1,
        'shards':  SHARD_COUNT,
    }

    await client.change_presence(game=discord.Game(name=text.format(**format_data), type=game_type), status=status_type)
    await client.send_message(
        message.channel,
        msg
    )

@register('e')
async def perms_channel(message,*args):
    """List permissions available to this  bot"""
    comp = None
    name = ''.join(args)

    member = message.author
    perms = message.channel.permissions_for(member)
    granted = []
    denied = []
    for perm in perms:
        name = perm[0]
        field = granted if perm[1] else denied
        field.append(name)

    embed = discord.Embed(
        colour=colour(message.author)
    )
    embed.set_author(
        name="Perms for {user.name} in {server.name}".format(
            user=member,
            server=member.server
        ),
        icon_url=member.avatar_url or member.default_avatar_url,
        url='https://discordapi.com/permissions.html#{}'.format(perms.value)
    )
    if len(granted) > 0:
        embed.add_field(
            name="Permissions Granted",
            value="```{}```".format('\n'.join(granted)),
            inline=True
        )
    if len(denied) > 0:
        embed.add_field(
            name="Permissions Denied",
            value="```{}```".format('\n'.join(denied)),
            inline=True
        )

    msg = await client.send_message(
        message.channel,
        embed=embed
    )

@register('perms',admin=True)
async def perms(message,*args):
    """List permissions available to this  bot"""
    comp = None
    name = ''.join(args)

    try: member = message.server.get_member_named(name)
    except: member = None
    if not member: member = message.server.get_member(message.mentions[0].id if len(message.mentions) > 0 else client.user.id)

    perms = message.channel.permissions_for(member)
    granted = []
    denied = []
    for perm in perms:
        name = ' '.join(word.capitalize() for word in perm[0].split('_')).replace('Tts','TTS')
        field = granted if perm[1] else denied
        field.append(name)

    embed = discord.Embed(
        colour=colour(message.author)
    )
    embed.set_author(
        name="Perms for {user.name} in {server.name}".format(
            user=member,
            server=member.server
        ),
        icon_url=member.avatar_url or member.default_avatar_url,
        url='https://discordapi.com/permissions.html#{}'.format(perms.value)
    )
    if len(granted) > 0:
        embed.add_field(
            name="Permissions Granted",
            value="```{}```".format('\n'.join(granted)),
            inline=True
        )
    if len(denied) > 0:
        embed.add_field(
            name="Permissions Denied",
            value="```{}```".format('\n'.join(denied)),
            inline=True
        )

    msg = await client.send_message(
        message.channel,
        embed=embed
    )

    asyncio.ensure_future(message_timeout(msg, 120))

@register('hole','@<mention users>',admin=True,typing=False)
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

@register('moverole','<role name> <position>',owner=True)
async def move_role(message,*args):
    """moves a role in the server to a given position"""
    if len(args) < 2: return False
    if args[1].isnumeric(): position = int(args[1])
    else: return False

    try: role = discord.utils.find(lambda r: r.name == args[0],message.server.roles)
    except Exception as e:
        await client.send_message(message.channel,"Role `{}` not found.".format(args[0]))
        logger.exception(e)
        return

    try:
        await client.move_role(message.server,role,position)
        await client.send_message(message.channel,"Moved `{}` to position `{}`".format(role.name,position))
    except Exception as e:
        await client.send_message(message.channel,"Could not move role")
        logger.exception(e)

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

    embed = discord.Embed(title="Banned users in {0.name}".format(message.server),color=colour(message.author),description=str)
    msg = await client.send_message(message.channel,embed=embed)
    asyncio.ensure_future(message_timeout(msg, 60))

@register('fkoff',owner=True,alias='restart',typing=False)
@register('restart',owner=True,typing=False)
async def fkoff(message,*args):
    """Restart the bot"""
    logger.warn('Shutting down...')
    await client.send_message(message.channel, MESG.get('shutdown','Shutting down.'))

    await client.logout()

    try:
        sys.exit()
    except Exception as e:
        pass

@register('calc','<expression>',rate=1)
async def do_calc(message,*args):
    """Perform mathematical calculation: numbers and symbols (+-*/) allowed only"""
    logger.debug('Calc')

    if len(args) < 1:
        return False

    maths = ''.join(args)

    if (re.findall('[^0-9\(\)\/\*\+-\.]+',maths) != []):
        await client.send_message(message.channel, MESG.get('calc_illegal','Illegal chars in {0}').format(maths))

    else:
        logger.debug(' -> ' + str(maths))
        try:
            ans = calculate(maths)
            await client.send_message(message.channel,'`{} = {}`'.format(maths,"Life, the Universe and Everything" if ans == 42 else ans))
        except Exception as e:
            logger.exception(e)
            await client.send_message(message.channel, MESG.get('maths_illegal','Error in {0}').format(maths))

@register('skinnn','',rate=1,alias='skin')
@register('skinn','',rate=1,alias='skin')
@register('skin','',rate=1)
async def skinn_link(message,*args):
    logger.debug('skinnn')

    await client.send_message(message.channel, 'https://twitter.com/4eyes_/status/805851294292381696')

"""Utility functions"""
def diffTuple(t):
    a = [31536000, 2592000, 604800, 86400, 3600, 60, 1, 0.001]
    b = ['Y', 'M', 'W', 'd', 'h', 'm', 's', 'ms']

    d = []
    for e in a:
        f = t // e
        t -= f * e
        d.append(f)

    return list(zip(d,b))


def diff(t):
    e = diffTuple(t)
    return ' '.join('{:.0f}{}'.format(*f) for f in e if all(f))


def clean_string(unclean, whitelist="", blacklist="`*_~", remove="") -> str:
    """

    :param unclean: str | List[str]
    :param whitelist: str | List[str]
    :param blacklist: str | List[str]
    :param remove: str | List[str]
    :return: str
    """
    base = unclean
    try:
        base = str(unclean)
    except Exception as e:
        log.debug(e)
        base = str(
            getattr(
                unclean,
                (
                    discord.utils.get(dir(base), check=lambda k: not k.startswith('__'))
                    or
                    [base.__class__.__name__]
                )[0]
            )
        )  # type: str

    clean_chars = ''.join({'*', '`', '~', '_'}.difference(whitelist).intersection(blacklist))
    if remove != "":
        clean = re.sub(r'(['+remove+'])', r'', base)
    else:
        clean = base
    clean = re.sub(r'(['+clean_chars+'])', r'\\\1', clean)
    return clean


def colour(user):
    """get user colour properly"""
    for role in sorted(user.roles, key=lambda r: -r.position):
        if role.colour.value:
            return role.colour

    return discord.Colour.default()

def tempfile(ext="png"):
    return '{}.{}'.format(hashlib.sha1(os.urandom(8)).hexdigest(), ext)

def time_diff(t_from,t_to):
    """returns a human-readable time difference"""
    timedelta = t_to - t_from
    seconds = timedelta.days * 86400 + timedelta.seconds
    deltas = (seconds // (86400*365), seconds // 86400, seconds // 3600, seconds // 60, seconds)

    unit = -1
    for i in range(5):
        if deltas[i] > 0:
            unit = i
            break
    units = ['year','day','hour','minute','second']
    string = "{} {}".format(deltas[unit],units[unit]) + ('s' if deltas[unit] != 1 else '')

    return string

def get_time(when:str="") -> str:
    now = datetime.now()
    if not when: when = now.isoformat()
    then = parse(when)
    return time_diff(now,then)

emoji = { '0':':zero:', '1':':one:', '2':':two:', '3':':three:', '4':':four:', '5':':five:', '6':':six:', '7':':seven:', '8':':eight:', '9':':nine:', '!':':exclamation:', '?':':question:', 'a': ':regional_indicator_a:', 'b': ':regional_indicator_b:', 'c': ':regional_indicator_c:', 'd': ':regional_indicator_d:', 'e': ':regional_indicator_e:', 'f': ':regional_indicator_f:', 'g': ':regional_indicator_g:', 'h': ':regional_indicator_h:', 'i': ':regional_indicator_i:', 'j': ':regional_indicator_j:', 'k': ':regional_indicator_k:', 'l': ':regional_indicator_l:', 'm': ':regional_indicator_m:', 'n': ':regional_indicator_n:', 'o': ':regional_indicator_o:', 'p': ':regional_indicator_p:', 'q': ':regional_indicator_q:', 'r': ':regional_indicator_r:', 's': ':regional_indicator_s:', 't': ':regional_indicator_t:', 'u': ':regional_indicator_u:', 'v': ':regional_indicator_v:', 'w': ':regional_indicator_w:', 'x': ':regional_indicator_x:', 'y': ':regional_indicator_y:', 'z': ':regional_indicator_z:', 'dog':'🐶', 'cat':'🐱', 'mouse':'🐭', 'rabbit':'🐰', 'bear':'🐻', 'koala':'🐨', 'tiger':'🐯', 'lion':'🦁', 'cow':'🐮', 'pig':'🐷', 'frog':'🐸', 'octopus':'🐙', 'money':'🐵', 'peguin':'🐧', 'chicken':'🐔', 'bird':'🐦', 'wolf':'🐺', 'horse':'🐴', 'bee':'🐝', 'turtle':'🐢', 'snake':'🐍', 'crab':'🦀', 'fish':'🐟', 'dolphin':'🐬', 'whale':'🐳', 'crocodile':'🐊', 'leopard':'🐆', 'elephant':'🐘',}

def emoji_string(string: str = "") -> str:
    msg = ""; string2 = ""
    for word in string.split():
        string2 += (emoji.get(word,word) if len(word) > 1 else word) + " "

    for character in string2:
        this = emoji.get(character.lower(), character+" ")
        if len(msg) + len(this) <= 1900:
            msg += this
    return msg

def c(s,d=0,t=int):
    try:
        return t(s)
    except:
        try:
            return t(d)
        except:
            return None

def roll_dice(inp:str="") -> list:
    rolls = []
    for throw in inp.split():
        try: 
            #die = re.findall(r'^([0-9]*)(?=[Dd])[Dd]?([0-9]+)*(?:([+-]?[0-9]*))$', throw)
            die = re.findall(r'^(?:([0-9]*)(?=[Dd]))?[Dd]?([0-9]+)*(?:([+-]?[0-9]*))$', throw)
        except Exception as e:
            logger.warn("Invalid die: " + throw)

        for (n,d,m) in die:
            n = abs(c(n, 1) or 0)
            d = abs(c(d, 20) or 0)
            m = c(m)

            if d < 1: continue
            if n < 1: continue
            if m > 0 and d < 1: continue

            if n > 100 or d > 500 or abs(m) > 100: continue

            string = "{}d{}{:+}".format(n,d,m)
            roll = []

            for i in range(n):
                roll.append(randint(1, d))

            data = (string, sum(roll) + m, tuple(roll))
            rolls.append( data )
    return rolls

def isolate_channel(image,channel=0):
    """removes all but one channel from an image"""
    a = numpy.array(image)
    channels = [x for x in [0,1,2] if x != channel]
    for i in channels: 
        try: a[:,:,i] *= 0
        except: pass

    return Image.fromarray(a)


def is_image_embed(embed):
    return embed.get('type','') == 'image'

def not_me(msg):
    return msg.author != client.user

async def get_last_image(channel):
    """returns last image posted in channel"""
    async for msg in client.logs_from(channel,limit=50,reverse=False):
        try:
            images = list(filter(is_image_embed,msg.embeds))
            if (len(msg.attachments) > 0 or len(images) > 0):
                url = images[0].get('url','') if len(images) > 0 else msg.attachments[0]['proxy_url']
                if (int(requests.head(url,headers={'Accept-Encoding': 'identity'}).headers['content-length']) / 1024 / 1024) >= 8:
                    await client.send_message(message.channel,'Image is too large.')
                    return
                attachment = get(url)
                content_type = attachment.headers.get_content_type()
                if 'image' in content_type:
                    img_file = io.BytesIO(attachment.read())
                    img = Image.open(img_file)
                    return img
        except: return None

def server_icon(server):
    """return better url for server than discord.Server.icon_url"""
    return "https://cdn.discordapp.com/icons/{server.id}/{server.icon}.webp".format(server=server) if server.icon_url else None 

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
    if discord.Member: permissions = permissions.server_permissions
    if not isinstance(permissions,discord.Permissions): return False
    if isinstance(required,str): required = required.split(',')
    if isinstance(required,discord.Permissions): return permissions >= required
    if not required: return True

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

users={}
async def do_record(message=None):
    """scores points for user on message"""
    if message.author.bot: return
    last = users.get((message.author.id,message.server.id),0)
    now = datetime.now().timestamp()
    if last+60 < now:
       users[(message.author.id,message.server.id)] = now
    else: return

    cursor = pedant_db.cursor()
    increment_xp = randrange(5,30)
    #cursor.execute("INSERT INTO `pedant`.`levels` (`xp`,`user_id`, `guild_id`) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE xp = xp+%s", (increment_xp, message.author.id, message.server.id, increment_xp))
    #pedant_db.commit()

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
        logger.info(' -> ' + reminder.get('user_id', 'nobody') + ': ' + reminder.get('message', 'empty msg'))

        mentions = []
        mention_ids = [reminder.get('user_id', '')] + reminder.get('mentions', [])

        #await client.send_message(client.get_channel(reminder['channel_id']), reminder.get('user_id') + ': ' + reminder['message'])
        try:
            chan = client.get_channel(reminder.get('channel_id'))
            server = chan.server
            user = server.get_member(reminder.get('user_id'))
            
            for mention in mention_ids:
                member = server.get_member(mention)
                if member:
                    mentions.append(member.mention)

        except Exception as e:
            logger.exception(e)
            user = discord.User(id="0", discriminator="0000")
            user.name = "Unknown User"

        logger.info(reminder)

        d = datetime.fromtimestamp(reminder.get('time', 0))
        embed = discord.Embed(
            description=reminder['message'], 
            timestamp=d, 
            color=user.color if hasattr(user, 'color') else discord.Color.default()
        )

        embed.set_footer(
            text="PedantBot Reminders",
            icon_url=client.user.avatar_url or client.user.default_avatar_url
        )

        embed.set_author(
            name="{}'s reminder for {}".format(user.display_name, d.strftime('%I:%M%p %Z(GMT%z)')),
            icon_url=user.avatar_url or user.default_avatar_url
        )

        await client.send_message(
            client.get_channel(reminder.get('channel_id')),
            content=', '.join(mentions) if mentions else None,
            embed=embed
        )

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

async def join_voice(message, join_first=False):
    """join the nearest voice channel"""
    clnt = client.voice_client_in(message.server)
    if clnt:
        return clnt
    else:
        server = message.server
        channels = server.channels
        channel = None
        first_non_empty = None
        for chan in server.channels:
            if channel:
                break
            for user in chan.voice_members:
                if user == message.author:
                    channel = chan
                    break

                if not first_non_empty:
                    first_non_empty = chan

        if not channel:
            if first_non_empty and join_first:
                channel = first_non_empty
            else:
                return False

        connected = await client.join_voice_channel(channel)
    return connected

def try_load_font(fn=None, size=18, pref="regular"):
    variants = ["regular","light","bold","italic","bolditalic"]
    methods = {"ttf": ImageFont.truetype, "otf": ImageFont.FreeTypeFont}

    fb = ImageFont.truetype('NotoMono-Regular.ttf', size)

    font = None
    if fn is not None:
        if pref not in variants:
            pref = variants[0]

        variants.remove(pref)
        variants.insert(0, pref)

        for variant in variants:
            for ext,method in methods.items():
                try:
                    p = "/bots/public/fonts/{}/{}.{}".format(fn, variant, ext)
                    font = method(p, size)
                    
                    return font
                except Exception as e:
                    logger.exception(e)
                    font = None

    return fb

def generate_text_image(input_text="",colour='#ffffff',font=None,transparent=False):
    """returns Image with text in it"""
    if '\n' in input_text:
        wrap_text = input_text.splitlines()
    else:
        wrap_text = textwrap.wrap(input_text, width=30)
    current_h, pad = 10, 10
    colour = colour.replace('#','')

    MAX_W, MAX_H = 200, 200
    im = Image.new('RGB', (1,1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)

    if font is None:
        font = try_load_font(font, 18)

    MAX_W = sorted([draw.textsize(x, font=font)[0] for x in wrap_text],key=lambda w: -w)[0] + 2*pad
    MAX_H = (draw.textsize(wrap_text[0], font=font)[1]) * len(wrap_text) + 2*pad
    im = Image.new('RGB',(MAX_W+20, MAX_H), (0, 0, 0, 0))
    im = Image.new('RGBA', (MAX_W, MAX_H), (0, 0, 0, 0 if transparent else 255))
    draw = ImageDraw.Draw(im)

    def text_outline(draw,text="",x=0,y=0,fill="white",stroke="black",thickness=1):
        """draw text with stroke"""
        coords = [(x+thickness,y),(x-thickness,y),(x,y+thickness),(x,y-thickness)]
        for loc in coords:
            draw.text(loc,text,stroke,font)
        draw.text((x,y),text,fill,font)

    for line in wrap_text:
        w, h = draw.textsize(line, font=font)
        draw.text(((MAX_W - w) / 2, current_h), line, font=font,fill=struct.unpack('BBB',bytes.fromhex(colour)))
        current_h += h

    return im

"""Exit procedure"""
@atexit.register
def save_reminders():
    """Save all in-memory reminders to file"""
    str = ''
    rems = []
    for rem in reminders[:]:
        rems.append({'user_name':rem['user_name'], 'user_mention':rem.get('user_mention'), 'invoke_time':rem['invoke_time'], 'time':rem['time'], 'channel_id':rem['channel_id'], 'message':rem['message'], 'is_cancelled':rem['is_cancelled']})
    for rem in rems:
        rem['task'] = None
        str += json.dumps(rem, sort_keys=True, skipkeys=True) + '\n'
    with open(CONF.get('dir_pref','./')+'reminders.txt', 'w') as file:
        file.write(str)

"""Load reminders from file into memory"""
reminders = []
if os.path.isfile(CONF.get('dir_pref','./')+'reminders.txt'):
    with open(CONF.get('dir_pref','./')+'reminders.txt') as file:
        for line in file:
            try:
                reminders.append(json.loads(line))
            except json.decoder.JSONDecodeError as e:
                logger.error('JSON Error:')
                logger.exception(e)

"""Import definition overrides"""
special_defs = {}
if os.path.isfile(CONF.get('dir_pref','./')+'special_defs.txt'):
    with open(CONF.get('dir_pref','./')+'special_defs.txt') as file:
        for line in file:
            if line.find(':') < 0:
                continue
            line = line.split(':',1)
            special_defs[line[0].lower()] = line[1].replace('\n','')

"""Update bot status: "Playing Wikipedia: Albert Einstein"""
async def update_status(cln):
    statuses = [
        (lambda : ("Wikipedia: " + wikipedia.random(pages=1)), 0),
        ("{users:,} users in {servers:,} servers", 3),
        ("{users:,} users", 2)
    ]

    game_type = 0
    default = "Shard {shardid:,}/{shards:,} | {users:,} users in {servers:,} servers"
    try:
        if not statuses: status = default
        if hasattr(cln, 'override') and cln.override is not None:
            raise RuntimeError("Status overridden")
        else:
            status_text, game_type = statuses[randrange(len(statuses))]
            try:
                if type(lambda: "") == type(status_text): status_text = status_text()
            except: pass

            if not isinstance(status_text, str): status_text = default

        if '{users' in status_text:
            logger.info("Updating user cache")
            cln.users = set()
            for server in cln.servers:
                for user in server.members:
                    cln.users.add( (user.id,str(user)) )

        format_data = {
            'servers':len(cln.servers),
            'users':len(cln.users),
            'shardid':SHARD_ID+1,
            'shards':SHARD_COUNT,
        }
        try: status_message = status_text.format(**format_data)
        except: status_message = default.format(**format_data)

        await cln.change_presence(game=discord.Game(name=status_message, type=game_type), afk=False, status=discord.Status.online)
    except Exception as e:
        logger.exception(e)

    await asyncio.sleep(300)
    asyncio.ensure_future(update_status(cln))

"""Locate OAuth token"""
token = CONF.get('token',None)
if not token:
    with open(CONF.get('dir_pref','./')+'tokens.txt') as file:
        token = file.read().splitlines()[0]

"""Run program"""
if __name__ == '__main__':
    try:
        client.run(token, bot=True)
        logging.shutdown()
    except Exception as e:
        logger.exception(e)

    logger.info("Waiting 5 seconds")
    time.sleep(3)
