"""
Bridge between the AGENT_ui web backend and the real LangGraph pipeline in
team_03/python/.

The terminal agent (main.py) runs `app.invoke()` synchronously and blocks at the
`user_checkpoint` node on `input("Your decision: ")`, printing a menu (agent
message, score, viewport toggles, suggestions, memory rules, actions) to stdout.

This module lets the web backend run that EXACT pipeline by:
  - build_context(layout_name): construct the pipeline Context without bootstrap's
    argparse / interactive resume prompt.
  - StdoutTee: capture everything the pipeline prints, strip ANSI, forward line by
    line to a callback (so the browser sees "the terminal").
  - CheckpointParser: turn the known checkpoint menu lines into a structured
    payload (agent message, score, suggestions, rules, actions) for the UI's
    right-side options panel.

server.py inserts team_03/python on sys.path, so the pipeline imports resolve.
"""
from __future__ import annotations

import re
import json
import socket
from urllib.parse import urlparse
from pathlib import Path
from typing import Any, Callable, Optional

# Pipeline imports (team_03/python is on sys.path via server.py)
from _runtime.config import load_settings
from _runtime.mcp_client import McpClient
from _runtime.llm import create_chat_llm, get_llm_response_format
from _runtime.session import create_session
from _runtime.bootstrap import Context


# ---------------------------------------------------------------------------
# Context builder — bootstrap() minus argparse and the interactive resume prompt
# ---------------------------------------------------------------------------

def _team_dir() -> Path:
    # …/AIA26_Studio/team_03/AGENT_ui/backend/pipeline_bridge.py → team_03/
    return Path(__file__).resolve().parents[2]


def _probe_mcp(endpoint: str, timeout: float = 3.0) -> None:
    """Fast TCP reachability check for the MCP/Swiftlet endpoint. Raises a clear
    ConnectionError if the host:port is not accepting connections, so a missing
    Rhino/Swiftlet fails in seconds instead of hanging on the long HTTP timeout."""
    parsed = urlparse(endpoint)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        raise ConnectionError(
            f"Cannot reach the MCP server (Swiftlet) at {host}:{port} — "
            f"is Rhino 8 + Swiftlet running? ({exc})"
        ) from exc


def build_context(layout_name: str, progress: Optional[Callable[[str], None]] = None) -> Context:
    """Construct a pipeline Context for the given layout, non-interactively.

    Mirrors _runtime/bootstrap.bootstrap() but: takes the layout name as an
    argument (no argparse), always starts a FRESH session from the base layout
    (no "resume?" stdin prompt), and probes the MCP endpoint first so a down
    Swiftlet fails fast. `progress(msg)` (optional) reports setup steps.
    """
    def _say(m: str) -> None:
        if progress:
            try:
                progress(m)
            except Exception:
                pass

    settings = load_settings()
    team_dir = _team_dir()

    name = layout_name.replace(".json", "") if layout_name else ""
    if not name:
        raise ValueError("No layout selected. Load a layout before chatting.")

    matches = list((team_dir / "layout").rglob(f"{name}.json"))
    if not matches:
        raise FileNotFoundError(f"Layout '{name}.json' not found under team_03/layout/")
    resolved_layout = matches[0]

    workspace_path = team_dir / "workspace"
    output_path = team_dir / "output"

    # Always start fresh from the base layout (base file is never modified).
    layout_data = create_session(resolved_layout, workspace_path)
    _say(f"Loaded layout '{name}'.")

    # Fail fast if Swiftlet/Rhino is unreachable (avoids a silent long hang).
    _say(f"Connecting to Grasshopper (MCP) at {settings.mcp_endpoint}…")
    _probe_mcp(settings.mcp_endpoint)

    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    _say(f"MCP connected — {len(tools)} tool(s) available.")

    # Cost control: force the cheapest Anthropic model (Haiku) regardless of what
    # ANTHROPIC_MODEL is set to in .env, so the UI agent never runs a pricier
    # Claude (Opus/Sonnet) by accident. Other providers keep their configured
    # model (their defaults — gpt-5-nano, gemini-flash-lite — are already cheap).
    HAIKU = "claude-haiku-4-5"
    model = settings.llm_model
    if settings.llm_provider == "anthropic" and model != HAIKU:
        model = HAIKU
        _say(f"Cost control: overriding Anthropic model → {HAIKU}.")

    _say(f"Initializing LLM ({model})…")
    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=model,
        timeout_seconds=settings.request_timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    )
    _say("LLM ready — starting the agent…")

    knowledge_dir = team_dir / "python" / "knowledge"

    return Context(
        llm=llm,
        mcp_client=mcp_client,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        workspace_path=workspace_path,
        output_path=output_path,
        layout_name=name,
        knowledge_dir=knowledge_dir,
    )


# ---------------------------------------------------------------------------
# stdout capture
# ---------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


class StdoutTee:
    """A writable stream that forwards to the original stdout AND emits each
    completed line (ANSI-stripped) to a callback. Used with
    contextlib.redirect_stdout around the pipeline run."""

    def __init__(self, original: Any, on_line: Callable[[str], None]) -> None:
        self._original = original
        self._on_line = on_line
        self._buf = ""

    def write(self, s: str) -> int:
        try:
            self._original.write(s)
        except Exception:
            pass
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            try:
                self._on_line(strip_ansi(line))
            except Exception:
                pass
        return len(s)

    def flush(self) -> None:
        try:
            self._original.flush()
        except Exception:
            pass

    # `input()` writes its prompt via sys.stdout in some setups; the prompt text
    # ("Your decision: ") arrives here with no trailing newline, so also expose
    # the pending buffer so the parser can detect the prompt.
    def pending(self) -> str:
        return self._buf


# ---------------------------------------------------------------------------
# Checkpoint menu parser
# ---------------------------------------------------------------------------

class CheckpointParser:
    """Consumes ANSI-stripped pipeline lines and reconstructs the structured
    checkpoint payload that checkpoint.py prints. Call feed(line) for every
    line; when a full checkpoint menu has been seen and the "Your decision:"
    prompt appears, take_checkpoint() returns the payload (or None)."""

    _SCORE_RE = re.compile(r"LAYOUT SCORE:\s*([\d.]+)\s*/\s*100\s*Grade:\s*(\S+)")
    _SUG_RE = re.compile(r"^\s*(s\d)\s*=\s*(.+?)\s*$")
    _RULE_RE = re.compile(r"^\s*\d+\.\s+(.*\S)\s*$")
    _AGENT_SEP_RE = re.compile(r"^[─\-]{10,}$")  # ──── or ----

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._score: Optional[float] = None
        self._grade: Optional[str] = None
        self._suggestions: list[dict] = []
        self._rules: list[str] = []
        self._actions = {"approve": True, "end": True, "yes": False}
        self._agent_lines: list[str] = []
        self._mode: Optional[str] = None  # 'suggestions' | 'rules' | 'agent'
        self._ready = False

    def feed(self, line: str) -> None:
        stripped = line.strip()

        m = self._SCORE_RE.search(line)
        if m:
            try:
                self._score = float(m.group(1))
            except ValueError:
                self._score = None
            self._grade = m.group(2)
            return

        # Section headers
        if stripped.startswith("Suggestions:"):
            self._mode = "suggestions"
            return
        if stripped.startswith("Memory") and "user rules" in stripped:
            self._mode = "rules"
            return
        if stripped.startswith("Agent:"):
            self._mode = "agent"
            self._agent_lines = []
            return
        if stripped.startswith("Actions:") or stripped.startswith("Zone '") or \
           stripped.startswith("All zones") or "complete." in stripped:
            self._mode = None
            if "'yes'" in stripped or "proceed to next zone" in stripped:
                self._actions["yes"] = True
            return

        # Agent narrative block ends on a separator line
        if self._mode == "agent":
            if self._AGENT_SEP_RE.match(stripped):
                self._mode = None
                return
            self._agent_lines.append(line.rstrip())
            return

        if self._mode == "suggestions":
            sm = self._SUG_RE.match(line)
            if sm:
                self._suggestions.append({"key": sm.group(1), "label": sm.group(2)})
                return
            if stripped == "":
                return

        if self._mode == "rules":
            rm = self._RULE_RE.match(line)
            if rm:
                self._rules.append(rm.group(1))
                return
            if stripped == "":
                return

        # Detect 'yes' availability from the actions hints
        if "proceed to next zone" in stripped:
            self._actions["yes"] = True

    def prompt_seen(self, pending: str) -> bool:
        """True once the input() prompt 'Your decision:' has been emitted."""
        return "Your decision:" in pending or "Resume existing session" in pending

    def take_checkpoint(self) -> dict:
        """Return the structured payload and reset for the next checkpoint."""
        agent_msg = "\n".join(self._agent_lines).strip()
        payload = {
            "type": "agent_checkpoint",
            "agentMessage": agent_msg,
            "score": self._score,
            "grade": self._grade,
            "suggestions": list(self._suggestions),
            "rules": list(self._rules),
            "actions": dict(self._actions),
        }
        self.reset()
        return payload


def read_session_layout(workspace_path: Path) -> Optional[dict]:
    """Read the live workspace layout (latest placements) for a state_update."""
    try:
        f = workspace_path / "session_active.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None
