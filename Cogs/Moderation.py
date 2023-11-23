import discord
from discord import Forbidden, app_commands
from discord.ext import commands

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        print("Moderation Enforced")
        await self.client.tree.sync()

        
        
    # Static method to check for allowed users
    @staticmethod
    async def is_allowed_user(interaction: discord.Interaction):
        allowed_users = [175421668850794506, 427689980241117184]  # User IDs
        return interaction.user.id in allowed_users


       

    @app_commands.command(name= "ping", description= "Ping the bot")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.client.latency * 1000)}ms")

    @app_commands.check(is_allowed_user)
    @app_commands.command(name="purge", description="Clear chat messages")
    @commands.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, count: int):
        try:
            await interaction.channel.purge(limit=count)
            await interaction.response.send_message(f"{count} message(s) have been deleted")  # Use interaction.response to send the message
            
        except Forbidden:
            await interaction.send("Missing permissions")

        except Exception as e:
            await interaction.send(f"Purge failed: {e}")

    @app_commands.check(is_allowed_user)
    @app_commands.command(name="kick", description="Kick Member")
    @commands.has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member=None,):
        if member is None:
            member = interaction.user
        elif member is not None:
            member = member
        
        if member is None:
            await interaction.send_message("Please mention a member to kick.")
        elif member == interaction.author:
            await interaction.send_message("You cannot kick yourself.")
        elif member == interaction.guild.owner:
            await interaction.send_message("You cannot kick the owner.")
        elif member.top_role >= interaction.author.top_role:
            await interaction.send_message("You cannot kick someone with a higher role than you.")
        else:
            await interaction.guild.kick(member)
            await interaction.send_message(f"{member.mention} has been kicked from the server {interaction.author.mention}.")
        await interaction.user.kick(discord.Member)
        await interaction.send_message(f"{interaction.member.mention} has been kicked from the server {interaction.author.mention}.")

async def setup(client):
    await client.add_cog(Moderation(client))
