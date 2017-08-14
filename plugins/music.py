import logging
import json
import youtube_dl

from classes.plugin import Plugin
from decorators import *
from util import *

log = logging.getLogger('pedantbot')


class Music(Plugin):
    plugin_name = "music"

    def __init__(self, *args, **kwargs):
        Plugin.__init__(self, *args, **kwargs)
        self.ytdl = youtube_dl.YoutubeDL({
            'format': 'webm[abr>0]/bestaudio/best',
            'prefer_ffmpeg': False
        })
        self.players = {}
        self.volume = {}

    def get_track_info(self, url, search=False):
        if search:
            url = "ytsearch:" + url

        raw = self.ytdl.extract_info(url, download=False)

        entries = raw.get('entries', [])
        if search:
            return entries

        if entries:
            entry = entries[0]
        else:
            entry = raw

        info = {
            'title': entry.get('title', ''),
            'length': entry.get('duration', 0),
            'url': entry.get('webpage_url', ''),
            'thumbnail': entry.get('thumbnail', ''),
            'uploader': entry.get('uploader', '')
        }
        return info

    def _play_audio(self, server: discord.Server):
        asyncio.run_coroutine_threadsafe(self.play_audio(server), self.client.loop)

    async def play_audio(self, server: discord.Server,
                         skip=False, pause=False, resume=False, volume=False, force=True):
        player = self.players.get(server.id)
        if volume is not False:
            if not 0 < volume <= 100:
                return False
            self.volume[server.id] = volume
            if player:
                player.volume = volume
            return True

        if ([skip,pause,resume,volume]) and player and (player.is_playing() or not player.is_done() or force):
            if skip:
                player.stop()
                return player.now_playing if hasattr(player, 'now_playing') else True
            elif pause:
                return player.pause()
            elif resume:
                return player.resume()

        storage = await self.get_storage(server)
        tracks = await storage.lrange('queue', 0, 1)
        if not tracks:
            voice = self.client.voice_client_in(server)
            if voice:
                await self.client.voice_client_in(server).disconnect()
            return

        track_info = json.loads(tracks[0] or '{}')
        user = server.get_member(track_info.get('added_by', ''))
        if not user:
            user = server.owner

        voice = self.client.voice_client_in(server) or await join_voice(
            self.client,
            user,
        )
        if not voice:
            return False

        if track_info:
            self.players[server.id] = await voice.create_ytdl_player(
                track_info.get('url', ''),
                after=lambda: self._play_audio(server)
            )
            self.players[server.id].now_playing = track_info or {}
            self.players[server.id].start()
            self.players[server.id].volume = self.volume.get(server.id, 0.5)

            await storage.lpop('queue')

            channel = server.get_channel(track_info.get('channel_id'))
            if channel:
                await self.client.send_message(
                    channel,
                    "Now playing \"{}\", requested by {}".format(
                        track_info.get('title', 'Unknown'),
                        user
                    )
                )

        else:
            return False

    @command(pattern="^!(?:music|m) (?:play|p)",
             description="start audio playback",
             usage="!music play")
    async def start_playback(self, message: discord.Message, *_):
        server = message.server

        player = self.players.get(server.id)
        if player:
            if not (player.is_playing() and player.is_done()):
                player.resume()
                return
        await self.play_audio(server)

    @command(pattern="^!(?:music|m) (?:queue|q) (.*)$",
             description="queue a youtube video",
             usage="!music queue <song name|youtube url>")
    async def add_to_queue(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.client.send_typing(channel)

        try:
            if not args[0]:
                raise ValueError()
            results = self.get_track_info(args[0], search=True)
        except youtube_dl.utils.DownloadError:
            await self.client.send_message(
                channel,
                "{user.mention} you must specify a valid youtube URL".format(user=user)
            )
            return

        if not results:
            return
        elif len(results) == 1:
            info = results[0]
        else:
            options = []
            body = ""
            for (i, track) in enumerate(results):
                body += "{i}. \"{title}\" - [`{duration}`]\n".format(
                    i=i + 1,
                    title=track.get('title', 'Unknown'),
                    duration="{:0>2}:{:0>2}".format(track.get('duration', 0) // 60, track.get('duration', 0) % 60)
                )
                options.append(str(i+1))
            options = tuple(options)

            res = await confirm_dialog(self.client, channel, user, "Multiple results found.", body, options)

            if not res or res.content.lower() == 'n':
                return

            index = int(res.content)
            info = results[index]
        info['channel_id'] = channel.id

        embed = discord.Embed(
            title=info.get('title', 'Unknown'),
            description="**Uploader**: {uploader}\n**Duration**: [`{duration}`]".format(
                uploader=truncate(clean_string(info.get('uploader', 'Unknown')), 64),
                duration="{:0>2}:{:0>2}".format(info.get('duration', 0) // 60, info.get('duration', 0) % 60)
            ),
            colour=discord.Colour.magenta(),
        )
        storage = await self.get_storage(server)
        thumbs = await storage.get('thumbnails') or '0'
        if int(thumbs):
            embed.set_image(
                url=info.get('thumbnail', '')
            )

        await self.client.send_message(
            channel,
            "Adding track to queue.",
            embed=embed
        )

        storage = await self.get_storage(server)
        await storage.rpush('queue', json.dumps(info))

        player = self.players.get(server.id)
        if (player and player.is_playing()):
            return
        await self.play_audio(server)

    @command(pattern="^!(?:music|m) (?:queue|q)$",
             description="view the play queue",
             usage="!music queue")
    async def view_play_queue(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.client.send_typing(channel)

        player = self.players.get(server.id)
        if hasattr(player, 'now_playing'):
            now_playing = player.now_playing
        else:
            now_playing = None

        storage = await self.get_storage(server)
        queue =await storage.lrange('queue', 0, 10) or []

        body = "**Play Queue for {}**\n".format(server)
        if now_playing:
            body += "Now Playing: "
            body += "\"{title}\" - [`{duration}`]\n".format(
                title=now_playing.get('title', 'Unknown'),
                duration="{:0>2}:{:0>2}".format(now_playing.get('duration', 0) // 60, now_playing.get('duration', 0) % 60)
            )

        for (i,item) in enumerate(queue):
            track = json.loads(item or '{}')
            body += "{i}. \"{title}\" - [`{duration}`]\n".format(
                i=i + 1,
                title=track.get('title', 'Unknown'),
                duration="{:0>2}:{:0>2}".format(track.get('duration', 0) // 60, track.get('duration', 0) % 60)
            )

        await self.client.send_message(
            channel,
            body
        )

    @command(pattern="^!(?:music|m) (?:join|j)$",
             description="join voice channel",
             usage="!music join")
    async def summon_to_vc(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        try:
            voice = await join_voice(self.client, user, has_permission(user, 'manage_channels'), has_permission(user, 'move_members'))
        except ConnectionError as e:
            await self.client.send_message(
                channel,
                "Could not join channel: '{}'".format(e or "Unknown error")
            )
            return

        if voice:
            await self.client.send_message(
                channel,
                "{user.mention}, I am connected to {channel.mention}".format(
                    user=user,
                    channel=voice.channel
                )
            )

    @command(pattern="^!(?:music|m) (?:leave|l)$",
             description="join voice channel",
             usage="!music leave")
    async def leave_vc(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        voice = self.client.voice_client_in(server)
        await voice.disconnect()

    @command(pattern="^!(?:music|m) (?:skip|s)$",
             description="skip the current audio track",
             usage="!music skip")
    async def skip_track(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        skipped_track = await self.play_audio(server, skip=True)
        if skipped_track:
            await self.client.send_message(
                channel,
                "{user} skipped \"{track}\"".format(
                    user=user,
                    track=skipped_track.get('title', 'Unknown')
                )
            )

    @command(pattern="^!(?:music|m) (?:forceskip|fs)$",
             description="force skip the current song if it gets stuck",
             usage="!music forceskip")
    async def force_skip(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        skipped_track = await self.play_audio(server, skip=True, force=True)
        if skipped_track:
            await self.client.send_message(
                channel,
                "{user} force-skipped \"{track}\"".format(
                    user=user,
                    track=skipped_track.get('title', 'Unknown')
                )
            )

    @command(pattern="^!(?:music|m) pause$",
             description="pause the music",
             usage="!music pause")
    async def pause_music(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        await self.play_audio(server, skip=False, pause=True)

    @command(pattern="^!(?:music|m) (?:volume|v) ((?:200|1?[0-9]{1,2}))$",
             description="change the volume",
             usage="!music volume <volume>")
    async def change_volume(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        volume = int(args[0]) / 100
        changed = await self.play_audio(server, volume=volume)
        if changed:
            msg = "Set volume to {}% successfully."
        else:
            msg = "Could not set volume."

        await self.client.send_message(
            channel,
            msg.format(args[0])
        )

    @command(pattern="^!(?:music|m) (?:volume|v)$",
             description="view the current volume",
             usage="!music volume")
    async def show_volume(self, message: discord.Message, args: tuple):
        server = message.server
        channel = message.channel
        user = message.author

        player = self.players.get(server.id)
        if not player:
            volume = self.volume.get(server.id, 0.5)
        else:
            volume = player.volume or 0.5
        output_volume = (volume or 0.5) * 100

        await self.client.send_message(
            channel,
            "The volume is currently {:.0f}%".format(output_volume)
        )

    @command(pattern="^!(?:music|m) (?:clear|c)$",
             description="clear the play queue",
             usage="!music clear")
    async def clear_queue(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        queue = await storage.llen('queue')

        res = await confirm_dialog(
            self.client,
            channel,
            user,
            "Confirm clear queue",
            "This will remove {:,} tracks from the play queue. Are you sure?".format(queue),
            colour=discord.Colour.red()
        )

        if res is None or res.content == 'n':
            return

        await storage.delete('queue')
        await self.play_audio(server, skip=True)

        await self.client.send_message(
            channel,
            "{user} cleared {deleted:,} tracks from the play queue!".format(
                user=user,
                deleted=queue
            )
        )

    @command(pattern="^!(?:music|m) (?:clear|c) ([0-9]+)$",
             description="clear the play queue",
             usage="!music remove <position>")
    async def remove_one_from_queue(self, message: discord.Message, args):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        await storage.lset('queue', int(args[0]), "")
        removed = await storage.lrem('queue', 100, "")

        await self.client.send_message(
            channel,
            "{user} cleared {removed:,} tracks from the play queue!".format(
                user=user,
                removed=removed)
        )

    # async def get_lastfm_token(self, user: discord.Member):
    #     db = self.client.db.redis
    #     token = await db.get("Music.global:{}:lastfm_token".format(user.id))
    #     if token is None:
    #         raise LookupError("Not authenticated")
    #
    #     return token

    @command(pattern="^!(?:music|m) (?:thumbnail|thumb|t)$",
             description="toggle whether to show a thumbnail when queueing a track",
             usage="!music thumbnail")
    async def toggle_thumb(self, message: discord.Message, *_):
        server = message.server
        channel = message.channel
        user = message.author

        storage = await self.get_storage(server)
        enabled = await storage.get('thumbnails')
        enabled = int(not int(enabled))
        await storage.set('thumbnails', enabled)

        await self.client.send_message(
            channel,
            ("Thumbnails will be shown in {}." if enabled else "Thumbnails will not be shown in {}.").format(
                server
            )
        )
