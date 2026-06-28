"""Design option store — saved shape versions in the Shape Library.

A "design option" is a saved snapshot of a manipulated building geometry. Options
are versioned: each save creates a NEW option (never overwrites) with a parent
pointer + manipulation history, so the Shape Library reads like:

    H Shape
     ├ H_Option_01 (original)
     ├ H_Option_02 (daylight courtyard edit)   parent H_Option_01
     └ H_Option_03 (taller central mass)        parent H_Option_02

Stored on the session state under `design_options` (a list). Pure data layer; the
route + shape_version_manager use it.
"""
from __future__ import annotations

import time
from typing import Any


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def list_options(state: dict[str, Any]) -> list[dict[str, Any]]:
    return list(state.get("design_options") or [])


def next_option_id(state: dict[str, Any], shape_type: str | None = None) -> str:
    """Generate a stable, human-readable id, e.g. 'shape_003'."""
    existing = list_options(state)
    n = len(existing) + 1
    return f"shape_{n:03d}"


def make_option(
    *,
    state: dict[str, Any],
    geometry: dict[str, Any],
    shape_type: str | None = None,
    parent_option_id: str | None = None,
    manipulation_history: list[dict[str, Any]] | None = None,
    created_from_prompt: str | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    """Build a saved-option record (does NOT persist — caller writes it to state)."""
    oid = next_option_id(state, shape_type)
    return {
        "shape_option_id": oid,
        "parent_option_id": parent_option_id,
        "shape_type": shape_type or geometry.get("shape_type") or "Custom",
        "label": label or _auto_label(created_from_prompt, manipulation_history),
        "geometry": geometry,
        "manipulation_history": list(manipulation_history or []),
        "created_from_prompt": created_from_prompt or "",
        "created_at": _now_iso(),
        "status": "saved",
    }


def add_option(state: dict[str, Any], option: dict[str, Any]) -> dict[str, Any]:
    """Append a new option to the store (never overwrites an existing one)."""
    opts = list_options(state)
    opts.append(option)
    state["design_options"] = opts
    return option


def get_option(state: dict[str, Any], option_id: str) -> dict[str, Any] | None:
    return next((o for o in list_options(state) if o.get("shape_option_id") == option_id), None)


def _auto_label(prompt: str | None, history: list | None) -> str:
    """A short label for the Shape Library row."""
    if prompt:
        words = prompt.strip().split()
        return " ".join(words[:6]) + ("…" if len(words) > 6 else "")
    if history:
        last = history[-1]
        return last.get("text") or last.get("op") or "edit"
    return "edited version"
