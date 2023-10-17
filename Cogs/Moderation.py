import discord
from discord import Forbidden, app_commands
from discord.ext import commands

class SlashModeration(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("SlashModeration Enabled")
        await self.client.tree.sync()

   
   
   
    @app_commands.command(name="reload_cog", description="Reload a specific cog")
    @commands.is_owner()
    async def reload_cog(self, interaction: discord.Interaction, cog_name: str):
        await interaction.response.defer()
        
        try:
            self.client.unload_extension(f'cogs.{cog_name}')
            self.client.load_extension(f'cogs.{cog_name}')
            await interaction.followup.send(f'Reloaded {cog_name} successfully!')
        except Exception as e:
            await interaction.followup.send(f'Failed to reload {cog_name}. Error: {e}')




    @app_commands.command(name="purge", description="Clear chat messages")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, count: int):
        await interaction.response.defer()
        try:
            await interaction.channel.purge(limit=count)
            await interaction.followup.send(f"{count} message(s) have been deleted")
        except Forbidden:
            await interaction.followup.send("Missing permissions")
        except Exception as e:
            await interaction.followup.send(f"Purge failed: {e}")

    @app_commands.command(name="kick", description="Kick a member")
    @commands.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        try:
            await interaction.guild.kick(member)
            await interaction.followup.send(f"{member.mention} has been kicked.")
        except Forbidden:
            await interaction.followup.send("Missing permissions")
        except Exception as e:
            await interaction.followup.send(f"Kick failed: {e}")

    @app_commands.command(name="ban", description="Ban a member")
    @commands.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await interaction.response.defer()
        try:
            await interaction.guild.ban(member)
            await interaction.followup.send(f"{member.mention} has been banned.")
        except Forbidden:
            await interaction.followup.send("Missing permissions")
        except Exception as e:
            await interaction.followup.send(f"Ban failed: {e}")

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @commands.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, userId: int):
        await interaction.response.defer()
        user = discord.Object(id=userId)
        try:
            await interaction.guild.unban(user)
            await interaction.followup.send(f"User {userId} has been unbanned.")
        except Forbidden:
            await interaction.followup.send("Missing permissions")
        except Exception as e:
            await interaction.followup.send(f"Unban failed: {e}")

async def setup(client):
    await client.add_cog(SlashModeration(client))
