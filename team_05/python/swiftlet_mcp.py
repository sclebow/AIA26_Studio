"""
Swiftlet MCP Tools Integration
Communicates with the running Grasshopper/Rhino Swiftlet server via JSON-RPC.
Endpoint: http://localhost:3001/mcp/
"""
import json
import sys
import os
from pathlib import Path

# Allow importing from _runtime when running from the python/ directory
sys.path.insert(0, os.path.dirname(__file__))

try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

def _load_mcp_endpoint(default: str = "http://localhost:3001/mcp/") -> str:
    """Load MCP endpoint from repo-root mcp.json, supporting both known schemas."""
    try:
        repo_root = Path(__file__).resolve().parents[2]
        cfg_path = repo_root / "mcp.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

        # New schema: {"servers": {"Name": {"url": "..."}}}
        for srv in cfg.get("servers", {}).values():
            if isinstance(srv, dict):
                url = srv.get("url")
                if isinstance(url, str) and url.strip():
                    return url.strip()

        # Legacy schema: {"mcpServers": {"Name": {"url": "..."|"args": ["..."]}}}
        for srv in cfg.get("mcpServers", {}).values():
            if not isinstance(srv, dict):
                continue
            url = srv.get("url")
            if isinstance(url, str) and url.strip():
                return url.strip()
            args = srv.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], str) and args[0].strip():
                return args[0].strip()
    except Exception:
        pass
    return default


MCP_ENDPOINT = _load_mcp_endpoint()
TIMEOUT_S = 15.0

# GH tools that accept a layout JSON and return an updated layout
_AREA_TOOL   = "Area-Based Cost Calculator Tool"
_VOLUME_TOOL = "Volume-Based Cost Calculator Tool"


# ── low-level JSON-RPC ────────────────────────────────────────────────────────

def _rpc(method: str, params: dict | None = None) -> dict:
    if not _HTTPX_AVAILABLE:
        raise RuntimeError("httpx not installed — run: pip install httpx")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        payload["params"] = params
    r = httpx.post(MCP_ENDPOINT, json=payload, timeout=TIMEOUT_S)
    r.raise_for_status()
    body = r.json()
    if "error" in body:
        raise RuntimeError(f"MCP error [{method}]: {body['error']}")
    return body.get("result", {})


def _call_tool(tool_name: str, arguments: dict) -> str:
    result = _rpc("tools/call", {"name": tool_name, "arguments": arguments})
    content = result.get("content", [])
    if isinstance(content, list):
        return "\n".join(
            item["text"] for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content)


# ── public helpers ────────────────────────────────────────────────────────────

def check_connection() -> tuple[bool, str]:
    """
    Ping the Swiftlet MCP server.
    Returns (True, tool_names_str) on success, (False, error_msg) on failure.
    """
    try:
        _rpc("initialize", {"clientInfo": {"name": "aia26-check", "version": "0"}, "capabilities": {}})
        result = _rpc("tools/list")
        tools = [t["name"] for t in result.get("tools", [])]
        return True, ", ".join(tools)
    except Exception as e:
        return False, str(e)


def push_layout_to_grasshopper(layout: dict, room_name: str | None = None) -> dict:
    """
    Send the updated layout JSON to Grasshopper and return GH's response.

    Returns:
        {
            ok              : bool,
            tool            : str | None,
            gh_layout       : dict | None,   # GH's authoritative layout (with its colors)
            response_preview: str | None,
            error           : str | None,
        }
    """
    layout_str = json.dumps(layout)
    payload: dict = {
        "layout_json":   layout_str,
        "layout_schema": layout_str,
    }
    if room_name:
        payload["room_name"]  = room_name
        payload["eoom_name"]  = room_name  # alias used by some GH clusters

    last_err = "no tools tried"
    for tool in (_AREA_TOOL, _VOLUME_TOOL):
        try:
            response = _call_tool(tool, payload)
            preview = response[:120].replace("\n", " ")

            # Try to parse GH's returned layout JSON
            gh_layout = None
            try:
                parsed = json.loads(response.strip())
                if isinstance(parsed, dict) and isinstance(parsed.get("rooms"), list):
                    gh_layout = parsed
            except (json.JSONDecodeError, AttributeError):
                pass

            return {
                "ok": True,
                "tool": tool,
                "gh_layout": gh_layout,
                "response_preview": preview,
                "error": None,
            }
        except Exception as e:
            last_err = str(e)

    return {"ok": False, "tool": None, "gh_layout": None, "response_preview": None, "error": last_err}


# ── entry point (called from langgraph_agent) ─────────────────────────────────

def process_with_swiftlet(context: dict) -> str:
    """Forward the request to the live Swiftlet/Grasshopper MCP server."""
    user_input:  str  = context.get("user_input", "")
    layout_json: str  = context.get("layout_json", "")

    if not layout_json:
        return (
            "No layout loaded. Please upload a layout JSON so I can forward "
            "your request to Grasshopper."
        )

    # Route to the Area-Based tool (most requests involve area costs)
    try:
        layout = json.loads(layout_json)
        result = push_layout_to_grasshopper(layout)
        if result["ok"]:
            return (
                f"Sent to Grasshopper via **{result['tool']}**.\n"
                f"Response: {result['response_preview']}"
            )
        else:
            return (
                f"Grasshopper call failed: {result['error']}\n"
                "Make sure Rhino is open with the team_05 definition running."
            )
    except Exception as e:
        return f"Swiftlet MCP error: {e}"
