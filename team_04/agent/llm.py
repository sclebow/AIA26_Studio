from __future__ import annotations

import os
from typing import Any

try:
    from langchain_openai import ChatOpenAI
except ModuleNotFoundError:  # pragma: no cover - exercised when LLM deps are absent in unit tests
    ChatOpenAI = Any  # type: ignore[misc,assignment]


def create_chat_llm(
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    model_kwargs: dict[str, Any] | None = None,
) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=llm_model,
        timeout=timeout_seconds,
        temperature=0,
        model_kwargs=model_kwargs or {},
    )


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing or empty required environment variable: {name}")
    return value


def resolve_llm_connection(
    provider: str,
    model: str | None,
) -> tuple[str, str, str]:
    normalized_provider = provider.strip().lower()

    if normalized_provider == "local":
        api_key = "local"
        base_url = _required_env("LOCAL_LLM_ENDPOINT")
        resolved_model = model or os.environ.get("LOCAL_MODEL", "local")
    elif normalized_provider == "cloudflare":
        api_key = _required_env("CF_API_TOKEN")
        account_id = _required_env("CF_ACCOUNT_ID")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        resolved_model = model or _required_env("CF_MODEL")
    elif normalized_provider == "openai":
        api_key = _required_env("OPENAI_API_KEY")
        base_url = "https://api.openai.com/v1"
        resolved_model = model or _required_env("OPENAI_MODEL")
    elif normalized_provider == "google":
        api_key = _required_env("GOOGLE_API_KEY")
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        resolved_model = model or _required_env("GOOGLE_MODEL")
    elif normalized_provider == "anthropic":
        api_key = _required_env("ANTHROPIC_API_KEY")
        base_url = "https://api.anthropic.com/v1"
        resolved_model = model or _required_env("ANTHROPIC_MODEL")
    else:
        raise ValueError(f"Unsupported provider override: {provider}")

    return api_key, base_url, resolved_model


def resolve_timeout_seconds(llm: Any) -> float:
    timeout = getattr(llm, "timeout", None)
    if isinstance(timeout, (int, float)) and timeout > 0:
        return float(timeout)
    return 30.0


def resolve_active_llm(
    llm: ChatOpenAI,
    provider: str | None = None,
    model: str | None = None,
) -> ChatOpenAI:
    if provider is None and model is None:
        return llm

    resolved_provider = provider or os.environ.get("LLM_PROVIDER", "")
    if not resolved_provider:
        raise RuntimeError("LLM_PROVIDER is required when using team_04 benchmarking overrides")

    api_key, base_url, resolved_model = resolve_llm_connection(resolved_provider, model)
    model_kwargs = getattr(llm, "model_kwargs", {})
    if not isinstance(model_kwargs, dict):
        model_kwargs = {}

    return create_chat_llm(
        api_key=api_key,
        base_url=base_url,
        llm_model=resolved_model,
        timeout_seconds=resolve_timeout_seconds(llm),
        model_kwargs=model_kwargs,
    )