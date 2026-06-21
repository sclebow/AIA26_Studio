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
from _runtime.session import create_session, save_session
from _runtime.bootstrap import Context


# ---------------------------------------------------------------------------
# Runtime model state — switched via WebSocket model_switch message
# ---------------------------------------------------------------------------

ANTHROPIC_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

_active_model: Optional[str] = None  # None = use .env default


def set_active_model(model_key: str) -> str:
    """Set the active Anthropic model. model_key is 'haiku' or 'sonnet'.
    Returns the full model string that was set."""
    global _active_model
    full = ANTHROPIC_MODELS.get(model_key.lower())
    if not full:
        raise ValueError(f"Unknown model key '{model_key}'. Use 'haiku' or 'sonnet'.")
    _active_model = full
    print(f"[model] Active model switched → {full}")
    return full


def get_active_model() -> Optional[str]:
    """Return the currently active model string, or None to use .env default."""
    return _active_model


# ---------------------------------------------------------------------------
# Pinned version — when the user selects a revision in the Version History panel,
# the chat must run on THAT layout, not the base. build_context normally always
# starts a fresh session from the base file; a pin overrides the working layout.
# ---------------------------------------------------------------------------

_pinned_layout: Optional[dict] = None
_pinned_for: Optional[str] = None  # base layout name the pin belongs to


def set_pinned_layout(layout_name: Optional[str], data: Optional[dict]) -> None:
    """Pin a specific version as the working layout for `layout_name` (or clear
    with data=None). The next chat run (build_context) uses it instead of the
    base file. Selecting a different base layout should clear this."""
    global _pinned_layout, _pinned_for
    _pinned_layout = data
    _pinned_for = layout_name if data is not None else None


def get_pinned_layout(layout_name: str) -> Optional[dict]:
    """Return the pinned version for `layout_name`, or None when no pin applies."""
    if _pinned_layout is not None and _pinned_for == layout_name:
        return _pinned_layout
    return None


# ---------------------------------------------------------------------------
# Context builder — bootstrap() minus argparse and the interactive resume prompt
# ---------------------------------------------------------------------------

def _team_dir() -> Path:
    # …/AIA26_Studio/team_03/AGENT_ui/backend/pipeline_bridge.py → team_03/
    return Path(__file__).resolve().parents[2]


def _inject_user_profile(team_dir: Path, layout_name: str) -> None:
    """Merge the global onboarding profile (memory/user_profile.md) into this
    layout's memory file under the protected "## User Rules" block, so reason.py
    injects it into the LLM context every turn. Idempotent (replaces stale profile
    rules first). Never raises — a profile failure must not break chat startup."""
    try:
        profile_path = team_dir / "memory" / "user_profile.md"
        if not profile_path.exists():
            return

        # Reuse the pipeline's own rule helpers (team_03/python is on sys.path).
        from nodes.memory import load_memory, save_memory, add_user_rule, remove_user_rule

        # Parse the profile bullets into prefixed rule lines.
        section: Optional[str] = None
        rules: list[str] = []
        for raw in profile_path.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            low = s.lower()
            if low.startswith("## user profile"):
                section = "User profile"; continue
            if low.startswith("## space profile"):
                section = "Space profile"; continue
            if s.startswith("## "):
                section = None; continue
            if section and s.startswith("- "):
                item = s[2:].strip()
                # Skip empty/placeholder bullets.
                if item and item not in ("(skipped)",) and not item.endswith(": —"):
                    rules.append(f"{section} — {item}")

        mem_path = team_dir / "memory" / f"{layout_name}.md"
        text = load_memory(mem_path)
        # Drop any prior profile rules so re-onboarding doesn't accumulate stale lines.
        text, _ = remove_user_rule(text, "User profile —")
        text, _ = remove_user_rule(text, "Space profile —")
        for r in rules:
            text = add_user_rule(text, r)
        save_memory(mem_path, text)
        if rules:
            print(f"[profile] Injected {len(rules)} profile rule(s) into {mem_path.name}")
    except Exception as exc:
        print(f"[profile] Could not inject user profile: {exc}")


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

    # If the user picked a revision in the Version History panel, run the chat on
    # THAT layout instead of the base one (overwrite the live workspace file so
    # reload / Grasshopper / observer all see the selected version too).
    pinned = get_pinned_layout(name)
    if pinned is not None:
        layout_data = pinned
        save_session(pinned, workspace_path)
        _say(f"Using the selected revision of '{name}'.")

    # Merge the onboarding profile into this layout's memory BEFORE the MCP probe,
    # so it's recorded even if Rhino/Swiftlet is down.
    _inject_user_profile(team_dir, name)

    # Fail fast if Swiftlet/Rhino is unreachable (avoids a silent long hang).
    _say(f"Connecting to Grasshopper (MCP) at {settings.mcp_endpoint}…")
    _probe_mcp(settings.mcp_endpoint)

    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    _say(f"MCP connected — {len(tools)} tool(s) available.")

    # Runtime model — can be switched via WebSocket model_switch message.
    # Falls back to .env ANTHROPIC_MODEL if no override has been set.
    model = get_active_model() or settings.llm_model
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
    _PREV_RE = re.compile(r"Previous:\s*([\d.]+)\s*/\s*100")
    _SUG_RE = re.compile(r"^\s*(s\d)\s*=\s*(.+?)\s*$")
    _RULE_RE = re.compile(r"^\s*\d+\.\s+(.*\S)\s*$")
    _AGENT_SEP_RE = re.compile(r"^[─\-]{10,}$")  # ──── or ----
    # "  collision        85.2/100  (weight 0.40, +34.10) ..."
    _BREAKDOWN_RE = re.compile(r"^\s*([A-Za-z_]+)\s+([\d.]+)\s*/\s*100\s+\(weight\s+([\d.]+)")
    # "  - BLOCKED: desk overlaps wall" / "  - some free-text violation"
    _VIOL_RE = re.compile(r"^\s*-\s*(.+\S)\s*$")
    # "  ADDED  desk   at (1.0, 2.0)  [workshop]" / "  MOVED  rack  (..) -> (..) [..]"
    _CHANGE_RE = re.compile(r"^\s*(ADDED|MOVED)\s+(.+\S)\s*$")
    # "  ADDED: door-3" / "  REMOVED: door-1" / "  MODIFIED: door-2"
    _DOOR_RE = re.compile(r"^\s*(ADDED|REMOVED|MODIFIED):\s*(.+\S)\s*$")

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._score: Optional[float] = None
        self._prev_score: Optional[float] = None
        self._grade: Optional[str] = None
        self._suggestions: list[dict] = []
        self._rules: list[str] = []
        self._breakdown: dict[str, dict] = {}   # tool -> {score, weight}
        self._violations: list[str] = []
        self._changes: list[dict] = []          # {action: ADDED|MOVED, text}
        self._door_changes: list[str] = []
        self._actions = {"approve": True, "end": True, "yes": False}
        self._agent_lines: list[str] = []
        # 'suggestions' | 'rules' | 'agent' | 'breakdown' | 'violations' | 'changes' | 'doors'
        self._mode: Optional[str] = None
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

        # Previous score (printed right under LAYOUT SCORE when a prior exists),
        # used by the UI to show the delta. Capture once.
        if self._prev_score is None:
            pm = self._PREV_RE.search(line)
            if pm:
                try:
                    self._prev_score = float(pm.group(1))
                except ValueError:
                    self._prev_score = None
                return

        # Section headers
        if stripped.startswith("Score breakdown:"):
            self._mode = "breakdown"
            return
        if stripped.startswith("Collision violations"):
            self._mode = "violations"
            return
        if stripped.startswith("Furniture changes made"):
            self._mode = "changes"
            return
        if stripped.startswith("Door changes detected"):
            self._mode = "doors"
            return
        # These end any open block but carry no list items we capture.
        if stripped.startswith("Viewport:") or stripped.startswith("Placed in ") or \
           stripped.startswith("Structural integrity fixes"):
            self._mode = None
            return
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

        if self._mode == "breakdown":
            bm = self._BREAKDOWN_RE.match(line)
            if bm:
                try:
                    self._breakdown[bm.group(1).lower()] = {
                        "score": float(bm.group(2)),
                        "weight": float(bm.group(3)),
                    }
                except ValueError:
                    pass
                return
            if stripped == "":
                return
            # any other non-blank line ends the breakdown section
            self._mode = None

        if self._mode == "violations":
            vm = self._VIOL_RE.match(line)
            if vm:
                self._violations.append(vm.group(1))
                return
            if stripped == "":
                return
            self._mode = None  # non-matching, non-blank line ends the block

        if self._mode == "changes":
            cm = self._CHANGE_RE.match(line)
            if cm:
                self._changes.append({"action": cm.group(1), "text": cm.group(2)})
                return
            if stripped == "":
                return
            self._mode = None

        if self._mode == "doors":
            dm = self._DOOR_RE.match(line)
            if dm:
                self._door_changes.append(f"{dm.group(1)}: {dm.group(2)}")
                return
            if stripped == "":
                return
            self._mode = None

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
            "prevScore": self._prev_score,
            "grade": self._grade,
            "suggestions": list(self._suggestions),
            "rules": list(self._rules),
            "breakdown": dict(self._breakdown),
            "violations": list(self._violations),
            "changes": list(self._changes),
            "doorChanges": list(self._door_changes),
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
