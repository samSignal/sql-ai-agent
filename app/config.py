"""Settings from environment variables (or a .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: str = ".env") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass
class Settings:
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "openai"))  # openai | ollama
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: _env("OPENAI_MODEL", "gpt-4o-mini"))
    openai_base_url: str = field(default_factory=lambda: _env("OPENAI_BASE_URL", ""))  # optional, for compatible APIs
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "qwen2.5:7b"))

    db_path: str = field(default_factory=lambda: _env("DB_PATH", "data/shop.db"))
    max_steps: int = field(default_factory=lambda: int(_env("MAX_STEPS", "8")))
    max_rows: int = field(default_factory=lambda: int(_env("MAX_ROWS", "50")))
    query_timeout_s: float = field(default_factory=lambda: float(_env("QUERY_TIMEOUT_S", "5")))


def get_settings() -> Settings:
    return Settings()
