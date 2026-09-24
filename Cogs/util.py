"""Shared utilities for XEDB cogs: absolute paths and atomic JSON persistence."""

import copy
import json
import logging
import os
from pathlib import Path

import config

logger = logging.getLogger(__name__)

BASE_DIR = config.HOME
DATA_DIR = BASE_DIR / "DataFiles"
RPG_DIR = DATA_DIR / "rpgFiles"

PLAYERS_PATH = RPG_DIR / "players.json"
SHOP_PATH = RPG_DIR / "shop-items.json"
MONSTERS_PATH = RPG_DIR / "monsters.json"
QUIZ_DATA_PATH = DATA_DIR / "quiz-data.json"
QUESTIONS_PATH = DATA_DIR / "questions.json"
USED_QUESTIONS_PATH = DATA_DIR / "used-questions.json"


def load_json(path, default=None):
    """Load JSON from *path*.

    *default* ({} if omitted) is returned for missing or corrupt files, and
    when the loaded value is not the same type as *default*. Corrupt files are
    backed up with a .bak suffix so live data is never discarded silently.
    """
    if default is None:
        default = {}
    expected = type(default)
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)

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
        return copy.deepcopy(default)

    if not isinstance(data, expected):
        logger.warning("JSON file %s is not a %s; treating as empty", path, expected.__name__)
        return copy.deepcopy(default)
    return data


def save_json(path, data) -> None:
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
