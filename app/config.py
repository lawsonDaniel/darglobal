"""All settings come from environment variables, read once at import."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.environ.get("DATA_DIR", ROOT / "data" / "processed"))
    index_dir: Path = Path(os.environ.get("INDEX_DIR", ROOT / "data" / "index"))
    openrouter_base: str = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    models: tuple[str, ...] = field(default_factory=lambda: tuple(
        m.strip() for m in os.environ.get(
            "OPENROUTER_MODELS", "nvidia/nemotron-3-ultra-550b-a55b:free,nvidia/nemotron-3.5-super-vl:free,openrouter/free").split(",")
        if m.strip()))
    app_url: str = os.environ.get("APP_URL", "http://localhost:8000")
    llm_timeout: int = _int("OPENROUTER_TIMEOUT", 45)
    request_deadline: int = _int("REQUEST_DEADLINE_SECONDS", 90)
    # Abuse and cost controls
    rate_per_minute: int = _int("RATE_LIMIT_PER_MIN", 8)
    rate_per_day: int = _int("RATE_LIMIT_PER_DAY", 60)
    global_per_day: int = _int("GLOBAL_LIMIT_PER_DAY", 400)
    max_concurrent: int = _int("MAX_CONCURRENT_CHATS", 4)
    trusted_proxy_hops: int = _int("TRUSTED_PROXY_HOPS", 1)
    max_message_chars: int = _int("MAX_MESSAGE_CHARS", 1500)
    max_body_bytes: int = _int("MAX_BODY_BYTES", 8192)
    session_ttl: int = _int("SESSION_TTL_SECONDS", 7200)
    max_sessions: int = _int("MAX_SESSIONS", 2000)
    history_turns: int = _int("HISTORY_MESSAGES", 12)
    enable_docs: bool = _bool("ENABLE_DOCS", False)
    verify_answers: bool = _bool("VERIFY_ANSWERS", True)


settings = Settings()


def openrouter_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "").strip()
