# PedantBot v3.0 **WIP**

![screenshot](https://i.themork.co.uk/7d5f012.png "PedantBot in action")

## Contents
* [Requirements](#requirements)
* [Installation](#installation)
* [Add to your server](#add-to-your-server)
* [How to use](#how-to-use)
* [Screenshots](#screenshots)

## Requirements
PedantBot is written for *python 3.5*, support for 3.4 and below unlikely with no plans to support 2.x.

Any operating system which supports Python *should* be supported, tested and working on the following:
* Windows 10 Education (64-bit)
* Ubuntu Server 16.04 (64-bit)

To install requirements, `requirements.txt` is provided for automatic installation via [pip](https://pip.pypa.io/en/stable/installing/).<br>
If installing manually, the following are required.

    asyncio
    discord.py[voice]
    youtube-dl
    aioredis
    redis
    pytz
    requests
    youtube_dl
    dateutils
    Pillow

In addition, the following programs/packages may be required:
    
    redis
    docker (optional)   

## Installation

### Basic
1. Clone this repository: `git clone http://git.themork.co.uk/TheMork/PedantBot.git`
2. Install dependencies
    * pip: `pip install -r requirements.txt` OR
    * manually install all the python packages listed in the [requirements](#requirements) section
3. Ensure the redis server is running, and that you know port it is running on.
4. Start the bot ```env python3```

<!--### Docker container
1. Ensure docker is installed on your system, and is running
2. Build the docker image with `docker build -t morkhub/pedantbot`
3. Create the docker container, substituting the values enclosed in `{}`.
```
docker run morkhub/pedantbot --name=PedantBot \
    -link redis:redis
    -e REDIS_ADDRESS={REDIS_ADDRESS}
    -e SHARDS={NUM_SHARDS}
    -e credentials.env
```-->

## Add to your server

**NOTE:** You must have the `manage_server` permission to add bots.

#### Public Instance
[Click here](https://discordapp.com/oauth2/authorize?client_id=221788578529804288&scope=bot&permissions=1848765527 "Discord invite link") 
 to invite the public instance to your server.

#### Self-hosted
When running this bot, it will output an invite link to `stdout`, or you can use the following template, replacing `{CLIENT_ID}` with your bot's [client ID](https://i.themork.co.uk/a7ebcbe.png)
```
https://discordapp.com/oauth2/authorize?client_id={CLIENT_ID}&permissions=1848765527&scope=bot
```

### How to use
Say `?help` in Discord when the bot has joined to view a list of enabled plugins. You can then use `?help <plugin>` to view commands for that plugin.

**Syntax:**<br>
Arguments enclosed by `<>` indicate required arguments, whereas `[]` indicated optional arguments:  
```
!command_name <required argument> [optional argument]
```

To enable a plugin, say `;enable <plugin>` and to disable a plugin, `;disable <plugin>`. This requires `manage_server` permission.

## Screenshots

Get help<br>
![help menu](https://i.themork.co.uk/b88c6cf.png "list of plugins")

List plugin commands<br>
![command_list](https://i.themork.co.uk/43a0627.png "list of commands in a plugin")

Get user's local time<br>
![local time](https://i.themork.co.uk/deb4e8b.png "user's local time")

Create custom commands<br>
![custom reactions](https://i.themork.co.uk/b2a0b5c.png "adding a custom reaction")

Get server information<br>
![server info](https://i.themork.co.uk/5987050.png "view server infomation")

Set reminders<br>
![set reminder](https://i.themork.co.uk/044753b.png "setting a reminder")

Reminders<br>
![reminder](https://i.themork.co.uk/09ec4b7.png "a reminder")

