"""
ROUTE_INTENT node — decides analysis depth: analyze / detect / full.
Uses LLM to read intent; falls back to keyword matching on error.
Writes comfort_depth to state.
"""

from __future__ import annotations
from _runtime.llm import call_llm_simple


# ---------------------------------------------------------------------------
# Keyword fallback — mirrors old preprocess.py depth detection
# ---------------------------------------------------------------------------

_FULL_KEYWORDS: tuple[str, ...] = (
    "improve", "suggest", "suggestion", "recommendation",
    "what should i", "what can i", "what to change", "what would you",
    "fix", "make better", "enhance", "upgrade",
    "how to fix", "how to improve", "how can i",
)

_DETECT_KEYWORDS: tuple[str, ...] = (
    "detect", "conflict", "conflicts", "problem", "problems",
    "issue", "issues", "what is wrong", "what's wrong",
    "failing", "fails", "poor", "bad", "below threshold",
)


def _keyword_fallback(prompt: str) -> str:
    lower = prompt.lower()
    if any(kw in lower for kw in _FULL_KEYWORDS):
        return "full"
    if any(kw in lower for kw in _DETECT_KEYWORDS):
        return "detect"
    return "analyze"


# ---------------------------------------------------------------------------
# System prompt for the LLM classifier
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a routing assistant for an architectural comfort analysis tool.

Given the user's request, decide which depth of analysis is needed:

  analyze  — The user wants comfort scores for the rooms (thermal, visual,
             acoustic, spatial, olfactory, tactile). Use this when they ask
             to "analyse", "check", "score", or "assess" a layout.

  detect   — The user wants to know what is wrong or where conflicts exist.
             Use this when they ask about "problems", "conflicts", "issues",
             "what fails", or "what is poor".

  full     — The user wants a full report with improvement suggestions.
             Use this when they ask to "improve", "fix", "suggest", or
             "what should I change".

Reply with ONLY one word: analyze, detect, or full.
No explanation. No punctuation. Just the single word.
"""


# ---------------------------------------------------------------------------
# Route intent node
# ---------------------------------------------------------------------------

def build_route_intent_node(llm):
    """Return the route_intent node function, capturing the LLM instance."""

    def route_intent_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")

        # ── LLM classification ────────────────────────────────────────────
        depth: str = "analyze"  # safe default
        try:
            response = call_llm_simple(llm, _SYSTEM_PROMPT, raw_prompt)
            # Clean up in case the LLM adds punctuation or wraps in a sentence
            candidate = response.strip().lower().split()[0].rstrip(".,;:")
            if candidate in ("analyze", "detect", "full"):
                depth = candidate
                print(f"[route_intent] LLM depth  : {depth}")
            else:
                depth = _keyword_fallback(raw_prompt)
                print(f"[route_intent] LLM returned '{candidate}' — keyword fallback: {depth}")
        except Exception as exc:
            depth = _keyword_fallback(raw_prompt)
            print(f"[route_intent] LLM error ({exc}) — keyword fallback: {depth}")

        return {
            **state,
            "comfort_depth": depth,
        }

    return route_intent_node
