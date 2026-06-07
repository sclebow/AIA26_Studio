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


def _load_mcp_server_from_json(config_path: Path) -> tuple[str, str]:
    if not config_path.exists():
        raise ValueError(f"MCP config file not found: {config_path}")

    raw = config_path.read_text(encoding="utf-8")
    if not raw.strip():
        raise ValueError(f"MCP config file is empty: {config_path}")

    parsed = json.loads(raw)

    if "mcpServers" in parsed:
        servers = parsed["mcpServers"]
    elif "servers" in parsed:
        servers = parsed["servers"]
    else:
        raise ValueError("mcp.json missing 'mcpServers' or 'servers' object")

    if not isinstance(servers, dict) or not servers:
        raise ValueError("mcp.json servers object must be a non-empty object")

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
        raise ValueError("mcp.json server entry missing supported endpoint field. Expected 'url' or 'args[0]'.")

    return server_key, endpoint


def load_settings() -> Settings:
    load_dotenv(dotenv_path=_repo_root() / ".env", override=True)

    mcp_json_path = _repo_root() / "mcp.json"
    mcp_server_key, mcp_endpoint = _load_mcp_server_from_json(mcp_json_path)

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
        base_url = None
        llm_model = _required_env("ANTHROPIC_MODEL")

    else:
        raise ValueError(f"Unsupported LLM_PROVIDER: {llm_provider}")

    print(f"[settings] provider={llm_provider} model={llm_model} base_url={base_url} key={api_key[:12]}...")

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
