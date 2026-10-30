"""Settings loaded from the environment (.env). Every variable is listed in .env.example."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    qloo_api_key: str
    qloo_base_url: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str
    routing_base_url: str
    max_stops: int
    cache_dir: Path

    @property
    def has_qloo(self) -> bool:
        return bool(self.qloo_api_key)

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


def load_settings() -> Settings:
    load_dotenv(REPO_ROOT / ".env")
    cache_dir = Path(os.getenv("CACHE_DIR", ".cache"))
    if not cache_dir.is_absolute():
        cache_dir = REPO_ROOT / cache_dir
    return Settings(
        qloo_api_key=os.getenv("QLOO_API_KEY", ""),
        qloo_base_url=os.getenv("QLOO_BASE_URL", "https://hackathon.api.qloo.com").rstrip("/"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_model=os.getenv("LLM_MODEL", ""),
        routing_base_url=os.getenv("ROUTING_BASE_URL", ""),
        max_stops=int(os.getenv("MAX_STOPS", "6")),
        cache_dir=cache_dir,
    )
