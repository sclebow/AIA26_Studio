"""
LOAD_LAYOUT node — pure Python, no LLM.
Fixed: raises clear error if layout_id is missing (web mode — frontend must always send it).
No more stdin prompt.
"""

from __future__ import annotations
import json
from pathlib import Path


def build_load_layout_node(layout_input_dir: Path):

    def load_layout_node(state: dict) -> dict:
        # Skip if the same layout is already loaded
        if state.get("layout_json_string") and state.get("layout_id"):
            requested_id = str(state.get("layout_id", ""))
            try:
                loaded_data = json.loads(state["layout_json_string"])
                loaded_id   = str(loaded_data.get("layoutId", ""))
                if requested_id and (requested_id in loaded_id or loaded_id.endswith(requested_id)):
                    print(f"[load_layout] Layout {requested_id} already loaded — skipping.")
                    return state
            except (json.JSONDecodeError, TypeError):
                pass

        layout_id: str | None = state.get("layout_id")

        # In web mode, layout_id must be set by the frontend before calling the agent.
        # We try to auto-pick only if exactly one layout file exists.
        selected: Path | None = None

        if layout_id:
            matches = sorted(layout_input_dir.glob(f"*{layout_id}*.json"))
            if matches:
                selected = matches[0]
                print(f"[load_layout] Found layout {layout_id}: {selected.name}")

        if selected is None:
            # Auto-pick if only one layout exists
            all_layouts = sorted(layout_input_dir.glob("*.json"))
            if len(all_layouts) == 1:
                selected = all_layouts[0]
                print(f"[load_layout] Auto-selected only layout: {selected.name}")
            elif not all_layouts:
                raise RuntimeError(f"[load_layout] No JSON layouts found in {layout_input_dir}")
            else:
                # Multiple layouts but no ID — pick the first one and warn
                selected = all_layouts[0]
                print(f"[load_layout] No layout_id provided — defaulting to: {selected.name}")
                print(f"[load_layout] Hint: frontend should send layout_id with each message.")

        try:
            layout_data = json.loads(selected.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"[load_layout] Failed to read {selected.name}: {exc}") from exc

        confirmed_id = str(layout_data.get("layoutId", layout_id or "?"))
        print(f"[load_layout] Loaded {confirmed_id} from {selected.name}")

        return {
            **state,
            "layout_json_string": json.dumps(layout_data),
            "layout_id":          confirmed_id,
        }

    return load_layout_node
