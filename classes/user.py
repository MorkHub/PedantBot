import discord
from classes.jsondict import JSONDict


class User(JSONDict):
    _ignore = ['nick', 'top_role', 'permissions']

    def __init__(self, user: discord.User = None, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(user, discord.User) and not kwargs:
            raise ValueError("Must pass a Channel or specify attributes.")

        self.id = user.id
        self.name = user.name
        self.discriminator = user.discriminator
        self.avatar = user.avatar
        self.bot = user.bot
        self.created_at = user.created_at.timestamp()

        if not isinstance(user, discord.Member):
            return

        self.nick = user.nick
        self.joined_at = user.joined_at.timestamp()
        self.top_role = user.top_role.id
        self.permissions = user.server_permissions.value
        self.colour = user.colour
