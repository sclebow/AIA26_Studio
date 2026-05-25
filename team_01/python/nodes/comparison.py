from __future__ import annotations
import json
import time


SYSTEM_PROMPT = """You are a structural design comparison analyst for an architect.

You will be given a compact structural diff (added/removed/changed elements).
Summarize in 3-5 sentences:
1. What changed and whether the modification achieved its goal.
2. Any new issues introduced or old ones resolved.

Return strictly valid JSON:
{
  "action": "final",
  "final_response": "<your comparison here>",
  "tool_calls": []
}
"""


def _structural_diff(original_json: str, modified_json: str) -> str:
    """Return a compact text diff of the structure arrays only."""
    def _struct_map(layout_str: str) -> dict:
        layout = json.loads(layout_str)
        return {s["id"]: s for s in layout.get("structure", [])}

    orig = _struct_map(original_json)
    mod  = _struct_map(modified_json)

    added   = [v for k, v in mod.items()  if k not in orig]
    removed = [v for k, v in orig.items() if k not in mod]
    changed = [
        {"id": k, "before": orig[k]["attributes"], "after": mod[k]["attributes"]}
        for k in orig if k in mod and orig[k]["attributes"] != mod[k]["attributes"]
    ]

    def _slim(el: dict) -> dict:
        return {"id": el["id"], "name": el.get("name", ""), "attrs": el.get("attributes", {})}

    return json.dumps({
        "added":   [_slim(e) for e in added],
        "removed": [_slim(e) for e in removed],
        "changed": changed,
    }, separators=(",", ":"))


def build_comparison_node(llm):

    def comparison_node(state):
        print(f"\n{'='*50}")
        print(f"  NODE: COMPARISON  (cycle {state.get('cycle', 0) + 1})")
        print(f"{'='*50}")

        original = state.get("original_layout_json_string") or state["layout_json_string"]
        diff = _structural_diff(original, state["layout_json_string"])

        context_message = f"Structural diff (added/removed/changed elements):\n{diff}"
        messages = [{"role": "user", "content": context_message}]

        result = None
        last_error = None
        for attempt in range(3):
            try:
                llm_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
                raw = llm.invoke(llm_messages)
                data = json.loads(raw.content)
                result = data.get("final_response", raw.content)
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    wait = 5 * (attempt + 1)
                    print(f"Comparison LLM failed (attempt {attempt+1}/3), retrying in {wait}s... {e}")
                    time.sleep(wait)

        if result is None:
            raise RuntimeError(f"Comparison LLM failed after 3 attempts: {last_error}")

        print(f"Comparison result: {result}")
        state["comparison_result"] = result
        state["cycle"] = state.get("cycle", 0) + 1
        state["messages"].append({
            "role": "user",
            "content": f"Comparison summary: {result}",
        })
        return state

    return comparison_node
