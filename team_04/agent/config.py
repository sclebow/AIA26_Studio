from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class AgentSettings:
    llm_provider: str
    api_key: str
    base_url: str
    llm_model: str
    decision_llm_provider: str | None
    decision_llm_model: str | None
    report_llm_provider: str | None
    report_llm_model: str | None
    mcp_endpoint: str
    request_timeout_seconds: float
    max_optimization_cycles: int
    output_result_path: Path


def _team_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _load_mcp_endpoint() -> str:
    repo_mcp_path = _repo_root() / "mcp.json"
    team_mcp_path = _team_root() / "mcp.example.json"
    config_path = repo_mcp_path if repo_mcp_path.exists() else team_mcp_path
    parsed = json.loads(config_path.read_text(encoding="utf-8"))
    servers = parsed.get("mcpServers", {})
    if not isinstance(servers, dict) or not servers:
        raise ValueError("mcp config does not contain any servers")
    first_server = next(iter(servers.values()))
    if not isinstance(first_server, dict):
        raise ValueError("mcp server entry must be an object")
    if isinstance(first_server.get("url"), str) and first_server["url"]:
        return first_server["url"]
    args = first_server.get("args")
    if isinstance(args, list) and args and isinstance(args[0], str) and args[0]:
        return args[0]
    raise ValueError("mcp config must provide either 'url' or 'args[0]'")


def load_settings() -> AgentSettings:
    repo_env = _repo_root() / ".env"
    team_env = _team_root() / ".env"
    env_path = repo_env if repo_env.exists() else team_env
    load_dotenv(dotenv_path=env_path, override=True)

    llm_provider = _required_env("LLM_PROVIDER").strip().lower()
    if llm_provider == "openai":
        api_key = _required_env("OPENAI_API_KEY")
        base_url = "https://api.openai.com/v1"
        llm_model = _required_env("OPENAI_MODEL")
    elif llm_provider == "cloudflare":
        api_key = _required_env("CF_API_TOKEN")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{_required_env('CF_ACCOUNT_ID')}/ai/v1"
        llm_model = _required_env("CF_MODEL")
    elif llm_provider == "google":
        api_key = _required_env("GOOGLE_API_KEY")
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        llm_model = _required_env("GOOGLE_MODEL")
    elif llm_provider == "anthropic":
        api_key = _required_env("ANTHROPIC_API_KEY")
        base_url = "https://api.anthropic.com/v1"
        llm_model = _required_env("ANTHROPIC_MODEL")
    elif llm_provider == "local":
        api_key = "local"
        base_url = _required_env("LOCAL_LLM_ENDPOINT")
        llm_model = os.environ.get("LOCAL_MODEL", "local")
    else:
        raise ValueError(f"Unsupported LLM provider: {llm_provider}")

    output_result_path = _team_root() / "team_04_placement_result.json"

    return AgentSettings(
        llm_provider=llm_provider,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        decision_llm_provider=os.environ.get("TEAM04_DECISION_LLM_PROVIDER") or None,
        decision_llm_model=os.environ.get("TEAM04_DECISION_LLM_MODEL") or None,
        report_llm_provider=os.environ.get("TEAM04_REPORT_LLM_PROVIDER") or None,
        report_llm_model=os.environ.get("TEAM04_REPORT_LLM_MODEL") or None,
        mcp_endpoint=_load_mcp_endpoint(),
        request_timeout_seconds=float(os.environ.get("REQUEST_TIMEOUT_SECONDS", "300")),
        max_optimization_cycles=int(os.environ.get("MAX_OPTIMIZATION_CYCLES", "4")),
        output_result_path=output_result_path,
    )
