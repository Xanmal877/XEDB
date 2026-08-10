import asyncio
import ipaddress
import logging
import os
import random
import urllib.parse
from dataclasses import dataclass
from enum import Enum

import discord
from discord import FFmpegPCMAudio, PCMVolumeTransformer, app_commands
from discord.ext import commands
from yt_dlp import YoutubeDL

from Cogs import util

logger = logging.getLogger(__name__)

VIEW_TIMEOUT = 30
ALONE_DISCONNECT_AFTER = 60
MAX_SEARCH_RESULTS = 5
QUEUE_DISPLAY_LIMIT = 10
REPEAT_MAX_FAILURES = 3
EXTRACT_TIMEOUT = 30
DEFAULT_VOLUME = 0.5


def is_blocked_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    host = parsed.hostname
    if not host:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local or ip.is_multicast or ip.is_unspecified


class RepeatMode(Enum):
    NONE = 0
    TRACK = 1
    QUEUE = 2


@dataclass
class Track:
    source: str
    title: str
    url: str
    requester: discord.Member


class YTSearchView(discord.ui.View):
    def __init__(self, tracks, cog, guild_id):
        super().__init__(timeout=VIEW_TIMEOUT)
        self.tracks = tracks
        self.cog = cog
        self.guild_id = guild_id
        self.interaction_lock = asyncio.Lock()
        self.message = None

        # Add buttons with song titles
        for idx, track in enumerate(tracks):
            # Truncate title to 75 chars to avoid Discord's 80-character button limit
            shortened_title = (track.title[:75] + "...") if len(track.title) > 75 else track.title
            button = discord.ui.Button(
                label=shortened_title,
                style=discord.ButtonStyle.secondary,
                custom_id=str(idx),  # Store track index in custom_id
            )
            button.callback = self.create_callback(idx)
            self.add_item(button)

    def create_callback(self, index: int):
        async def button_callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
            except discord.errors.NotFound:
                return

            async with self.interaction_lock:
                try:
                    for item in self.children:
                        item.disabled = True
                    if self.message:
                        await self.message.edit(content="✅ Track selected", view=None)

                    selected_track = self.tracks[index]
                    new_tracks = await self.cog._ytdl_extract(selected_track.url, selected_track.requester)

                    if not new_tracks:
                        await interaction.followup.send("❌ Track unavailable", ephemeral=True)
                        return

                    actual_track = new_tracks[0]
                    async with self.cog._guild_lock(self.guild_id):
                        self.cog.queues.setdefault(self.guild_id, []).append(actual_track)
                        voice_client = await self.cog._get_voice_client(self.guild_id)
                        if voice_client and not voice_client.is_playing():
                            await self.cog._play_next_locked(self.guild_id)
                    await interaction.followup.send(f"🎵 Added **{actual_track.title}** to queue")

                    if self in self.cog.active_views:
                        self.cog.active_views.remove(self)

                except Exception:
                    logger.exception("PROCESSING ERROR")
                    await interaction.followup.send("❌ Failed to process request", ephemeral=True)

        return button_callback

    async def on_timeout(self):
        try:
            for item in self.children:
                item.disabled = True
            if self.message:
                await self.message.edit(view=self)
        except discord.NotFound:
            pass
        finally:
            if self in self.cog.active_views:
                self.cog.active_views.remove(self)


class Music(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.queues = {}
        self.current_tracks = {}
        self.repeat_modes = {}
        self.volume_levels = {}
        self.user_last_channel = {}
        self.active_views = []
        self.local_files_cache = []
        self._fail_counters = {}  # guild_id -> consecutive failure count
        self._alone_timers = {}  # guild_id -> asyncio.Task for auto-disconnect
        self._played_tracks = {}  # guild_id -> tracks played, for QUEUE repeat
        self._guild_locks = {}  # guild_id -> asyncio.Lock

        # Ensure Songs directory exists BEFORE scanning it
        if not os.path.exists("Songs"):
            os.makedirs("Songs")
        self.refresh_local_files_cache()

    def refresh_local_files_cache(self):
        self.local_files_cache = [(f.lower(), f) for f in os.listdir("Songs") if f.endswith((".mp3", ".m4a", ".flac"))]

    def _guild_lock(self, guild_id: int) -> asyncio.Lock:
        return self._guild_locks.setdefault(guild_id, asyncio.Lock())

    def _cleanup_guild_state(self, guild_id: int):
        self._cancel_alone_timer(guild_id)
        self.current_tracks.pop(guild_id, None)
        self.queues.pop(guild_id, None)
        self.repeat_modes.pop(guild_id, None)
        self.volume_levels.pop(guild_id, None)
        self.user_last_channel.pop(guild_id, None)
        self._fail_counters.pop(guild_id, None)
        self._played_tracks.pop(guild_id, None)
        self._guild_locks.pop(guild_id, None)

    async def _get_voice_client(self, guild_id: int) -> discord.VoiceClient | None:
        if not guild_id:
            return None
        guild = self.client.get_guild(guild_id)
        return guild.voice_client if guild else None

    async def _connect_voice(self, interaction: discord.Interaction) -> discord.VoiceClient | None:
        if not interaction.guild_id:
            return None
        if not interaction.user.voice:
            await interaction.followup.send("❌ You need to be in a voice channel!")
            return None

        voice_client = await self._get_voice_client(interaction.guild_id)
        if voice_client:
            if voice_client.channel != interaction.user.voice.channel:
                await voice_client.move_to(interaction.user.voice.channel)
            return voice_client

        try:
            voice_client = await interaction.user.voice.channel.connect()
            self.user_last_channel[interaction.guild_id] = interaction.channel
            return voice_client
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect: {e!s}")
            return None

    async def _play_next(self, guild_id: int):
        async with self._guild_lock(guild_id):
            await self._play_next_locked(guild_id)

    async def _play_next_locked(self, guild_id: int):
        voice_client = await self._get_voice_client(guild_id)
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.queues.get(guild_id, [])
        repeat_mode = self.repeat_modes.get(guild_id, RepeatMode.NONE)
        current = self.current_tracks.get(guild_id)

        # If repeat track is failing repeatedly, disable repeat and disconnect
        fail_count = self._fail_counters.get(guild_id, 0)
        if repeat_mode == RepeatMode.TRACK and current and fail_count >= REPEAT_MAX_FAILURES:
            self.repeat_modes[guild_id] = RepeatMode.NONE
            self._fail_counters[guild_id] = 0
            await self._send_channel_message(guild_id, f"❌ Playback error: Track failed {REPEAT_MAX_FAILURES} times. Disabling repeat.")
            await self._disconnect_voice(guild_id)
            return

        if repeat_mode == RepeatMode.TRACK and current:
            queue.insert(0, current)

        if queue:
            track = queue.pop(0)
            self.current_tracks[guild_id] = track
            if repeat_mode == RepeatMode.QUEUE:
                self._played_tracks.setdefault(guild_id, []).append(track)
            source = None

            try:
                source = FFmpegPCMAudio(
                    track.source, before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2", options="-vn -threads 4"
                )

                # Guard against disconnect race
                if not voice_client.is_connected():
                    if source:
                        source.cleanup()
                    return

                # Wrap volume BEFORE playback to avoid a race on the live source
                source = PCMVolumeTransformer(source, self.volume_levels.get(guild_id, DEFAULT_VOLUME))

                def after_playback(error, *, guild_id=guild_id, source=source):
                    try:
                        source.cleanup()
                    except Exception:
                        logger.exception("Failed to clean up audio source for guild %s", guild_id)
                    if error:
                        self._fail_counters[guild_id] = self._fail_counters.get(guild_id, 0) + 1
                        logger.error("Playback error: %s", error)
                    else:
                        self._fail_counters[guild_id] = 0
                    asyncio.run_coroutine_threadsafe(self._play_next(guild_id), self.client.loop)

                voice_client.play(source, after=after_playback)

            except Exception as e:
                self._fail_counters[guild_id] = self._fail_counters.get(guild_id, 0) + 1
                if source:
                    try:
                        source.cleanup()
                    except Exception as cleanup_error:
                        logger.warning("Failed to clean up audio source: %s", cleanup_error)
                await self._handle_playback_error(guild_id, f"Failed to play: {e!s}")
                return

            await self._send_channel_message(guild_id, f"🎶 Now playing: **{track.title}** (Requested by {track.requester.mention})")
        else:
            if repeat_mode == RepeatMode.QUEUE and self._played_tracks.get(guild_id):
                self.queues[guild_id] = self._played_tracks.pop(guild_id, [])
                await self._play_next_locked(guild_id)
                return
            await self._disconnect_voice(guild_id)

    async def _send_channel_message(self, guild_id: int, message: str):
        channel = self.user_last_channel.get(guild_id)
        if not channel:
            return
        try:
            await channel.send(message)
        except Exception:
            logger.exception("Failed to send message to channel for guild %s", guild_id)

    async def _disconnect_voice(self, guild_id: int, reason: str = "finished"):
        self._cancel_alone_timer(guild_id)
        voice_client = await self._get_voice_client(guild_id)
        channel = self.user_last_channel.get(guild_id)

        if not voice_client or not voice_client.is_connected():
            self._cleanup_guild_state(guild_id)
            return

        try:
            await voice_client.disconnect()
        except Exception:
            logger.exception("Failed to disconnect voice client for guild %s", guild_id)

        self._cleanup_guild_state(guild_id)

        if channel and reason == "finished":
            try:
                await channel.send("✅ Queue finished. Disconnecting...")
            except Exception:
                logger.exception("Failed to send 'queue finished' message")

    async def _handle_playback_error(self, guild_id: int, error: str):
        await self._send_channel_message(guild_id, f"❌ Playback error: {error}")
        await self._play_next_locked(guild_id)

    async def _ytdl_extract(self, url: str, requester: discord.Member) -> list[Track] | None:
        if url.startswith(("http://", "https://")) and is_blocked_url(url):
            logger.warning("Rejected URL with private/reserved host: %s", url)
            return None

        ytdl_opts = {
            "format": "bestaudio/best",
            "extract_flat": "in_playlist",
            "socket_timeout": 8,
            "noplaylist": True,
            "ignoreerrors": False,
            "quiet": True,
            "no_warnings": True,
            "extractor_args": {"youtube": {"skip": ["dash", "hls"]}},
            "match_filter": lambda info: not info.get("is_live"),
            "headers": {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "en-US,en;q=0.9"},
        }

        cookies_file = util.BASE_DIR / "cookies.txt"
        if cookies_file.exists():
            ytdl_opts["cookiefile"] = str(cookies_file)

        try:
            with YoutubeDL(ytdl_opts) as ytdl:
                is_search = url.startswith("ytsearch")
                data = await asyncio.wait_for(
                    asyncio.to_thread(ytdl.extract_info, url, download=False, process=not is_search), timeout=EXTRACT_TIMEOUT
                )

                if is_search:
                    return await self._process_search_results(data, requester)
                return await self._process_direct_url(data, requester, url)

        except asyncio.TimeoutError:
            logger.warning("YTDL timeout for URL: %s", url)
            return None
        except Exception:
            logger.exception("YTDL Error for URL: %s", url)
            return None

    async def _process_search_results(self, data, requester):
        if not data or "entries" not in data:
            return None

        entries = list(data["entries"])[:MAX_SEARCH_RESULTS]

        return [
            Track(
                source=f"https://youtu.be/{entry['id']}", title=entry["title"], url=f"https://youtu.be/{entry['id']}", requester=requester
            )
            for entry in entries
            if entry and entry.get("id")
        ]

    async def _process_direct_url(self, data, requester, original_url):
        if not data:
            return None

        track_url = data.get("url") or original_url
        return [
            Track(
                source=track_url, title=data.get("title", "Unknown Track"), url=data.get("webpage_url", original_url), requester=requester
            )
        ]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild_id = member.guild.id

        # Bot got kicked / disconnected
        if member == self.client.user and not after.channel:
            self._cleanup_guild_state(guild_id)
            return

        voice_client = await self._get_voice_client(guild_id)
        if not voice_client or not voice_client.is_connected():
            return

        bot_channel = voice_client.channel
        if not bot_channel:
            return

        # Only react when the event touches the bot's current channel
        # (this also covers the bot itself being moved between channels)
        if before.channel != bot_channel and after.channel != bot_channel:
            return

        human_count = sum(1 for m in bot_channel.members if not m.bot)
        if human_count == 0:
            self._start_alone_timer(guild_id)
        else:
            self._cancel_alone_timer(guild_id)

    def _start_alone_timer(self, guild_id: int):
        self._cancel_alone_timer(guild_id)

        async def _disconnect_after_delay():
            await asyncio.sleep(ALONE_DISCONNECT_AFTER)
            channel = self.user_last_channel.get(guild_id)
            await self._disconnect_voice(guild_id, reason="alone")
            if channel:
                try:
                    await channel.send(f"👋 Left voice channel after being alone for {ALONE_DISCONNECT_AFTER} seconds.")
                except Exception:
                    logger.exception("Failed to send alone-timer message")

        self._alone_timers[guild_id] = asyncio.create_task(_disconnect_after_delay())

    def _cancel_alone_timer(self, guild_id: int):
        task = self._alone_timers.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    @app_commands.command(name="play_music", description="Play music from YouTube or local files")
    @app_commands.guild_only()
    @app_commands.describe(query="YouTube URL/search query or local file name")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        voice_client = await self._connect_voice(interaction)
        if not voice_client:
            return

        guild_id = interaction.guild_id
        self.volume_levels.setdefault(guild_id, DEFAULT_VOLUME)
        is_url = query.startswith(("http://", "https://"))

        try:
            if not is_url:
                query_lower = query.lower()
                matched = [original for (lower, original) in self.local_files_cache if query_lower in lower]

                if matched:
                    tracks = [
                        Track(source=os.path.join("Songs", f), title=os.path.splitext(f)[0], url="local-file", requester=interaction.user)
                        for f in matched
                    ]
                    async with self._guild_lock(guild_id):
                        self.queues.setdefault(guild_id, []).extend(tracks)
                        voice_client = await self._get_voice_client(guild_id)
                        if voice_client and not voice_client.is_playing():
                            await self._play_next_locked(guild_id)
                    await interaction.followup.send(f"🎵 Added {len(tracks)} local track(s) to queue", ephemeral=True)
                    return

            if is_url:
                tracks = await self._ytdl_extract(query, interaction.user)
            else:
                tracks = await self._ytdl_extract(f"ytsearch{MAX_SEARCH_RESULTS}:{query}", interaction.user)

            if not tracks:
                await interaction.followup.send(f"🔍 No results found for '{query}'", ephemeral=True)
                return

            if is_url:
                async with self._guild_lock(guild_id):
                    self.queues.setdefault(guild_id, []).extend(tracks)
                    voice_client = await self._get_voice_client(guild_id)
                    if voice_client and not voice_client.is_playing():
                        await self._play_next_locked(guild_id)
                await interaction.followup.send(f"🎵 Added **{tracks[0].title}** to queue")
                return

            view = YTSearchView(tracks, self, guild_id)
            view.message = await interaction.followup.send("🎵 Select a track:", view=view, ephemeral=True)
            self.active_views.append(view)

        except Exception as e:
            await interaction.followup.send(f"❌ Error processing request: {e!s}", ephemeral=True)
            logger.exception("Play Command Error")

    @app_commands.command(name="nowplaying", description="Show current track info")
    @app_commands.guild_only()
    async def nowplaying(self, interaction: discord.Interaction):
        track = self.current_tracks.get(interaction.guild_id)
        if track:
            embed = discord.Embed(title="Now Playing", color=0x00FF00)
            embed.add_field(name="Title", value=track.title, inline=False)
            embed.add_field(name="Requested By", value=track.requester.mention)
            embed.add_field(name="URL", value=track.url)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Nothing is currently playing")

    @app_commands.command(name="queue", description="Show the current playlist")
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        """Displays the current queue ephemerally"""
        queue = self.queues.get(interaction.guild_id, [])
        if not queue:
            await interaction.response.send_message("ℹ️ The queue is empty.", ephemeral=True)
            return

        embed = discord.Embed(title="Current Queue", color=0x00FF00)
        for idx, track in enumerate(queue[:QUEUE_DISPLAY_LIMIT], 1):  # Show up to QUEUE_DISPLAY_LIMIT tracks
            embed.add_field(name=f"{idx}. {track.title[:50]}...", value=f"Requested by {track.requester.mention}", inline=False)

        if len(queue) > QUEUE_DISPLAY_LIMIT:
            embed.set_footer(text=f"And {len(queue) - QUEUE_DISPLAY_LIMIT} more tracks...")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="skip", description="Skip the current track")
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        voice_client = await self._get_voice_client(interaction.guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭ Skipped current track")
        else:
            await interaction.response.send_message("❌ Nothing is currently playing")

    @app_commands.command(name="stop", description="Stop playback and clear queue")
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        self.queues[guild_id] = []
        await self._disconnect_voice(guild_id)
        await interaction.response.send_message("⏹ Stopped playback and cleared queue")

    @app_commands.command(name="volume", description="Adjust playback volume (0-100)")
    @app_commands.guild_only()
    @app_commands.describe(level="Volume level (0-100)")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
        guild_id = interaction.guild_id
        self.volume_levels[guild_id] = level / 100
        voice_client = await self._get_voice_client(guild_id)
        if voice_client and voice_client.source and isinstance(voice_client.source, PCMVolumeTransformer):
            voice_client.source.volume = self.volume_levels[guild_id]
            await interaction.response.send_message(f"🔊 Volume set to {level}%")
        else:
            await interaction.response.send_message(f"🔊 Volume set to {level}% (will apply to next track)")

    @app_commands.command(name="pause", description="Pause playback")
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        voice_client = await self._get_voice_client(interaction.guild_id)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸ Paused")
        else:
            await interaction.response.send_message("❌ Nothing is currently playing")

    @app_commands.command(name="resume", description="Resume playback")
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        voice_client = await self._get_voice_client(interaction.guild_id)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶ Resumed")
        else:
            await interaction.response.send_message("❌ Nothing is paused")

    @app_commands.command(name="loop", description="Toggle repeat mode")
    @app_commands.guild_only()
    @app_commands.describe(mode="Repeat mode: off, track, or queue")
    async def loop(self, interaction: discord.Interaction, mode: str):
        guild_id = interaction.guild_id
        mode_map = {"off": RepeatMode.NONE, "track": RepeatMode.TRACK, "queue": RepeatMode.QUEUE}
        parsed = mode_map.get(mode.lower())
        if parsed is None:
            await interaction.response.send_message("❌ Mode must be 'off', 'track', or 'queue'", ephemeral=True)
            return
        self.repeat_modes[guild_id] = parsed
        label = {RepeatMode.NONE: "off", RepeatMode.TRACK: "track", RepeatMode.QUEUE: "queue"}[parsed]
        await interaction.response.send_message(f"🔁 Repeat mode set to **{label}**")

    @app_commands.command(name="shuffle", description="Shuffle the current queue")
    @app_commands.guild_only()
    async def shuffle(self, interaction: discord.Interaction):
        guild_id = interaction.guild_id
        queue = self.queues.get(guild_id, [])
        if len(queue) < 2:
            await interaction.response.send_message("❌ Need at least 2 tracks to shuffle", ephemeral=True)
            return
        random.shuffle(queue)
        self.queues[guild_id] = queue
        await interaction.response.send_message("🔀 Queue shuffled")

    @app_commands.command(name="remove", description="Remove a track from the queue by position")
    @app_commands.guild_only()
    @app_commands.describe(position="Queue position to remove (1-based)")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 100]):
        guild_id = interaction.guild_id
        queue = self.queues.get(guild_id, [])
        if not queue:
            await interaction.response.send_message("❌ Queue is empty", ephemeral=True)
            return
        if position > len(queue):
            await interaction.response.send_message(f"❌ Queue only has {len(queue)} tracks", ephemeral=True)
            return
        removed = queue.pop(position - 1)
        self.queues[guild_id] = queue
        await interaction.response.send_message(f"🗑 Removed **{removed.title}** from queue")


async def setup(client: commands.Bot):
    await client.add_cog(Music(client))
    logger.info("Music Cog loaded!")
