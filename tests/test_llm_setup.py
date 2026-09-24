"""Tests for llm_setup personality.yaml loading, cogs, and local/cloud clients."""

from llm_setup import (
    COG_MODULES,
    ENABLED_EXTENSIONS,
    Personality,
    enabled_extensions,
    generate_response,
    load_personalities,
    make_client,
    mentioned_personality,
    needs_local_runtime,
    parse_cogs,
)


def _load(path, text):
    path.write_text(text)
    return load_personalities(path)


def test_load_personality_yaml(tmp_path):
    loaded = _load(
        tmp_path / "personality.yaml",
        """
id: tama
names: [tama, tamaneko]
model: gemma4
endpoint: local
system: You are Tama.
cogs:
  MusicCog: false
  quiz: false
""",
    )
    assert set(loaded) == {"tama"}
    spec = loaded["tama"]
    assert spec.names == ("tama", "tamaneko")
    assert spec.model == "gemma4"
    assert spec.endpoint == "local"
    assert spec.system == "You are Tama."
    assert mentioned_personality("hey tama", loaded) == "tama"
    assert "Cogs.MusicCog" not in ENABLED_EXTENSIONS
    assert "Cogs.QuizCog" not in ENABLED_EXTENSIONS
    assert "Cogs.ModerationCog" in ENABLED_EXTENSIONS
    assert "Cogs.RPGCog" in ENABLED_EXTENSIONS


def test_nested_personality_key(tmp_path):
    loaded = _load(
        tmp_path / "personality.yaml",
        """
personality:
  id: saki
  names: [saki, autumn]
  model: gemma4:31b
  endpoint: cloud
  system: You are Saki.
cogs:
  RPGCog: false
""",
    )
    assert loaded["saki"].endpoint == "cloud"
    assert mentioned_personality("hello autumn", loaded) == "saki"
    assert "Cogs.RPGCog" not in ENABLED_EXTENSIONS


def test_missing_file_is_empty(tmp_path):
    assert load_personalities(tmp_path / "missing.yaml") == {}


def test_invalid_endpoint_raises(tmp_path):
    path = tmp_path / "personality.yaml"
    path.write_text("id: x\nnames: [x]\nmodel: m\nendpoint: nope\n")
    try:
        load_personalities(path)
    except ValueError as exc:
        assert "endpoint" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_parse_cogs_defaults_on():
    flags = parse_cogs(None)
    assert flags == dict.fromkeys(COG_MODULES, True)
    assert enabled_extensions({"MusicCog": False, "ModerationCog": True, "RPGCog": True, "QuizCog": True}) == [
        "Cogs.ModerationCog",
        "Cogs.RPGCog",
        "Cogs.QuizCog",
    ]


def test_cloud_client_requires_key(monkeypatch):
    import config

    monkeypatch.setattr(config, "OLLAMA_API_KEY", None)
    try:
        make_client("cloud")
    except RuntimeError as exc:
        assert "OllamaApiKey" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_cloud_client_uses_cloud_host(monkeypatch):
    import config

    monkeypatch.setattr(config, "OLLAMA_API_KEY", "sk-test")
    monkeypatch.setattr(config, "OLLAMA_CLOUD_HOST", "https://ollama.com")
    client = make_client("cloud")
    assert str(client._client.base_url).rstrip("/") == "https://ollama.com"
    assert client._client.headers.get("authorization") == "Bearer sk-test"


def test_needs_local_runtime():
    cloud = {"saki": Personality("saki", ("saki",), "m", "cloud", "")}
    local = {"tama": Personality("tama", ("tama",), "m", "local", "")}
    assert needs_local_runtime(cloud) is False
    assert needs_local_runtime(local) is True


def test_fallbacks_from_yaml(tmp_path):
    loaded = _load(
        tmp_path / "personality.yaml",
        """
id: tama
names: [tama]
model: gemma4:31b
endpoint: cloud
fallbacks: [codex, luna]
""",
    )
    kinds = [p.kind for p in loaded["tama"].providers]
    assert kinds == ["codex", "luna"]
    from llm_setup import PERSONALITIES as imported
    assert "tama" in imported
    assert imported is loaded


def test_generate_response_falls_through(monkeypatch):
    from llm_setup import Provider

    calls = []

    def fake_chat(provider, messages):
        calls.append(provider.kind)
        if provider.kind == "ollama":
            raise RuntimeError("quota")
        if provider.kind == "codex":
            raise RuntimeError("no sub")
        return "luna-ok"

    monkeypatch.setattr("llm_setup._chat", fake_chat)
    spec = Personality(
        "tama",
        ("tama",),
        "gemma4:31b",
        "cloud",
        "",
        (Provider("codex", ""), Provider("luna", "")),
    )
    assert generate_response("hi", spec) == "luna-ok"
    assert calls == ["ollama", "codex", "luna"]
