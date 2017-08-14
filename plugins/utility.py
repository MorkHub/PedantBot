import logging
import os

import aioredis
import pytz
from PIL import Image, ImageDraw, ImageFont
from imageio import mimwrite
from numpy import array
from classes.plugin import Plugin

from decorators import *
from util import *
import socket

log = logging.getLogger('pedantbot')


class Utility(Plugin):
    plugin_name = "utility commands"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @command(pattern="^!who(?:is)? *([^ ]*)$",
             description="get information about a user",
             usage="!whois [user]")
    async def user_information(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,)
        ) if args[0] else user

        if not target:
            await self.client.send_message(
                channel,
                "Could not find a user by that name."
            )
            return

        embed = discord.Embed(
            timestamp=target.created_at,
            colour=target.colour
        )
        embed.set_thumbnail(
            url=target.avatar_url or target.default_avatar_url
        )

        if target.game:
            prefix = "streaming" if target.game.type == 1 else "playing"
        else:
            prefix = ""

        body = "**Username**: {user.name}\n" \
            "**Discord Tag**: #{user.discriminator}\n" \
            "**Snowflake ID**: `{user.id}`\n" \
            "**Status**: {user.status}\n" \
            "**Game**: {action} *{user.game}*".format(
                user=target,
                action=prefix
            )

        embed.add_field(
            name="__User__",
            value=body
        )

        db = self.client.db.redis  # type: aioredis.Redis
        locale = await db.get('Time.global:{}'.format(user.id))
        locale2 = await db.get('Time.global:{}'.format(target.id))

        tz = None

        if locale:
            try:
                tz = pytz.timezone(locale)
            except pytz.exceptions.UnknownTimeZoneError:
                pass

        body = "**Created at**: {created}\n" \
            "**Joined at**: {joined}\n" \
            "**Timezone**: {tz}".format(
                created=datetime.datetime.fromtimestamp(target.created_at.timestamp(), tz=tz).strftime(DATETIME_FORMAT),
                joined=datetime.datetime.fromtimestamp(target.joined_at.timestamp(), tz=tz).strftime(DATETIME_FORMAT),
                tz=locale2 or "Unknown"
            )

        embed.add_field(
            name="__Dates__",
            value=body,
            inline=False
        )

        db = self.client.db.redis  # type: aioredis.Redis
        xp = await db.get('Levels.{server.id}:player:{user.id}:xp'.format(
            server=server,
            user=target
        )) or 0
        xp = int(xp)

        body = "**Nickname**: {user.nick}\n" \
            "**Roles**: {roles}\n" \
            "**Colour**: `{user.colour}`\n" \
            "**XP**: `{xp:,}`\n".format(
                user=target,
                roles=', '.join([
                    str(x) for x in sorted(target.roles, key=lambda r: -r.position) if not x.is_everyone
                ]) or None,
                xp=xp
            )

        embed.add_field(
            name="__This server__",
            value=body,
            inline=False
        )
        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!avatar ?(.*)$",
             description="view a user's avatar",
             usage="!avatar [user|server]")
    async def view_avatar(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        await self.client.send_typing(channel)

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member, discord.Server)
        ) if args[0] else user

        if not target:
            await self.client.send_message(
                channel,
                "No user found by that name."
            )
            return

        if isinstance(target, discord.Server):
            attr = target.icon
            path = 'icons'
        else:
            attr = target.avatar
            path = 'avatars'

        url = 'https://cdn.discordapp.com/{path}/{id}/{avatar}.{ext}'.format(
            path=path,
            id=target.id,
            avatar=attr,
            ext='gif' if attr.startswith('a_') else 'png'
        )

        embed = discord.Embed(
            title=str(target),
            colour=discord.Color.magenta(),
            url=url
        )
        embed.set_image(url=url)
        embed.set_footer(text='ID: #{}'.format(target.id))

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!invites ?(.*)$",
             description="list active invite links",
             usage="!invites")
    async def view_invites(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        server = None
        if len(args) > 0:
            try:
                server = await self.client.get_server(args[0])
            except Exception:
                pass
        if not server:
            server = message.server

        try:
            active_invites = await self.client.invites_from(server)
        except:
            await self.client.send_message(
                channel,
                "I do not have permission to view server invites.\n"
                "Requires `manage_server`."
            )
            return

        template = '{code}: for {invite.channel.mention} by `{invite.inviter}`, used: `{uses}`{remaining}'

        code_active = '[`{invite.code}`]({invite.url})'
        code_revoked = '[`{invite.code}`]'

        uses_infinite = '{invite.uses}'
        uses_finite = '{invite.uses}/{invite.max_uses}'

        remaining_finite = ', expires approx {remaining}'

        unlimited_invites = []
        limited_invites = []
        revoked_invites = []

        unlim_count = 0
        lim_count = 0
        rev_count = 0

        length = 0
        for invite in active_invites:  # type: discord.Invite
            if (invite.max_age or invite.max_uses) and not has_permission(user, 'create_instant_invite'):
                continue

            string = template.format(
                code=code_revoked if invite.revoked else code_active,
                uses=uses_finite if invite.max_uses else uses_infinite,
                invite=invite,
                remaining=remaining_finite if invite.max_age else ''
            ).format(
                invite=invite,
                remaining=remaining_time(datetime.datetime.now() + datetime.timedelta(seconds=invite.max_age))
            )

            if length <= 1500:
                length += len(string)

            if invite.revoked:
                rev_count += 1
                if length <= 1500:
                    revoked_invites.append('~~'+string+'~~')
            elif invite.max_age != 0 or invite.max_uses:
                lim_count += 1
                if length <= 1500:
                    limited_invites.append(string)
            else:
                unlim_count += 1
                if length <= 1500:
                    unlimited_invites.append(string)

        embed = discord.Embed(
            title='__Invite links for {0.name}__'.format(server),
            color=discord.Colour.purple()
        )

        if unlimited_invites:
            embed.add_field(
                name='Unlimited Invites ({})'.format(unlim_count),
                value='\n'.join(unlimited_invites[:5])
            )

        if limited_invites:
            embed.add_field(
                name='Temporary/Finite Invites ({})'.format(lim_count),
                value='\n'.join(limited_invites)
            )

        if revoked_invites:
            embed.add_field(
                name='Revoked Invites ({})'.format(rev_count),
                value='\n'.join(revoked_invites)
            )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!(?:permissions|perms)(?: (.*))?$",
             description="list permissions available to a user",
             usage="!permissions [user]")
    async def list_perms(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,)
        ) if args[0] else user

        if not target:
            await self.client.send_message(
                channel,
                "Could not find a user by that name."
            )
            return

        permissions = channel.permissions_for(target)
        granted = []
        denied = []
        for permission in permissions:
            name = permission[0].replace('_',' ').title().replace('Tts', 'TTS')
            field = granted if permission[1] else denied
            field.append(name)

        embed = discord.Embed(
            colour=discord.Color.blue()
        )
        embed.set_author(
            name="Perms for {user.name} in {server.name}".format(
                user=target,
                server=target.server
            ),
            icon_url=target.avatar_url or target.default_avatar_url
        )
        if len(granted) > 0:
            embed.add_field(
                name="Permissions Granted",
                value="```diff\n+{}```".format('\n+'.join(granted)),
                inline=True
            )
        if len(denied) > 0:
            embed.add_field(
                name="Permissions Denied",
                value="```diff\n-{}```".format('\n-'.join(denied)),
                inline=True
            )

        msg = await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!ping$",
             description="test your ping",
             usage="!ping")
    async def ping(self, message: discord.Message, args: tuple):
        channel = message.channel

        sent = message.timestamp
        now = datetime.datetime.utcnow()
        if now <= sent:
            sent, now = now, sent

        diff = now - sent
        seconds = diff.seconds * 1000 + diff.microseconds // 1000

        await self.client.send_message(
            channel,
            ":ping_pong: Pong! {}ms".format(seconds)
        )

    @command(pattern="^!botratio$",
             description="see the ratio of bots to humans in the server",
             usage="!botratio")
    async def bot_ratio(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel

        humans = 0;
        bots = 0
        for member in server.members:
            if member.bot:
                bots += 1
            else:
                humans += 1

        if humans > bots:
            short_string = "{server}'s human:bot ratio"
            string = "The ratio of humans to bots is: __{humans}:{bots}__\nThat means there is about {ratio:.1f}x as many humans as bots."
            ratio = humans / bots
            icon = "hooman"
            colour = discord.Colour.magenta()
        else:
            short_string = "{server}'s bot:human ratio"
            string = "The ratio of bots to humans is: __{bots}:{humans}__\nThat means there is about {ratio:.1f}x as many bots as humans."
            ratio = bots / humans
            icon = "robit"
            colour = discord.Colour.blue()

        embed = discord.Embed(
            description=string.format(
                server=server,
                humans=humans,
                bots=bots,
                ratio=ratio
            ),
            colour=colour
        )
        embed.set_author(
            name=short_string.format(
                server=server
            ),
            icon_url=server.icon_url
        )
        embed.set_thumbnail(url='https://themork.co.uk/assets/{}.png'.format(icon))

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!age$",
             description="view the ages of users in this server",
             usage="!age")
    async def user_ages(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        _user = message.author
        users = server.members

        def age(user=discord.User()):
            return discord.utils.snowflake_time(user.id)

        string = ''
        users = sorted([x for x in users if not x.bot], key=age)
        for n, user in enumerate(sorted(users, key=age)[:20]):
            user.name = clean_string(user.name)
            string += '{n:>2}.  {d}**{user}**:`{user.id}` joined on `{date}`{d}\n'.format(
                n=n + 1,
                user=user,
                d="__" if user == _user else '',
                date=age(user).strftime('%d %B %Y @ %I:%M%p')
            )

        embed = discord.Embed(
            title="Age of users in {server.name}".format(server=message.server),
            color=discord.Colour.blue(),
            description=string
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!(?:quotemsg|qm) ([0-9]+)$",
             description="quote a message in the server",
             usage="!quotemsg <message id>", cooldown=2)
    async def quote_message(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        try:
            _message = await self.client.get_message(channel, args[0])  # type: discord.Message
        except discord.NotFound:
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
            embed.description += "\n`Rich Embed not shown`"

        embed.set_author(
            name=_message.author,
            icon_url=avatar(_message.author)
        )

        embed.set_footer(
            text="{} | Message: #{}".format(
                message.server.name,
                _message.id
            ),
            icon_url=avatar(_message.server)
        )

        await self.client.send_message(
            channel,
            "{user} quoted something".format(user=user),
            embed=embed
        )

    @command(pattern="^!spoiler ([0-9]+)(?: (.*))$",
             description="apply a spoiler warning to a message",
             usage="!spoiler <message ID>:[reason]")
    async def add_spoiler(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        try:
            msg = await self.client.get_message(channel, args[0])
        except discord.HTTPException:
            await self.client.send_message(
                channel,
                "No message found by that ID"
            )
            return

        reason = args[1]

        usr = msg.author

        img = generate_spoiler("{}: {}".format(
            msg.author,
            msg.clean_content
        ))

        await self.client.send_file(
            channel,
            img,
            content="**{}**'s message has been marked as a spoiler for: `{}`".format(
                usr,
                reason or 'No reason given'
            )
        )

        os.remove(img)

    @command(pattern="^!ip$",
             description="view IP address for bot",
             usage="!ip",
             global_cooldown=3)
    async def get_bot_ip(self, message: discord.Message, *_):
        channel = message.channel
        user = message.author

        if not has_permission(user, 'bot_owner'):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to view public IP address.\n"
                "Requires `bot_owner`.".format(
                    user=user
                )
            )
            return


        response = urllib.request.urlopen('https://api.ipify.org/')
        external = response.read().decode('utf-8')

        # internal = socket.getfqdn()
        internal = [l for l in ([ip for ip in socket.gethostbyname_ex(socket.gethostname())[2] if not ip.startswith("127.")][:1], [[(s.connect(('8.8.8.8', 53)), s.getsockname()[0], s.close()) for s in [socket.socket(socket.AF_INET, socket.SOCK_DGRAM)]][0][1]]) if l][0][0]

        embed = discord.Embed(
            title="IP address for {user.name}".format(user=self.client.user),
            color=message.author.color
        )

        embed.add_field(
            name='Internal',
            value='```{}```'.format(internal)
        )

        embed.add_field(
            name='External',
            value='```{}```'.format(external)
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!id(?: (.*))?$",
             description="get snowflake identifier for a discord user/channel/role",
             usage="!id <user|channel|role>")
    async def get_snowflake(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        target = await get_object(
            self.client,
            args[0],
            message,
            similar=True
        ) if args[0] else user

        if target is None:
            await self.client.send_message(
                channel,
                "No object found by that name."
            )
            return

        thumb = None
        if isinstance(target, discord.Channel):
            if target.type == discord.ChannelType.voice:
                name = target.name
            else:
                name = "#{}".format(target.name)
        elif isinstance(target, discord.Member):
            name = "@{}".format(target.name)
            thumb = "https://cdn.discordapp.com/avatars/{}/{}.{}".format(
                target.id,
                target.avatar,
                'gif' if target.avatar.startswith('a_') else 'png'
            )
        elif isinstance(target, discord.Role):
            name = "{}{}".format('@' if target.mentionable else '', target.name)
        elif isinstance(target, discord.Server):
            name = target.name
            thumb = "https://cdn.discordapp.com/icons/{}/{}.png".format(
                target.id,
                target.icon
            )
        else:
            name = str(target)

        embed = discord.Embed(
            title="Snowflake ID for {target}".format(target=name),
            description="Mobile users [click here](https://themork.co.uk/code/?code={0})\n```\n{0}```".format(target.id),
            colour=discord.Colour.magenta()
        )

        if thumb:
            embed.set_thumbnail(
                url=thumb
            )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^!oauth(?: (.*))?$",
             description="get invite link",
             usage="!oauth [basic|full]")
    async def get_oauth_link(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel

        if not args[0] or args[0] == "full":
            value = 334621751
        else:
            value = 36826112

        me = await self.client.application_info()  # type: discord.AppInfo

        link = discord.utils.oauth_url(
            me.id,
            permissions=discord.Permissions(value),
            server=server
        )

        await self.client.send_message(
            channel,
            "<{}>".format(link)
        )

    @command(pattern="!(?:checkurl|url|unshorten) (.+)",
             description="check where a short URL redirects to",
             usage="!checkurl <website address>")
    async def check_url(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        session = requests.Session()
        session.max_redirects = 1

        long = urllib.request.quote(args[0], safe='://')

        try:
            res = session.head(long, allow_redirects=False)
        except Exception as e:
            await self.client.send_message(
                channel,
                clean_string(e)
            )
            return

        redirect = res.is_redirect

        for redirects in range(10):
            if res.is_redirect:
                res = session.head(long, allow_redirects=True)
            else:
                break

        body = "URL: `{}`\n".format(clean_string(long))
        base = str(res.status_code)[0]

        if base == "2":
            colour = discord.Colour.green()
        if base == "3" or base == "4":
            colour = discord.Colour.red()
        elif base == "5":
            colour = discord.Colour.orange()
        else:
            colour = discord.Colour.gold()

        body += "Redirect: `{}`\n".format("Yes" if redirect else "No")
        if redirect:
            body += "Redirects to: ```{}```\n".format(clean_string(truncate(res.url)))
        body += "Status code: `{} {}`\n".format(res.status_code, clean_string(truncate(res.reason)))
        body += "Time taken: `{:,.0f}ms`".format(res.elapsed.total_seconds() * 1000)

        embed = discord.Embed(
            title="URL Checked",
            description=body,
            colour=colour
        )

        await self.client.send_message(
            channel,
            embed=embed
        )



font = ImageFont.truetype("arial.ttf", 18)

def generate_spoiler(text=""):
    warning = Image.new("RGB", (500, 40), "WHITE")
    spoiler = Image.new("RGB", (500, 40), "BLACK")
    draw_1 = ImageDraw.Draw(warning)
    draw_2 = ImageDraw.Draw(spoiler)

    warning_text = "Spoiler Inside."
    w, h = warning.size
    t_w, t_h = draw_1.textsize(warning_text, font=font)
    pad = h / 2 - t_h / 2
    draw_1.text((pad, pad), warning_text, font=font, fill="BLACK")

    w, h = spoiler.size
    t_w, t_h = draw_2.textsize(text, font=font)
    pad = h / 2 - t_h / 2
    draw_2.text((pad, pad), text, font=font, fill="WHITE")

    name = '{}.gif'.format(random(12))
    mimwrite(name, [array(warning), array(spoiler)], "GIF-PIL", loop=1)

    return name
