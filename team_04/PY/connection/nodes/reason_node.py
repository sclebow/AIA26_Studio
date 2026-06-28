"""LAYER 3 — Reason Node (composition wrapper).

The spec asks for a backend/nodes/reason_node.py that, AFTER an intent is detected,
"chooses the best geometry operation based on shape type, selected part, site
boundary, urban context, true-north edge metadata, setbacks, validation rules".

The geometry-selection logic lives in intent_to_operations.choose_operation (kept
separate so it's unit-testable). This module is the Reason Node ENTRY POINT used by
the pipeline: it takes an intent + context, asks the chooser for an ordered set of
candidate operations, and yields them so the caller can apply the FIRST one that
passes real downstream validation — falling through to the next on failure.

This is the key behavioural fix over the old system, which picked one operation and
failed hard when it didn't fit (e.g. "courtyard would consume the whole footprint").
The Reason Node now reasons over a candidate SET, not a single guess.

NOTE: the existing keyword engine connection/notebook_logic/reason_node.py is NOT
replaced — it remains the deterministic intent classifier used as the LLM fallback
in intent_classifier. This module sits one layer above it.
"""
from __future__ import annotations

from typing import Any, Iterator

from .architectural_operations import intent_label, operations_for
from .intent_to_operations import (
    _candidate_ok,
    _resolve_direction,
    choose_operation,
)


def reason(intent: str, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Pick the single best valid operation for an intent (one-shot).

    Returns the choose_operation result enriched with the human intent label.
    Use reason_candidates() instead when you want to try-then-fall-through.
    """
    result = choose_operation(intent, ctx or {})
    result["intent_label"] = intent_label(intent)
    return result


def reason_candidates(intent: str, ctx: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Yield EVERY valid candidate operation for an intent, best-first.

    The caller applies each phrase through the real validated backend and stops at
    the first that actually changes geometry. Skipped candidates (missing direction,
    growing op on a full site) are filtered out here so the caller only sees ops that
    are at least pre-condition-valid; final fit/setback validation is still the
    backend's job.
    """
    ctx = ctx or {}
    for opt in operations_for(intent):
        need_context = "context" in opt.needs
        direction = _resolve_direction(ctx, need_context) if "direction" in opt.needs else None
        if not _candidate_ok(opt, ctx, direction):
            continue
        phrase = opt.op_phrase.replace("{dir}", direction) if direction else opt.op_phrase
        yield {"op_phrase": phrase, "label": opt.label, "direction": direction}
