import os
import asyncio
import discord
import traceback
from discord import app_commands, FFmpegPCMAudio, PCMVolumeTransformer
from discord.ext import commands
from yt_dlp import YoutubeDL
from typing import Optional
from enum import Enum

class RepeatMode(Enum):
    NONE = 0
    TRACK = 1
    QUEUE = 2

class Track:
    def __init__(self, source: str, title: str, url: str, requester: discord.Member):
        self.source = source
        self.title = title
        self.url = url
        self.requester = requester

class YTSearchView(discord.ui.View):
    def __init__(self, tracks, cog, guild_id):
        super().__init__(timeout=30)
        self.tracks = tracks
        self.cog = cog
        self.guild_id = guild_id
        self.interaction_lock = asyncio.Lock()
        self.message = None

        # Add buttons with song titles
        for idx, track in enumerate(tracks):
            # Truncate title to 75 chars to avoid Discord's 80-character button limit
            shortened_title = (track.title[:75] + '...') if len(track.title) > 75 else track.title
            button = discord.ui.Button(
                label=shortened_title,
                style=discord.ButtonStyle.secondary,
                custom_id=str(idx)  # Store track index in custom_id
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
                    new_tracks = await self.cog._ytdl_extract(
                        selected_track.url, 
                        selected_track.requester
                    )
                    
                    if not new_tracks:
                        await interaction.followup.send("❌ Track unavailable", ephemeral=True)
                        return
                    
                    actual_track = new_tracks[0]
                    self.cog.queues.setdefault(self.guild_id, []).append(actual_track)
                    await interaction.followup.send(f"🎵 Added **{actual_track.title}** to queue")

                    voice_client = await self.cog._get_voice_client(self.guild_id)
                    if voice_client and not voice_client.is_playing():
                        await self.cog._play_next(self.guild_id)

                    if self in self.cog.active_views:
                        self.cog.active_views.remove(self)

                except Exception as e:
                    print(f"PROCESSING ERROR: {traceback.format_exc()}")
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
        self.search_lock = asyncio.Lock()
        self._fail_counters = {}  # guild_id -> consecutive failure count
        self._alone_timers = {}   # guild_id -> asyncio.Task for auto-disconnect

        # Ensure Songs directory exists BEFORE scanning it
        if not os.path.exists("Songs"):
            os.makedirs("Songs")
        self.refresh_local_files_cache()

    def refresh_local_files_cache(self):
        self.local_files_cache = [
            (f.lower(), f) 
            for f in os.listdir("Songs") 
            if f.endswith(('.mp3', '.m4a', '.flac'))
        ]

    async def _get_voice_client(self, guild_id: int) -> Optional[discord.VoiceClient]:
        guild = self.client.get_guild(guild_id)
        return guild.voice_client if guild else None

    async def _connect_voice(self, interaction: discord.Interaction) -> Optional[discord.VoiceClient]:
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
            await interaction.followup.send(f"❌ Failed to connect: {str(e)}")
            return None

    async def _play_next(self, guild_id: int):
        voice_client = await self._get_voice_client(guild_id)
        if not voice_client or not voice_client.is_connected():
            return

        queue = self.queues.get(guild_id, [])
        repeat_mode = self.repeat_modes.get(guild_id, RepeatMode.NONE)
        current = self.current_tracks.get(guild_id)

        # If repeat track is failing repeatedly, bail out
        fail_count = self._fail_counters.get(guild_id, 0)
        if repeat_mode == RepeatMode.TRACK and current and fail_count >= 3:
            await self._handle_playback_error(guild_id, "Track failed 3 times. Disabling repeat.")
            self.repeat_modes[guild_id] = RepeatMode.NONE
            self._fail_counters[guild_id] = 0
            return

        if repeat_mode == RepeatMode.TRACK and current:
            queue.insert(0, current)

        if queue:
            track = queue.pop(0)
            self.current_tracks[guild_id] = track
            source = None

            try:
                source = FFmpegPCMAudio(
                    track.source,
                    before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 2",
                    options="-vn -b:a 128k -threads 4"
                )

                # Guard against disconnect race
                if not voice_client.is_connected():
                    if source:
                        source.cleanup()
                    return

                def after_playback(error):
                    if error:
                        self._fail_counters[guild_id] = self._fail_counters.get(guild_id, 0) + 1
                        print(f"Playback error: {error}")
                    else:
                        self._fail_counters[guild_id] = 0
                    asyncio.run_coroutine_threadsafe(
                        self._play_next(guild_id),
                        self.client.loop
                    )

                voice_client.play(source, after=after_playback)
                voice_client.source = PCMVolumeTransformer(
                    voice_client.source,
                    self.volume_levels.get(guild_id, 0.5)
                )

                channel = self.user_last_channel.get(guild_id)
                if channel:
                    await channel.send(
                        f"🎶 Now playing: **{track.title}** (Requested by {track.requester.mention})"
                    )

            except Exception as e:
                self._fail_counters[guild_id] = self._fail_counters.get(guild_id, 0) + 1
                if source:
                    try:
                        source.cleanup()
                    except Exception:
                        pass
                await self._handle_playback_error(guild_id, f"Failed to play: {str(e)}")
                await self._play_next(guild_id)
        else:
            await self._disconnect_voice(guild_id)

    async def _disconnect_voice(self, guild_id: int):
        self._cancel_alone_timer(guild_id)
        voice_client = await self._get_voice_client(guild_id)
        if voice_client:
            await voice_client.disconnect()
            self.current_tracks.pop(guild_id, None)
            self.queues.pop(guild_id, None)
            self.repeat_modes.pop(guild_id, None)
            channel = self.user_last_channel.pop(guild_id, None)
            if channel:
                await channel.send("✅ Queue finished. Disconnecting...")

    async def _handle_playback_error(self, guild_id: int, error: str):
        channel = self.user_last_channel.get(guild_id)
        if channel:
            await channel.send(f"❌ Playback error: {error}")
        await self._play_next(guild_id)

    async def _ytdl_extract(self, url: str, requester: discord.Member) -> Optional[list[Track]]:
        ytdl_opts = {
            'format': 'bestaudio/best',
            'extract_flat': 'in_playlist',
            'socket_timeout': 8,
            'noplaylist': True,
            'ignoreerrors': False,
            'quiet': True,
            'no_warnings': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls']
                }
            },
            'match_filter': lambda info: not info.get('is_live'),
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        }

        try:
            with YoutubeDL(ytdl_opts) as ytdl:
                is_search = url.startswith('ytsearch')
                data = await asyncio.wait_for(
                    asyncio.to_thread(
                        ytdl.extract_info,
                        url,
                        download=False,
                        process=not is_search
                    ),
                    timeout=10
                )

                if is_search:
                    return await self._process_search_results(data, requester)
                return await self._process_direct_url(data, requester, url)

        except asyncio.TimeoutError:
            print(f"YTDL timeout for URL: {url}")
            return None
        except Exception as e:
            print(f"YTDL Error: {str(e)}\n{traceback.format_exc()}")
            return None

    async def _process_search_results(self, data, requester):
        if not data or 'entries' not in data:
            return None

        entries = list(data['entries'])[:5]

        return [
            Track(
                source=f"https://youtu.be/{entry['id']}",
                title=entry['title'],
                url=f"https://youtu.be/{entry['id']}",
                requester=requester
            )
            for entry in entries
            if entry and entry.get('id')
        ]

    async def _process_direct_url(self, data, requester, original_url):
        if not data:
            return None

        track_url = data.get('url') or original_url
        return [Track(
            source=track_url,
            title=data.get('title', 'Unknown Track'),
            url=data.get('webpage_url', original_url),
            requester=requester
        )]

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Bot got kicked / disconnected
        if member == self.client.user and not after.channel:
            self.current_tracks.pop(member.guild.id, None)
            self.queues.pop(member.guild.id, None)
            self._cancel_alone_timer(member.guild.id)
            return

        # Auto-disconnect when bot is left alone in a voice channel
        guild_id = member.guild.id
        voice_client = await self._get_voice_client(guild_id)
        if not voice_client or not voice_client.is_connected():
            return

        bot_channel = voice_client.channel
        # Someone left the bot's channel
        if before.channel == bot_channel and after.channel != bot_channel:
            human_count = sum(1 for m in bot_channel.members if not m.bot)
            if human_count == 0:
                self._start_alone_timer(guild_id)
            else:
                self._cancel_alone_timer(guild_id)
        # Someone joined the bot's channel
        elif after.channel == bot_channel and before.channel != bot_channel:
            self._cancel_alone_timer(guild_id)

    def _start_alone_timer(self, guild_id: int):
        self._cancel_alone_timer(guild_id)

        async def _disconnect_after_delay():
            await asyncio.sleep(60)
            await self._disconnect_voice(guild_id)
            channel = self.user_last_channel.get(guild_id)
            if channel:
                await channel.send("👋 Left voice channel after being alone for 60 seconds.")

        self._alone_timers[guild_id] = asyncio.create_task(_disconnect_after_delay())

    def _cancel_alone_timer(self, guild_id: int):
        task = self._alone_timers.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    @app_commands.command(name="play_music", description="Play music from YouTube or local files")
    @app_commands.describe(query="YouTube URL/search query or local file name")
    async def play(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer(ephemeral=True)
        voice_client = await self._connect_voice(interaction)
        if not voice_client:
            return

        guild_id = interaction.guild_id
        self.volume_levels.setdefault(guild_id, 0.5)

        try:
            if not query.startswith(('http://', 'https://')):
                query_lower = query.lower()
                matched = [original for (lower, original) in self.local_files_cache if query_lower in lower]
                
                if matched:
                    tracks = [
                        Track(
                            source=os.path.join("Songs", f),
                            title=os.path.splitext(f)[0],
                            url="local-file",
                            requester=interaction.user
                        )
                        for f in matched
                    ]
                    self.queues.setdefault(guild_id, []).extend(tracks)
                    await interaction.followup.send(f"🎵 Added {len(tracks)} local track(s) to queue", ephemeral=True)
                    if not voice_client.is_playing():
                        await self._play_next(guild_id)
                    return

            if query.startswith(('http://', 'https://')):
                tracks = await self._ytdl_extract(query, interaction.user)
            else:
                tracks = await self._ytdl_extract(f"ytsearch5:{query}", interaction.user)

            if not tracks:
                await interaction.followup.send(f"🔍 No results found for '{query}'", ephemeral=True)
                return

            if query.startswith(('http://', 'https://')):
                self.queues.setdefault(guild_id, []).extend(tracks)
                await interaction.followup.send(f"🎵 Added **{tracks[0].title}** to queue")
                if not voice_client.is_playing():
                    await self._play_next(guild_id)
                return

            view = YTSearchView(tracks, self, guild_id)
            view.message = await interaction.followup.send("🎵 Select a track:", view=view, ephemeral=True,)
            self.active_views.append(view)

        except Exception as e:
            await interaction.followup.send(f"❌ Error processing request: {str(e)}", ephemeral=True)
            print(f"Play Command Error: {traceback.format_exc()}")

    @app_commands.command(name="nowplaying", description="Show current track info")
    async def nowplaying(self, interaction: discord.Interaction):
        track = self.current_tracks.get(interaction.guild_id)
        if track:
            embed = discord.Embed(title="Now Playing", color=0x00ff00)
            embed.add_field(name="Title", value=track.title, inline=False)
            embed.add_field(name="Requested By", value=track.requester.mention)
            embed.add_field(name="URL", value=track.url)
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Nothing is currently playing")

    # Add this command to the Music cog class
    @app_commands.command(name="queue", description="Show the current playlist")
    async def queue(self, interaction: discord.Interaction):
        """Displays the current queue ephemerally"""
        queue = self.queues.get(interaction.guild_id, [])
        if not queue:
            await interaction.response.send_message("ℹ️ The queue is empty.", ephemeral=True)
            return

        embed = discord.Embed(title="Current Queue", color=0x00ff00)
        for idx, track in enumerate(queue[:10], 1):  # Show up to 10 tracks
            embed.add_field(
                name=f"{idx}. {track.title[:50]}...",
                value=f"Requested by {track.requester.mention}",
                inline=False
            )
        
        if len(queue) > 10:
            embed.set_footer(text=f"And {len(queue)-10} more tracks...")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


    # @app_commands.command(name="skip", description="Skip the current track")
    # async def skip(self, interaction: discord.Interaction):
    #     voice_client = await self._get_voice_client(interaction.guild_id)
    #     if voice_client and voice_client.is_playing():
    #         voice_client.stop()
    #         await interaction.response.send_message("⏭ Skipped current track")
    #     else:
    #         await interaction.response.send_message("❌ Nothing is currently playing")

    # @app_commands.command(name="stop", description="Stop playback and clear queue")
    # async def stop(self, interaction: discord.Interaction):
    #     guild_id = interaction.guild_id
    #     self.queues[guild_id] = []
    #     voice_client = await self._get_voice_client(guild_id)
    #     if voice_client:
    #         voice_client.stop()
    #         await self._disconnect_voice(guild_id)
    #     await interaction.response.send_message("⏹ Stopped playback and cleared queue")

    # @app_commands.command(name="volume", description="Adjust playback volume (0-100)")
    # @app_commands.describe(level="Volume level (0-100)")
    # async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 100]):
    #     guild_id = interaction.guild_id
    #     self.volume_levels[guild_id] = level / 100
    #     voice_client = await self._get_voice_client(guild_id)
    #     if voice_client and voice_client.source:
    #         voice_client.source.volume = self.volume_levels[guild_id]
    #         await interaction.response.send_message(f"🔊 Volume set to {level}%")
    #     else:
    #         await interaction.response.send_message("❌ Nothing is currently playing")

async def setup(client: commands.Bot):
    await client.add_cog(Music(client))
    print("🎵 Music Cog loaded!")