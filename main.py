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
        "nacl": "PyNaCl",
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

    log_dir = os.path.dirname(os.path.abspath(__file__))
    normal = logging.FileHandler(os.path.join(log_dir, "bot.log"), encoding="utf-8")
    normal.setFormatter(formatter)
    root.addHandler(normal)

    error = logging.FileHandler(os.path.join(log_dir, "bot-error.log"), encoding="utf-8")
    error.setLevel(logging.ERROR)
    error.setFormatter(formatter)
    root.addHandler(error)


logger = logging.getLogger(__name__)

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _ensure_env():
    """Create .env interactively, or exit if running non-interactively."""
    if os.path.exists(ENV_PATH):
        return

    if not sys.stdin.isatty():
        print("❌ No .env found. Copy .env.example to .env and set BotToken.")
        sys.exit(1)

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


import asyncio

import config
from bot import PERSONALITIES, EchoBot
from cog_manager import CogManager
from safety_checks import ensure_ollama_model, health_checks


async def main():
    token = config.BOT_TOKEN
    chat_channel = config.CHAT_CHANNEL
    default_personality = config.DEFAULT_PERSONALITY

    if not token:
        print("❌ BotToken not found in .env")
        print("   Run the bot once interactively to create .env, or add BotToken=... manually")
        sys.exit(1)

    if default_personality not in PERSONALITIES:
        logger.warning("Unknown default personality '%s'. Falling back to 'tama'.", default_personality)
        default_personality = "tama"

    bot = EchoBot(token=token, chatChannel=chat_channel, default_personality=default_personality)
    cog_manager = CogManager(bot.client)

    async def setup_hook():
        await cog_manager.load_cogs()

    bot.client.setup_hook = setup_hook

    logger.info("EchoBot starting. Default personality: %s", default_personality)
    await bot.client.start(bot.token)


if __name__ == "__main__":
    _setup_logging()
    _ensure_env()
    config.load(override=True)
    for pid in PERSONALITIES:
        PERSONALITIES[pid]["model"] = config.OLLAMA_MODEL
    health_checks()
    ensure_ollama_model(config.OLLAMA_MODEL)
    asyncio.run(main())
