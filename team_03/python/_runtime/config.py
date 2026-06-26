import json
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
    mcp_config_path: str
    mcp_server_key: str
    mcp_endpoint: str
    request_timeout_seconds: float
    max_iterations: int


def _repo_root() -> Path:
    # team_03/python/_runtime/config.py → parents[3] is AIA26_Studio/ (repo root)
    # .env and mcp.json live at the repo root, not inside team_03/
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


def _load_mcp_server_from_json(config_path: Path) -> tuple[str, str]:
    if not config_path.exists():
        raise ValueError(f"MCP config file not found: {config_path}")

    raw = config_path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"MCP config file is empty: {config_path}")

    parsed = json.loads(raw)

    if "mcpServers" not in parsed:
        raise ValueError("mcp.json missing 'mcpServers' object")

    servers = parsed["mcpServers"]
    if not isinstance(servers, dict) or not servers:
        raise ValueError("mcp.json 'mcpServers' must be a non-empty object")

    server_key = next(iter(servers))
    server_config = servers[server_key]
    if not isinstance(server_config, dict):
        raise ValueError(f"mcp.json server entry must be an object: {server_key}")

    endpoint: str | None = None

    if "url" in server_config:
        url_value = server_config["url"]
        if not isinstance(url_value, str) or not url_value:
            raise ValueError("mcp.json server 'url' must be a non-empty string")
        endpoint = url_value
    elif "args" in server_config:
        args_value = server_config["args"]
        if not isinstance(args_value, list) or not args_value:
            raise ValueError("mcp.json server 'args' must be a non-empty array")
        first_arg = args_value[0]
        if not isinstance(first_arg, str) or not first_arg:
            raise ValueError("mcp.json server args[0] must be a non-empty string endpoint")
        endpoint = first_arg
    else:
        raise ValueError(
            "mcp.json server entry missing supported endpoint field. Expected 'url' or 'args[0]'."
        )

    return server_key, endpoint


def resolve_provider_credentials(provider: str) -> tuple[str, str, str]:
    """Resolve (api_key, base_url, default_model) for a given provider from env.

    Pure env lookup — does NOT call load_dotenv (callers are expected to have the
    env populated, e.g. via load_settings() earlier in the same process). Raises
    ValueError (from _required_env) naming the missing variable when a required key
    is absent, so a runtime provider switch can surface "add GOOGLE_API_KEY" cleanly
    instead of crashing. Used both by load_settings() and by the AGENT_ui provider
    toggle (pipeline_bridge.build_context) to resolve the *active* provider when it
    differs from the .env LLM_PROVIDER.
    """
    provider = provider.strip().lower()

    if provider == "local":
        return "No API Key Required", _required_env("LOCAL_LLM_ENDPOINT"), "local"

    if provider == "cloudflare":
        api_key = _required_env("CF_API_TOKEN")
        base_url = f"https://api.cloudflare.com/client/v4/accounts/{_required_env('CF_ACCOUNT_ID')}/ai/v1"
        return api_key, base_url, _required_env("CF_MODEL")

    if provider == "openai":
        return _required_env("OPENAI_API_KEY"), "https://api.openai.com/v1", _required_env("OPENAI_MODEL")

    if provider == "google":
        return (
            _required_env("GOOGLE_API_KEY"),
            "https://generativelanguage.googleapis.com/v1beta/openai",
            _required_env("GOOGLE_MODEL"),
        )

    if provider == "anthropic":
        return _required_env("ANTHROPIC_API_KEY"), "", _required_env("ANTHROPIC_MODEL")

    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")


def load_settings() -> Settings:
    load_dotenv(dotenv_path=_repo_root() / ".env", override=True)

    mcp_json_path = _repo_root() / "mcp.json"
    mcp_server_key, mcp_endpoint = _load_mcp_server_from_json(mcp_json_path)

    timeout_value = os.environ.get("REQUEST_TIMEOUT_SECONDS", "30").strip()
    max_iterations_value = os.environ.get("MAX_ITERATIONS", "4")

    llm_provider = _required_env("LLM_PROVIDER").strip().lower()
    api_key, base_url, llm_model = resolve_provider_credentials(llm_provider)

    return Settings(
        llm_provider=llm_provider,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        debug_graph=_parse_bool_env("DEBUG_GRAPH", False),
        mcp_config_path=str(mcp_json_path),
        mcp_server_key=mcp_server_key,
        mcp_endpoint=mcp_endpoint,
        request_timeout_seconds=float(timeout_value),
        max_iterations=int(max_iterations_value),
    )
