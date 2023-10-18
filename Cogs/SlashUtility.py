import discord
from discord import app_commands
from discord.ext import commands

class SlashUtility(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Slash Utility Enabled")

    @app_commands.command(name="loadedcogs", description="Lists loaded cogs")
    async def loadedcogs(self, interaction: discord.Interaction):
        loaded_cogs = [cog for cog in self.client.extensions.keys()]
        await interaction.response.send_message(f"Currently loaded cogs: {', '.join(loaded_cogs)}" if loaded_cogs else "No cogs are currently loaded.")

    @app_commands.command(name="load", description="Loads a cog")
    async def load(self, interaction: discord.Interaction, extension: str):
        try:
            await self.client.load_extension(f'Cogs.{extension}')
            await interaction.response.send_message(f"Cog `{extension}` has been loaded.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not load `{extension}`. Error: {e}", ephemeral=True)

    @app_commands.command(name="unload", description="Unloads a cog")
    async def unload(self, interaction: discord.Interaction, extension: str):
        try:
            await self.client.unload_extension(f'Cogs.{extension}')
            await interaction.response.send_message(f"Cog `{extension}` has been unloaded.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not unload `{extension}`. Error: {e}", ephemeral=True)

    @app_commands.command(name="reload", description="Reloads a cog")
    async def reload(self, interaction: discord.Interaction, extension: str):
        try:
            await self.client.unload_extension(f'Cogs.{extension}')
            await self.client.load_extension(f'Cogs.{extension}')
            await interaction.response.send_message(f"Cog `{extension}` has been reloaded.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Could not reload `{extension}`. Error: {e}", ephemeral=True)

async def setup(client):
    await client.add_cog(SlashUtility(client))
