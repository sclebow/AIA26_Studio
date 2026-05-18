"""
nodes/load_layout.py — LOAD_LAYOUT node for the Comfort Copilot state graph.

Pure Python — no LLM, no MCP calls. Runs after PREPROCESS on the comfort path.

Responsibilities:
  1. If a layout_id was detected in the prompt (e.g. "201"), find and load
     the matching JSON file from layout_input_dir automatically.
  2. If no layout_id was found (or the file is not found), show the
     interactive terminal picker so the user can select a layout.
  3. Skip loading entirely if a layout is already in state from a previous
     turn in the multi-turn session.

Writes to state:
  layout_json_string  (str)  — full JSON of the loaded layout
  layout_id           (str)  — confirmed layout ID (e.g. "201")

===========================================================================
INPUT SCHEMA  (randomized_layouts/layout_{id}.json)
Comfort Copilot | AIA26 Studio Module 03 | Team 02
===========================================================================

Layout root:
  "layoutId":  str                   -- e.g. "Layout-201"
  "name":      str                   -- e.g. "Modern 2-Bedroom Apartment"
  "outline":   [[float, float], ...] -- perimeter polygon

rooms[]  -- used by compute_comfort_scores  [Form + Use + Site]
  "id", "name", "geometry"
  attributes:
    "area":            float   -- m²                        → spatial score
    "roomType":        str     -- "living"|"bedroom"|...    → baseline scores
    "height":          float   -- m                         → spatial score
    "orientation":     str     -- "N"|"S"|"E"|"W"|...       → thermal score
    "glazingRatio":    float   -- 0.0–1.0                   → visual score
    "ventilationType": str     -- "natural"|"mechanical"|"mixed" → olfactory score
  -- output_writer.py adds "analysis":{...} here after each comfort turn

doors[]  -- used for acoustic score  [Use team]
  "connectsRooms": [str, str]  -- adjacency penalty if bedroom next to kitchen/living

windows[]  -- used for thermal score  [Form + Site teams]
  "roomId":      str           -- links window to room
  "glazingType": str           -- "single"|"double"|"triple" → thermal adjustment

furniture[]  -- used for tactile + olfactory + visual scores  [Use team]
  "roomId":   str
  "type":     str              -- "plant" type adds biophilic bonus (olfactory + visual)
  "material": str              -- mapped to warmth score → tactile score

structure[]  -- used for tactile score  [Structure team]
  "material": str              -- wall material averaged across layout → tactile score

mep[]  -- NOT used by scoring script  [Structure / MEP team — future]
  "system":   str              -- ventilationType on rooms is the current proxy

NOTE: source files in randomized_layouts/ are never overwritten.
      Enriched copies are written to resulting_layout/Layout-{id}_modified.json.
===========================================================================
"""

from __future__ import annotations
import json
from pathlib import Path


def build_load_layout_node(layout_input_dir: Path):
    """Return the load_layout node function, capturing layout_input_dir."""

    def load_layout_node(state: dict) -> dict:

        # ── Skip only if the SAME layout is already loaded ────────────────
        # If the user asks for a different layout ID, reload even if something
        # is already in state (e.g. switching from layout 201 to layout 202).
        if state.get("layout_json_string") and state.get("layout_id"):
            requested_id = str(state.get("layout_id", ""))
            try:
                loaded_data = json.loads(state["layout_json_string"])
                loaded_id   = str(loaded_data.get("layoutId", ""))
                # Match e.g. "202" against "Layout-202"
                if requested_id and (requested_id in loaded_id or loaded_id.endswith(requested_id)):
                    print(f"[load_layout] Layout {requested_id} already loaded — skipping.")
                    return state
            except (json.JSONDecodeError, TypeError):
                pass  # Fall through and reload

        layout_id: str | None = state.get("layout_id")

        # ── Try to load by ID first ───────────────────────────────────────
        selected: Path | None = None

        if layout_id:
            matches = sorted(layout_input_dir.glob(f"*{layout_id}*.json"))
            if matches:
                selected = matches[0]
                print(f"[load_layout] Found layout for ID {layout_id}: {selected.name}")

        # ── Fall back to interactive picker ──────────────────────────────
        if selected is None:
            selected = _pick_layout_interactively(layout_input_dir)

        # ── Read and store ────────────────────────────────────────────────
        try:
            layout_data = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"[load_layout] Failed to read {selected.name}: {exc}") from exc

        # Confirm the layout ID from the file itself (more reliable than prompt)
        confirmed_id = str(layout_data.get("layoutId", layout_id or "?"))
        print(f"[load_layout] Loaded layout {confirmed_id} from {selected.name}")

        return {
            **state,
            "layout_json_string": json.dumps(layout_data),
            "layout_id":          confirmed_id,
        }

    return load_layout_node


# ---------------------------------------------------------------------------
# Interactive picker (terminal)
# ---------------------------------------------------------------------------

def _pick_layout_interactively(layout_input_dir: Path) -> Path:
    """List JSON files in layout_input_dir and prompt the user to pick one."""
    if not layout_input_dir.exists():
        raise RuntimeError(f"[load_layout] Layout directory not found: {layout_input_dir}")

    layout_files = sorted(layout_input_dir.glob("*.json"))
    if not layout_files:
        raise RuntimeError(f"[load_layout] No JSON files found in {layout_input_dir}")

    if len(layout_files) == 1:
        print(f"[load_layout] Using the only available layout: {layout_files[0].name}")
        return layout_files[0]

    print("\nAvailable layouts:")
    for i, f in enumerate(layout_files, 1):
        print(f"  {i}. {f.name}")

    while True:
        try:
            choice = input("\nSelect a layout (enter number): ").strip()
            index = int(choice) - 1
            if 0 <= index < len(layout_files):
                selected = layout_files[index]
                print(f"Selected: {selected.name}\n")
                return selected
            print(f"Please enter a number between 1 and {len(layout_files)}")
        except ValueError:
            print("Invalid input. Please enter a number.")
