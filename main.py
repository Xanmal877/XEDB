import sys
import subprocess
import importlib.util
import os

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
        os.execv(sys.executable, [sys.executable] + sys.argv)

_ensure_deps()

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
import discord
from discord.ext import commands
import random
from dotenv import load_dotenv
import argparse
import ollama
import json

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
DEFAULT_MODEL = "gemma4"

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

parser = argparse.ArgumentParser(description="Run Xanrean Echo Discord Bot")
parser.add_argument("bot", choices=["tama", "saki"], help="Legacy arg, ignored. Personalities are automatic.", nargs="?", default="tama")
args = parser.parse_args()

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
    except Exception as e:
        print(f"Error in GenerateResponse: {e}")
        return None

# ── Utility: Build game list for Discord activity ─────────────────────
def GenerateGameList():
    bot_directory = os.path.dirname(os.path.abspath(__file__))
    game_list_file = os.path.join(bot_directory, "DataFiles", "GameList.json")
    games = []

    try:
        with open(game_list_file, "r") as file:
            gamelist = json.load(file)["games"]
            games.extend(gamelist)
    except FileNotFoundError:
        print(f"GameList.json not found: {game_list_file}")
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing GameList.json: {e}")

    steam_directory = r"C:\Program Files (x86)\Steam\steamapps\common"
    if os.path.isdir(steam_directory):
        try:
            steam_games = [
                name for name in os.listdir(steam_directory)
                if os.path.isdir(os.path.join(steam_directory, name))
            ]
            games.extend(steam_games)
        except Exception as e:
            print(f"Error accessing Steam directory: {e}")

    return games

# ── Background task: Rotate Discord presence every 12 hours ──────────
async def SetActivity(client):
    while True:
        try:
            games = GenerateGameList()
            if not games:
                print("No games found for activity rotation.")
                return

            game = random.choice(games)
            await client.change_presence(
                status=discord.Status.online,
                activity=discord.Game(name=game),
            )
            print(f"Activity set to: {game}")
            await asyncio.sleep(43200)  # 12 hours
        except Exception as e:
            print(f"Error in SetActivity: {e}")
            await asyncio.sleep(300)  # Retry in 5 min on error

# ── Unified bot class ────────────────────────────────────────────────────
class EchoBot:
    def __init__(self, token, chatChannel, default_personality):
        self.client = commands.Bot(
            command_prefix=["!"],
            case_insensitive=True,
            intents=discord.Intents.all(),
        )
        self.client.chatlog_dir = "logs/"
        self.token = token
        self.chatChannel = chatChannel
        self.default_personality = default_personality
        self.current_personality = default_personality

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    def _detect_personality(self, text: str) -> str:
        """Return personality ID if text contains a personality trigger word."""
        text_lower = text.lower()
        for pid, config in PERSONALITIES.items():
            if any(name in text_lower for name in config["names"]):
                return pid
        return self.current_personality

    async def on_ready(self):
        self.client.loop.create_task(SetActivity(self.client))
        print(f"EchoBot logged in as {self.client.user}")
        print(f"Default personality: {self.default_personality}")

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
class CogManager:
    def __init__(self, client):
        self.client = client

    async def load_cogs(self):
        await self.remove_cogs()

        # Load all cogs for the unified bot
        all_cogs = [
            "Cogs.ModerationCog",
            "Cogs.MusicCog",
            "Cogs.RPGCog",
            "Cogs.QuizCog",
        ]
        loaded = []
        for cog in all_cogs:
            try:
                await self.client.load_extension(cog)
                loaded.append(cog.split(".")[-1])
            except Exception as e:
                print(f"⚠️  Failed to load {cog}: {e}")

        print(f"Loaded cogs: {', '.join(loaded) if loaded else 'none'}")

    async def remove_cogs(self):
        all_cogs = [
            "Cogs.ModerationCog",
            "Cogs.MusicCog",
            "Cogs.QuizCog",
            "Cogs.RPGCog",
        ]
        for cog in all_cogs:
            try:
                await self.client.unload_extension(cog)
            except commands.ExtensionNotLoaded:
                pass

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
        print(f"⚠️  Unknown default personality '{default_personality}'. Falling back to 'tama'.")
        default_personality = "tama"

    bot = EchoBot(token=token, chatChannel=chat_channel, default_personality=default_personality)
    cog_manager = CogManager(bot.client)
    await cog_manager.load_cogs()

    print(f"\n🤖 EchoBot Online! Default personality: {default_personality}")
    await bot.client.start(bot.token)

if __name__ == "__main__":
    asyncio.run(main())
