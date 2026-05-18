"""
nodes/output_writer.py -- Write analysis results back into the resulting_layout/ folder.

Called from run_agent (graph.py) after each comfort-path turn.
Writes to: resulting_layout/Layout-{id}_modified.json
Source layouts in randomized_layouts/ are never touched.

Output schema (per room, inside attributes{}):
  "analysis": {
    "_source":       "Comfort Copilot",
    "persona":       str,
    "depth":         "analyze" | "detect" | "full",
    "timestamp":     "2026-05-10T14:32:00",
    "overallScore":  float,
    "comfortScores": { "thermal": float, "visual": float, ... },
    "conflicts":     ["acoustic", "thermal"],   -- flagged sense names, [] if not run
    "suggestions":   [{"sense": str, "priority": int, "suggestion": str}]  -- [] if not run
  }

Output schema (layout root):
  "analysis": {
    "_source":      "Comfort Copilot",
    "persona":      str,
    "depth":        str,
    "timestamp":    str,
    "overallScore": float,
    "bestRoom":     str,
    "worstRoom":    str
  }

Room lookup strategy:
  The writer tries room_id first, falls back to room_name on conflicts/suggestions.

NOTE (Phase 3): Grasshopper can read attributes.analysis.comfortScores per
room ID and map values to a colour gradient for in-Rhino visualisation.
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

_SOURCE_TAG = "Comfort Copilot"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_analysis_to_layout(state: dict, layout_output_dir: Path) -> None:
    """Enrich the layout JSON with analysis results and write to resulting_layout/."""
    layout_json_str = state.get("layout_json_string", "")
    if not layout_json_str:
        print("[output_writer] No layout in state -- skipping write.")
        return

    try:
        layout = json.loads(layout_json_str)
    except json.JSONDecodeError as exc:
        print("[output_writer] Could not parse layout JSON: {}".format(exc))
        return

    persona   = state.get("persona_detected", "Neutral")
    depth     = state.get("comfort_depth", "analyze")
    layout_id = state.get("layout_id", "")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    scores_by_room      = _parse_scores(state.get("last_scores_json", ""))
    conflicts_by_room   = _parse_conflicts(state.get("last_conflicts_json", ""))
    suggestions_by_room = _parse_suggestions(state.get("last_suggestions_json", ""))


    best_room   = None
    worst_room  = None
    best_score  = -1.0
    worst_score = 2.0

    for room in layout.get("rooms", []):
        room_id   = room.get("id", "")
        room_name = room.get("name", "")
        scores    = scores_by_room.get(room_id, {})

        if not scores:
            continue

        overall = scores.get("overallScore", 0.0)

        conflicts   = (conflicts_by_room.get(room_id)
                       or conflicts_by_room.get(room_name, []))
        suggestions = (suggestions_by_room.get(room_id)
                       or suggestions_by_room.get(room_name, []))

        room.setdefault("attributes", {})["analysis"] = {
            "_source":      _SOURCE_TAG,
            "persona":      persona,
            "depth":        depth,
            "timestamp":    timestamp,
            "overallScore": round(overall, 4),
            "comfortScores": {
                k: round(_safe_float(v), 4)
                for k, v in scores.get("comfortScores", {}).items()
            },
            "conflicts":    conflicts,
            "suggestions":  suggestions,
        }

        if overall > best_score:
            best_score = overall
            best_room  = room_id
        if overall < worst_score:
            worst_score = overall
            worst_room  = room_id

    all_scores = [
        s.get("overallScore", 0.0)
        for s in scores_by_room.values()
        if s.get("overallScore") is not None
    ]
    layout_overall = round(sum(all_scores) / len(all_scores), 4) if all_scores else 0.0

    layout["analysis"] = {
        "_source":      _SOURCE_TAG,
        "persona":      persona,
        "depth":        depth,
        "timestamp":    timestamp,
        "overallScore": layout_overall,
        "bestRoom":     best_room,
        "worstRoom":    worst_room,
    }

    numeric  = layout_id.replace("Layout-", "").replace("layout-", "").strip()
    out_file = layout_output_dir / "Layout-{}_modified.json".format(numeric)

    try:
        layout_output_dir.mkdir(parents=True, exist_ok=True)
        out_file.write_text(
            json.dumps(layout, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print("[output_writer] Analysis written to {}".format(out_file.name))
    except OSError as exc:
        print("[output_writer] Write failed: {}".format(exc))


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _safe_float(value, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _parse_scores(scores_json: str) -> dict:
    """Returns {roomId: {"overallScore": float, "comfortScores": {...}}}"""
    if not scores_json:
        return {}
    try:
        data = json.loads(scores_json)
    except json.JSONDecodeError:
        return {}
    result = {}
    try:
        for room in data.get("rooms", []):
            rid = room.get("roomId") or room.get("id", "")
            if rid:
                result[rid] = {
                    "overallScore":  _safe_float(room.get("overallScore", 0.0)),
                    "comfortScores": {
                        k: _safe_float(v)
                        for k, v in room.get("comfortScores", {}).items()
                    },
                }
    except Exception as exc:
        print("[output_writer] Warning in _parse_scores: {}".format(exc))
    return result


def _parse_conflicts(conflicts_json: str) -> dict:
    """
    Returns {roomId_or_roomName: ["acoustic", "thermal", ...]}
    GH returns conflicts as a plain list of sense name strings per room.
    Also handles the dict format just in case.
    """
    if not conflicts_json:
        return {}
    try:
        data = json.loads(conflicts_json)
    except json.JSONDecodeError:
        return {}
    result = {}
    try:
        for room in data.get("flaggedRooms", []):
            rid = (room.get("roomId")
                   or room.get("id")
                   or room.get("roomName", ""))
            if not rid:
                continue
            senses = []
            for c in room.get("conflicts", []):
                if isinstance(c, str):
                    senses.append(c)
                elif isinstance(c, dict):
                    for sense in ("thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"):
                        if sense in c:
                            senses.append(sense)
                            break
            result[rid] = senses
    except Exception as exc:
        print("[output_writer] Warning in _parse_conflicts: {}".format(exc))
    return result


def _parse_suggestions(suggestions_json: str) -> dict:
    """Returns {roomId_or_roomName: [{"sense", "priority", "suggestion"}, ...]}"""
    if not suggestions_json:
        return {}
    try:
        data = json.loads(suggestions_json)
    except json.JSONDecodeError:
        return {}
    result = {}
    try:
        for room in data.get("improvements", []):
            rid = (room.get("roomId")
                   or room.get("id")
                   or room.get("roomName", ""))
            if not rid:
                continue
            suggestions = []
            for i, s in enumerate(room.get("suggestions", []), start=1):
                suggestions.append({
                    "sense":      s.get("sense", ""),
                    "priority":   i,
                    "suggestion": s.get("suggestion", ""),
                })
            result[rid] = suggestions
    except Exception as exc:
        print("[output_writer] Warning in _parse_suggestions: {}".format(exc))
    return result
