"""
nodes/preprocess.py — PREPROCESS node for the Comfort Copilot state graph.

Pure Python — no LLM, no MCP calls. Runs first on every user message.

Responsibilities:
  1. Detect the top-level path (coarse routing only):
       "comfort"  → a layout ID (201 / 202 / 203) was mentioned
       "inspire"  → an image was attached
       "chitchat" → everything else
  2. Detect which persona the user mentioned, if any.
  3. Flag if a persona is still missing (so ask_persona node knows to run).

Depth within the comfort path (analyze / detect / full) is decided later
by route_intent.py, which uses the LLM.
"""

from __future__ import annotations
import re
from personas import detect_persona_in_text


# Layout IDs that are valid for this project
_LAYOUT_IDS: tuple[str, ...] = ("201", "202", "203")

# Words that strongly indicate an inspire / atmosphere request.
# Include inflected forms ("inspired", "inspiring") -- absent forms fall to chitchat.
_INSPIRE_KEYWORDS: tuple[str, ...] = (
    "inspire", "inspired", "inspiring", "inspiration",
    "atmosphere", "ambiance", "ambience",
    "mood", "aesthetic", "vibe",
    "feel like", "generate image", "create image", "imagine",
)

# Action keywords that mean "do comfort work on the already-loaded layout".
# Used only when a layout is already in session — prevents chitchat false
# positives on follow-up turns like "now detect the conflicts".
_COMFORT_CONTEXT_KEYWORDS: tuple[str, ...] = (
    "detect", "conflict", "conflicts",
    "analyse", "analyze", "analysis",
    "improve", "suggest", "suggestions", "recommendation",
    "fix", "enhance", "upgrade",
    "what's wrong", "what is wrong",
    "issues", "problems", "assess",
)

# Words that mean the user just wants to see what rooms exist -- no analysis
_OVERVIEW_KEYWORDS: tuple[str, ...] = (
    "what rooms", "list rooms", "list the rooms", "show rooms",
    "what's in", "what is in", "overview", "what do we have",
    "show me the layout", "describe the layout", "rooms in layout",
    "whats in layout", "what's in layout",
)


# ---------------------------------------------------------------------------
# Coarse intent detection
# ---------------------------------------------------------------------------

def detect_coarse_intent(
    prompt: str,
    has_image: bool = False,
    has_loaded_layout: bool = False,
) -> str:
    """
    Classify the prompt into one of three top-level paths.

    Returns one of: "comfort", "inspire", "chitchat"

    Priority:
      1. Image attached            → inspire
      2. Layout ID in prompt       → comfort (new layout)
      3. Layout loaded + action kw → comfort (use existing layout)
      4. Inspire keywords          → inspire
      5. Everything else           → chitchat
    """
    if has_image:
        return "inspire"

    lower = prompt.lower()

    # Overview intent: user wants to see what rooms exist -- no analysis
    if (any(lid in lower for lid in _LAYOUT_IDS) or has_loaded_layout):
        if any(kw in lower for kw in _OVERVIEW_KEYWORDS):
            return "overview"

    # Explicit layout ID -> always comfort (may switch to a new layout)
    if any(lid in lower for lid in _LAYOUT_IDS):
        return "comfort"

    # Layout already loaded + comfort action keyword -> stay on comfort path
    # (covers follow-up turns: "now detect the conflicts", "what should I fix?")
    if has_loaded_layout and any(kw in lower for kw in _COMFORT_CONTEXT_KEYWORDS):
        return "comfort"

    if any(kw in lower for kw in _INSPIRE_KEYWORDS):
        return "inspire"

    return "chitchat"


# ---------------------------------------------------------------------------
# Preprocess node — wired into StateGraph in graph.py
# ---------------------------------------------------------------------------

def preprocess_node(state: dict) -> dict:
    """
    Read the raw user prompt, run coarse routing, detect persona.

    Writes to state:
      intent            (str)        — "comfort" | "overview" | "inspire" | "chitchat"
      layout_id         (str | None) — e.g. "201" if found in prompt
      persona_detected  (str | None) — persona name, or None
      needs_persona_ask (bool)       — True when comfort but no persona found
    """
    raw_prompt: str = state.get("raw_prompt", "")
    has_image: bool = state.get("has_image", False)

    has_loaded_layout: bool = bool(state.get("layout_json_string"))
    print(f"\n[preprocess] Prompt : {raw_prompt[:120]}")

    # ── 1. Coarse intent ─────────────────────────────────────────────────
    intent = detect_coarse_intent(raw_prompt, has_image, has_loaded_layout)
    print(f"[preprocess] Intent : {intent}")

    # ── 2. Extract layout ID (if present) ────────────────────────────────
    # Both comfort and overview need the layout ID extracted the same way.
    layout_id: str | None = None
    if intent in ("comfort", "overview"):
        lower = raw_prompt.lower()
        for lid in _LAYOUT_IDS:
            if lid in lower:
                layout_id = lid
                break
        # No new ID in prompt -- keep the session's layout_id so load_layout
        # can correctly match and skip reloading.
        if layout_id is None:
            layout_id = state.get("layout_id")
    print(f"[preprocess] Layout : {layout_id or 'none'}")

    # ── 3. Detect persona — only relevant on the comfort path ────────────
    # On chitchat / inspire / overview, skip persona detection entirely.
    # On comfort: prompt keyword WINS over session -- so "for a child" always
    # overrides a previously loaded persona.
    if intent == "comfort":
        prompt_persona  = detect_persona_in_text(raw_prompt)
        session_persona = state.get("persona_detected")
        persona: str | None = prompt_persona or session_persona
    else:
        persona = None
    print(f"[preprocess] Persona: {persona or 'not found'}")

    # ── 4. Flag missing persona for comfort requests ──────────────────────
    needs_persona_ask = (intent == "comfort") and (persona is None)

    return {
        **state,
        "intent":            intent,
        "layout_id":         layout_id,
        "persona_detected":  persona,
        "needs_persona_ask": needs_persona_ask,
    }
