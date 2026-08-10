import contextlib
import importlib.util
import logging
import os
import subprocess
import sys


# ── Bootstrap: auto-install missing dependencies ──────────────────────
def _ensure_deps():
    """Check for required packages and pip-install anything missing."""
    required = {
        "discord": "discord.py",
        "dotenv": "python-dotenv",
        "ollama": "ollama",
        "yt_dlp": "yt-dlp",
        "pytz": "pytz",
    }
    missing = []
    for module, package in required.items():
        if importlib.util.find_spec(module) is None:
            missing.append(package)

    if missing:
        print(f"[Bootstrap] Missing packages: {missing}")
        print("[Bootstrap] Installing...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
        print("[Bootstrap] Done. Restarting with new packages...")
        os.execv(sys.executable, [sys.executable, *sys.argv])


_ensure_deps()


# ── Logging setup ─────────────────────────────────────────────────────
def _setup_logging():
    """Configure console + file logging (bot.log / bot-error.log)."""
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    normal = logging.FileHandler("bot.log", encoding="utf-8")
    normal.setFormatter(formatter)
    root.addHandler(normal)

    error = logging.FileHandler("bot-error.log", encoding="utf-8")
    error.setLevel(logging.ERROR)
    error.setFormatter(formatter)
    root.addHandler(error)


logger = logging.getLogger(__name__)
_setup_logging()

# ── Interactive .env setup ────────────────────────────────────────────
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if not os.path.exists(ENV_PATH):
    print("\n=== First-time setup ===")
    print("Create a Discord bot at https://discord.com/developers/applications\n")

    bot_token = input("Bot token: ").strip()
    chat_channel = input("Chat channel name [general]: ").strip() or "general"
    default_personality = input("Default personality [tama]: ").strip() or "tama"

    lines = []
    if bot_token:
        lines.append(f"BotToken={bot_token}")
    lines.append(f"ChatChannel={chat_channel}")
    lines.append(f"DefaultPersonality={default_personality}")

    with open(ENV_PATH, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[Bootstrap] Created {ENV_PATH}\n")

# ── Third-party imports (safe now that deps are guaranteed) ──────────
import asyncio
import json
import random

import discord
import ollama
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()


# ── External dependency health checks ─────────────────────────────────
def _check_ollama():
    """Check if Ollama is running locally."""
    import urllib.request

    try:
        urllib.request.urlopen("http://localhost:11434", timeout=2)
        return True
    except Exception:
        return False


def _check_ffmpeg():
    """Check if ffmpeg is installed on the system."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def _offer_open(url: str, name: str):
    """Ask user if they want to open a download page."""
    try:
        response = input(f"Open {name} download page in browser? [y/N]: ").strip().lower()
        if response in ("y", "yes"):
            import webbrowser

            webbrowser.open(url)
            print(f"[Bootstrap] Opened {url}")
    except (EOFError, KeyboardInterrupt):
        pass


if not _check_ollama():
    print("\n⚠️  Ollama is not running on http://localhost:11434")
    print("   The bot needs Ollama for AI responses.")
    _offer_open("https://ollama.com/download", "Ollama")
    print("   Start Ollama and try again.\n")

if not _check_ffmpeg():
    print("\n⚠️  ffmpeg is not installed or not in PATH")
    print("   The MusicCog needs ffmpeg for voice channel audio playback.")
    _offer_open("https://ffmpeg.org/download.html", "ffmpeg")
    print("   Install ffmpeg and try again.\n")

# ── Ollama model bootstrap ─────────────────────────────────────────────
DEFAULT_MODEL = os.getenv("OllamaModel", "gemma4")


def _ensure_ollama_model(model_name: str):
    """Pull the model from Ollama if it's not already available locally."""
    try:
        response = ollama.list()
        models = []
        if hasattr(response, "models"):
            models = [getattr(m, "model", str(m)) for m in response.models]
        elif isinstance(response, dict):
            models = [m.get("model", m.get("name", "")) for m in response.get("models", [])]

        if any(model_name == m or model_name in m for m in models):
            print(f"[Bootstrap] Ollama model '{model_name}' is available")
            return

        print(f"[Bootstrap] Pulling Ollama model '{model_name}' (this may take a few minutes)...")
        ollama.pull(model_name)
        print(f"[Bootstrap] Model '{model_name}' ready")
    except Exception as e:
        print(f"[Bootstrap] Warning: could not pull '{model_name}': {e}")
        print(f"   Make sure Ollama is running and try manually: ollama pull {model_name}")


_ensure_ollama_model(DEFAULT_MODEL)

# ── Personality Configuration ────────────────────────────────────────
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


# ── Utility: Generate AI response via Ollama ──────────────────────────
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


# ── Utility: Build game list for Discord activity ─────────────────────
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


# ── Background task: Rotate Discord presence every 12 hours ──────────
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


# ── Unified bot class ────────────────────────────────────────────────────
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

    def _detect_personality(self, text: str) -> str:
        """Return personality ID if text contains a personality trigger word."""
        text_lower = text.lower()
        for pid, config in PERSONALITIES.items():
            if any(name in text_lower for name in config["names"]):
                return pid
        return self.current_personality

    async def on_ready(self):
        self.client.loop.create_task(SetActivity(self.client))
        logger.info("EchoBot logged in as %s", self.client.user)
        logger.info("Default personality: %s", self.default_personality)

    async def on_message(self, message):
        if message.author.bot or message.content.startswith("!"):
            return

        channel_name = message.channel.name if hasattr(message.channel, "name") else None
        content_lower = message.content.lower()

        # Detect which personality is being addressed
        personality_id = self._detect_personality(content_lower)
        model_name = PERSONALITIES[personality_id]["model"]

        # 1. Dedicated chat channel — always respond
        if channel_name == self.chatChannel:
            response = GenerateResponse(message, model_name)
            if response:
                await message.channel.send(response)
            return

        # 2. Mentioned by personality name in other channels
        if personality_id != self.current_personality:
            response = GenerateResponse(message, model_name)
            if response:
                await message.channel.send(response)
            return

        # 3. Random 1-in-6 chance in other channels
        if channel_name != self.chatChannel and random.randrange(0, 6) == 0:
            response = GenerateResponse(message, model_name)
            if response:
                await message.channel.send(response)


# ── Cog manager ───────────────────────────────────────────────────────
ALL_COGS = [
    "Cogs.ModerationCog",
    "Cogs.MusicCog",
    "Cogs.RPGCog",
    "Cogs.QuizCog",
]


class CogManager:
    def __init__(self, client):
        self.client = client

    async def load_cogs(self):
        await self.remove_cogs()

        # Load all cogs for the unified bot
        loaded = []
        for cog in ALL_COGS:
            try:
                await self.client.load_extension(cog)
                loaded.append(cog.split(".")[-1])
            except Exception as e:
                logger.warning("Failed to load %s: %s", cog, e)

        logger.info("Loaded cogs: %s", ", ".join(loaded) if loaded else "none")

    async def remove_cogs(self):
        for cog in ALL_COGS:
            with contextlib.suppress(commands.ExtensionNotLoaded):
                await self.client.unload_extension(cog)


# ── Entry point ───────────────────────────────────────────────────────
async def main():
    token = os.getenv("BotToken")
    chat_channel = os.getenv("ChatChannel", "general")
    default_personality = os.getenv("DefaultPersonality", "tama")

    if not token:
        print("❌ BotToken not found in .env")
        print("   Run the bot once interactively to create .env, or add BotToken=... manually")
        sys.exit(1)

    if default_personality not in PERSONALITIES:
        logger.warning("Unknown default personality '%s'. Falling back to 'tama'.", default_personality)
        default_personality = "tama"

    bot = EchoBot(token=token, chatChannel=chat_channel, default_personality=default_personality)
    cog_manager = CogManager(bot.client)
    await cog_manager.load_cogs()
    await bot.client.tree.sync()

    logger.info("EchoBot Online! Default personality: %s", default_personality)
    await bot.client.start(bot.token)


if __name__ == "__main__":
    asyncio.run(main())
