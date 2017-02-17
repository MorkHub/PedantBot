# PedantBot v2.0 [beta]
**NOTE**: This branch contains the latest features as they are added. This means that some features may be missing or broken. Use at your own risk.

```python
@register('git',owner=False,hidden=False,rate=5)
async def welcome(message,*args):
  logger.info('{user} wants to view the GitHub repository'.format(user=message.author))
  await client.send_message(message.channel, 'Come find out about me at: https://github.com/MorkHub/PedantBot')
```
## Contents
* Add to your server
* How to use
* Commands
  * [For fun](#fun)
  * [Useful](#useful)
  * [Dev](#dev)
  * [Admin-only (bot owner)](#admin)

### Commands
	Prefix: \
	USAGE: \command <required> [optional]
	For more details: \help [command]

### [Add to your server](https://discordapp.com/oauth2/authorize?client_id=169112287297142784&scope=bot&permissions=1848765527 "Discord invite link")

### Commands

#### Fun
| Command            | Parameters                                 |  Description  |
| ------------------ | ------------------------------------------ | ------------- |
| **avatar**         | `@<mention user>`                          | Display a user's avatar
| **bigger**         | `<custom server emoji>`                    | Display a larger image of the specified emoji
| **elijah**         |                                            | elijah wood
| **grid**           | `<x> <y>`                                  | Display a custom-size grid made of server custom emoji
| **random**         |                                            | Retrieve a random WikiPedia article
| **quote**          | `[quote id]`                               | Embed a quote from https://themork.co.uk/quotes
| **showemoji**      |                                            | Displays all available custom emoji in this server
| **shrug**          |                                            | Send a shrug: mobile polyfill
| **woop**           |                                            | fingers or something
| **wrong**          |                                            | Send the WRONG! image
| **thyme**          |                                            | Send some thyme to your friends
| **vote**           | `"<vote question>" <emoji>`                | Initiate a vote using Discord Message Reactions.

#### Useful
| Command            | Parameters                                 |  Description  |
| ------------------ | ------------------------------------------ | ------------- |
| **help**           | `[command name]`                           | Display help message(s), optionally append command name for specific help
| **age**            |                                            | Get user's Discord age
| **cal**            |                                            | Displays a formatted calendar
| **remindme**       | `in <number of> [secs|mins|hours|days]`    | 
| **editreminder**   | `<reminder ID> <message|timestamp> [data]` | Edit scheduled reminders
| **cancelreminder** | `<reminder id>`                            | Cancel an existing reminder
| **reminders**      |                                            | 
| **define**         | `<term>`                                   | Search for a wikipedia page and show summary
| **invite**         |                                            | List active invite link for the current server
| **maths**          | `<expression>`                             | Perform mathematical calculation

#### Dev
| Command            | Parameters                                 |  Description  |
| ------------------ | ------------------------------------------ | ------------- |
| **oauth**          | `[OAuth client ID] [server ID]`            | Get OAuth invite link
| **ping**           | `[<host> [count]]`                         | Test latency by receiving a ping message
| **test**           | `[list of parameters]`                     | Print debug output

#### Admin
| Command            | Parameters                                 |  Description  |
| ------------------ | ------------------------------------------ | ------------- |
| **bannedusers**    |                                            | List users that have been banned from this server
| **ban**            | `@<mention users>`                         | Bans the specified user from the server
| **channels**       | `[server ID]`                              | Displays a list of channels and servers currently available 
| **ip**             |                                            | Looks up external IP of the host machine
| **kick**           | `@<mention users>`                         | Kicks the specified user from the server
| **perms**          |                                            | List permissions available to this  bot
| **ranks**          |                                            | Displays a list of ranks in the server
| **restart**        |                                            | Restart the bot
| **sendmsg**        | `<channel> <content>`                      | Harness the power of Discord
| **servers**        |                                            | Lists servers currently connected
| **speedtest**      |                                            | Run a speedtest from the bot's LAN.
