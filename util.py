import logging
import datetime
import discord
import re
from random import *
import urllib.request
import requests
import io
from PIL import Image

log = logging.getLogger('pedantbot')

TIME_FORMAT = "%H:%M %Z"
DATE_FORMAT = "%d-%b-%Y"
DATETIME_FORMAT = "{} @ {}".format(DATE_FORMAT, TIME_FORMAT)


class StrProxy(object):
    def __init__(self, *args, **kwargs):
        self.array = []
        self.dict = {}

        for value in args:
            self.array.append(value)

        for (key, value) in kwargs.items():
            if value:
                self.dict[key] = value

    def __getitem__(self, item):
        return self.array[item]

    def __getattr__(self, item):
        return self.dict.get(item)

    def __str__(self):
        if not self.array:
            return ''

        temp = ''
        for (i, value) in enumerate(self.array):
            if not value:
                continue
            temp += str(value)
            if len(self.array)-1 > i and self.array[i+1]:
                temp += " "
        return temp

    def __repr__(self):
        return repr(str(self))

    def __eq__(self, other):
        if isinstance(other, StrProxy):
            if other.array != self.array:
                return False
            elif other.dict != self.dict:
                return False

        return str(self) == other


def remaining_time(
    d: datetime.datetime = None, d2: datetime.datetime = None, fmt: bool = False,
    years = True, months = True, weeks = True, days = True, hours = True, minutes = True, seconds = True, if_now = "now"
) -> StrProxy:

    if d is None:
        return StrProxy(if_now, years=0, days=0, hours=0, minutes=0, seconds=0)

    if d2 is not None:
        now, d = d, d2
    else:
        now = datetime.datetime.now()

    if d > now:
        prefix = "in"
        suffix = ""
    else:
        d, now = now, d
        prefix = ""
        suffix = "ago"

    diff = d - now
    seconds = abs(diff.total_seconds())

    Y, M, w, d, h, m, s = 0, 0, 0, 0, 0, 0, 0

    parts = []

    if years:
        Y = seconds // 86400 * 365
        seconds -= Y * 86400 * 365
        parts.append("{:.0f}Y".format(Y))

    if months:
        M = seconds // 86400 * 30
        seconds -= M * 86400 * 30
        parts.append("{:.0f}M".format(M))

    if weeks:
        w = seconds // 86400 * 7
        seconds -= w * 86400 * 7
        parts.append("{:.0f}w".format(w))

    if days:
        d = seconds // 86400
        seconds -= d * 86400
        parts.append("{:.0f}d".format(d))

    if hours:
        h = seconds // 3600
        seconds -= h * 3600
        parts.append("{:.0f}h".format(h))

    if minutes:
        m = seconds // 60
        seconds -= m * 60
        parts.append("{:.0f}m".format(m))

    if seconds:
        s = seconds % 60
        parts.append("{:.0f}s".format(s))

    return StrProxy(
        *parts,
        years=Y,
        months=M,
        weeks=w,
        days=d,
        hours=h,
        minutes=m,
        seconds=s
    )


def has_permission(permissions: discord.Permissions = discord.Permissions(), required: tuple = ()) -> bool:
    """
    :param permissions: discord.Permissions | discord.Member
    :param required: discord.Permissions | tuple[str] | str
    :return: bool
    """
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


async def confirm_dialog(client: discord.Client, channel: discord.Channel, user: discord.User,
                         title: str = "Are you sure?", description: str = "", options: tuple = ('y', 'n'),
                         author: dict = None, colour: discord.Color = discord.Color.default(), timeout=30):
    """
    :param client: discord.Client
    :param channel: discord.Channel
    :param title: str
    :param user: discord.User
    :param description: str
    :param options: tuple[str]
    :param author: dict
    :param colour: str
    :param timeout: int
    :return: discord.Message | None
    """
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


def printf(string: str="", **kwargs) -> str:
    if not string:
        return ""

    formatted = string
    for kwarg in kwargs:
        placeholder = "%{}%".format(kwarg)
        formatted = formatted.replace(placeholder, str(kwargs.get(kwarg, placeholder)))

    return formatted


def truncate(string: str, length: int = None, suffix: str = '...') -> str:
    if not length:
        return string
    if len(string) <= length:
        return string

    new_string = string[:length] + str(suffix)
    return new_string


async def join_voice(client: discord.Client, member: discord.Member, join_first: bool = False, move: bool = False):
    """join the nearest voice channel"""
    server = member.server
    vc = client.voice_client_in(server)
    if vc and not move:
        return vc

    else:
        channels = server.channels
        channel = None
        first_non_empty = None

        for chan in channels:
            if channel:
                break
            for user in chan.voice_members:
                if user == server.me:
                    continue
                if user == member:
                    channel = chan
                    break

                if not first_non_empty:
                    first_non_empty = chan

        if not channel:
            if first_non_empty and join_first:
                channel = first_non_empty  # type: discord.Channel
            else:
                if vc:
                    return vc
                return False

        if channel.permissions_for(server.me).connect is False:
            raise ConnectionError("Not allowed to connect to this channel")

        if vc and move:
            connected = await vc.move_to(channel)
        else:
            connected = await client.join_voice_channel(channel)
        if not connected:
            connected = vc
    return connected


def roll_dice(inp: str = "") -> list:
    rolls = []
    for throw in inp.split():
        try:
            dice = re.findall(
                r'^([0-9]*)(?=[Dd])[Dd]?([0-9]+)*(?:([+-]?[0-9]*))$',
                throw
            )
        except Exception as e:
            log.warning("{}\nInvalid dice: {}".format(
                e,
                throw
            ))
            continue

        for (n, d, m) in dice:
            if len(n) > 2 or len(d) > 3 or len(m) > 2:
                continue

            try:
                n, d, m = (int(n or '1'), int(d or '1'), int(m or '0'))
            except Exception as e:
                log.exception(e)
                continue

            if float(m) > (0.6 * d):
                continue
            if n < 1 or d < 1:
                continue

            string = "{}d{}{:+}".format(n, d, m)

            rolls = []
            for i in range(n):
                roll.append(randint(1, d) + m)

            roll = sum(rolls)
            data = (string, roll, rolls)

            rolls.append(data)
    return rolls


def find_match(haystack, needle: str = "", match_case=False):
    needle_words = needle.split()
    for item in haystack:
        if item[0] == '*' and item[-1] == '*' and item[1:-1].lower() in needle.lower():
            return (item, ())
        if item == needle or \
                match_case is True and item.lower() == needle.lower():
            return (item, ())

        args = []
        haystack_words = item.split()
        if len(haystack_words) != len(needle_words):
            continue

        for (i, word) in enumerate(haystack_words):
            if word == "%arg%":
                haystack_words[i] = needle_words[i]
                args.append(needle_words[i])

        if haystack_words == needle_words or \
                match_case is False and ' '.join(haystack_words).lower() == ' '.join(needle_words).lower():
            return (item, tuple(args))
    return (False, ())

try:
    from bot import VERSION
except ImportError:
    VERSION = '3.0'

HTTP_HEADERS = {'User-Agent': 'PedantBot v{}'.format(VERSION)}


def get(url):
    return urllib.request.urlopen(
        urllib.request.Request(
            url,
            data=None,
            headers=HTTP_HEADERS
        )
    )


def redis_address(inp=''):
    address = inp + ':6379'
    for address, port in re.findall(r'(.+?):([0-9]{1,5})', address):
        return (address, int(port))

    return ("localhost", 6379)

def random(length=1):
    string = ""
    if length > 0:
        for i in range(length):
            char = chr(randint(97, 122))
            if randint(0, 1) == 1:
                char = char.upper()
            string += char

    return string

#  Hyperlink markdown

hyperlink_pattern = re.compile(r'<a .*?href="((https?):\/\/([\w.]+)(\/[\w\/]*)?(\/[\w\/]*\.[\w]+)?)".*?>(.+?)<\/a>')
def markdown_links(string: str = ""):
    formatted = hyperlink_pattern.sub(
        r'[\6](\1)',
        string
    )
    return formatted


def avatar(target: [discord.Server, discord.User, discord.Member] = None):
    base = "https://cdn.discordapp.com/{}/{}/{}.{}"
    hash = target.icon if isinstance(target, discord.Server) else target.avatar
    return base.format(
        "icons" if isinstance(target, discord.Server) else "avatars",
        target.id,
        hash,
        "gif" if hash.startswith('a_') else "png"
    )


def is_image_embed(embed: discord.Embed):
    if hasattr(embed, 'type'):
        return embed.type == 'image'
    elif hasattr(embed,'get'):
        return embed.get('type') == 'image'

    return False

def not_me(msg: discord.Message):
    return msg.author != msg.server.me


async def get_last_image(channel, client):
    async for msg in client.logs_from(channel, limit=50, reverse=False):
        try:
            images = list(filter(is_image_embed, msg.embeds))
            if images:
                url = images[0].get('url', '')
            elif msg.attachments:
                url = msg.attachments[0]['proxy_url']
            else:
                continue

            if (int(requests.head(
                    url,
                    headers={'Accept-Encoding': 'identity'}).headers['content-length']) / 1024 / 1024
                ) >= 8:

                await client.send_message(channel, 'Image is too large.')
                return

            attachment = get(url)
            content_type = attachment.headers.get_content_type()

            if 'image' in content_type:
                img_file = io.BytesIO(attachment.read())
                img = Image.open(img_file)
                return img
        except Exception as e:
            log.exception(e)
            return None


def search(term, iterable, similar: bool = False, attr: str = 'name'):
    if similar:
        needle = ".*{}.*".format(re.escape(term))

    def case_sensitive(item):
        this = getattr(item, attr) if hasattr(item, attr) else str(item)
        if similar:
            return re.match(needle, str(this))
        else:
            return this == term

    def case_insensitive(item):
        this = getattr(item, attr) if hasattr(item, attr) else str(item)
        if similar:
            return re.match(needle.lower(), str(this).lower()) is not None
        else:
            return str(this).lower() == term.lower()

    return discord.utils.find(case_sensitive, iterable) or \
           discord.utils.find(case_insensitive, iterable)


async def get_object(cln: discord.Client, name: str, message: discord.Message = None, similar: bool = False,
                     types: tuple = (discord.Member, discord.Role, discord.Channel, discord.Server)):
    target = None
    if message and name == 'me' and discord.Member in types:
        return message.author
    elif message and name == 'channel' and discord.Channel in types:
        return message.channel
    elif message and name == 'server' and discord.Server in types:
        return message.server
    elif message.mentions and discord.Member in types:
        return message.mentions[0]
    elif message.channel_mentions and discord.Channel in types:
        return message.channel_mentions[0]
    elif name:
        if discord.Member in types:
            haystack = sorted(message.server.members, key=lambda m: -m.top_role.position)
            target = search(name, haystack, similar=similar) or \
                     search(name, haystack, similar=similar, attr='nick') or \
                     search(name, haystack, similar=similar, attr='id')

        if target is None and discord.Channel in types:
            haystack = sorted(message.server.channels, key=lambda c: c.position)
            target = search(name, haystack, similar=similar) or \
                     search(name, haystack, similar=similar, attr='id')

        if target is None and discord.Role in types:
            haystack = sorted(message.server.roles, key=lambda r: r.position)
            target = search(name, haystack, similar=similar) or \
                     search(name, haystack, similar=similar, attr='id')

    return target

def fancy_join(d):
    return ", ".join([str(x) for x in data[:-2]] + [" and ".join(str(x) for x in data[-2:])])
