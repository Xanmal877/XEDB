"""Env-backed runtime settings. Importing this module loads `.env` from the instance home."""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

CODE_ROOT = Path(__file__).resolve().parent
HOME = CODE_ROOT
PERSONALITY_PATH = HOME / "personality.yaml"

BOT_TOKEN = None
BOT_OWNER_ID = None
CHAT_CHANNEL = "general"
DEFAULT_PERSONALITY = None
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_CLOUD_HOST = "https://ollama.com"
OLLAMA_API_KEY = None
OPENAI_API_KEY = None
OPENAI_BASE_URL = "https://api.openai.com/v1"
CODEX_MODEL = "gpt-5.3-codex"
LUNA_API_KEY = None
LUNA_BASE_URL = None
LUNA_MODEL = "gpt-5.6-luna"
COMMAND_PREFIX = "!"
REPLY_CHANCE = 6
ACTIVITY_HOURS = 12
SONGS_DIR = "Songs"
QUIZ_TIMEZONE = "US/Arizona"
STEAM_GAMES_DIR = None
ALONE_DISCONNECT_SECONDS = 60


def instance_home() -> Path:
    raw = os.getenv("XEDB_HOME")
    if raw and raw.strip():
        return Path(raw).expanduser().resolve()
    return CODE_ROOT


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
    """Read instance `.env` into module attributes. Call again after the first-run wizard."""
    global HOME, PERSONALITY_PATH
    global BOT_TOKEN, BOT_OWNER_ID, CHAT_CHANNEL, DEFAULT_PERSONALITY
    global OLLAMA_HOST, OLLAMA_CLOUD_HOST, OLLAMA_API_KEY
    global OPENAI_API_KEY, OPENAI_BASE_URL, CODEX_MODEL
    global LUNA_API_KEY, LUNA_BASE_URL, LUNA_MODEL
    global COMMAND_PREFIX, REPLY_CHANCE, ACTIVITY_HOURS
    global SONGS_DIR, QUIZ_TIMEZONE, STEAM_GAMES_DIR, ALONE_DISCONNECT_SECONDS

    HOME = instance_home()
    PERSONALITY_PATH = HOME / "personality.yaml"
    if not PERSONALITY_PATH.exists():
        PERSONALITY_PATH = CODE_ROOT / "personality.yaml"

    load_dotenv(HOME / ".env", override=override)

    BOT_TOKEN = _str("BotToken")
    BOT_OWNER_ID = _owner_id()
    CHAT_CHANNEL = _str("ChatChannel", "general") or "general"
    DEFAULT_PERSONALITY = _str("DefaultPersonality")
    OLLAMA_HOST = _str("OllamaHost") or _str("OLLAMA_HOST") or "http://localhost:11434"
    OLLAMA_CLOUD_HOST = _str("OllamaCloudHost") or "https://ollama.com"
    OLLAMA_API_KEY = _str("OllamaApiKey") or _str("OLLAMA_API_KEY")
    OPENAI_API_KEY = _str("OpenAIApiKey") or _str("OPENAI_API_KEY")
    OPENAI_BASE_URL = _str("OpenAIBaseUrl") or _str("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    CODEX_MODEL = _str("CodexModel") or "gpt-5.3-codex"
    LUNA_API_KEY = _str("LunaApiKey") or _str("LUNA_API_KEY")
    LUNA_BASE_URL = _str("LunaBaseUrl") or _str("LUNA_BASE_URL")
    LUNA_MODEL = _str("LunaModel") or "gpt-5.6-luna"
    COMMAND_PREFIX = _str("CommandPrefix", "!") or "!"
    REPLY_CHANCE = max(1, _int("ReplyChance", 6))
    ACTIVITY_HOURS = max(1, _int("ActivityHours", 12))
    songs = _str("SongsDir", "Songs") or "Songs"
    SONGS_DIR = songs if os.path.isabs(songs) else str(HOME / songs)
    QUIZ_TIMEZONE = _str("QuizTimezone", "US/Arizona") or "US/Arizona"
    STEAM_GAMES_DIR = _str("SteamGamesDir")
    ALONE_DISCONNECT_SECONDS = max(1, _int("AloneDisconnectSeconds", 60))
    os.environ["OLLAMA_HOST"] = OLLAMA_HOST


load()
