"""LAYER 3 (selection half) — Reason Node operation chooser.

Given a detected INTENT plus the design context (shape type, selected part, site
boundary, urban context, true-north edges, setbacks), choose the single best VALID
geometry operation to satisfy that intent.

This is the "Reason Node selects the best valid operation" step. It does NOT apply
geometry — it returns a parser-ready phrase + a human label. The route then runs
that phrase through the existing validated backend (feedback_routes), so all the
real fit/setback/site validation still happens downstream exactly as before.

Selection rules:
  - Resolve {dir} placeholders from REAL edge/context metadata. If an op needs a
    direction or context and none is available, that candidate is SKIPPED (never
    fabricate a direction) — honouring the "use real available context only" rule.
  - Deprioritise footprint-GROWING ops when the building already nearly fills the
    site (they'd just be rejected downstream).
  - Respect the selected part when one is given.
  - Fall through the intent's preference list until a candidate passes.
"""
from __future__ import annotations

from typing import Any

from .architectural_operations import OperationOption, operations_for


def _resolve_direction(ctx: dict[str, Any], need_context: bool) -> str | None:
    """Pick a real direction from context. Priority:
       selected edge → selected corner → a context-relevant edge → None.
    Never invents a direction; returns None if nothing real is available."""
    sel_edge = ctx.get("selected_edge") or {}
    if isinstance(sel_edge, dict):
        d = sel_edge.get("direction") or sel_edge.get("compass")
        if d:
            return str(d).lower()

    sel_corner = ctx.get("selected_corner") or {}
    if isinstance(sel_corner, dict) and sel_corner.get("name"):
        # corners aren't a cardinal facade direction; only use if no context needed
        if not need_context:
            name = str(sel_corner["name"]).lower()
            for card in ("north", "south", "east", "west"):
                if card in name:
                    return card

    # Fall back to a named direction in the prompt-resolved context intent, if the
    # route already extracted one (directional/context intent).
    d = ctx.get("resolved_direction")
    if d:
        return str(d).lower()

    return None


def _has_context(ctx: dict[str, Any]) -> bool:
    edges = ctx.get("edges") or []
    return bool(edges) or bool(ctx.get("selected_edge")) or bool(ctx.get("urban_context"))


def _nearly_fills_site(ctx: dict[str, Any]) -> bool:
    """True if the building footprint already covers most of the site (so a growing
    op would be rejected). Uses site_coverage when available; conservative default."""
    cov = ctx.get("site_coverage")
    try:
        return float(cov) >= 0.6
    except (TypeError, ValueError):
        return False


def _candidate_ok(opt: OperationOption, ctx: dict[str, Any], direction: str | None) -> bool:
    for need in opt.needs:
        if need == "direction" and not direction:
            return False
        if need == "context" and not _has_context(ctx):
            return False
    if opt.grows and _nearly_fills_site(ctx):
        return False
    return True


def choose_operation(intent: str, ctx: dict[str, Any] | None = None) -> dict[str, Any]:
    """Choose the best valid operation phrase for an intent.

    Returns:
      {op_phrase, label, direction, candidates, skipped, reason}
      op_phrase is None if NO candidate was valid (caller reports why via 'reason').
    """
    ctx = ctx or {}
    candidates = operations_for(intent)
    if not candidates:
        return {"op_phrase": None, "label": "", "direction": None,
                "candidates": [], "skipped": [],
                "reason": f"no operations are defined for intent '{intent}'"}

    skipped: list[str] = []
    for opt in candidates:
        need_context = "context" in opt.needs
        direction = _resolve_direction(ctx, need_context) if "direction" in opt.needs else None
        if not _candidate_ok(opt, ctx, direction):
            why = []
            if "direction" in opt.needs and not direction:
                why.append("no edge/direction selected")
            if "context" in opt.needs and not _has_context(ctx):
                why.append("no urban context available")
            if opt.grows and _nearly_fills_site(ctx):
                why.append("building already fills the site")
            skipped.append(f"{opt.op_phrase} ({', '.join(why) or 'not valid'})")
            continue
        phrase = opt.op_phrase.replace("{dir}", direction) if direction else opt.op_phrase
        return {
            "op_phrase": phrase,
            "label": opt.label,
            "direction": direction,
            "candidates": [c.op_phrase for c in candidates],
            "skipped": skipped,
            "reason": "",
        }

    # Nothing valid — explain precisely what was missing (transparency rule).
    return {
        "op_phrase": None,
        "label": "",
        "direction": None,
        "candidates": [c.op_phrase for c in candidates],
        "skipped": skipped,
        "reason": ("the building context needed for this change isn't available — "
                   + "; ".join(skipped) if skipped else "no valid operation for the current state"),
    }
