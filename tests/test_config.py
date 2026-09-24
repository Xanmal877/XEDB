"""Tests for env-backed config defaults and validation."""

import os

import config


def test_defaults_without_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    for key in (
        "BotToken",
        "BotOwnerId",
        "ChatChannel",
        "DefaultPersonality",
        "OllamaModel",
        "OllamaHost",
        "OLLAMA_HOST",
        "CommandPrefix",
        "ReplyChance",
        "ActivityHours",
        "SongsDir",
        "QuizTimezone",
        "SteamGamesDir",
        "AloneDisconnectSeconds",
    ):
        monkeypatch.delenv(key, raising=False)
    config.load(override=True)
    assert config.BOT_TOKEN is None
    assert config.BOT_OWNER_ID is None
    assert config.CHAT_CHANNEL == "general"
    assert config.DEFAULT_PERSONALITY == "tama"
    assert config.OLLAMA_MODEL == "gemma4"
    assert config.OLLAMA_HOST == "http://localhost:11434"
    assert config.COMMAND_PREFIX == "!"
    assert config.REPLY_CHANCE == 6
    assert config.ACTIVITY_HOURS == 12
    assert config.SONGS_DIR == "Songs"
    assert config.QUIZ_TIMEZONE == "US/Arizona"
    assert config.STEAM_GAMES_DIR is None
    assert config.ALONE_DISCONNECT_SECONDS == 60


def test_invalid_integers_fall_back(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("ReplyChance", "nope")
    monkeypatch.setenv("BotOwnerId", "abc")
    monkeypatch.setenv("ActivityHours", "")
    config.load(override=True)
    assert config.REPLY_CHANCE == 6
    assert config.BOT_OWNER_ID is None
    assert config.ACTIVITY_HOURS == 12


def test_ollama_host_exported(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("OllamaHost", "http://127.0.0.1:11434")
    config.load(override=True)
    assert config.OLLAMA_HOST == "http://127.0.0.1:11434"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11434"
