from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    provider: str          # "local" (OpenAI-compatible) or "anthropic"
    api_key: str
    base_url: str
    llm_model: str
    request_timeout_seconds: float
    max_iterations: int


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def load_settings() -> Settings:
    load_dotenv(dotenv_path=_repo_root() / ".env", override=False)
    provider = os.environ.get("LLM_PROVIDER", "local").strip().lower()
    timeout = float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "60"))
    max_iter = int(os.environ.get("MAX_ITERATIONS", "20"))

    if provider == "anthropic":
        return Settings(
            provider="anthropic",
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            base_url="",  # unused for Anthropic
            llm_model=os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            request_timeout_seconds=timeout,
            max_iterations=max_iter,
        )

    # Default: local OpenAI-compatible endpoint (e.g. LM Studio)
    return Settings(
        provider="local",
        api_key="no-key-needed",
        base_url=os.environ.get("LOCAL_LLM_ENDPOINT", "http://127.0.0.1:1234/v1/"),
        llm_model=os.environ.get("LOCAL_LLM_MODEL", "openai/gpt-oss-20b:2"),
        request_timeout_seconds=timeout,
        max_iterations=max_iter,
    )
