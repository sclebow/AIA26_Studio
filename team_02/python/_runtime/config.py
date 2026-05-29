import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    api_key: str
    base_url: str
    llm_model: str
    debug_graph: bool
    request_timeout_seconds: float
    max_iterations: int


def _repo_root() -> Path:
    # _runtime/config.py is three levels deep: python/_runtime/config.py → repo root is parents[3]
    return Path(__file__).resolve().parents[3]


def _required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ValueError(f"Missing or empty required environment variable: {name}")
    return value


def _parse_bool_env(name: str, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"Invalid value for {name}: {raw_value}. Allowed values are 'true' or 'false'.")


def load_settings() -> Settings:
    # Comfort tools run in-process now (see _runtime/local_tool_client.py), so the
    # old Grasshopper MCP config (mcp.json) is no longer read here.
    load_dotenv(dotenv_path=_repo_root() / ".env", override=False)

    timeout_value = os.environ.get("REQUEST_TIMEOUT_SECONDS", "30")
    max_iterations_value = os.environ.get("MAX_ITERATIONS", "4")

    llm_provider = _required_env("LLM_PROVIDER").strip().lower()

    if llm_provider == "local":
        api_key = "No API Key Required"
        base_url = _required_env("LOCAL_LLM_ENDPOINT")
        llm_model = "local"
    elif llm_provider == "cloudflare":
        api_key = _required_env("CF_API_TOKEN")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{_required_env('CF_ACCOUNT_ID')}/ai/v1"
        llm_model = _required_env("CF_MODEL")
    elif llm_provider == "openai":
        api_key = _required_env("OPENAI_API_KEY")
        base_url = "https://api.openai.com/v1"
        llm_model = _required_env("OPENAI_MODEL")
    elif llm_provider == "google":
        api_key = _required_env("GOOGLE_API_KEY")
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
        llm_model = _required_env("GOOGLE_MODEL")
    elif llm_provider == "anthropic":
        api_key = _required_env("ANTHROPIC_API_KEY")
        base_url = "https://api.anthropic.com/v1/"
        llm_model = _required_env("ANTHROPIC_MODEL")
    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {llm_provider}")

    return Settings(
        llm_provider=llm_provider,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        debug_graph=_parse_bool_env("DEBUG_GRAPH", False),
        request_timeout_seconds=float(timeout_value),
        max_iterations=int(max_iterations_value),
    )
