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
    print("Create Discord bots at https://discord.com/developers/applications")
    print("(Leave a field blank to skip it. You can edit .env later.)\n")

    tama_token = input("Tama bot token: ").strip()
    saki_token = input("Saki bot token: ").strip()
    chat_channel = input("Chat channel name [general]: ").strip() or "general"

    lines = []
    if tama_token:
        lines.append(f"TamaToken={tama_token}")
    if saki_token:
        lines.append(f"SakiToken={saki_token}")
    lines.append(f"ChatChannel={chat_channel}")

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
parser = argparse.ArgumentParser(description="Run TamaBot or SakiBot")
parser.add_argument("bot", choices=["tama", "saki"], help="Specify the bot to run (tama or saki)", nargs="?", default="tama")
args = parser.parse_args()

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

# ── Base bot class ────────────────────────────────────────────────────
class DiscordBotBase:
    def __init__(self, modelName, commandPrefix, intents, token, chatChannel):
        self.client = commands.Bot(
            command_prefix=commandPrefix,
            case_insensitive=True,
            intents=intents,
        )
        self.client.chatlog_dir = "logs/"
        self.token = token
        self.chatChannel = chatChannel
        self.modelName = modelName
        self.botNames = []

        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    async def on_ready(self):
        self.client.loop.create_task(SetActivity(self.client))
        print(f"{self.__class__.__name__} logged in as {self.client.user}")

    async def on_message(self, message):
        if message.author.bot or message.content.startswith("!"):
            return

        channel_name = message.channel.name if hasattr(message.channel, "name") else None
        content_lower = message.content.lower()
        mentioned = any(name in content_lower for name in self.botNames)

        # 1. Dedicated chat channel — always respond
        if channel_name == self.chatChannel:
            response = GenerateResponse(message, self.modelName)
            if response:
                await message.channel.send(response)
            return

        # 2. Mentioned by name in other channels
        if mentioned:
            response = GenerateResponse(message, self.modelName)
            if response:
                await message.channel.send(response)
            return

        # 3. Random 1-in-6 chance in other channels
        if channel_name != self.chatChannel and random.randrange(0, 6) == 0:
            response = GenerateResponse(message, self.modelName)
            if response:
                await message.channel.send(response)

# ── TamaBot ───────────────────────────────────────────────────────────
class TamaBot(DiscordBotBase):
    def __init__(self):
        super().__init__(
            modelName="Tamaneko",
            commandPrefix=["tama"],
            intents=discord.Intents.all(),
            token=os.getenv("TamaToken"),
            chatChannel=os.getenv("ChatChannel"),
        )
        self.botNames = ["tama", "tamaneko"]

# ── SakiBot ───────────────────────────────────────────────────────────
class SakiBot(DiscordBotBase):
    def __init__(self):
        super().__init__(
            modelName="Autumn",
            commandPrefix=["saki"],
            intents=discord.Intents.all(),
            token=os.getenv("SakiToken"),
            chatChannel=os.getenv("ChatChannel"),
        )
        self.botNames = ["saki", "autumn"]

# ── Cog manager ───────────────────────────────────────────────────────
class CogManager:
    def __init__(self, client):
        self.client = client

    async def load_cogs(self):
        await self.remove_cogs()

        if args.bot == "tama":
            await self.client.load_extension("Cogs.ModerationCog")
            await self.client.load_extension("Cogs.MusicCog")
            await self.client.load_extension("Cogs.RPGCog")
            print("Loaded Tama cogs: Moderation, Music, RPG")
        elif args.bot == "saki":
            await self.client.load_extension("Cogs.ModerationCog")
            # await self.client.load_extension("Cogs.QuizCog")
            print("Loaded Saki cogs: Moderation")

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
                print(f"Unloaded {cog}")
            except commands.ExtensionNotLoaded:
                continue

# ── Entry point ───────────────────────────────────────────────────────
async def main():
    if args.bot == "tama":
        bot = TamaBot()
    elif args.bot == "saki":
        bot = SakiBot()
    else:
        raise ValueError("Bot must be 'tama' or 'saki'")

    cog_manager = CogManager(bot.client)
    await cog_manager.load_cogs()

    print(f"\n{args.bot.capitalize()} Online!")
    await bot.client.start(bot.token)

if __name__ == "__main__":
    asyncio.run(main())
