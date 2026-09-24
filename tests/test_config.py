"""Tests for env-backed config defaults and validation."""

import os

import config


def test_defaults_without_overrides(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CODE_ROOT", tmp_path)
    monkeypatch.delenv("XEDB_HOME", raising=False)
    for key in (
        "BotToken",
        "BotOwnerId",
        "ChatChannel",
        "DefaultPersonality",
        "OllamaHost",
        "OLLAMA_HOST",
        "OllamaApiKey",
        "OLLAMA_API_KEY",
        "OllamaCloudHost",
        "OpenAIApiKey",
        "OPENAI_API_KEY",
        "OpenAIBaseUrl",
        "OPENAI_BASE_URL",
        "CodexModel",
        "LunaApiKey",
        "LUNA_API_KEY",
        "LunaBaseUrl",
        "LUNA_BASE_URL",
        "LunaModel",
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
    assert config.DEFAULT_PERSONALITY is None
    assert tmp_path == config.HOME
    assert config.OLLAMA_HOST == "http://localhost:11434"
    assert config.OPENAI_API_KEY is None
    assert config.OPENAI_BASE_URL == "https://api.openai.com/v1"
    assert config.CODEX_MODEL == "gpt-5.3-codex"
    assert config.LUNA_MODEL == "gpt-5.6-luna"
    assert config.COMMAND_PREFIX == "!"
    assert config.REPLY_CHANCE == 6
    assert config.ACTIVITY_HOURS == 12
    assert str(tmp_path / "Songs") == config.SONGS_DIR
    assert config.QUIZ_TIMEZONE == "US/Arizona"
    assert config.STEAM_GAMES_DIR is None
    assert config.ALONE_DISCONNECT_SECONDS == 60


def test_invalid_integers_fall_back(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CODE_ROOT", tmp_path)
    monkeypatch.delenv("XEDB_HOME", raising=False)
    monkeypatch.setenv("ReplyChance", "nope")
    monkeypatch.setenv("BotOwnerId", "abc")
    monkeypatch.setenv("ActivityHours", "")
    config.load(override=True)
    assert config.REPLY_CHANCE == 6
    assert config.BOT_OWNER_ID is None
    assert config.ACTIVITY_HOURS == 12


def test_ollama_host_exported(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CODE_ROOT", tmp_path)
    monkeypatch.delenv("XEDB_HOME", raising=False)
    monkeypatch.setenv("OllamaHost", "http://127.0.0.1:11434")
    config.load(override=True)
    assert config.OLLAMA_HOST == "http://127.0.0.1:11434"
    assert os.environ["OLLAMA_HOST"] == "http://127.0.0.1:11434"


def test_xedb_home_loads_env(monkeypatch, tmp_path):
    monkeypatch.delenv("XEDB_HOME", raising=False)
    home = tmp_path / "tama"
    home.mkdir()
    (home / ".env").write_text("BotToken=abc\nChatChannel=lounge\n")
    monkeypatch.setenv("XEDB_HOME", str(home))
    config.load(override=True)
    assert home == config.HOME
    assert config.BOT_TOKEN == "abc"
    assert config.CHAT_CHANNEL == "lounge"
    assert str(home / "Songs") == config.SONGS_DIR
