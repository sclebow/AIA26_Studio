"""TerraPilot prompt-understanding orchestrator — the single entry point that
runs the 3-layer pipeline and returns a structured understanding the route can act
on. Behaves like an architectural AI assistant: understands MEANING, not words.

    understand(prompt, ctx) -> {
        layer:        "direct" | "intent" | "unrecognized",
        is_command:   bool,                  # Layer 1 hit
        direct_op:    {op, transform, text}|None,
        intent:       "<canonical id>"|None, # Layer 2
        intent_label: str,
        confidence:   float,
        intent_source:"llm"|"keyword"|None,
        matched:      bool,                  # real intent vs gibberish (halluc. guard)
        candidates:   [ {op_phrase,label,direction}, ... ],  # Layer 3, best-first
        reason:       str,                   # why / what was understood
    }

Flow:
  1. DIRECT COMMAND LAYER — if the prompt is an explicit command, return its op and
     stop (no LLM).
  2. INTENT CLASSIFICATION — otherwise classify into one of 12 canonical intents
     (LLM-first, keyword fallback).
  3. REASON NODE — produce the ordered candidate operations for that intent given
     the real shape/part/site/context, so the caller applies the first VALID one.

The route applies the result through the EXISTING validated geometry backend; this
module never touches geometry itself.
"""
from __future__ import annotations

from typing import Any

from . import direct_command, intent_classifier
from .architectural_operations import intent_label
from .reason_node import reason_candidates


def understand(prompt: str, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = ctx or {}
    base: dict[str, Any] = {
        "prompt": prompt,
        "layer": "unrecognized",
        "is_command": False,
        "direct_op": None,
        "intent": None,
        "intent_label": None,
        "confidence": 0.0,
        "intent_source": None,
        "matched": False,
        "candidates": [],
        "reason": "",
    }
    if not prompt or not prompt.strip():
        base["reason"] = "empty prompt"
        return base

    # ---- LAYER 1: DIRECT COMMAND ----
    if direct_command.is_direct_command(prompt):
        op = direct_command.parse_direct(prompt)
        if op:
            base.update(
                layer="direct", is_command=True, direct_op=op, matched=True,
                confidence=1.0,
                reason=f"direct command: {op.get('text', op.get('op'))}",
            )
            return base
        # Looked like a command but didn't parse — fall through to intent.

    # ---- LAYER 2: INTENT CLASSIFICATION ----
    cls = intent_classifier.classify_intent(prompt)
    if not cls:
        base["reason"] = "could not map the prompt to a known architectural intent"
        return base

    intent = cls["intent"]
    base.update(
        layer="intent",
        intent=intent,
        intent_label=intent_label(intent),
        confidence=cls.get("confidence", 0.0),
        intent_source=cls.get("source"),
        matched=bool(cls.get("matched", True)),
        reason=cls.get("reason", ""),
    )

    # ---- LAYER 3: REASON NODE — candidate operations (best-first) ----
    base["candidates"] = list(reason_candidates(intent, ctx))
    if not base["candidates"]:
        base["reason"] = (
            f"understood the intent as '{base['intent_label']}', but no valid operation "
            "is available for the current shape/site/context"
        )
    return base
