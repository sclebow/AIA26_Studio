"""
nodes/memory.py — long-term, per-layout conversational memory.

The memory node feeds the reason node. It runs only at the points where a real
user message enters the graph (the initial prompt and each checkpoint "continue"),
never on internal tool/adjustment loops.

On each run it:
  1. Loads the persistent memory file once (memory/<layout_name>.md) into
     working memory (state["memory_text"]).
  2. Distills the latest user message into durable facts and merges them into
     working memory via call_llm_simple (MEMORY_DISTILL_PROMPT).
  3. Writes working memory back to disk immediately (crash-safe).

reason.py injects state["memory_text"] into the LLM context every turn, so the
agent can recall facts from past and current conversations.

All work is wrapped in try/except so a memory failure never breaks the pipeline
(same defensive pattern as the spatial_graph and visualizer integrations).
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from _runtime.llm import call_llm_simple
from prompts import MEMORY_DISTILL_PROMPT


# ---------------------------------------------------------------------------
# Prefixes used to skip system/assistant-style messages when locating the last
# genuine user message. Mirrors the SYSTEM_PREFIXES filter in graph.py's
# _route_after_checkpoint so injected correction/analysis messages are ignored.
# ---------------------------------------------------------------------------

_SYSTEM_PREFIXES = (
    "tool result:", "scoring complete", "layout score",
    "collision", "visibility", "path analysis",
    "reachability", "analysis complete", "placed ",
    "moved ", "spatial graph", "current layout",
    "space config", "profile config", "active space config",
    "active profile config", "memory (recall", "spatial relationship graph",
    "space config will be determined",
)


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _memory_path(state: dict) -> Path:
    """memory/<layout_name>.md, sibling of the workspace/ directory."""
    workspace = Path(state["workspace_path"])
    layout_name = state.get("layout_name", "default")
    return workspace.parent / "memory" / f"{layout_name}.md"


def load_memory(path: Path) -> str:
    """Read the persistent memory file. Returns "" if it does not exist."""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        print(f"[memory] Could not read {path}: {exc}")
    return ""


def save_memory(path: Path, text: str) -> None:
    """Write working memory back to disk, creating the directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((text or "").strip() + "\n", encoding="utf-8")


def _last_user_message(messages: list) -> str:
    """Return the most recent genuine user message, skipping injected/system text.

    Handles both plain dicts and LangChain message objects (the add_messages
    reducer may convert dicts into message objects).
    """
    for msg in reversed(messages or []):
        role = msg.type if hasattr(msg, "type") else msg.get("role", "")
        if role not in ("human", "user"):
            continue
        content = (msg.content if hasattr(msg, "content")
                   else msg.get("content", "")) or ""
        content = content.strip()
        if not content:
            continue
        if any(content.lower().startswith(p) for p in _SYSTEM_PREFIXES):
            continue
        return content
    return ""


# ---------------------------------------------------------------------------
# Distillation
# ---------------------------------------------------------------------------

def distill_memory(llm: Any, existing: str, user_msg: str) -> str:
    """Merge durable facts from user_msg into existing memory. Returns Markdown.

    Falls back to the existing memory unchanged on any failure or empty input.
    """
    if not user_msg.strip():
        return existing
    payload = (
        f"EXISTING MEMORY:\n{existing or '(empty)'}\n\n"
        f"LATEST USER MESSAGE:\n{user_msg}"
    )
    result = call_llm_simple(llm, MEMORY_DISTILL_PROMPT, payload)
    if isinstance(result, dict):
        updated = result.get("memory")
        if isinstance(updated, str) and updated.strip():
            return updated.strip()
    return existing


# ---------------------------------------------------------------------------
# Node factory
# ---------------------------------------------------------------------------

def build_memory_node(llm: Any):
    """Return a memory node ready to be added to the LangGraph StateGraph."""

    def memory_node(state: dict) -> dict:
        try:
            path = _memory_path(state)

            # Load the persistent file once per session, then keep working
            # memory in state. _keep_last treats None as "no update", so we
            # always return a concrete string.
            memory_text = state.get("memory_text")
            if not state.get("memory_loaded"):
                memory_text = load_memory(path)
                if memory_text:
                    print(f"[memory] Loaded {len(memory_text)} chars from {path.name}")
                else:
                    print(f"[memory] No prior memory for this layout — starting fresh")

            # Distill the latest user message into durable facts.
            user_msg = _last_user_message(state.get("messages"))
            if user_msg:
                before = memory_text or ""
                memory_text = distill_memory(llm, before, user_msg)
                if memory_text != before:
                    save_memory(path, memory_text)
                    print(f"[memory] Updated memory ({len(memory_text)} chars) -> {path.name}")

            return {
                "memory_text": memory_text or "",
                "memory_loaded": True,
            }
        except Exception as exc:
            print(f"[memory] Warning: {exc}")
            # Never break the pipeline — mark loaded so we don't retry the
            # file read every turn, and preserve whatever we had.
            return {"memory_loaded": True}

    return memory_node
