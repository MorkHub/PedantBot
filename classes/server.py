import discord
from classes.jsondict import JSONDict
from classes.role import Role
from classes.emoji import Emoji


class Server(JSONDict):
    _ignore = ['emoji', 'roles']

    def __init__(self, server: discord.Server = None, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(server, discord.Server) and not kwargs:
            raise ValueError("Must pass a Server or specify attributes.")

        self.id = server.id
        self.name = server.name

        self.roles = []
        for role in server.roles:
            if role.is_everyone:
                continue
            if role.managed:
                continue
            role = Role(role)
            self.roles.append(role)

        self.emoji = []
        for emoji in server.emojis:
            emoji = Emoji(emoji)
            self.emoji.append(emoji)

        self.region = str(server.region)
        if server.afk_channel:
            self.afk_channel = server.afk_channel.id
        else:
            self.afk_channel = ""

        self.icon = server.icon
        self.member_count = server.member_count
        self.owner = server.owner_id
        self.large = server.large
        self.mfa_level = server.mfa_level
        self.features = server.features
        self.splash_url = server.splash_url
        self.created_at = server.created_at.timestamp()
