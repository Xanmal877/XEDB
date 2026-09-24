import argparse
import asyncio
import contextlib
import importlib.util
import logging
import os
import signal
import subprocess
import sys
from pathlib import Path


def _ensure_deps():
    """Check for required packages and pip-install anything missing."""
    required = {
        "discord": "discord.py[voice]",
        "dotenv": "python-dotenv",
        "ollama": "ollama",
        "yt_dlp": "yt-dlp",
        "pytz": "pytz",
        "nacl": "PyNaCl",
        "yaml": "PyYAML",
    }
    # Voice is opt-in in discord.py 2.7+: without davey, joining a voice
    # channel raises RuntimeError and every MusicCog command fails at runtime
    # rather than at startup. Check it explicitly so a clone can't boot "fine"
    # and then be unable to play anything.
    voice_extras = {"davey": "davey"}
    missing = []
    for module, package in {**required, **voice_extras}.items():
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


async def run_bot(client, token: str, *, stop_event: asyncio.Event | None = None) -> None:
    """Run the gateway until a stop signal arrives, then close it cleanly.

    `await client.start(token)` never returns on its own and never calls
    `close()`. If the process is killed while that coroutine is suspended,
    Discord keeps showing the bot as online. Entering the client as an async
    context manager makes the library call `close()` on exit, which sends a
    proper close frame (code 1000) and shuts the HTTP session down.

    Both SIGINT (Ctrl+C) and SIGTERM (what systemd sends) are handled in-process,
    so a stop request always unwinds through `close()` instead of killing the
    interpreter mid-frame. Pass `stop_event` to drive shutdown from a test.
    """
    if stop_event is None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError, AttributeError, ValueError, RuntimeError):
                loop.add_signal_handler(sig, stop_event.set)

    try:
        async with client:
            runner = asyncio.create_task(client.start(token), name="gateway")
            waiter = asyncio.create_task(stop_event.wait(), name="stop-signal")
            done, pending = await asyncio.wait({runner, waiter}, return_when=asyncio.FIRST_COMPLETED)

            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

            if runner in done and not runner.cancelled():
                # start() returned or raised on its own; surface real failures
                # (bad token, privileged intents) instead of swallowing them.
                error = runner.exception()
                if error is not None:
                    raise error
            else:
                logger.info("Shutdown requested; closing gateway connection.")
    finally:
        logger.info("EchoBot stopped.")


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
    await run_bot(bot.client, bot.token)


if __name__ == "__main__":
    _setup_logging()
    _ensure_env()
    config.load(override=True)
    load_personalities()
    health_checks()
    ensure_personality_models()
    asyncio.run(main())
