"""
LOAD_LAYOUT node — pure Python, no LLM.

Robust to the three ID formats in play: the frontend sends "204", the files are
named layout_204.json, and the JSON carries "layoutId": "Layout-204". We match on
the NUMERIC part only, and we write a normalized short id ("204") back to state so
subsequent turns keep matching. If a layout_id was requested but no file matches,
we surface an explicit "not found" instead of silently analysing the wrong layout.
"""

from __future__ import annotations
import json
from pathlib import Path

from nodes._shared.utils import layout_digits as _norm_id


def build_load_layout_node(layout_input_dir: Path):

    def load_layout_node(state: dict) -> dict:
        requested_norm = _norm_id(state.get("layout_id"))

        # Skip if the same layout is already loaded (compare on digits only).
        if state.get("layout_json_string") and requested_norm:
            try:
                loaded_data = json.loads(state["layout_json_string"])
                if _norm_id(loaded_data.get("layoutId")) == requested_norm:
                    print(f"[load_layout] Layout {requested_norm} already loaded — skipping.")
                    skipped = {**state, "layout_id": requested_norm}
                    if state.get("action") == "load":
                        skipped["final_response"] = (
                            f"Layout {requested_norm} is already loaded. "
                            "Ask me to analyse it whenever you're ready."
                        )
                    return skipped
            except (json.JSONDecodeError, TypeError):
                pass

        all_layouts = sorted(layout_input_dir.glob("*.json"))
        if not all_layouts:
            raise RuntimeError(f"[load_layout] No JSON layouts found in {layout_input_dir}")

        selected: Path | None = None

        if requested_norm:
            # Match on the numeric part so "204" / "Layout-204" / "layout_204" all hit.
            matches = [p for p in all_layouts if _norm_id(p.name) == requested_norm]
            if matches:
                selected = matches[0]
                print(f"[load_layout] Found layout {requested_norm}: {selected.name}")
            else:
                # An explicit id was requested but doesn't exist — do NOT fall back to
                # an arbitrary layout (that produced the "204 → 201" bug). Surface it.
                available = ", ".join(sorted(_norm_id(p.name) for p in all_layouts))
                print(f"[load_layout] Requested layout {requested_norm} not found. Available: {available}")
                return {
                    **state,
                    "layout_not_found": True,
                    "final_response": (
                        f"I couldn't find layout {requested_norm}. "
                        f"Available layouts: {available}."
                    ),
                }
        elif len(all_layouts) == 1:
            selected = all_layouts[0]
            print(f"[load_layout] Auto-selected only layout: {selected.name}")
        else:
            # No id at all and multiple layouts — pick the first and warn.
            selected = all_layouts[0]
            print(f"[load_layout] No layout_id provided — defaulting to: {selected.name}")
            print(f"[load_layout] Hint: frontend should send layout_id with each message.")

        try:
            layout_data = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"[load_layout] Failed to read {selected.name}: {exc}") from exc

        # Normalize what we keep in state so future turns keep matching the file.
        confirmed_norm = _norm_id(layout_data.get("layoutId")) or _norm_id(selected.name) or requested_norm
        display_id = str(layout_data.get("layoutId", confirmed_norm or "?"))
        print(f"[load_layout] Loaded {display_id} from {selected.name} (id={confirmed_norm})")

        out = {
            **state,
            "layout_json_string": json.dumps(layout_data),
            "layout_id":          confirmed_norm,
            "layout_not_found":   False,
            # A genuinely fresh layout load resets the suggestion-lifecycle accumulator:
            # a suggestion is crossed off only after a real edit applies it WITHIN the
            # current editing session, so loading a new layout (or this one at its initial
            # state) starts every suggestion un-crossed. The "already loaded — skipping"
            # path above returns early and preserves it, so edits within a session persist.
            "applied_suggestions": [],
        }
        # Silent LOAD intent: render the plan only and wait — no scoring. The graph ends
        # the turn here (see _route_after_load_layout), so set the spoken acknowledgment.
        if state.get("action") == "load":
            out["final_response"] = (
                f"Loaded {display_id}. The plan's on the canvas — "
                "ask me to analyse it whenever you're ready."
            )
        return out

    return load_layout_node
