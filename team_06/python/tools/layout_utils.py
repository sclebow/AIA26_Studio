import json
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def load_all_layouts() -> list[dict]:
    """Load all layouts from sample_layouts.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    return json.loads(layouts_path.read_text(encoding="utf-8"))

def load_and_save_layout(layout_id: str, state: dict, save_path: Path) -> dict:
    """Load layout by ID, update state, and save to file."""
    all_layouts = load_all_layouts()
    layout = next((l for l in all_layouts if l.get("layoutId") == layout_id), None)
    
    if not layout:
        return {"error": f"Layout {layout_id} not found"}
    
    state["layout_json_string"] = json.dumps(layout)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
    return {"status": "loaded", "saved_to": str(save_path)}

def save_layout(layout_data: dict, state: dict, save_path: Path) -> dict:
    """Save layout data to file and update state."""
    state["layout_json_string"] = json.dumps(layout_data)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_text(json.dumps(layout_data, indent=2), encoding="utf-8")
    return {"status": "saved", "saved_to": str(save_path)}