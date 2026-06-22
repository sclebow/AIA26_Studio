from typing import Any
import json
import re
from pathlib import Path
from functools import lru_cache
from tools.layout_evaluator import (
    summarize_evaluation,
    compute_daylight_score,
    compute_room_fit_score,
    compute_access_fit,
    compute_adjacency_fit,
    compute_size_score,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_SUBSCORE_WEIGHTS: dict[str, float] = {
    "room_fit":      0.30,
    "lifestyle_fit": 0.25,
    "access_fit":    0.20,
    "adjacency_fit": 0.12,
    "size":          0.13,
}



@lru_cache(maxsize=1)
def _get_description_index():
    from tools.embedding_matcher import DescriptionIndex
    descriptions_dir = _REPO_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions"
    return DescriptionIndex(descriptions_dir)


def _compute_lifestyle_fit(description_query: str, layout_id: str) -> dict | None:
    if not description_query or not layout_id:
        return None
    try:
        index = _get_description_index()
        results = index.search(description_query, candidate_ids={layout_id})
        for lid, cosine in results:
            if lid == layout_id:
                # Rescale: 0.30 → 0, 0.85 → 100 (typical cosine range for layout descriptions)
                score = max(0, min(100, round((cosine - 0.30) / 0.55 * 100)))
                return {"score": score}
    except Exception:
        pass
    return None

FIXED_CLOSING_SENTENCE = (
    "If you are happy with this layout, we can keep it. Otherwise, you can select a different candidate layout or refine the search with more information."
)
 
SYSTEM_PROMPT = (
    "You are writing a short qualitative comment for a residential layout recommendation. "
    "Write exactly 2 sentences as plain text — no JSON, no markdown, no bullet points.\n"
    "Rules:\n"
    "- Focus on how well the layout matches the user's brief — what fits, what is missing or different.\n"
    "- Do NOT repeat or mention any numeric scores — they are already shown in the UI.\n"
    "- Do NOT mention daylight unless the user's brief explicitly asks for it in a specific room.\n"
    "- Do NOT comment on daylight in bathrooms, WCs, or wet rooms — these almost never have windows.\n"
    "- If adaptation failed, briefly note the comment refers to the closest available layout.\n"
    "- Kitchen is always part of the living area in this dataset — never a separate room.\n"
    "- Treat circulation as entry, hallway, or corridor.\n"
    "- Do not invent features not present in the layout description.\n"
)


def _build_layout_evaluation_payload(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    summary = summarize_evaluation(layout_data, topology_json)
    rooms = layout_data.get("rooms") if isinstance(layout_data.get("rooms"), list) else []

    compact_rooms: list[dict[str, Any]] = []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        attributes = room.get("attributes") if isinstance(room.get("attributes"), dict) else {}
        geometry = room.get("geometry") if isinstance(room.get("geometry"), list) else []
        compact_rooms.append({
            "id": room.get("id"),
            "name": room.get("name"),
            "program": attributes.get("program"),
            "area": attributes.get("area"),
            "vertex_count": len(geometry),
        })

    apartment = layout_data.get("apartment") if isinstance(layout_data.get("apartment"), dict) else {}
    apartment_attributes = apartment.get("attributes") if isinstance(apartment.get("attributes"), dict) else {}

    return {
        "layoutId": layout_data.get("layoutId"),
        "apartment_area": apartment_attributes.get("area"),
        "apartment_description": apartment_attributes.get("description"),
        "brief": topology_json,
        "rooms": compact_rooms,
        "rule_issues": summary.get("evaluation_issues", []) if isinstance(summary, dict) else [],
    }


def _load_planfinder_description(layout_id: str | None) -> str | None:
    if not isinstance(layout_id, str) or not layout_id.strip():
        return None

    repo_root = Path(__file__).resolve().parent.parent.parent
    description_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions" / f"{layout_id.strip()}.json"
    if not description_path.exists():
        return None

    try:
        payload = json.loads(description_path.read_text(encoding="utf-8"))
    except Exception:
        return None

    description = payload.get("description")
    if not isinstance(description, str) or not description.strip():
        return None
    return description.strip()


def _extract_chat_summary(raw: str) -> str | None:
    """Extract plain-text summary from whatever format the LLM returned."""
    candidates: list[str] = []

    # 1. Decision-schema wrapper: {"action":..., "final_response":"...", ...}
    if '"final_response"' in raw:
        try:
            outer = json.loads(raw)
            fr = outer.get("final_response")
            if isinstance(fr, dict):
                candidates.append(json.dumps(fr))
            elif isinstance(fr, str) and fr.strip() and not fr.strip() in ('{', '}'):
                candidates.append(fr.strip())
        except Exception:
            pass

    # 2. Raw string itself (plain text or JSON)
    candidates.append(raw.strip())

    for candidate in candidates:
        if not candidate:
            continue
        # Try parsing as {"chat_summary": "..."} JSON
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                cs = parsed.get("chat_summary")
                if isinstance(cs, str) and cs.strip():
                    return cs.strip()
        except Exception:
            pass
        # Use as plain text if it doesn't look like a broken JSON fragment
        if not candidate.startswith('{') and len(candidate) > 5:
            return candidate
    return None


def _format_evaluation_message(evaluation: dict[str, Any], warning: str | None = None) -> str:
    parts = []
    if warning:
        parts.append(f"⚠️ {warning}")
    if evaluation.get("chat_summary"):
        parts.append(evaluation["chat_summary"])
    parts.append(FIXED_CLOSING_SENTENCE)
    return "\n\n".join(parts)


def _build_subscores(
    room_fit: dict | None,
    lifestyle_fit: dict | None,
    access_fit: dict | None = None,
    adjacency_fit: dict | None = None,
    size: dict | None = None,
) -> tuple[int, list[dict]]:
    """Compute fit_score from available subscores and build the subscores list."""
    available: dict[str, dict | None] = {
        "room_fit":      room_fit,
        "lifestyle_fit": lifestyle_fit,
        "access_fit":    access_fit,
        "adjacency_fit": adjacency_fit,
        "size":          size,
    }

    total_weight = 0.0
    weighted_sum = 0.0
    for id_, weight in _SUBSCORE_WEIGHTS.items():
        s = available.get(id_)
        if s is not None and s.get("score") is not None:
            weighted_sum += s["score"] * weight
            total_weight += weight
    fit_score = round(weighted_sum / total_weight) if total_weight > 0 else 0

    def _slot(id_: str, label: str, result: dict | None) -> dict:
        if result is None:
            return {"id": id_, "label": label, "score": None, "available": False, "details": None}
        return {"id": id_, "label": label, "score": result.get("score"), "available": True, "details": result.get("details")}

    subscores = [
        _slot("room_fit",      "Rooms",   room_fit),
        _slot("lifestyle_fit", "Lifestyle",  lifestyle_fit),
        _slot("access_fit",    "Access",     access_fit),
        _slot("adjacency_fit", "Adjacency",  adjacency_fit),
        _slot("size",          "Size",       size),
    ]

    return fit_score, subscores


def build_evaluate_node(llm: Any) -> Any:
    """Evaluate the current layout against the parsed brief."""
    def evaluate(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        adaptation_failed = state.get("adaptation_failed", False)
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {
                "clarification": "No layout available for evaluation.",
                "iteration": iteration + 1,
            }

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            topology_json = state.get("topology_graph_json_string")
            layout_id = state.get("layout_id")

            # --- Deterministic subscores ---
            room_fit      = compute_room_fit_score(layout_data, topology_json)
            access_fit    = compute_access_fit(layout_data, topology_json)
            adjacency_fit = compute_adjacency_fit(layout_data, topology_json)
            size          = compute_size_score(layout_data, topology_json)
            description_query = ""
            if topology_json:
                try:
                    description_query = json.loads(topology_json).get("description", "")
                except Exception:
                    pass
            lifestyle_fit = _compute_lifestyle_fit(description_query, layout_id or "")
            fit_score, subscores = _build_subscores(
                room_fit, lifestyle_fit, access_fit, adjacency_fit, size
            )

            # --- Daylight (optional, deterministic) ---
            daylight_evaluation = compute_daylight_score(layout_data)

            # --- Layout context for the LLM ---
            evaluation_payload = _build_layout_evaluation_payload(layout_data, topology_json)
            evaluation_payload["planfinder_description"] = _load_planfinder_description(evaluation_payload.get("layoutId"))

            planfinder_description = evaluation_payload.get("planfinder_description") or ""
            brief_description = ""
            if topology_json:
                try:
                    brief_description = json.loads(topology_json).get("description", "")
                except Exception:
                    pass

            # Build a factual room count summary from the actual layout data
            rooms_raw = layout_data.get("rooms") if isinstance(layout_data.get("rooms"), list) else []
            from collections import Counter
            prog_counts = Counter(
                r.get("attributes", {}).get("program", "unknown")
                for r in rooms_raw if isinstance(r, dict)
            )
            room_facts = ", ".join(
                f"{count}× {prog}" for prog, count in sorted(prog_counts.items())
            ) or "unknown"

            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"User brief: {brief_description or topology_json}\n\n"
                    f"Layout description: {planfinder_description or '(not available)'}\n\n"
                    f"Actual rooms in this layout: {room_facts}\n\n"
                    + (f"Note: adaptation to this layout failed — comment refers to the closest available layout.\n\n" if adaptation_failed else "")
                    + "Write the 2-sentence qualitative comment. Use the actual room facts if the description is inaccurate."
                )}
            ]
            try:
                response = llm.invoke(llm_messages)
                raw = response.content if isinstance(response.content, str) else str(response.content)
                print(f"[evaluate] raw response (first 200): {raw[:200]}", flush=True)
                chat_summary = _extract_chat_summary(raw)
                llm_output = {"chat_summary": chat_summary} if chat_summary else {"chat_summary": "Layout evaluated."}
            except Exception as e:
                print(f"[evaluate] LLM summary failed: {e}", flush=True)
                llm_output = {"chat_summary": "Layout evaluated."}

            evaluation_summary: dict[str, Any] = {
                "fit_score": fit_score,
                "subscores": subscores,
                **llm_output,
            }
            if daylight_evaluation is not None:
                evaluation_summary["daylight_score"] = daylight_evaluation["score"]
                evaluation_summary["daylight_rooms"] = daylight_evaluation["rooms"]

            return {
                "evaluation_json_string": json.dumps(evaluation_summary),
                "clarification": _format_evaluation_message(evaluation_summary, state.get("routine_warning")),
                "iteration": iteration + 1,
            }

        except Exception as e:
            return {
                "clarification": f"Evaluation failed: {str(e)}",
                "iteration": iteration + 1,
            }

    return evaluate