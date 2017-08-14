from classes.plugin import Plugin
from decorators import command
from util import *


log = logging.getLogger('pedantbot')


class Info(Plugin):
    plugin_name = 'Bot info'

    @command(pattern='^!info$',
             description="get info about the bot",
             usage='!info')
    async def bot_info(self, message: discord.Message, args: tuple=()):
        """Print information about the Application"""
        channel = message.channel
        log.debug(args)

        me = await self.client.application_info()
        owner = me.owner

        embed = discord.Embed(
            title=me.name,
            description=me.description,
            color=discord.Colour.purple(),
            timestamp=discord.utils.snowflake_time(me.id)
        )
        embed.set_thumbnail(
            url=me.icon_url
        )
        embed.set_author(
            name="Owner: {owner.name}".format(owner=owner),
            icon_url=owner.avatar_url or owner.default_avatar_url
        )
        embed.set_footer(text="Client ID: {}".format(me.id))

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!servers",
             description="view the servers currently connected",
             usage="!servers")
    async def view_servers(self, message: discord.Message, *_):
        channel = message.channel

        body = ""
        displayed = 0
        for server in self.client.servers:
            temp = '•   __{server.owner.name}\'s__ **{server.name}** ([{server.id}](https://themork.co.uk/code?code={server.id}))\n'.format(
                server=server
            )
            if len(body) + len(temp) <= 1500:
                body += temp
                displayed += 1
            else:
                body += "{} more ...".format(len(self.client.servers) - displayed)
                break

        embed = discord.Embed(
            title='Servers {0} is connected to ({1}/{2} shown)'.format(self.client.user, displayed, len(self.client.servers)),
            colour=discord.Colour.purple(),
            description=body
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!channels",
             description="view the servers currently connected",
             usage="!channels")
    async def view_channels(self, message: discord.Message, *_):
        server = message.server
        _channel = message.channel

        t_body = ""
        v_body = ""
        for channel in sorted(server.channels, key=lambda c: c.position):
            topic = (channel.topic or "").strip()
            voice = channel.type == discord.ChannelType.voice
            if topic:
                topic = ' "{}"'.format(topic)

            body = ('• [`{channel.id}`] **{s}{channel.name}**{topic}\n').format(
                channel=channel,
                s='' if voice else '#',
                topic=topic
            )

            if voice:
                v_body += body
            else:
                t_body += body

        embed = discord.Embed(
            title='Channels in {}'.format(server),
            colour=discord.Colour.purple(),
        )

        if t_body:
            embed.add_field(
                name="Text Channels",
                value=t_body
            )
        if v_body:
            embed.add_field(
                name="Voice Channels",
                value=v_body
            )

        await self.client.send_message(
            _channel,
            embed=embed
        )

    @command(pattern="^!(?:serverinfo|si)$",
             description="view information about the current server",
             usage="!serverinfo")
    async def server_info(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        embed = discord.Embed(
            colour=discord.Colour.purple()
        )

        embed.set_author(
            name=server,
            icon_url="https://cdn.discordapp.com/icons/{}/{}.png".format(server.id, server.icon)
        )

        # if server.emojis:
        #     embed.add_field(
        #         name="Emojis",
        #         value=','.join('<:{}:{}>'.format(emoji.name, emoji.id) for emoji in server.emojis)
        #     )

        roles_hoist = []
        roles = []

        for role in sorted(server.roles, key=lambda r: -r.position):
            if role.is_everyone:
                continue

            role_list = roles_hoist if role.hoist else roles
            role_list.append(role.name)

        embed.add_field(
            name="Roles",
            value="{}\n\n{}".format(
                ', '.join(roles_hoist),
                ', '.join(roles)
            )
        )
        embed.add_field(
            name="AFK Channel",
            value="Inactivity period: `{}s`\n"
                  "Channel: {}".format(server.afk_timeout, server.afk_channel)
        )

        if server.features:
            embed.add_field(
                name="Features",
                value='\n'.join('• {}'.format(feature) for feature in server.features) or 'None'
            )

        embed.set_thumbnail(
            url="https://cdn.discordapp.com/icons/{server.id}/{server.icon}.png".format(server=server)
        )

        embed.add_field(
            name="Statistics",
            value="Server Age: {age}\n"
                  "Members: {members}\n"
                  "Channels: {channels}\n"
                  "Roles: {roles}\n".format(
                age=' '.join(x for x in remaining_time(
                    datetime.datetime.now(),
                    server.created_at, fmt=True)[:3] if x[0] != "0"),
                members=server.member_count,
                channels=len(server.channels),
                roles=len(server.roles) -1
            )
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!(?:roles|ranks)(?: (.*))?$",
             description="view a list of all roles in the server",
             usage="!roles [user]")
    async def server_roles(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        pad = 0
        padm = 0

        target = await get_object(
            self.client,
            name=args[0],
            message=message,
            types=(discord.Member,),
            similar=True
        ) if args[0] else server

        for role in target.roles:
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

        msg = "Roles in {}\n".format(server)
        for role in sorted(target.roles, key=lambda r: -r.position):
            if role.is_everyone:
                continue

            temp = "• `[{role.id}] ({members}) {name:<{pad}} {role.colour} {role.permissions.value} {hoist}`\n".format(
                pad=pad,
                role=role,
                name=clean_string(role.name),
                members=members.get(role.id, 0),
                hoist='hoisted' if role.hoist else ''
            )
            if len(msg) + len(temp) <= 1800:
                msg += temp
            else:
                break

        await self.client.send_message(
            channel,
            msg
        )

    @command(pattern="^!members ?(.*)$",
             description="view a list of members in the server",
             usage="!members")
    async def view_members(self, message: discord.Message, args: tuple):
        _server = message.server
        channel = message.channel
        user = message.author

        if args[0]:
            server = self.client.get_server(args[0])
        else:
            server = _server

        if server is None:
            await self.client.send_message(
                channel,
                "No server could be find for that ID."
            )
            return

        msg = ""
        for member in sorted(server.members, key=lambda m: -top_role(m, True).position):
            role = top_role(member)
            role_name = "[`{}`] ".format(clean_string(role)) if role else ''
            temp = "• {role}**{member}** `{perms}`\n".format(
                member=clean_string(member),
                perms=member.server_permissions.value,
                role=role_name
            )
            if len(msg + temp) >= 1500:
                break
            else:
                msg += temp

        embed = discord.Embed(
            description=msg,
            colour=discord.Colour.purple()
        )

        embed.set_author(
            name='Ranks for {server.name}.'.format(server=message.server),
            icon_url=server.icon_url
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!emojis$",
             description="show all custom emoji in the server",
             usage="!emojis")
    async def list_custom_emojis(self, message: discord.Message, *_):
        server = message.server  # type: discord.Server
        channel = message.channel
        user = message.author

        body = ""
        for n, emoji in enumerate(sorted(server.emojis, key=lambda e: int(e.id))):
            c = ':' if emoji.require_colons else ''
            temp = "{emoji} `{c}{emoji.name}{c}`".format(emoji=emoji, c=c)
            if len(body) + len(temp) <= 1800:
                body += temp
                body += "  |  "  if  (n+1) % 4 else "\n"
            else:
                break

        await self.client.send_message(
            channel,
            "Emojis in {}:\n".format(server.name) + body
        )

def top_role(member: discord.Member, everyone: bool = False):
    e = None
    for role in sorted(member.roles, key=lambda r: -r.position):
        if e is None and role.is_everyone:
            if everyone:
                e = role
            else:
                continue
        elif role.hoist:
            return role
    return e