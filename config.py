"""Env-backed runtime settings. Importing this module loads `.env` from the repo root."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent

BOT_TOKEN = None
BOT_OWNER_ID = None
CHAT_CHANNEL = "general"
DEFAULT_PERSONALITY = "tama"
OLLAMA_MODEL = "gemma4"
OLLAMA_HOST = "http://localhost:11434"
COMMAND_PREFIX = "!"
REPLY_CHANCE = 6
ACTIVITY_HOURS = 12
SONGS_DIR = "Songs"
QUIZ_TIMEZONE = "US/Arizona"
STEAM_GAMES_DIR = None
ALONE_DISCONNECT_SECONDS = 60


def _str(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s: %r (using %s)", name, raw, default)
        return default


def _owner_id() -> int | None:
    raw = _str("BotOwnerId")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("BotOwnerId env var is not a valid integer: %r", raw)
        return None


def load(*, override: bool = False) -> None:
    """Read `.env` into module attributes. Call again after the first-run wizard."""
    load_dotenv(ROOT / ".env", override=override)

    global BOT_TOKEN, BOT_OWNER_ID, CHAT_CHANNEL, DEFAULT_PERSONALITY
    global OLLAMA_MODEL, OLLAMA_HOST, COMMAND_PREFIX, REPLY_CHANCE, ACTIVITY_HOURS
    global SONGS_DIR, QUIZ_TIMEZONE, STEAM_GAMES_DIR, ALONE_DISCONNECT_SECONDS

    BOT_TOKEN = _str("BotToken")
    BOT_OWNER_ID = _owner_id()
    CHAT_CHANNEL = _str("ChatChannel", "general") or "general"
    DEFAULT_PERSONALITY = _str("DefaultPersonality", "tama") or "tama"
    OLLAMA_MODEL = _str("OllamaModel", "gemma4") or "gemma4"
    OLLAMA_HOST = _str("OllamaHost") or _str("OLLAMA_HOST") or "http://localhost:11434"
    COMMAND_PREFIX = _str("CommandPrefix", "!") or "!"
    REPLY_CHANCE = max(1, _int("ReplyChance", 6))
    ACTIVITY_HOURS = max(1, _int("ActivityHours", 12))
    SONGS_DIR = _str("SongsDir", "Songs") or "Songs"
    QUIZ_TIMEZONE = _str("QuizTimezone", "US/Arizona") or "US/Arizona"
    STEAM_GAMES_DIR = _str("SteamGamesDir")
    ALONE_DISCONNECT_SECONDS = max(1, _int("AloneDisconnectSeconds", 60))
    os.environ["OLLAMA_HOST"] = OLLAMA_HOST


load()
