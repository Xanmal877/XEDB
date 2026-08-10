"""Shared utilities for XEDB cogs: absolute paths and atomic JSON persistence."""

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "DataFiles"
RPG_DIR = DATA_DIR / "rpgFiles"

PLAYERS_PATH = RPG_DIR / "players.json"
SHOP_PATH = RPG_DIR / "shop-items.json"
MONSTERS_PATH = RPG_DIR / "monsters.json"
QUIZ_DATA_PATH = DATA_DIR / "quiz-data.json"
QUESTIONS_PATH = DATA_DIR / "questions.json"
USED_QUESTIONS_PATH = DATA_DIR / "used-questions.json"


def load_json(path) -> dict:
    """Load a JSON object from *path*, returning {} for missing files.

    Corrupt or non-object files are backed up with a .bak suffix instead of
    being silently discarded, so live data is never lost.
    """
    path = Path(path)
    if not path.exists():
        return {}

    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.exception("Corrupt JSON at %s", path)
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(backup)
            logger.info("Corrupt JSON backed up to %s", backup)
        except OSError:
            logger.exception("Could not back up corrupt JSON at %s", path)
        return {}

    if not isinstance(data, dict):
        logger.warning("JSON file %s is not an object; treating as empty", path)
        return {}
    return data


def save_json(path, data: dict) -> None:
    """Atomically write *data* to *path* via a temp file + os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
            f.write("\n")
        os.replace(tmp, path)
    except OSError:
        logger.exception("Failed to save JSON to %s", path)
        raise
