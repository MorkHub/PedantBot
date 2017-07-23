import discord
from classes.jsondict import JSONDict


class Channel(JSONDict):
    def __init__(self, channel: discord.Channel = None, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(channel, discord.Channel) and not kwargs:
            raise ValueError("Must pass a Channel or specify attributes.")

        self.id = channel.id
        self.name = channel.name
        self.topic = channel.topic or "None"
        self.position = channel.position
        self.type = str(channel.type)
        self.user_limit = channel.user_limit
        self.is_default = channel.is_default
        self.created_at = channel.created_at.timestamp()
