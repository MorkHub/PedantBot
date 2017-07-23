import discord
from classes.jsondict import JSONDict
from classes.server import Server
from classes.channel import Channel
from classes.user import User

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    import datetime

class Message(JSONDict):
    _ignore = ['clean_content', 'channel_mentions', 'mentions', 'pinned',
               'server', 'channel', 'embeds', 'timestamp', 'edited_timestamp']

    def __init__(self, message: discord.Message = None, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(message, discord.Message) and not kwargs:
            raise ValueError("Must pass a 'discord.Message' or specify attributes.")

        if message is None:
            return

        self.id = message.id
        self.server = Server(message.server)
        self.channel = Channel(message.channel)
        self.content = message.content
        self.clean_content = message.clean_content
        self.author = message.author
        self.attachments = message.attachments
        self.channel_mentions = message.channel_mentions
        self.embeds = tuple(embed.__dict__ for embed in message.embeds)
        self.edited_timestamp = message.edited_timestamp  # type: datetime.datetime
        self.timestamp = message.timestamp  # type: datetime.datetime
        self.pinned = message.pinned
        self.mentions = message.mentions
        self.type = message.type

    def to_dict(self, simple=False):
        if simple:
            return {
                **super().to_dict(True),
                'server': self.server.id,
                'channel': self.channel.id,
                'timestamp': self.timestamp.timestamp(),
                'edited_timestamp': self.edited_timestamp.timestamp() if self.edited_timestamp else None
            }
        else:
            return super().to_dict()
