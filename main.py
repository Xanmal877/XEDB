import argparse
import asyncio
import importlib.util
import logging
import os
import subprocess
import sys
from pathlib import Path


def _ensure_deps():
    """Check for required packages and pip-install anything missing."""
    required = {
        "discord": "discord.py",
        "dotenv": "python-dotenv",
        "ollama": "ollama",
        "yt_dlp": "yt-dlp",
        "pytz": "pytz",
        "nacl": "PyNaCl",
        "yaml": "PyYAML",
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


def _apply_home():
    parser = argparse.ArgumentParser(description="XEDB Discord bot")
    parser.add_argument("--home", help="Instance directory: .env, personality.yaml, DataFiles, logs")
    args, _unknown = parser.parse_known_args()
    if args.home:
        os.environ["XEDB_HOME"] = str(Path(args.home).expanduser().resolve())


_ensure_deps()
_apply_home()


def _log_dir() -> str:
    home = os.environ.get("XEDB_HOME")
    if home:
        Path(home).mkdir(parents=True, exist_ok=True)
        return home
    return os.path.dirname(os.path.abspath(__file__))


def _setup_logging():
    """Configure console + file logging (bot.log / bot-error.log)."""
    formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    log_dir = _log_dir()
    normal = logging.FileHandler(os.path.join(log_dir, "bot.log"), encoding="utf-8")
    normal.setFormatter(formatter)
    root.addHandler(normal)

    error = logging.FileHandler(os.path.join(log_dir, "bot-error.log"), encoding="utf-8")
    error.setLevel(logging.ERROR)
    error.setFormatter(formatter)
    root.addHandler(error)


logger = logging.getLogger(__name__)


def _env_path() -> str:
    home = os.environ.get("XEDB_HOME")
    if home:
        return os.path.join(home, ".env")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def _ensure_env():
    """Create .env interactively, or exit if running non-interactively."""
    env_path = _env_path()
    if os.path.exists(env_path):
        return

    if not sys.stdin.isatty():
        print("❌ No .env found. Copy .env.example to the instance home and set BotToken.")
        sys.exit(1)

    print("\n=== First-time setup ===")
    print("Create a Discord bot at https://discord.com/developers/applications\n")

    bot_token = input("Bot token: ").strip()
    chat_channel = input("Chat channel name [general]: ").strip() or "general"

    Path(env_path).parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if bot_token:
        lines.append(f"BotToken={bot_token}")
    lines.append(f"ChatChannel={chat_channel}")

    with open(env_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[Bootstrap] Created {env_path}\n")


import config
from bot import EchoBot
from cog_manager import CogManager
from llm_setup import ENABLED_EXTENSIONS, PERSONALITIES, ensure_personality_models, load_personalities
from safety_checks import health_checks


async def main():
    token = config.BOT_TOKEN
    chat_channel = config.CHAT_CHANNEL
    default_personality = (config.DEFAULT_PERSONALITY or "").lower() or next(iter(PERSONALITIES), None)

    if not token:
        print("❌ BotToken not found in .env")
        print("   Add BotToken=... to the instance .env")
        sys.exit(1)

    if default_personality not in PERSONALITIES:
        fallback = next(iter(PERSONALITIES), None)
        if config.DEFAULT_PERSONALITY:
            logger.warning(
                "Unknown default personality '%s'. Falling back to '%s'.",
                config.DEFAULT_PERSONALITY,
                fallback,
            )
        default_personality = fallback
        if not default_personality:
            print("❌ No personality defined in personality.yaml")
            sys.exit(1)

    bot = EchoBot(token=token, chatChannel=chat_channel, default_personality=default_personality)
    cog_manager = CogManager(bot.client, ENABLED_EXTENSIONS)

    async def setup_hook():
        await cog_manager.load_cogs()

    bot.client.setup_hook = setup_hook

    logger.info("EchoBot starting. Personality: %s  home: %s  cogs: %s", default_personality, config.HOME, ENABLED_EXTENSIONS)
    await bot.client.start(bot.token)


if __name__ == "__main__":
    _setup_logging()
    _ensure_env()
    config.load(override=True)
    load_personalities()
    health_checks()
    ensure_personality_models()
    asyncio.run(main())
