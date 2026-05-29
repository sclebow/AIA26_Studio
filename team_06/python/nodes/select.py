from typing import Any
import json
import re
from pathlib import Path

def build_select_node():
    def select(state: dict) -> dict:
        print("[SELECT] Entered select node")
        user_prompt = state.get("user_prompt", "").lower()
        print("[SELECT] user_prompt:", user_prompt)
        tried_layout_ids = state.get("tried_layout_ids", [])
        print("[SELECT] tried_layout_ids:", tried_layout_ids)

        # Check if user provided a layout ID
        if "layout-" in user_prompt:
            print("[SELECT] State before selection, layout_json_string:", state.get("layout_json_string", "<none>"))
            match = re.search(r'layout-(\w+)', user_prompt)
            if match:
                layout_id = f"layout-{match.group(1)}"
                search_json = state.get("search_results_json_string", "[]")
                try:
                    results = json.loads(search_json)
                except Exception:
                    results = []
                found = any(f"{r['id']}" == layout_id for r in results)
                if found and layout_id not in tried_layout_ids:
                    # Load layout from team_06/layout_inputs/sample_layouts.json
                    layouts_path = Path(__file__).parent.parent.parent / "layout_inputs" / "sample_layouts.json"
                    all_layouts = json.loads(layouts_path.read_text(encoding="utf-8"))
                    layout = next((l for l in all_layouts if l.get("layoutId") == layout_id), None)
                    if not layout:
                        print(f"[SELECT] Layout {layout_id} not found in sample_layouts.json.")
                        return {
                            "select_result": "failed",
                            "clarification": f"Layout {layout_id} not found in sample_layouts.json. How would you like to proceed?",
                            "tried_layout_ids": tried_layout_ids
                        }
                    save_path = Path(__file__).parent.parent.parent / "team_06_edited_layout.json"
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    save_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
                    tried_layout_ids.append(layout_id)
                    print("[SELECT] Selected layout:", json.dumps(layout)[:300])
                    return {
                        "select_result": "success",
                        "selected_layout_id": layout_id,
                        "tried_layout_ids": tried_layout_ids,
                        "clarification": None,
                        "layout_json_string": json.dumps(layout)
                    }
                else:
                    print(f"[SELECT] Layout {layout_id} not found or already tried.")
                    return {
                        "select_result": "failed",
                        "clarification": f"Layout {layout_id} not found or already tried. How would you like to proceed?",
                        "tried_layout_ids": tried_layout_ids
                    }

        # Otherwise, pick the next untried layout from search results
        search_json = state.get("search_results_json_string", "[]")
        try:
            results = json.loads(search_json)
        except Exception:
            print("[SELECT] No search results found.")
            return {
                "select_result": "failed",
                "clarification": "No search results found. How would you like to proceed?",
                "tried_layout_ids": tried_layout_ids
            }

        # Filter out already tried layouts
        untried = [r for r in results if f"{r['id']}" not in tried_layout_ids]

        if not untried:
            print("[SELECT] No layouts left to try.")
            return {
                "select_result": "failed",
                "clarification": "No layouts left to try. How would you like to proceed? (Type 'end' to exit or write a new request)",
                "tried_layout_ids": tried_layout_ids
            }

        # Pick the next untried layout
        next_layout = untried[0]
        layout_id = f"{next_layout['id']}"
        # Load layout from team_06/layout_inputs/sample_layouts.json
        layouts_path = Path(__file__).parent.parent.parent / "layout_inputs" / "sample_layouts.json"
        all_layouts = json.loads(layouts_path.read_text(encoding="utf-8"))
        layout = next((l for l in all_layouts if l.get("layoutId") == layout_id), None)
        if not layout:
            print(f"[SELECT] Layout {layout_id} not found in sample_layouts.json.")
            return {
                "select_result": "failed",
                "final_response": f"Layout {layout_id} not found in sample_layouts.json.",
                "tried_layout_ids": tried_layout_ids
            }
        save_path = Path(__file__).parent.parent.parent / "team_06_edited_layout.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_text(json.dumps(layout, indent=2), encoding="utf-8")
        tried_layout_ids.append(layout_id)

        print("[SELECT] Selected layout:", json.dumps(layout)[:300])
        return {
            "select_result": "success",
            "selected_layout_id": layout_id,
            "tried_layout_ids": tried_layout_ids,
            "clarification": None,
            "layout_json_string": json.dumps(layout)
        }
    return select