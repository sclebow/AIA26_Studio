"""
LOAD_LAYOUT node — pure Python, no LLM.
Loads a layout JSON by ID (auto-match from prompt) or interactive terminal picker.
Skips loading if the same layout is already in session state.
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
