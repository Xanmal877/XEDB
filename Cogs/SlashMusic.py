import discord
from discord import FFmpegPCMAudio, PCMVolumeTransformer, app_commands
from discord.ext import commands
import random
import os

class SlashMusic(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.current_audio_file = None

    @commands.Cog.listener()
    async def on_ready(self):
        print("Music Enabled")
        await self.client.tree.sync()

    async def play_random_song(self, interaction, voice_client):
        audio_folder = "F:\\Coding Projects\\Bots\\Python\\Xans-Python-Discord-Bot\\Music"
        audio_files = [file for file in os.listdir(audio_folder) if file.endswith((".mp3", ".m4a"))]

        if not audio_files:
            await interaction.followup.send("No audio files found.")
            return

        random.shuffle(audio_files)
        self.current_audio_file = audio_files[0]
        audio_path = os.path.join(audio_folder, self.current_audio_file)

        source = FFmpegPCMAudio(executable="ffmpeg", source=audio_path)
        voice_client.stop()
        voice_client.play(PCMVolumeTransformer(source, volume=0.5), after=lambda e: self.client.loop.create_task(self.play_random_song(interaction, voice_client)))

        await interaction.followup.send(f"Now playing: {self.current_audio_file}")

    @app_commands.command(name="join", description="Join the voice channel")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if interaction.user.voice:
            channel = interaction.user.voice.channel
            voice_client = interaction.guild.voice_client

            if voice_client is None:
                voice_client = await channel.connect()
                await interaction.followup.send(f"Joined {channel.name}")
            else:
                await interaction.followup.send("Already connected to a voice channel.")
        else:
            await interaction.followup.send("You're not in a voice channel.")

    @app_commands.command(name="play", description="Play random music from a folder")
    async def play(self, interaction: discord.Interaction):
        await interaction.response.defer()
        voice_client = interaction.guild.voice_client

        if voice_client is None:
            await interaction.followup.send("I'm not connected to a voice channel.")
            return

        await self.play_random_song(interaction, voice_client)

    @app_commands.command(name="set_volume", description="Set the audio volume")
    async def set_volume(self, interaction: discord.Interaction, volume: float):
        await interaction.response.defer()
        voice_client = interaction.guild.voice_client

        print(f"Volume received: {volume}")  # Debug
        print(f"Voice client source: {voice_client.source}")  # Debug

        if voice_client and voice_client.source:
            voice_client.source.volume = volume
            await interaction.followup.send(f"Set the volume to {volume}")
        else:
            await interaction.followup.send("I'm not playing any music, so I can't adjust the volume.")


    @app_commands.command(name="stop", description="Stop the music")
    async def stop(self, interaction: discord.Interaction):
        await interaction.response.defer()
        voice_client = interaction.guild.voice_client

        if voice_client:
            voice_client.stop()
            await interaction.followup.send("Stopped the music.")
        else:
            await interaction.followup.send("I'm not playing any music.")

async def setup(client):
    await client.add_cog(SlashMusic(client))
