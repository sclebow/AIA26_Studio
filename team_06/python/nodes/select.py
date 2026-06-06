import json
from pathlib import Path

def _load_layout_by_id(layout_id: str, repo_root: Path) -> dict | None:
    """Load a layout from the Planfinder dataset."""
    pf_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if pf_path.exists():
        return json.loads(pf_path.read_text(encoding="utf-8"))
    return None


def _next_select_result(state: dict) -> str:
    return "daylight"


def build_select_node():
    def select(state: dict) -> dict:
        print("[SELECT] Entered select node")
        layout_id = state.get("layout_id")
        print("[SELECT] layout_id:", layout_id)

        if not layout_id:
            return {
                "select_result": "failed",
                "clarification": "No layout_id found in state. How would you like to proceed?"
            }

        repo_root = Path(__file__).parent.parent.parent
        layout = _load_layout_by_id(layout_id, repo_root)
        if not layout:
            print(f"[SELECT] Layout {layout_id} not found.")
            return {
                "select_result": "failed",
                "clarification": f"Layout {layout_id} not found. How would you like to proceed?"
            }

        print("[SELECT] Selected layout:", json.dumps(layout)[:300])
        return {
            "select_result": _next_select_result(state),
            "layout_id": layout_id,
            "clarification": None,
            "layout_json_string": json.dumps(layout)
        }
    return select