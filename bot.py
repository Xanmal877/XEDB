"""EchoBot: Discord client, personality routing, and presence rotation."""

import asyncio
import json
import logging
import os
import random
import re

import discord
import ollama
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("OllamaModel", "gemma4")

PERSONALITIES = {
    "tama": {
        "model": DEFAULT_MODEL,
        "names": ["tama", "tamaneko"],
    },
    "saki": {
        "model": DEFAULT_MODEL,
        "names": ["saki", "autumn"],
    },
}


def mentioned_personality(text: str) -> str | None:
    """Return personality ID if *text* contains a trigger as a whole word."""
    text_lower = text.lower()
    for pid, config in PERSONALITIES.items():
        if any(re.search(rf"\b{re.escape(name)}\b", text_lower) for name in config["names"]):
            return pid
    return None


def GenerateResponse(message, modelName):
    try:
        response = ollama.chat(
            model=modelName,
            messages=[{"role": "user", "content": message.content}],
            stream=False,
        )
        return response["message"]["content"]
    except Exception:
        logger.exception("Error in GenerateResponse")
        return None


def GenerateGameList():
    bot_directory = os.path.dirname(os.path.abspath(__file__))
    game_list_file = os.path.join(bot_directory, "DataFiles", "GameList.json")
    games = []

    try:
        with open(game_list_file) as file:
            gamelist = json.load(file)["games"]
            games.extend(gamelist)
    except FileNotFoundError:
        logger.warning("GameList.json not found: %s", game_list_file)
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning("Error parsing GameList.json: %s", e)

    steam_directory = r"C:\Program Files (x86)\Steam\steamapps\common"
    if os.path.isdir(steam_directory):
        try:
            steam_games = [name for name in os.listdir(steam_directory) if os.path.isdir(os.path.join(steam_directory, name))]
            games.extend(steam_games)
        except Exception as e:
            logger.warning("Error accessing Steam directory: %s", e)

    return games


async def SetActivity(client):
    while True:
        try:
            games = GenerateGameList()
            if not games:
                logger.info("No games found for activity rotation.")
                return

            game = random.choice(games)
            await client.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name=game),
            )
            logger.info("Activity set to: %s", game)
            await asyncio.sleep(43200)  # 12 hours
        except Exception:
            logger.exception("Error in SetActivity")
            await asyncio.sleep(300)  # Retry in 5 min on error


class EchoBot:
    def __init__(self, token, chatChannel, default_personality):
        self.client = commands.Bot(
            command_prefix=["!"],
            case_insensitive=True,
            intents=discord.Intents.all(),
        )
        self.token = token
        self.chatChannel = chatChannel
        self.default_personality = default_personality
        self.current_personality = default_personality
        self._synced = False

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

        @self.client.tree.error
        async def _on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self._handle_app_command_error(interaction, error)

    async def _handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Friendly user-facing message for slash command failures."""
        if isinstance(error, app_commands.CommandNotFound):
            return

        if isinstance(error, app_commands.MissingPermissions):
            message = f"❌ You need the {', '.join(error.missing_permissions)} permission to use this."
        elif isinstance(error, app_commands.MissingRole):
            message = "❌ You don't have the required role to use this."
        elif isinstance(error, app_commands.CommandOnCooldown):
            message = f"⏳ Command on cooldown. Try again in {error.retry_after:.1f}s."
        elif isinstance(error, app_commands.CheckFailure):
            message = "❌ You do not have permission to use this command."
        elif isinstance(error, app_commands.CommandInvokeError):
            logger.error("Command %r raised: %s", interaction.command, error.original)
            message = "❌ Something went wrong while running this command."
        else:
            logger.error("Unhandled command error for %r: %s", interaction.command, error)
            message = "❌ Something went wrong while running this command."

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
        except (discord.HTTPException, discord.NotFound):
            logger.exception("Could not send error response for command %r", interaction.command)

    async def on_ready(self):
        if not self._synced:
            try:
                await self.client.tree.sync()
                self._synced = True
                logger.info("Slash commands synced")
            except Exception:
                logger.exception("Failed to sync slash commands")
        self.client.loop.create_task(SetActivity(self.client))
        logger.info("EchoBot logged in as %s", self.client.user)
        logger.info("Default personality: %s", self.default_personality)

    async def on_message(self, message):
        if message.author.bot or message.content.startswith("!"):
            return

        channel_name = message.channel.name if hasattr(message.channel, "name") else None
        mentioned = mentioned_personality(message.content)
        if mentioned:
            self.current_personality = mentioned
        personality_id = mentioned or self.current_personality
        model_name = PERSONALITIES[personality_id]["model"]

        should_reply = channel_name == self.chatChannel or mentioned or random.randrange(0, 6) == 0
        if not should_reply:
            return

        response = await asyncio.to_thread(GenerateResponse, message, model_name)
        if response:
            await message.channel.send(response)
