"""Ollama clients and the instance personality.yaml."""

from __future__ import annotations

import json
import logging
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import ollama
import yaml

import config

logger = logging.getLogger(__name__)

_CLOUD = "cloud"
_LOCAL = "local"

COG_MODULES = {
    "ModerationCog": "Cogs.ModerationCog",
    "MusicCog": "Cogs.MusicCog",
    "RPGCog": "Cogs.RPGCog",
    "QuizCog": "Cogs.QuizCog",
}

_COG_ALIASES = {
    "moderation": "ModerationCog",
    "moderationcog": "ModerationCog",
    "music": "MusicCog",
    "musiccog": "MusicCog",
    "rpg": "RPGCog",
    "rpgcog": "RPGCog",
    "quiz": "QuizCog",
    "quizcog": "QuizCog",
}


@dataclass(frozen=True)
class Provider:
    kind: str
    model: str
    endpoint: str = "cloud"


@dataclass(frozen=True)
class Personality:
    id: str
    names: tuple[str, ...]
    model: str
    endpoint: str
    system: str
    providers: tuple[Provider, ...] = ()


@dataclass
class BotProfile:
    personality: Personality
    cogs: dict[str, bool] = field(default_factory=dict)


PERSONALITIES: dict[str, Personality] = {}
PROFILE: BotProfile | None = None
ENABLED_EXTENSIONS: list[str] = list(COG_MODULES.values())


def _parse_endpoint(raw: str | None) -> str:
    value = (raw or _CLOUD).strip().lower()
    if value not in {_LOCAL, _CLOUD}:
        raise ValueError(f"endpoint must be 'local' or 'cloud', got {raw!r}")
    return value


def _names(raw, fallback: str) -> tuple[str, ...]:
    if raw is None:
        return (fallback,)
    if isinstance(raw, str):
        names = tuple(n.strip().lower() for n in raw.split(",") if n.strip())
    else:
        names = tuple(str(n).strip().lower() for n in raw if str(n).strip())
    return names or (fallback,)


def _canonical_cog(name: str) -> str | None:
    key = name.strip()
    if key in COG_MODULES:
        return key
    return _COG_ALIASES.get(key.lower())


def parse_cogs(raw) -> dict[str, bool]:
    """Map each known cog to enabled/disabled. Omitted cogs default to on."""
    enabled = dict.fromkeys(COG_MODULES, True)
    if raw is None:
        return enabled
    if not isinstance(raw, dict):
        raise TypeError("cogs must be a mapping of name: true/false")
    for key, value in raw.items():
        cog = _canonical_cog(str(key))
        if cog is None:
            logger.warning("Unknown cog in personality.yaml: %s", key)
            continue
        enabled[cog] = bool(value)
    return enabled


def enabled_extensions(cogs: dict[str, bool] | None = None) -> list[str]:
    flags = cogs if cogs is not None else dict.fromkeys(COG_MODULES, True)
    return [COG_MODULES[name] for name in COG_MODULES if flags.get(name, True)]


def _named_provider(kind: str, model: str = "", endpoint: str | None = None) -> Provider:
    name = kind.strip().lower()
    if name in {"ollama", "openai", "codex", "luna"}:
        return Provider(kind=name, model=model.strip(), endpoint=_parse_endpoint(endpoint) if name == "ollama" else _CLOUD)
    raise ValueError(f"unknown provider {kind!r} (use ollama, openai, codex, or luna)")


def _parse_fallbacks(raw) -> tuple[Provider, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, list):
        items = raw
    else:
        raise TypeError("fallbacks must be a list or comma-separated string")
    providers: list[Provider] = []
    for item in items:
        if isinstance(item, str):
            providers.append(_named_provider(item))
            continue
        if not isinstance(item, dict):
            raise TypeError(f"fallback entry must be a string or mapping, got {type(item).__name__}")
        kind = str(item.get("provider") or item.get("name") or "").strip()
        providers.append(_named_provider(kind, str(item.get("model") or ""), item.get("endpoint")))
    return tuple(providers)


def _personality_from_mapping(raw: dict, fallback_id: str) -> Personality:
    pid = str(raw.get("id") or fallback_id).strip().lower()
    if not pid:
        raise ValueError("personality is missing id")
    model = str(raw.get("model") or "").strip()
    if not model:
        raise ValueError(f"personality {pid!r} is missing model")
    return Personality(
        id=pid,
        names=_names(raw.get("names"), pid),
        model=model,
        endpoint=_parse_endpoint(raw.get("endpoint")),
        system=str(raw.get("system") or ""),
        providers=_parse_fallbacks(raw.get("fallbacks")),
    )


def load_personalities(path: Path | None = None) -> dict[str, Personality]:
    """Load personality.yaml (one character per instance)."""
    global PERSONALITIES, PROFILE
    path = Path(path) if path is not None else config.PERSONALITY_PATH
    PERSONALITIES.clear()
    PROFILE = None
    ENABLED_EXTENSIONS[:] = list(COG_MODULES.values())

    if not path.exists():
        logger.warning("No personality file at %s", path)
        return PERSONALITIES

    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise TypeError("personality.yaml must be a mapping")

    nested = data.get("personality")
    body = nested if isinstance(nested, dict) else data
    personality = _personality_from_mapping(body, fallback_id=path.stem)
    if not personality.providers:
        extra = data.get("fallbacks")
        if extra is not None:
            personality = Personality(
                id=personality.id,
                names=personality.names,
                model=personality.model,
                endpoint=personality.endpoint,
                system=personality.system,
                providers=_parse_fallbacks(extra),
            )
    cogs_raw = data.get("cogs")
    if cogs_raw is None:
        cogs_raw = body.get("cogs")
    cogs = parse_cogs(cogs_raw)
    PROFILE = BotProfile(personality=personality, cogs=cogs)
    PERSONALITIES.clear()
    PERSONALITIES[personality.id] = personality
    ENABLED_EXTENSIONS[:] = enabled_extensions(cogs)
    return PERSONALITIES


def mentioned_personality(text: str, personalities: dict[str, Personality] | None = None) -> str | None:
    personalities = personalities if personalities is not None else PERSONALITIES
    text_lower = text.lower()
    for pid, spec in personalities.items():
        if any(re.search(rf"\b{re.escape(name)}\b", text_lower) for name in spec.names):
            return pid
    return None


def make_client(endpoint: str):
    if endpoint == _CLOUD:
        if not config.OLLAMA_API_KEY:
            raise RuntimeError("OllamaApiKey is required for cloud personalities")
        return ollama.Client(
            host=config.OLLAMA_CLOUD_HOST,
            headers={"Authorization": f"Bearer {config.OLLAMA_API_KEY}"},
        )
    return ollama.Client(host=config.OLLAMA_HOST)


def _message_text(response) -> str | None:
    if isinstance(response, dict):
        return (response.get("message") or {}).get("content")
    message = getattr(response, "message", None)
    if message is None:
        return None
    if isinstance(message, dict):
        return message.get("content")
    return getattr(message, "content", None)


def iter_providers(personality: Personality) -> tuple[Provider, ...]:
    primary = Provider(kind="ollama", model=personality.model, endpoint=personality.endpoint)
    return (primary, *personality.providers)


def _openai_settings(provider: Provider) -> tuple[str | None, str, str]:
    """Return (api_key, base_url, model) for an OpenAI-compatible provider."""
    if provider.kind == "luna":
        key = config.LUNA_API_KEY or config.OPENAI_API_KEY
        base = config.LUNA_BASE_URL or config.OPENAI_BASE_URL
        model = provider.model or config.LUNA_MODEL
    elif provider.kind == "codex":
        key = config.OPENAI_API_KEY
        base = config.OPENAI_BASE_URL
        model = provider.model or config.CODEX_MODEL
    else:
        key = config.OPENAI_API_KEY
        base = config.OPENAI_BASE_URL
        model = provider.model or config.CODEX_MODEL
    return key, base.rstrip("/"), model


def openai_chat(messages: list[dict], model: str, api_key: str, base_url: str) -> str | None:
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"OpenAI base URL must be http(s), got {base_url!r}")
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = json.dumps({"model": model, "messages": messages, "stream": False}).encode()
    request = urllib.request.Request(  # noqa: S310
        url,
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"openai {model} HTTP {exc.code}: {detail[:300]}") from exc
    choices = body.get("choices") or []
    if not choices:
        return None
    message = (choices[0] or {}).get("message") or {}
    content = message.get("content")
    return str(content) if content else None


def _chat(provider: Provider, messages: list[dict]) -> str | None:
    if provider.kind == "ollama":
        client = make_client(provider.endpoint)
        return _message_text(client.chat(model=provider.model, messages=messages, stream=False))
    if provider.kind in {"openai", "codex", "luna"}:
        key, base, model = _openai_settings(provider)
        if not key:
            raise RuntimeError(f"{provider.kind} has no API key")
        if not model:
            raise RuntimeError(f"{provider.kind} has no model")
        return openai_chat(messages, model, key, base)
    raise ValueError(f"unknown provider kind {provider.kind!r}")


def generate_response(user_text: str, personality: Personality) -> str | None:
    messages = []
    if personality.system.strip():
        messages.append({"role": "system", "content": personality.system})
    messages.append({"role": "user", "content": user_text})
    last_error: Exception | None = None
    for provider in iter_providers(personality):
        try:
            text = _chat(provider, messages)
        except Exception as exc:
            last_error = exc
            logger.warning("provider %s/%s failed: %s", provider.kind, provider.model or "?", exc)
            continue
        if text:
            if provider.kind != "ollama":
                logger.info("reply via fallback %s (%s)", provider.kind, provider.model)
            return text
        logger.warning("provider %s/%s returned empty", provider.kind, provider.model)
    if last_error:
        logger.error("all providers failed for %s: %s", personality.id, last_error)
    return None


def needs_local_runtime(personalities: dict[str, Personality] | None = None) -> bool:
    personalities = personalities if personalities is not None else PERSONALITIES
    for spec in personalities.values():
        if spec.endpoint == _LOCAL:
            return True
        if any(p.kind == "ollama" and p.endpoint == _LOCAL for p in spec.providers):
            return True
    return False


def _listed_models(client) -> list[str]:
    response = client.list()
    if hasattr(response, "models"):
        return [str(getattr(m, "model", m)) for m in response.models]
    if isinstance(response, dict):
        return [str(m.get("model", m.get("name", ""))) for m in response.get("models", [])]
    return []


def ensure_model(personality: Personality) -> None:
    if personality.endpoint == _CLOUD:
        print(f"[Bootstrap] {personality.id}: cloud model '{personality.model}' via {config.OLLAMA_CLOUD_HOST}")
        return
    try:
        client = make_client(_LOCAL)
        models = _listed_models(client)
        if any(personality.model == m or personality.model in m for m in models):
            print(f"[Bootstrap] {personality.id}: local model '{personality.model}' is available")
            return
        if not sys.stdin.isatty():
            print(f"[Bootstrap] {personality.id}: '{personality.model}' is not local.")
            print(f"   Pull it manually: ollama pull {personality.model}")
            return
        print(f"[Bootstrap] Pulling '{personality.model}'...")
        client.pull(personality.model)
        print(f"[Bootstrap] Model '{personality.model}' ready")
    except Exception as e:
        print(f"[Bootstrap] Warning: could not pull '{personality.model}': {e}")
        print(f"   Make sure Ollama is running: ollama pull {personality.model}")


def ensure_personality_models(personalities: dict[str, Personality] | None = None) -> None:
    personalities = personalities if personalities is not None else PERSONALITIES
    seen: set[tuple[str, str]] = set()
    for spec in personalities.values():
        key = (spec.endpoint, spec.model)
        if key in seen:
            continue
        seen.add(key)
        ensure_model(spec)
