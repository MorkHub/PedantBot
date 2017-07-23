import discord
from classes.jsondict import JSONDict


class Emoji(JSONDict):
    def __init__(self, emoji: discord.Emoji = None, **kwargs):
        super().__init__(**kwargs)
        if not (isinstance(emoji, discord.Emoji) or isinstance(emoji, str)) and not kwargs:
            raise ValueError("Must pass an Emoji or specify attributes.")

        if not isinstance(emoji, discord.Emoji):
            self.name = emoji
            self.id = None
            return

        self.id = emoji.id
        self.name = emoji.name
