import uuid
import json

from plugins.time import Time
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

        owners = await self.db.redis.smembers('owners') or {}
        if user.id not in owners:
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
            return
        elif text:
            msg = "Updated status: {}".format(text)
        else:
            msg = "Cleared status."

        await self.client.change_presence(game=discord.Game(name=text))
        await self.client.send_message(
            channel,
            msg
        )

    # Warnings & Bans
    @command(pattern='^\.warn (.*) for (.*)$',
             description="warn a user, optionally provide a reason",
             usage=".warn <user> for [reason]",
             requires_permissions="ban_members")
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

        await self.client.send_typing(channel)

        reason = args[1]
        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,),
            similar=True
        )

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
        warnings = await storage.lrange('warnings:{}'.format(target.id), 0, -1)
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        warn_count = 0
        for warning_json in warnings:
            if warning_json is None:
                continue

            warning = json.loads(warning_json or "null")
            if warning.get('cancelled', False) is False:
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

        await self.client.send_typing(channel)

        if res.content.lower() == 'y':
            added = await storage.rpush('warnings:{}'.format(target.id), json.dumps(this_warning))
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
                msg = await self.client.send_message(
                    private,
                    "You have been **{action}** from __{server}__ for: `{reason}`".format(
                        user=clean_string(target.name),
                        server=clean_string(server.name),
                        reason=clean_string(reason or "-"),
                        action=action+suffix
                    )
                )
            except discord.Forbidden as e:
                if 'private' not in locals():
                    await self.client.send_message(
                        channel,
                        "**{user}** could not be kicked from {action}: ```\n{reason}```".format(
                            user=clean_string(target.name),
                            action=action+suffix,
                            reason=clean_string(e)
                        )
                    )
                    return
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

    @command(pattern="^\.delwarn ([0-9]+) for (.*)$",
             description="clear a warning for a user",
             usage=".delwarn <num> for <user>")
    async def remove_warning(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        target = await get_object(
            self.client,
            args[1],
            message,
            types=(discord.Member,)
        )

        await self.client.send_typing(channel)

        if target is None:
            await self.client.send_message(
                channel,
                "No user found by that name."
            )
            return

        storage = await self.get_storage(server)
        warning_json = await storage.lrange('warnings:{}'.format(target.id), int(args[0]), int(args[0]) + 1)

        if not warning_json:
            await self.client.send_message(
                channel,
                "No warning found at that index."
            )
            return

        warning = json.loads(warning_json[0])

        tz = await Time.get_user_timezone(self.client, target.id)

        by = server.get_member(warning['by']) if warning.get('by') else 'UNKNOWN'
        to = server.get_member(warning['user']) if warning.get('user') else 'UNKNOWN'
        reason = warning['reason'] if warning.get('reason') else 'UNKNOWN'
        timestamp = datetime.datetime.fromtimestamp(warning['timestamp'], tz=tz) if warning.get('reason') else 'UNKNOWN'

        res = await confirm_dialog(
            self.client,
            channel,
            user=user,
            title="Clear this warning?",
            description="This will clear the following warning:\n"
                        "```FROM: {}\n"
                        "TO: {}\n"
                        "DATE: {}\n"
                        "REASON: {}```".format(
                            by,
                            to,
                            timestamp.strftime(DATETIME_FORMAT),
                            reason
                        ),
            colour=discord.Colour.red()
        )

        if res is None or res.content.lower() == "n":
            return

        await self.client.send_typing(channel)

        warning['cancelled'] = True

        deleted = await storage.lset(('warnings:{}'.format(target.id)), int(args[0]), json.dumps(warning))
        if deleted:
            await self.client.send_message(
                channel,
                "Warning Cleared"
            )

    @command(pattern='^\.(?:warns|warnlist)(?: (.*))?$',
             description="list warnings for user or self",
             usage='.warnlist <user>')
    async def list_warnings(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,)
        ) if args[0] else user

        await self.client.send_typing(channel)

        if target is None:
            await self.client.send_message(
                channel,
                "No user found by that name"
            )
            return

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
        warnings_raw = await storage.lrange('warnings:{}'.format(target.id), 0, -1)
        warnings = []

        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        warn_count = 0
        for warning_json in warnings_raw:
            warning = json.loads(warning_json or "null")
            if warning is None:
                continue

            if not warning.get('cancelled', False):
                warn_count += 1

            warnings.append(warning)

        if warn_count + 1 >= thresholds.get('ban', 5):
            action = "ban"
        elif warn_count + 1 == thresholds.get('kick', 3):
            action = "kick"
        else:
            action = "written warning only"

        body = ''
        for n, warning in enumerate(warnings):
            time_string = str(
                datetime.datetime.utcfromtimestamp(float(warning.get('timestamp'))).strftime(DATETIME_FORMAT)
            )
            body += "{s}__#{i}__ [`{time}`] for  *`{reason:.100}`* by {by}{s}\n".format(
                i=n,
                time=time_string,
                reason=str(warning.get('reason')) or "-",
                by=server.get_member(warning.get('by')) or server.name,
                s="~~" if warning.get('cancelled') else ''
            )

        embed = discord.Embed(
            title="Warnings for {user} in {server}".format(
                user=target,
                server=server
            ),
            description=body,
            colour=discord.Colour.orange()
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

    @command(pattern='^\.warn threshold (kick|ban) ([0-9]+)$',
             description="set the warning threshold for kick/ban",
             usage=".warn threshold <kick|ban> <# of warnings>")
    async def set_threshold(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        if not has_permission(user, "manage_server"):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to change warning thresholds.\n"
                "Requires `manage_server`.".format(user=user)
            )
            return

        await self.client.send_typing(channel)

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

    @command(pattern="^\.warn threshold$",
             description="view the current warning threshold for kick/ban",
             usage=".warn threshold")
    async def view_thresholds(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel

        await self.client.send_typing(channel)

        storage = await self.get_storage(server)
        thresholds = await storage.get('thresholds') or '{"kick":3,"ban":5}'
        thresholds = json.loads(thresholds)

        embed = discord.Embed(
            title="Warning thresholds for {}".format(server),
            description="**Kick**: `{0[kick]}`\n**Ban**: `{0[ban]}`".format(thresholds),
            colour=discord.Colour.orange()
        )
        await self.client.send_message(
            channel,
            embed=embed
        )
        return

    @command(pattern='^\.kick (.+) (?:for (.*))?$',
             description="kick user from the current server",
             usage=".kick <user> [for <reason>]")
    async def kick_user(self, message: discord.Message, args: tuple):
        server = message.server  # type: discord.Server
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        target = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Member,)
        )

        await self.client.send_typing(channel)

        if not target:
            await self.client.send_message(
                channel,
                "No user by that name could be found in this server."
            )
            return

        if len(args) > 1:
            reason = args[1] or None
        else:
            reason = None

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

        await self.client.send_typing(channel)

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

        await self.client.send_typing(channel)
        bans = await self.client.get_bans(server)

        body = ''
        for user in bans:
            body += "• {0.mention} (`{0.name}#{0.discriminator}`): [`{0.id}`]\n".format(user)

        embed = discord.Embed(
            title="Banned users in {0.name}".format(server),
            description=body,
            color=discord.Color.red()
        )

        await self.client.send_message(
            channel,
            embed=embed
        )

    @command(pattern="^\.clean ([0-9]*)$",
             description="clean up bot messages",
             usage=".clean <max # of messages>")
    async def clean_channel(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel

        limit = 20
        if args[0] and args[0].isnumeric():
            limit = int(args[0])

        if not 0 < limit <= 200:
            limit = 20

        await self.client.purge_from(
            channel,
            check=lambda m: m.author == self.client.user,
            limit=limit
        )

    @command(pattern="^\.purge ([0-9]+)(?: from (.*))?$",
             description="purge messages from channel",
             usage=".purge <max # of messages> [from <user>]")
    async def purge_channel(self, message: discord.Message, args: tuple):
        channel = message.channel  # type: discord.Channel
        user = message.author  # type: discord.Member

        await self.client.send_typing(channel)

        limit = 20
        if len(args) > 0:
            if args[0].isnumeric():
                limit = int(args[0])

        if not 0 < limit <= 200:
            limit = 20

        target = None
        if args[1]:
            if args[1] == "bots":
                target = "bots"
            else:
                target = await get_object(
                    self.client,
                    args[1],
                    message,
                    types=(discord.Member, discord.Role)
                )

            if target is None:
                await self.client.send_message(
                    channel,
                    "No user/role found by that name."
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
            def check(*_): return True
        elif target == "bots":
            def check(m): return m.author.bot
        elif isinstance(target, discord.Role):
            def check(m): return target in m.author.roles
        else:
            def check(m): return m.author == target

        deleted = 0
        try:
            deleted = await self.client.purge_from(
                channel,
                check=check,
                limit=limit
            )
            deleted = len(deleted)

        except Exception as e:
            log.exception(e)
            if not deleted:
                deleted = 0

        msg = await self.client.send_message(
            channel,
            "Deleted `{:,}` messages in {}.".format(
                int(deleted),
                channel.mention
            )
        )

        await asyncio.sleep(10)
        try:
            await self.client.delete_message(msg)
        except discord.HTTPException:
            pass

    @command(pattern="^\.iam add (.+?)(?: as (.*))?$",
             description="define self-assignable role",
             usage=".iam add <role> [as <name>]")
    async def add_iam_role(self, message: discord.Message, args: tuple):
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

        role = await get_object(
            self.client,
            args[0],
            message,
            types=(discord.Role,)
        )

        reserved = ['add', 'del', 'list', 'not']
        if args[0] in reserved and not args[0] or \
                args[1] in reserved:
            await self.client.send_message(
                channel,
                "Could not add iam role: `name reserved`"
            )
            return

        if not role:
            await self.client.send_message(
                channel,
                "Could not add iam role: `role not found`"
            )
            return

        if role.position >= user.top_role.position and not has_permission(user, 'administrator'):
            await self.client.send_message(
                channel,
                "{user.mention}, You do not have permission to add that role as an iam role.\n"
                "Requires `administrator`, or `{role}` or above.".format(user=user, role=role)
            )
            return

        if args[1]:
            name = args[1].strip() or role.name
        else:
            name = role.name

        storage = await self.get_storage(server)

        exists = await storage.get('iam_id:{}'.format(name))
        if exists:
            await self.client.send_message(
                channel,
                "Could not add iam role: `already exists`"
            )
            return

        added = await storage.set('iam_id:{}'.format(name), role.id)

        if added:
            await storage.sadd('iam_roles', name)
            msg = "{role} has been set as a self-assignable role, under the name `{name}`.\n" \
                "User `.iam {name}` to use.".format(
                    role=role,
                    name=name
                )
        else:
            msg = "Could not add role: `unknown error`"

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

            msg = await self.client.send_message(
                channel,
                "{} has been granted the role `{}`".format(clean_string(user.name), role)
            )

            await asyncio.sleep(5)
            await self.client.delete_message(msg)

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

            msg = await self.client.send_message(
                channel,
                "{} has removed their role `{}`".format(clean_string(user.name), role)
            )

            await asyncio.sleep(5)
            await self.client.delete_message(msg)

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
        server_roles = [role.id for role in server.roles]

        body = "```yaml\n.iam <name> # give yourself a role```"
        for iam in items:
            role_id = await storage.get('iam_id:{}'.format(iam))
            if role_id not in server_roles:
                continue

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
            ),
            colour=discord.Colour.green()
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

        user = None
        for user_id in ['154542529591771136']:
            try:
                user = await self.client.get_user_info(user_id)
                await self.client.send_message(user, 'Added to {server}'.format(server=server), embed=embed)
            except discord.HTTPException as e:
                log.exception(e)
                if user is not None:
                    await self.client.send_message(user, 'Added to {server.owner}\'s `{server}`'.format(server=server))

    @command(pattern="^\.who(?:has|can) (.*?)(?: in (.*))?$",
             description="find out which users have a specific permission",
             usage=".whohas <permission> [in <channel>]")
    async def members_with_permission(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        permission_names = [x[0] for x in discord.Permissions()]
        permissions = [search(x.strip().replace(' ', '_'), permission_names) for x in args[0].split(",")]
        if None in permissions:
            await self.client.send_message(
                channel,
                "No permission found by that name."
            )
            return

        if len(args) == 2 and args[1]:
            chan = await get_object(
                self.client,
                args[1].replace(' ', '_'),
                message,
                types=(discord.Channel,)
            )
            check = lambda m: has_permission(m.permissions_in(chan), permissions)
            location = chan
        else:
            check = lambda m: has_permission(m, permissions)
            location = server

        try:
            granted_members = filter(check, server.members)
        except discord.Forbidden:
            await self.client.send_message(
                channel,
                "I do not have permission to view that channel."
            )
            return

        body = "Members who have `{}` granted in `{}`:\n\n`".format(
            ', '.join(permissions),
            clean_string(location.mention if isinstance(location, discord.Channel) else location.name)
        )

        body += truncate('`, `'.join([
            clean_string(member.name) for member in sorted(granted_members, key=lambda m: -m.top_role.position)
        ]), 1500)

        await self.client.send_message(
            channel,
            truncate(body, 1800) + '`'
        )
