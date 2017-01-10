#!/usr/bin/env python3

from datetime import date
from datetime import datetime
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

admins = ['154542529591771136','154543065594462208']
last_message_time = {}

dir_pref = '/home/shwam3/pedant/' if platform.system() == 'Linux' else ''
cmd_pref = '/'
dateFormat = '%A %d %B %Y @ %I:%M%p'
ALLOWED_EMBED_CHARS = ' abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!"#$%&\'()*+,-./:;<=>?@[\]^_`{|}~'

try:
    logging.basicConfig(format='[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',stream=sys.stdout)
    logger = logging.getLogger('pedantbot')
    logger.setLevel(logging.INFO)

    log_handler = logging.handlers.RotatingFileHandler(dir_pref+'define.log', 'a', backupCount=5, delay=True)
    log_handler.setLevel(logging.DEBUG)

    err_log_handler = logging.StreamHandler(stream=sys.stderr)
    err_log_handler.setLevel(logging.WARNING)

    formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s')
    log_handler.setFormatter(formatter)
    err_log_handler.setFormatter(formatter)


    if os.path.isfile(dir_pref+'define.log'):
        log_handler.doRollover()

    logger.addHandler(log_handler)
    logger.addHandler(err_log_handler)

    logger.warn('Starting...')
except Exception as e:
    print(e)

client = discord.Client()

VERSION = '1.0.0.1'
voteMessages = {}

@client.event
async def on_ready():
    logger.info('Version ' + VERSION)
    logger.info('Logged in as')
    logger.info(' ->	Name: '+client.user.name)
    logger.info(' ->    ID: '+client.user.id)

    logger.info('Setting reminders')
    for rem in reminders:
        if rem.get('is_cancelled', False):
            continue
        task = asyncio.ensure_future(do_reminder(client, rem['invoke_time']))
        rem['task'] = task

    asyncio.ensure_future(update_status())

    logger.info(' -> set ' + str(len(reminders)) + ' reminders')

    save_reminders()

@client.event
async def on_message(message):
    await client.wait_until_ready()

    try:
        if message.author.id == client.user.id:
            return
        elif message.content.lower().startswith(cmd_pref + 'pedant') or message.content.lower().startswith(cmd_pref + 'define'):
            if len(message.content.split()) < 2:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'pedant <term>`')
                return
            term = message.content.split(' ', 1)[1].strip()
            search = term
            content = None
            found = False

            await client.send_typing(message.channel)
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
                        await client.send_message(message.channel, 'No results found for: `' + term + '`')
                        return
                    else:
                        logger.info(' -> Wiki page')
                        try:
                            content = wikipedia.summary(arts[0], chars=750)
                        except wikipedia.DisambiguationError as de:
                            logger.info(' -> ambiguous wiki page')
                            content = wikipedia.summary(de.options[0], chars=750)

                deleted = False
                try:
                    await client.delete_message(message)
                    deleted = True
                except discord.Forbidden:
                    pass

                logger.info(' -> Found stuff')
                embed = discord.Embed(title='Definition for ' + term,
                                    	description=''.join(x for x in content if x in ALLOWED_EMBED_CHARS),
                                    	color=colour(message)
                                     )
                #embed.set_thumbnail(url='https://en.wikipedia.org/static/images/project-logos/enwiki.png')
                #embed.set_author(text=search)
                #await client.send_message(message.channel, (message.author.mention + ' Defining ' if deleted is True else 'Defining ') + search + ':\n' + content)
                await client.send_message(message.channel,embed=embed)
            except:
                await client.send_message(message.channel,'Unable to retrieve results at this time.')

        elif message.content.lower().startswith(cmd_pref + 'runescape'):
            img = message.content.lower().startswith(cmd_pref + 'runescapeimg')

            if len(message.content.split()) < 2:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'runescape <term>`')
                return

            term = message.content.split(' ', 1)[1].strip()
            search = term
            content = None
            found = False

            await client.send_typing(message.channel)
            logger.info('Finding runescape definition: "' + term + '"')

            try:
                if not found:
                    try:
                        arts = wikia.search('Runescape',term)
                    except ValueError:
                        logger.info(' -> No results found')
                        await client.send_message(message.channel, 'No results found for: `' + term + '`')
                        return
                    else:
                        logger.info(' -> Runescape wiki page')
                        try:
                            page = wikia.page('Runescape',arts[0])
                            content = '{:.750}'.format(page.summary)
                        except wikia.DisambiguationError as de:
                            logger.info(' -> ambiguous runescape wiki page')
                            page = wikia.page('Runescape',de.options[0])
                            content = '{:.750}'.format(page.summary)

                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass

                logger.info(' -> Found runescape stuff')
                embed = discord.Embed(title=page.title,
                                    	description='' if img else (''.join(x for x in content if x in ALLOWED_EMBED_CHARS)),
                                    	color=colour(message),
                                      url=page.url
                                     )
                embed.set_footer(text='ID #' + str(page.pageid))
                if len(page.images) > 0:
                    if img:
                        embed.set_image(url=page.images[0])
                    else:
                        embed.set_thumbnail(url=page.images[0])

                await client.send_message(message.channel,embed=embed)
            except Exception as e:
                await client.send_message(message.channel,'Unable to retrieve results at this time.')
                logger.error(e)

        elif message.content.lower().startswith(cmd_pref + 'anagram'):
            if len(message.content.split()) < 2:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'anagram <term>`')
                return
            term = message.content.lower().split(' ', 1)[1].strip()
            logger.info('Anagram: ' + term)

            await client.send_typing(message.channel)
            response = urllib.request.urlopen('http://anagram-solver.net/' + urllib.request.quote(term))
            webContent = response.read().decode('utf-8')

            if webContent.find('No answers found for ') > -1:
                logger.info(' -> No results found')
                await client.send_message(message.channel, 'No results found for: `' + term + '`')
            else:
                results = []
                lastEnd = webContent.find('<ul class="answers">')
                while True:
                    webLinkStart = webContent.find('<li><a href="/', lastEnd)
                    if webLinkStart < 0:
                        break
                    webLinkStart = webContent.find('">', webLinkStart)+2
                    webLinkEnd = webContent.find('</a></li>', webLinkStart)
                    lastEnd = webLinkEnd
                    results.append(webContent[webLinkStart:webLinkEnd])

                deleted = False
                try:
                    await client.delete_message(message)
                    deleted = True
                except discord.Forbidden:
                    pass
                logger.info(' -> found ' + str(len(results)) + ' results')
                await client.send_message(message.channel, (message.author.mention + ' ' if deleted is True else '') + 'Found ' + str(len(results)) + ' anagrams of: `' + term + '`\n```' + '\n'.join(results) + '```')

        elif message.content.lower().startswith(cmd_pref + 'remindme'):
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            if len(message.content.split()) < 4:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'remindme in <time> [seconds|minutes|hours] <message>`')
                return

            command = message.content.split(' ', 3)
            if command[1] != 'in' or int(command[2]) <= 0:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'remindme in <time> [seconds|minutes|hours] <message>`')
                return

            invoke_time = int(time.time())

            logger.info('Set reminder')
            await client.send_typing(message.channel)

            reminder_msg = command[3]
            is_cancelled = False
            split = reminder_msg.split(' ',1)
            unit = split[0]
            unit_specified = True
            reminder_if_unit = split[1] if len(split) > 1 else None

            if unit == 'seconds' or unit == 'second' or unit == 'secs' or unit == 'sec':
                unit_mult = 1
            elif unit == 'minutes' or unit == 'minute' or unit == 'mins' or unit == 'min':
                unit_mult = 60
            elif unit == 'hours' or unit == 'hour' or unit == 'hrs' or unit == 'hr':
                unit_mult = 3600
            else:
                unit_mult = 60
                unit_specified = False

            if not reminder_if_unit and not unit_specified:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'remindme in <time> [seconds|minutes|hours] <message>`')
                return

            if reminder_if_unit and unit_specified:
                reminder_msg = reminder_if_unit

            if not reminder_msg:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'remindme in <time> [seconds|minutes|hours] <message>`')
                return

            remind_delta = int(command[2]) * unit_mult
            remind_timestamp = invoke_time + remind_delta

            if remind_delta <= 0:
                await client.send_message(message.channel, 'Cant set a reminder against our current laws of physics')
                return

            reminder = {'user_name':message.author.display_name, 'user_mention':message.author.mention, 'invoke_time':invoke_time, 'time':remind_timestamp, 'channel_id':message.channel.id, 'message':reminder_msg, 'task':None, 'is_cancelled':is_cancelled}
            reminders.append(reminder)
            async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
            reminder['task'] = async_task

            logger.info(' -> reminder scheduled for ' + str(datetime.fromtimestamp(remind_timestamp)))
            await client.send_message(message.channel, message.author.mention + ' Reminder scheduled for ' + datetime.fromtimestamp(remind_timestamp).strftime(dateFormat))

            if remind_delta > 15:
                save_reminders()

        elif message.content.lower().startswith(cmd_pref + 'editreminder'):
            if len(message.content.split(maxsplit=3)) != 4:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'editreminder <reminder_id> <msg <message>|time <timestamp>>`')
                return

            logger.info('Edit reminder')
            await client.send_typing(message.channel)

            invoke_time = int(message.content.split(maxsplit=2)[1])

            reminder = get_reminder(invoke_time)

            if not reminder:
                await client.send_message(message.channel, 'Invalid reminder ID `' + invoke_time + '`')
                return

            spl = message.content.split(maxsplit=3)

            try:
                if spl[2].lower() == 'msg' or spl[2].lower() == 'message':
                    reminder['message'] = spl[3]
                elif spl[2].lower() == 'time' or spl[2].lower() == 'timestamp' or spl[2].lower() == 'ts':
                    #check backwards and negative
                    reminder['time'] = int(spl[3])
                else:
                    await client.send_message(message.channel, 'Please choose an option `<msg|time>`')
                    return
            except:
                await client.send_message(message.channel, 'Invalid edit parameters')
                return

            reminder['task'].cancel()
            async_task = asyncio.ensure_future(do_reminder(client, invoke_time))
            reminder['task'] = async_task

            await client.send_message(message.channel, 'Reminder re-scheduled')

        elif message.content.lower().startswith(cmd_pref + 'cancelreminder'):
            if len(message.content.split()) != 2:
                await client.send_message(message.channel, 'Usage: `'+cmd_pref+'cancelreminder <reminder_id>`')
                return

            logger.info('Cancel reminder')
            await client.send_typing(message.channel)

            invoke_time = int(message.content.split()[1])

            reminder = get_reminder(invoke_time)
            reminder['is_cancelled'] = True
            reminder['task'].cancel()

            await client.send_typing(message.channel)

        elif message.content.lower() == cmd_pref + 'reminders':
            logger.info('Listing reminders')
            await client.send_typing(message.channel)

            msg = 'Current reminders:\n'

            for rem in reminders:
                try:
                    msg += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' at ' + datetime.fromtimestamp(rem['time']).strftime(dateFormat) + ': ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')
                except:
                    msg += ('~~' if rem.get('is_cancelled',False) else '') + rem['user_name'] + ' in ' + str(rem['time']) + ' seconds: ``' + rem['message'] +'`` (id:`'+str(rem['invoke_time'])+'`)' + ('~~\n' if rem.get('is_cancelled',False) else '\n')

            if len(reminders) == 0:
                msg += 'No reminders'
            await client.send_message(message.channel, msg)

        elif message.content.lower() == cmd_pref + 'speedtest':
            logger.info('SpeedTest')

            st = pyspeedtest.SpeedTest(host='speedtest.as50056.net')
            msg = await client.send_message(message.channel,':race_car: **Speedtest Results**\n'+
                'Working... :hourglass_flowing_sand:')

            try:
                ping = st.ping()
                logger.info(' -> ping: ' + str(round(ping,1)) + 'ms')
                msg = await client.edit_message(msg, ':race_car: **Speedtest Results**\n'+
                    '**Ping:** ' + str(round(ping,1)) + 'ms\n'+
                    'Working... :hourglass_flowing_sand:')

                down = st.download()
                logger.info(' -> download: ' + str(round(down/1024/1024,2)) + 'Mb/s')
                msg = await client.edit_message(msg, ':race_car: **Speedtest Results**\n'+
                    '**Ping:** ' + str(round(ping,1)) + 'ms\n'+
                    '**Download Speed:** ' + str(round(down/1024/1024,2)) + 'Mb/s\n'+
                    'Working... :hourglass_flowing_sand:')

                up = st.upload()
                logger.info(' -> upload: ' + str(round(up/1024/1024,2)) + 'Mb/s')
                msg = await client.edit_message(msg, ':race_car: **Speedtest Results**\n'+
                    '**Ping:** ' + str(round(ping,1)) + 'ms\n'+
                    '**Download Speed:** ' + str(round(down/1024/1024,2)) + 'Mb/s\n'+
                    '**Upload Speed:** ' + str(round(up/1024/1024,2)) + 'Mb/s')
            except Exception as e:
                logger.exception(e)
                await client.edit_message(msg, msg.content + '\n**An error has occured**')

        elif message.content.lower().startswith(cmd_pref + 'random'):
            logger.info('Finding random article')
            await client.send_typing(message.channel)
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

            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            await client.send_message(message.channel, embed=embed)

        elif message.content.lower().startswith(cmd_pref + 'brerb'):
            logger.info('Brerb')
            await client.send_typing(message.channel)
            await client.send_message(message.channel, '<:brerb:230806961996693505> ' + ('https://i.imgur.com/ALbUCnw.gifv' if message.content.lower().find('false') != -1 else ''))

        elif message.content.lower() == cmd_pref + 'ping':
            logger.info('Ping')
            await client.send_message(message.channel, ":ping_pong: Pong!")

        elif message.content.lower().startswith(cmd_pref + 'oauth'):
            logger.info('OAuth')
            if len(message.content.split()) > 2:
                await client.send_message(message.channel, 'Usage: '+cmd_pref+'oauth [client_id]')
                return

            client_id = message.content.split()[1] if len(message.content.split()) == 2 else None

            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass
            await client.send_message(message.channel, discord.utils.oauth_url(client_id if client_id else client.user.id, permissions=discord.Permissions(1278733312), server=None, redirect_uri=None))

        elif message.content.lower().startswith(cmd_pref + 'b64img'):
            if len(message.content.split()) != 2:
                await client.send_message(message.channel, 'Usage: '+cmd_pref+'b64img <data_uri>')
                return

            await client.send_typing(message.channel)
            logger.info('Sending base64 image')

            uri = message.content.split(' ', 1)[1]
            header, data = uri.split(';',1)

            if header != 'data:image/png' and header != 'data:image/jpeg' and header != 'data:image/jpg' and header != 'data:image/gif':
                await client.send_message(message.channel, 'Usage: '+cmd_pref+'b64img <data_uri>')
                return

            format = header.split('/')[1]

            if data.startswith('base64'):
                data = data[7:]

            binary_data = base64.b64decode(data.encode())

            imgName = dir_pref+'image-' + str(int(time.time())) + '.' + format
            with open(imgName, 'wb') as fd:
                fd.write(binary_data)
                fd.flush()

            deleted = False
            try:
                await client.delete_message(message)
                deleted = True
            except discord.Forbidden:
                pass

            logger.info(' -> sent ' + imgName)
            await client.send_file(message.channel, imgName, content=(message.author.mention+' shared an image') if deleted else None)
            os.remove(imgName)

        elif message.content.lower().startswith(cmd_pref + 'calc'):
            logger.info('Calc')
            try:
                client.delete_message(message)
            except discord.Forbidden:
                pass
            await client.send_typing(message.channel)
            maths = ''.join(str(message.content).split(' ')[1:])
            if (re.findall('[^0-9\(\)\/\*\+-\.]+',maths) != []):
                await client.send_message(message.channel,'no \'%s\' is not allowed' % maths)
            else:
                logger.info(' -> ' + str(maths))
                await client.send_message(message.channel,'`{} = {}`'.format(maths,eval(maths)))

        elif message.content.startswith(cmd_pref + 'vote'):
            logger.info(message.author.name + ' started a vote')
            await client.send_typing(message.channel)
            stuff = message.content.split(' ',1)[1]
            q, question = re.findall('(["\'])([^\\1]*)\\1',stuff)[0]
            logger.info(' -> "' + question + '"')
            allowedReactions = str(stuff[len(q+question+q)+1:]).replace('  ',' ').split()
            logger.info(' -> %s' % ', '.join(allowedReactions))
            msg = await client.send_message(message.channel, '**' + question + '**\nReact with one of the following to vote: [ ' + ', '.join(allowedReactions) +	' ]')
            digits = [':zero:',':one:',':two:',':three:',':four:',':five:',':six:',':seven:',':eight:',':nine:']
            for e in allowedReactions:
                await client.add_reaction(msg, e)
            for i in range(30,0,-1):
                tens = round((i - (i % 10)) / 10)
                ones = i % 10
                num = (digits[tens] if (digits[tens] != ':zero:') else '') + ' ' + digits[ones]
                await client.edit_message(msg,msg.content + '\nTime Remaining: ' + num)
                await asyncio.sleep(1)
            await client.edit_message(msg,msg.content + '\n***Voting ended.***')
            msg = await client.get_message(msg.channel,msg.id)
            reacts = []
            validReactions = 0
            if len(msg.reactions) == 0:
                await client.send_message(msg.channel,'Nobody submitted any votes :(')
                logger.info(' -> no winner')
            else:
                for reaction in msg.reactions:
                    if reaction.emoji in allowedReactions:
                        if reaction.count > 1:
                            reacts.append((reaction.emoji,reaction.count -1))
                            validReactions += 1
                if validReactions == 0:
                    await client.send_message(msg.channel,'Nobody submitted any valid votes :(')
                    logger.info(' -> no winner')
                else:
                    reacts = sorted(reacts, key=lambda x: x[1])
                    reacts.reverse()
                    await client.send_message(msg.channel,'**'+ question +'**\nThe winning vote was: ' + reacts[0][0] + '\n```' + graph.draw(msg.reactions,height=5,find=lambda x: x.count-1) + '```')
                    logger.info(' -> %s won' % reacts[0][0])

        elif message.content.lower().startswith(cmd_pref + 'bigger'):
            logger.info('Debug emoji:')
            await client.send_typing(message.channel)
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            thisEmoji = message.content.lower().split(' ')[1]

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
                await client.send_message(message.channel,'Only custom emoji for \'{}\' are supported'.format(message.server.name))

        elif message.content.lower() == cmd_pref + 'showemoji':
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass
            await client.send_message(message.channel,' '.join('{}'.format('<:{}:{}>'.format(emoji.name,emoji.id),emoji.name) for emoji in message.server.emojis))

        elif message.content.lower().startswith(cmd_pref + 'quote'):
            logger.info('Quote')
            await client.send_typing(message.channel)

            id = ' '.join(message.content.lower().split(' ')[1:])

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

                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass

                await client.send_message(message.channel,embed=embed)

                break
            cursor.close()
            cnx.close()

        elif message.content.lower().startswith(cmd_pref + 'shrug'):
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            embed = discord.Embed(title=message.author.name+' sent something:',description='¯\_(ツ)_/¯',color=colour(message),timestamp=datetime.now())
            await client.send_message(message.channel,embed=embed)

        elif message.content.lower().startswith(cmd_pref + 'wrong'):
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            embed = discord.Embed(title='THIS IS WRONG!',color=colour(message))
            embed.set_image(url='http://i.imgur.com/CMBlDO2.png')

            await client.send_message(message.channel,embed=embed)

        elif message.content.lower().startswith(cmd_pref + 'id'):
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass
            await client.send_message(message.channel,message.author.mention + ': ' + message.author.id)

        elif message.content.lower() == cmd_pref + 'help':
            await client.send_typing(message.channel)

            msg = 'Command help for ' + message.server.get_member(client.user.id).display_name + ':\n```'

            msg += cmd_pref+'define <term>\n'
        	 #msg += cmd_pref+'pedant <term>\n'
            msg += cmd_pref+'anagram <term>\n'
            msg += cmd_pref+'remindme in <time> [seconds|minutes|hours] <message>\n'
            msg += cmd_pref+'cancelreminder <reminder_id>\n'
            msg += cmd_pref+'reminders\n'
            msg += cmd_pref+'speedtest\n'
            msg += cmd_pref+'random\n'
            msg += cmd_pref+'brerb\n'
            msg += cmd_pref+'ping\n'
            msg += cmd_pref+'b64img <base_64_image>\n'
            msg += cmd_pref+'calc <expression>\n'
            msg += cmd_pref+'vote <prompt> [reaction_filter]\n'
            msg += cmd_pref+'id\n'
            msg += '-'*25 + '\n'
        	 #msg += cmd_pref+'restart\n'
            msg += cmd_pref+'fkoff'

            msg += '```'

            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass
            await client.send_message(message.channel, msg)

    	 #elif message.content.lower() == cmd_pref + 'fkoffbutonlyforabit' or message.content.lower() == cmd_pref + 'restart':
    	 #    if message.author.id in admins:
    	 #        logger.info('Restarting')
    	 #        logger.info('-------------------------')
    	 #        await client.send_message(message.channel, ":wave:")
    	 #        try:
    	 #            await client.delete_message(message)
    	 #        except discord.Forbidden:
    	 #            pass
    	 #        await client.logout()
    	 #        os.execv(sys.executable, ['python'] + sys.argv)
    	 #    else:
    	 #        await client.send_message(message.channel, 'kekno boi, git permission')

        elif message.content.lower() == cmd_pref + 'fkoff':
            if message.author.id in admins:
                logger.info('Stopping')
                await client.send_message(message.channel, ':wave:')
                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass
                await client.logout()
                try:
                    sys.exit()
                except Exception as e:
                    logger.exception(e)
                    pass
            else:
                await client.send_message(message.channel,'kekno boi, git permissions')

        elif message.content.lower() == cmd_pref + 'ip':
            if message.author.id in admins:
                logger.info('IP')
                await client.send_typing(message.channel)

                response = urllib.request.urlopen('https://api.ipify.org/')
                webContent = response.read().decode('utf-8')

                await client.send_message(message.channel, 'IP: `' + webContent + '`')
                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass
            else:
                await client.send_message(message.channel,'kekno boi, git permissions')

        elif message.content.lower() == cmd_pref + 'perms':
            if message.author.id in admins:
                logger.info('Perms')
                await client.send_typing(message.channel)
                
                bot_member = message.server.get_member(client.user.id)
                perms = message.channel.permissions_for(bot_member)

                await client.send_message(message.channel, 'Perms: \n```' + '\n'.join(' '.join(w.capitalize() for w in x[0].split('_')).replace('Tts','TTS') for x in perms if x[1]) + '```')
                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass
            else:
                await client.send_message(message.channel,'kekno boi, git permissions')

        elif message.content.lower().startswith(cmd_pref + 'avatar'):
            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            if len(message.mentions) > 0:
                user = message.mentions[0]
                name = user.nick or user.name
                avatar = user.avatar_url or user.default_avatar_url

                embed = discord.Embed(title=name,type='rich',colour=colour(message),)
                embed.set_image(url=avatar)
                embed.set_footer(text='ID: #{}'.format(user.id))
                await client.send_message(message.channel,embed=embed)


        elif message.content.lower().startswith(cmd_pref + 'grid'):
            try:
                x,y = [int(x) for x in message.content.lower().split()[1:3]]
            except ValueError:
                x,u = 0,0

            x,y = min(x,12),min(y,4)

            try:
                await client.delete_message(message)
            except discord.Forbidden:
                pass

            string = ''
            emoji = message.server.emojis

            for i in range(y):
                for j in range(x):
                    temp = emoji[randrange(len(emoji))]
                    temp_emoji = '<:{}:{}> '.format(temp.name,temp.id)
                    if len(string) + len(temp_emoji) <= 2000:
                        string += temp_emoji
                if j < y-1:
                    string += '\n'

            await client.send_message(message.channel,string)

        elif message.content.lower().startswith(cmd_pref + 'abuse'):
            if message.author.id in admins:
                channel = message.content.split(" ")[1]
                if channel == 'here':
                    channel = message.channel.id
                msg = ' '.join(message.content.split(" ")[2::])

                try:
                    await client.delete_message(message)
                except discord.Forbidden:
                    pass

                try:
                    await client.send_message(client.get_channel(channel),msg)
                except Exception as e:
                    logger.error('abuse: ' + str(e))
                    pass
            else:
                try:
                    await client.send_message(message.channel,'fuck nah, ' + message.author.mention + ', you dont have perms')
                except:
                    pass

        elif message.content.lower().startswith(cmd_pref + 'thyme'):
            await client.send_typing(message.channel)
            embed = discord.Embed(title='Thyme',timestamp=message.edited_timestamp or message.timestamp)
            embed.set_image(url='http://shwam3.altervista.org/thyme/image.jpg')
            embed.set_footer(text='Love you long thyme')

            await client.send_message(message.channel,embed=embed)

    except Exception as e:
        logger.error('error in on_message')
        logger.exception(e)
        await log_exception(e, 'on_message')

def colour(message=None):
    try:
        if message:
            return sorted([x for x in message.author.roles if x.colour != discord.Colour.default()], key=lambda x: -x.position)[0].colour
    except:
        pass

    return discord.Colour.default()

async def check_admin(message=None):
    if message.author.id in admins:
        return True

    await client.send_message(message.channel, 'no pls')
    return False

async def log_exception(e,location=None):
    try:
        exc = ''.join(traceback.format_exception(None, e, e.__traceback__).format(chain=True))
        exc = [exc[i:i+2000-6] for i in range(0, len(exc), 2000-6)]
        await client.send_message('257152358490832906', 'Error ' + ('in `{}`:'.format(location) if location else 'somewhere:'))
        for i,ex in enumerate(exc):
            await client.send_message('257152358490832906','```{:.1994}```'.format(ex))
    except:
        pass

def get_proper_link(link):
    if link.startswith('http') and link.find('/wiki/') < 0:
        return
    if not link.startswith('https://'):
        link = 'https://en.wikipedia.org' + link


    response = urllib.request.urlopen(link)
    webContent = response.read().decode('utf-8')

    editLinkStart = webContent.find('rel="edit"')
    if editLinkStart < 0:
        return link
    editLinkStart = webContent.find('href="', editLinkStart)+6
    editLinkStart = webContent.find('title=', editLinkStart)+6
    editLinkEnd = webContent.find('action=', editLinkStart)-5

    editLink = 'https://en.wikipedia.org/wiki/' + webContent[editLinkStart:editLinkEnd]
    if link != editLink:
        logger.info(' -> redirect')
        return get_proper_link(editLink)
    else:
        return link

def get_reminder(invoke_time):
    invoke_time = int(invoke_time)
    for rem in reminders:
        if rem['invoke_time'] == invoke_time:
            return rem

    return None

async def do_reminder(client, invoke_time):
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

async def update_status():
    await client.change_presence(game=discord.Game(name='Wikipedia: ' + wikipedia.random(pages=1)),afk=False,status=None)
    await asyncio.sleep(60)
    asyncio.ensure_future(update_status())

@atexit.register
def save_reminders():
    str = ''
    rems = []
    for rem in reminders[:]:
        rems.append({'user_name':rem['user_name'], 'user_mention':rem['user_mention'], 'invoke_time':rem['invoke_time'], 'time':rem['time'], 'channel_id':rem['channel_id'], 'message':rem['message'], 'is_cancelled':rem['is_cancelled']})
    for rem in rems:
        rem['task'] = None
        str += json.dumps(rem, sort_keys=True, skipkeys=True) + '\n'
    with open(dir_pref+'reminders.txt', 'w') as file:
        file.write(str)

def _print(msg):
    print('[' + str(datetime.now()) + '] ' + msg)

special_defs = {}
if os.path.isfile(dir_pref+'special_defs.txt'):
    with open(dir_pref+'special_defs.txt') as file:
        for line in file:
            if line.find(':') < 0:
                continue
            line = line.split(':',1)
            special_defs[line[0].lower()] = line[1].replace('\n','')

reminders = []
if os.path.isfile(dir_pref+'reminders.txt'):
    with open(dir_pref+'reminders.txt') as file:
        for line in file:
            try:
                reminders.append(json.loads(line))
            except json.decoder.JSONDecodeError as e:
                logger.error('JSON Error:')
                logger.exception(e)

token = ''
with open(dir_pref+'tokens.txt') as file:
    token = file.read().splitlines()[0]

if __name__ == '__main__':
    client.run(token, bot=True)
    logging.shutdown()
