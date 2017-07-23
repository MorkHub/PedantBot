# from storage import Storage
# import asyncio
# import discord
import json
import logging
import uuid

from classes.plugin import Plugin
from decorators import *
from util import *

log = logging.getLogger('pedantbot')


class Admin(Plugin):
    plugin_name = "administration"
    config_vars = {
        'thresholds': "JSON",

    }

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)

    @command(pattern="^!status ?(.*)$",
             description="set bot's playing status (owner only)",
             usage="!status [message]")
    async def set_status(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        app = await self.client.application_info()  # type: discord.AppInfo
        owners = await self.db.redis.smembers('owners') or {}
        if not user.id in owners:
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to set bot status.\n"
                "Requires `bot_owner`.".format(
                    user=user
                )
            )
            return

        text = args[0].strip() or None
        current = server.me.game
        if text is current or (hasattr(current, 'name') and current.name == text):
            msg = "Status not changed."
            status = None
        elif text:
            status = discord.Game(name=text)
            msg = "Updated status: {}".format(text)
        else:
            status = discord.Game()
            msg = "Cleared status."

        if status:
            await self.client.change_presence(game=status)

        await self.client.send_message(
            channel,
            msg
        )

    # Warnings & Bans
    @command(pattern='\.warn ([^ ]*)(?: (.*))?',
             description="warn a user, optionally provide a reason",
             usage=".warn <user> [reason]")
    async def warn_user(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel
        user = message.author

        if not has_permission(user, "ban_members"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to warn users.\n"
                "Requires `ban_users`.".format(
                    user=user
                )
            )
            return

        reason = args[1]
        target = None
        if len(message.mentions) > 0:
            target = message.mentions[0]

        if not target or not isinstance(user, discord.Member):
            target = server.get_member_named(args[0])
            if not target:
                target = server.get_member(args[0])

        if not target or not isinstance(user, discord.Member):
            await self.client.send_message(
                channel,
                "No user by that name could be found in this server."
            )
            return

        this_warning = {
            'id': str(uuid.uuid4()),
            'user': target.id,
            'reason': reason or "-",
            'timestamp': datetime.datetime.now().timestamp(),
            'by': user.id,
            'cancelled': False
        }
        warning_json = json.dumps(this_warning)

        storage = await self.get_storage(server)
        warnings = await storage.smembers('warnings:{}'.format(target.id))
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        warn_count = 0
        for i in warnings:
            warning = await storage.get('warning:{}'.format(i))
            if warning is None:
                continue

            warning = json.loads(warning)
            if not warning.get('cancelled', False):
                warn_count += 1

        if warn_count+1 >= thresholds.get('ban', 5):
            action = "ban"
            long = "They will not be able to join again unless they are unbanned."
        elif warn_count+1 == thresholds.get('kick', 3):
            action = "kick"
            long = "They will be able to join again with an invite link."
        else:
            action = "written warning only"
            long = ""

        res = await confirm_dialog(
            self.client,
            channel,
            title="Warn {user} for \"{reason:.20}\"?".format(
                user=target,
                reason=reason
            ),
            description="Are you sure you want to warn {user} in {server}?\n"
                        "This warning will result in a `{action}`.\n"
                        "{long}".format(
                user=target,
                server=server,
                action=action,
                long=long
            ),
            user=user,
            author={
                'name': target,
                'icon': target.avatar_url or target.default_avatar_url
            },
            colour=discord.Colour.red()
        )

        if not res:
            return

        if res.content.lower() == 'y':
            added = await storage.set('warning:{}'.format(this_warning.get('id')), warning_json)
            if added:
                added = await storage.sadd('warnings:{}'.format(target.id), this_warning.get('id'))
            if not added:
                await self.client.send_message(
                    channel,
                    "Could not add warning."
                )
                return

            func = None
            suffix = ""
            if action == "ban":
                suffix = "ned"
                func = self.client.ban
            elif action == "kick":
                suffix = "ed"
                func = self.client.kick
            elif action == "written warning only":
                action = "warned"

            try:
                if func:
                    await func(target)
                private = await self.client.start_private_message(target)
                await self.client.send_message(
                    private,
                    "You have been {action} from {server} for: `{reason}`".format(
                        user=target,
                        server=server,
                        reason=reason or "-",
                        action=action+suffix
                    )
                )
            except discord.Forbidden as e:
                log.exception(e)
            except discord.HTTPException:
                pass

            await self.client.send_message(
                channel,
                "{user.mention} has been {action} for: `{reason}`.\n"
                "Please respect the rules of this server.".format(
                    user=target,
                    reason=reason or "-",
                    action=action + suffix
                )
            )

        else:
            await self.client.send_message(
                channel,
                "Cancelled. No action has been taken."
            )

    @command(pattern='\.(?:warns|warnlist)(?: (.*))?',
             description="list warnings for user or self",
             usage='.warnlist <user>')
    async def list_warnings(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        target = None
        if len(message.mentions) > 0:
            target = message.mentions[0]

        if (not target or not isinstance(user, discord.Member)) and args[0]:
            target = server.get_member_named(args[0])
            if not target:
                target = server.get_member(args[0])

        if not args[0]:
            target = user

        if not (target == user or has_permission(user, "ban_members")):
            await self.client.send_message(
                channel,
                "{user.mention}, You cannot list warnings for another user.\n"
                "Requires `ban_members`.".format(user=user)
            )
            return

        if not target or not isinstance(user, discord.Member):
            await self.client.send_message(
                channel,
                "No user by that name could be found in this server."
            )
            return

        storage = await self.get_storage(server)
        warnings = await storage.smembers('warnings:{}'.format(target.id))
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        warn_count = 0
        for i in warnings:
            warning = await storage.get('warning:{}'.format(i))
            if warning is None:
                continue
            warning = json.loads(warning)
            if not warning.get('cancelled', False):
                warn_count += 1

        if warn_count + 1 >= thresholds.get('ban', 5):
            action = "ban"
        elif warn_count + 1 == thresholds.get('kick', 3):
            action = "kick"
        else:
            action = "written warning only"

        body = ''
        for n, warning_id in enumerate(warnings):
            warning_json = await storage.get('warning:{}'.format(warning_id))
            try:
                warning = json.loads(str(warning_json))
            except Exception as e:
                log.exception(e)

            if not warning:
                continue

            time_string = str(
                datetime.datetime.utcfromtimestamp(float(warning.get('timestamp'))).strftime(DATETIME_FORMAT)
            )
            body += "__#{i}__ [`{time}`]: *`{reason:.100}`* by {by}\n".format(
                i=n,
                time=time_string,
                reason=str(warning.get('reason')) or "-",
                by=server.get_member(warning.get('by')) or server.name
            )

        embed = discord.Embed(
            title="Warnings for {user} in {server}".format(
                user=target,
                server=server
            ),
            description=body
        )
        embed.add_field(
            name="Next warning penalty",
            value="{user} will receive: `{action}`".format(
                user=target,
                action=action
            )
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern='\.threshold (kick|ban) ([0-9]+)',
             description="set the warning threshold for kick/ban",
             usage=".threshold <kick|ban> <# of warnings>")
    async def set_threshold(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.channel

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to change warning thresholds.\n"
                "Requires `manage_server`.".format(user=user)
            )
            return

        storage = await self.get_storage(server)
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        action, threshold = args  # type: str
        changed = None

        if isinstance(threshold, int) or (isinstance(threshold, str) and threshold.isnumeric()):
            threshold = int(threshold)
            if 1 <= threshold <= 10:
                thresholds[action] = int(threshold)
                changed = await storage.set('thresholds', json.dumps(thresholds))
                if changed:
                    await self.client.send_message(
                        channel,
                        "Threshold for `{}` changed to {}".format(
                            action,
                            threshold
                        )
                    )

        if not changed:
            await self.client.send_message(
                channel,
                "Threshold for `{}` could not be changed.".format(action)
            )

    @command(pattern="\.threshold",
             description="view the current warning threshold for kick/ban",
             usage=".threshold")
    async def view_thresholds(self, message: discord.Message):
        server = message.server
        channel = message.channel

        storage = await self.get_storage(server)
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        embed = discord.Embed(
            title="Warning thresholds for {}".format(server),
            description="**Kick**: `{0[kick]}`\n**Ban**: `{0[ban]}`".format(thresholds)
        )
        await self.client.send_message(
            channel,
            embed=embed
        )
        return

    @command(pattern='\.kick ([^]+) ([^"]*)',
             description="kick user from the current server",
             usage=".kick <user> [reason]")
    async def kick_user(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        target = None  # type: discord.Member
        reason = None
        if len(message.mentions) > 0:
            target = message.mentions[0]

        if len(args) > 0:
            target = server.get_member_named(args[0])
            if not target:
                target = server.get_member(args[0])

        if not target:
            await self.client.send_message(
                channel,
                "No user by that name could be found in this server."
            )
            return

        if len(args) > 1:
            reason = args[1]

        if not target == server.owner and target.top_role.position >= user.top_role.position:
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to kick that user.\n"
                "{target.name} is too highly ranked.\n"
                "Requires higher role than `{target.top_role}`.".format(
                    user=user,
                    target=target,
                )
            )
            return

        res = await confirm_dialog(
            self.client,
            channel,
            title="Confirm kick {user} from {server}?".format(
                user=target,
                server=server
            ),
            description="Responding with `y` will remove {user.mention} from {server}\n"
            "They will be able to join again with an invite link.".format(
                user=target,
                server=server
            ),
            user=user,
            author={
                'name': target,
                'icon': target.avatar_url or target.default_avatar_url
            },
            colour=discord.Colour.red()
        )

        if not res:
            return
        
        if res.content.lower() == 'y':
            kicked = None
            try:
                kicked = await self.client.kick(target)
            except discord.Forbidden:
                pass

            try:
                private = await self.client.start_private_message(target)
                await self.client.send_message(
                    private,
                    "You have been kicked from {server} for: `{reason}`".format(
                        user=target,
                        server=server,
                        reason=reason or "-",
                    )
                )
            except discord.Forbidden as e:
                log.exception(e)
            except discord.HTTPException:
                pass

            if not kicked:
                await self.client.send_message(
                    channel,
                    "Could not kick user."
                )
                return

            await self.client.send_message(
                channel,
                "{user.mention} has been kicked for: `{reason}`.\n"
                "Please respect the rules of this server.".format(
                    user=target,
                    reason=reason or "-",
                )
            )
        else:
            await self.client.send_message(
                channel,
                "Cancelled. No action has been taken."
            )

    @command(pattern="^\.(?:banlist|bans)$",
             description="list users who have been banned form this server",
             usage=".bans")
    async def list_bans(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "ban_members"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to view bans.\n"
                "Requires `ban_members`.".format(
                    user=user
                )
            )
            return

        bans = await self.client.get_bans(server)

        body = ''
        for user in bans:
            body += "• {0.mention} (`{0.name}#{0.discriminator}`): [`{0.id}`]\n".format(user)

        embed = discord.Embed(
            title="Banned users in {0.name}".format(server),
            color=discord.Color.red(),
            description=body
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="\.clean ([0-9]*)",
             description="clean up bot messages",
             usage=".clean 100")
    async def clean_channel(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        limit = 20
        if len(args) > 0:
            if args[0].isnumeric():
                limit = int(args[0])

        if not 0 < limit <= 200:
            limit = 20

        await self.client.purge_from(
            channel,
            check=lambda m: m.author == self.client.user,
            limit=limit
        )

    @command(pattern="^\.purge ([0-9]+) ?(.*)$",
             description="purge messages from channel",
             usage=".purge <amount> [user]")
    async def purge_channel(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        limit = 20
        if len(args) > 0:
            if args[0].isnumeric():
                limit = int(args[0])

        if not 0 < limit <= 200:
            limit = 20

        target = None
        if message.mentions:
            target = message.mentions[0]
        elif args[1]:
            if args[1] == "bots":
                target = "bots"
            else:
                target = server.get_member_named(args[1])
            if not target:
                await self.client.send_message(
                    channel,
                    "No user found by that name."
                )
                return

        if target != "bots" and target != self.client.user and not has_permission(user, "manage_messages"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to purge user messages.\n"
                "Requires `manage_messages`.".format(
                    user=user
                )
            )
            return

        if not target:
            check = lambda m: True
        elif target == "bots":
            check = lambda m: m.author.bot
        else:
            check = lambda m: m.author == target

        try:
            deleted = await self.client.purge_from(
                channel,
                check=check,
                limit=limit
            )
            deleted = len(deleted)

        except Exception as e:
            log.exception(e)
            deleted = 0

        await self.client.send_message(
            channel,
            "Deleted `{:,}` messages in {}.".format(
                int(deleted),
                channel.mention
            )
        )

    @command(pattern="^\.iam add ([^:]+)(?:\:(.+))?$",
             description="define self-assignable role",
             usage=".iam add <role>")
    async def add_iam_role(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_roles"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to manage roles.\n"
                "Requires `manage_roles`.".format(user=user)
            )
            return

        role = None
        if args[0]:
            role = discord.utils.get(server.roles, name=args[0])  # type: discord.Role

        if not role:
            await self.client.send_message(
                channel,
                "No role found by that name."
            )
            return

        if role.position >= user.top_role.position and not has_permission(user, 'administrator'):
            await self.client.send_message(
                channel,
                "You may not set a role above/equal to your own as self-assignable without `administrator` permission."
            )
            return

        if len(args) > 1:
            name = args[1] or role
        else:
            name = role

        storage = await self.get_storage(server)
        added = await storage.set('iam_id:{}'.format(name), role.id)

        if added:
            await storage.sadd('iam_roles', name)
            msg = "{role} has been set as a self-assignable role, under the name `{name}`.\n" \
                "User `.iam {name}` to use.".format(
                role=role,
                name=name
            )
        else:
            msg = "Could not add role."

        await self.client.send_message(
            channel,
            msg
        )

    @command(pattern="^\.iam del (.+)$",
             description="delete a self-assignable role",
             usage=".iam del <role>")
    async def del_iam_role(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        log.info(args)

        if not has_permission(user, "manage_roles"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to manage roles.\n"
                "Requires `manage_roles`.".format(user=user)
            )
            return

        storage = await self.get_storage(server)
        role_id = await storage.get('iam_id:{}'.format(args[0]))

        if not role_id:
            await self.client.send_message(
                channel,
                "No role found by that name."
            )
            return

        deleted = await storage.delete('iam_id:{}'.format(args[0]))

        if deleted:
            await storage.srem('iam_roles', args[0])
            msg = "{name} has been unset as a self-assignable role.".format(
                name=args[0]
            )
        else:
            msg = "Could not remove role."

        await self.client.send_message(
            channel,
            msg
        )

    @command(pattern="^\.iam (?!add|del|list|not)(.+)$",
             description="add a self-assignable role to yourself",
             usage=".iam <role>")
    async def iam_role(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        role_id = await storage.get('iam_id:{}'.format(args[0]))

        if not role_id:
            await self.client.send_message(
                channel,
                "No role found by that name."
            )
            return

        role = discord.utils.get(server.roles, id=role_id)
        if not role:
            return

        if role not in user.roles:
            await self.client.add_roles(user, role)

            await self.client.send_message(
                channel,
                "You have been granted the role `{}`".format(role)
            )

    @command(pattern="^\.iam not (.+)$",
             description="remove self-assignable role from yourself",
             usage=".iam not <role>")
    async def iam_not_role(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        role_id = await storage.get('iam_id:{}'.format(args[0]))

        if not role_id:
            await self.client.send_message(
                channel,
                "No role found by that name."
            )
            return

        role = discord.utils.get(server.roles, id=role_id)
        if not role:
            return

        if role in user.roles:
            await self.client.remove_roles(user, role)

    @command(pattern="^\.iam list$",
             description="view self-assignable roles",
             usage=".iam list")
    async def list_iam_roles(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_roles"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to manage roles.\n"
                "Requires `manage_roles`.".format(user=user)
            )
            return

        storage = await self.get_storage(server)
        items = await storage.smembers('iam_roles')

        body = "```yaml\n.iam <name> # give yourself a role```"
        for iam in items:
            body += "• {}\n".format(iam)

        embed = discord.Embed(
            title="**Self-assignable roles in {server}**\n".format(server=server),
            description=body,
            colour=discord.Colour.gold()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    async def on_server_join(self, server):
        log.info("Joined {server.owner}'s {server} [{server.id}]".format(server=server))

        embed = discord.Embed(
            title=server.name,
            description="Server: **`{server}`** has `{members}` members, `{roles}` roles and is owned by `{server.owner}`".format(
                server=server,
                members=len(server.members),
                roles=len(server.roles)
            )
        )

        channels = ""
        displayed, count = 0, 0
        for channel in sorted(server.channels, key=lambda c: c.position):
            if channel.type != discord.ChannelType.text:
                continue

            count += 1
            if displayed < 10:
                displayed += 1
            else:
                continue

            template = '• [`{channel.id}`] **{channel.name}**'
            if channel.topic:
                topic = channel.topic.strip().replace('\n', '')
                if topic != '':
                    template += ' "{topic}"'
            else:
                topic = ""
            template += "\n"

            channels += template.format(
                channel=channel,
                topic=topic
            )

        embed.add_field(
            name="Channels ({}/{} shown)".format(
                displayed,
                count
            ),
            value=channels,
            inline=False
        )

        roles = ""
        displayed, count = 0, 0
        for role in sorted(server.roles[:10], key=lambda r: -r.position):
            if role.is_everyone:
                continue

            count += 1
            if displayed < 10:
                displayed += 1
            else:
                continue

            template = "[`{role.id}`] **`{s}{name}`** Hoist: {role.hoist}, Permissions: `{role.permissions.value}`\n"
            roles += template.format(
                s='@' if role.mentionable else '',
                role=role,
                name=clean_string(role.name)
            )


        embed.add_field(
            name="Roles ({}/{} shown)".format(
                displayed,
                count
            ),
            value=roles or "No roles.",
            inline=False
        )

        if server.emojis:
            embed.add_field(
                name="Emoji",
                value=' '.join([
                    ":{emoji.name}:".format(emoji=emoji) for emoji in server.emojis
                ]) or "No custom Emoji.",
                inline=False
            )

        embed.set_footer(
            text="{server.name} | ID: #{server.id}".format(server=server),
            icon_url="https://cdn.discordapp.com/icons/{}/{}.png".format(server.id, server.icon)
        )

        for user_id in ['154542529591771136']:
            try:
                user = await self.client.get_user_info(user_id)
                await self.client.send_message(user, 'Added to {server}'.format(server=server), embed=embed)
            except discord.HTTPException as e:
                log.exception(e)
                if user:
                    await self.client.send_message(user, 'Added to {server.owner}\'s `{server}`'.format(server=server))

    @command(pattern="^\.pair$",
             description="start a pairing request with another server",
             usage=".pair")
    async def start_pairing(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to modify server settings.\n"
                "Requires `manage_server`.".format(
                    user=user
                )
            )
            return

        token = await self.client.db.redis.get('Admin.global:pairing_key:{}'.format(server.id))
        if not token:
            import hashlib, os
            token = hashlib.sha1(os.urandom(128)).hexdigest()
            saved = await self.client.db.redis.set('Admin.global:pairing_key:{}'.format(server.id), token, expire=240)
            if saved:
                await self.client.db.redis.set('Admin.global:pairing_server:{}'.format(token), server.id)
            else:
                return

        await self.client.send_message(
            channel,
            "Your pairing key is below. Use `.pair <key>` in another server to pair.\n"
            "```\n{}```".format(token)
        )

    @command(pattern="^\.pair (.+)$",
             description="complete a pairing request",
             usage=".pair <key>")
    async def complete_pairing(self, message: discord.Message, args):
        server = message.server
        channel = message.channel
        user = message.author

        if len(args[0]) < 40:
            await self.client.send_message(
                channel,
                "Invalid pairing key. Valid pairing keys are 40 characters long.\n"
            )
            return

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to modify server settings.\n"
                "Requires `manage_server`.".format(
                    user=user
                )
            )
            return

        server_id = await self.client.db.redis.get('Admin.global:pairing_server:{}'.format(args[0]))
        _server = self.client.get_server(server_id)
        log.info(_server)

        if not _server:
            await self.client.send_message(
                channel,
                "Pairing key not found. Aborting."
            )

        paired = await self.client.db.redis.set('Admin.global:paired_server:{}'.format(server.id), _server.id)
        log.info(paired)
        if paired:
            await self.client.db.redis.delete('Admin.global:pairing_key:{}'.format(_server.id))
            await self.client.db.redis.delete('Admin.global:pairing_server:{}'.format(args[0]))

            await self.client.send_message(
                channel,
                "Successfully paired `{}` with `{}`.\n"
                "Configuration is now synchronised.".format(
                    clean_string(server.name),
                    clean_string(_server.name)
                )
            )
        else:
            await self.client.send_message(
                channel,
                "Pairing failed."
            )

    @command(pattern="^\.unpair (.+)$",
             description="unpair server",
             usage=".unpair")
    async def complete_pairing(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, you do not have permission to modify server settings.\n"
                "Requires `manage_server`.".format(
                    user=user
                )
            )
            return

        paired = await self.client.db.redis.get('Admin.global:paired_server:{}'.format(server_id))
        if not paired:
            await self.client.send_message(
                channel,
                "`{}` is not currently paired to any server."
            )
            return

        res = confirm_dialog()