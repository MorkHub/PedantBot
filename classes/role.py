import discord
from classes.jsondict import JSONDict


class Role(JSONDict):
    def __init__(self, role: discord.Role = None, **kwargs):
        super().__init__(**kwargs)
        if not (isinstance(role, discord.Role) or kwargs):
            raise ValueError("Must pass a Role or specify attributes.")

        self.id = role.id
        self.name = role.name
        self.permissions = role.permissions.value
        self.created_at = role.created_at.timestamp()
        self.colour = role.colour.value
        self.position = role.position
        self.managed = role.managed
        self.mentionable = role.mentionable
        self.hoist = role.hoist
        self.server = role.server
