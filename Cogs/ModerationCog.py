import discord
from discord import Forbidden, app_commands
from discord.ext import commands
from typing import Dict, List
import os
import traceback

OWNER_ID = os.getenv("BotOwnerId")
OWNER_ID = int(OWNER_ID) if OWNER_ID else None

def _is_owner_or_admin(interaction: discord.Interaction) -> bool:
    """Check if the user is the configured owner, guild owner, or has administrator perms."""
    # Configured owner ID from .env
    if OWNER_ID is not None and interaction.user.id == OWNER_ID:
        return True
    # Guild owner fallback
    if interaction.guild and interaction.guild.owner_id == interaction.user.id:
        return True
    # Administrator permission fallback
    if interaction.permissions and interaction.permissions.administrator:
        return True
    return False

class Moderation(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        await self.client.tree.sync()

    @staticmethod
    async def is_allowed_user(interaction: discord.Interaction):
        if not _is_owner_or_admin(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this command.", ephemeral=True
            )
            return False
        return True

    @staticmethod
    async def _safe_response(interaction: discord.Interaction, content: str, *, ephemeral=False):
        """Send a response safely, handling cases where interaction was already responded to."""
        try:
            if interaction.response.is_done():
                await interaction.followup.send(content, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(content, ephemeral=ephemeral)
        except Exception:
            # interaction may have expired
            pass

    # ── Utility ──────────────────────────────────────────────────────────

    @app_commands.command(name="ping", description="Ping the bot")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! {round(self.client.latency * 1000)}ms")

    @app_commands.command(name="cogs", description="List loaded cogs")
    async def cogs(self, interaction: discord.Interaction):
        loaded = []
        for ext_name in list(self.client.extensions.keys()):
            ext = self.client.extensions.get(ext_name)
            loaded.append(ext_name)
        lines = "\n".join(f"• {name}" for name in loaded) if loaded else "None loaded"
        embed = discord.Embed(title="Loaded Cogs", color=0x00ff00)
        embed.description = f"```\n{lines}\n```"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="modhelp", description="List moderation commands")
    async def modhelp(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Moderation Commands", color=0x00ff00)
        embed.add_field(
            name="Messages",
            value="`/purge <count>` — Bulk delete messages\n`/speak <message> [channel]` — Send as bot",
            inline=False
        )
        embed.add_field(
            name="Member Actions",
            value="`/kick <member> [reason]` — Kick user\n`/ban <member> [reason]` — Ban user\n`/unban <user_id> [reason]` — Unban user\n`/timeout <member> <minutes> [reason]` — Timeout user\n`/untimeout <member>` — Remove timeout",
            inline=False
        )
        embed.add_field(
            name="Bot",
            value="`/reload_cogs` — Hot-reload all cogs\n`/cogs` — List loaded cogs",
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Message Cleanup ────────────────────────────────────────────────

    @app_commands.command(name="purge", description="Clear chat messages")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.check(is_allowed_user)
    async def purge(self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]):
        try:
            await interaction.response.defer(ephemeral=True)
            deleted = await interaction.channel.purge(limit=count)
            await interaction.followup.send(f"🗑 Deleted {len(deleted)} messages.", ephemeral=True)
        except Forbidden:
            await interaction.followup.send("❌ Missing permissions.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Purge failed: {e}", ephemeral=True)

    @app_commands.command(name="speak", description="Make the bot send a message")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def speak(
        self,
        interaction: discord.Interaction,
        message: app_commands.Range[str, 1, 2000],
        channel: discord.TextChannel = None
    ):
        await interaction.response.defer(ephemeral=True)
        target_channel = channel or interaction.channel

        try:
            if len(message) > 2000:
                await interaction.followup.send("❌ Message exceeds 2000 characters.", ephemeral=True)
                return
            await target_channel.send(message)
            await interaction.followup.send(
                f"✅ Message sent to {target_channel.mention}.", ephemeral=True
            )
        except Forbidden:
            await interaction.followup.send("❌ Bot lacks permissions in that channel.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    # ── Member Actions ─────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.check(is_allowed_user)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.kick(reason=reason)
            await interaction.response.send_message(
                f"{member.mention} has been kicked.\n📋 Reason: `{reason}`", ephemeral=True
            )
        except Forbidden:
            await interaction.response.send_message("❌ I can't kick this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.check(is_allowed_user)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.ban(reason=reason)
            await interaction.response.send_message(
                f"{member.mention} has been banned.\n📋 Reason: `{reason}`", ephemeral=True
            )
        except Forbidden:
            await interaction.response.send_message("❌ I can't ban this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="unban", description="Unban a member from the server")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.check(is_allowed_user)
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            user = await self.client.fetch_user(int(user_id))
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(
                f"{user.mention} has been unbanned.\n📋 Reason: `{reason}`", ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
        except Forbidden:
            await interaction.response.send_message("❌ I can't unban this user.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="timeout", description="Temporarily timeout a member")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],  # max ~4 weeks
        reason: str = "No reason provided"
    ):
        try:
            duration = discord.utils.utcnow() + discord.timedelta(minutes=minutes)
            await member.timeout(duration, reason=reason)
            await interaction.response.send_message(
                f"🔇 {member.mention} has been timed out for **{minutes} minute(s)**.\n📋 Reason: `{reason}`",
                ephemeral=True
            )
        except Forbidden:
            await interaction.response.send_message("❌ I can't timeout this member.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.check(is_allowed_user)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        try:
            await member.timeout(None, reason=reason)
            await interaction.response.send_message(
                f"🔊 {member.mention}'s timeout has been removed.\n📋 Reason: `{reason}`", ephemeral=True
            )
        except Forbidden:
            await interaction.response.send_message("❌ I can't remove this timeout.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error: {e}", ephemeral=True)

    # ── Cog Management ──────────────────────────────────────────────────

    @app_commands.command(name="reload_cogs", description="Hot-reload all cogs")
    @app_commands.check(is_allowed_user)
    async def reload_cogs(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        all_extensions = ["Cogs.ModerationCog", "Cogs.MusicCog", "Cogs.QuizCog", "Cogs.RPGCog"]
        results = []

        for ext in all_extensions:
            is_loaded = ext in self.client.extensions
            try:
                if is_loaded:
                    await self.client.reload_extension(ext)
                    results.append(f"🔄 {ext} — reloaded")
                else:
                    await self.client.load_extension(ext)
                    results.append(f"✅ {ext} — loaded")
            except Exception as e:
                err = str(e).split("\n")[-1]  # last line usually has the meat
                results.append(f"❌ {ext} — {err}")

        # Note: ModerationCog reload inside itself works in discord.py 2.x+
        # but if it fails for any reason, we've already tried it and logged the error.
        embed = discord.Embed(title="Cog Reload Results", color=0x00ff00)
        embed.description = "\n".join(results)
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(client):
    await client.add_cog(Moderation(client))
    print("Moderation Online")
