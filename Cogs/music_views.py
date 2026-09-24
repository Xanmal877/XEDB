"""YouTube search result buttons for MusicCog."""

import asyncio
import logging

import discord

logger = logging.getLogger(__name__)
VIEW_TIMEOUT = 30


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
                        voice_client = self.cog._get_voice_client(self.guild_id)
                        if voice_client and not voice_client.is_playing():
                            await self.cog._play_next_locked(self.guild_id)
                    await interaction.followup.send(f"🎵 Added **{actual_track.title}** to queue")

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

