import networkx as nx
import json
import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Paths to rules and synonyms
RULES_PATH = Path(__file__).parent.parent / "rules" / "room_size.json"
SYNONYMS_PATH = Path(__file__).parent.parent / "rules" / "room_synonyms.json"

# Load rules and synonyms once at import
with open(RULES_PATH, encoding="utf-8") as f:
    RULES = json.load(f)
with open(SYNONYMS_PATH, encoding="utf-8") as f:
    SYNONYMS = json.load(f)

# Minimal daylight requirements (can also be moved to rules if preferred)
DAYLIGHT_REQUIRED = {"bed": 0.05, "living": 0.1}

def normalize_program(prog: str) -> str:
    if not prog:
        return ""
    p = prog.strip().lower().replace(' ', '').replace('-', '_')
    return SYNONYMS.get(p, p)

def evaluate_layout(layout_data: dict, expected_topology_json: str = None) -> dict:
    """
    Evaluates a generated layout against relaxed architectural rules,
    including room presence, proportions, minimum dimensions, and doors.
    """
    issues = []
    rooms = layout_data.get('rooms', [])
    doors = layout_data.get('doors', [])

    # 1. Check topology matches
    if expected_topology_json:
        try:
            expected_graph = nx.node_link_graph(json.loads(expected_topology_json))
            expected_programs = [normalize_program(d.get('program', '')) for _, d in expected_graph.nodes(data=True)]
            actual_programs = [normalize_program(r.get('attributes', {}).get('program', '')) for r in rooms]

            from collections import Counter
            expected_counts = Counter(p for p in expected_programs if p)
            actual_counts = Counter(p for p in actual_programs if p)

            for prog, count in expected_counts.items():
                if actual_counts.get(prog, 0) < count:
                    issues.append(f"Missing room(s): Expected at least {count} '{prog}', but found {actual_counts.get(prog, 0)}.")
        except Exception as e:
            logger.error(f"Could not parse expected topology: {e}")
            issues.append(f"Error parsing expected topology: {e}")

    # 2. Check doors connectivity
    rooms_with_doors = set()
    for door in doors:
        connected = door.get('attributes', {}).get('connectsRooms', [])
        for r_id in connected:
            rooms_with_doors.add(r_id)

    # 3. Check Room Dimensions, Proportions, Area, and Daylight
    for room in rooms:
        program = normalize_program(room.get('attributes', {}).get('program', ''))
        room_name = room.get('name', room['id'])

        # Door check
        if room['id'] not in rooms_with_doors:
            issues.append(f"Connectivity: '{room_name}' is not connected to any doors.")

        geom = room.get('geometry', [])
        area = room.get('attributes', {}).get('area', 0.0)

        if geom and len(geom) >= 3:
            xs = [pt[0] for pt in geom]
            ys = [pt[1] for pt in geom]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)

            if width > 0 and height > 0:
                min_edge = min(width, height)
                ratio = max(width/height, height/width)

                # Apply specific rules if the program is mapped
                if program in RULES:
                    rule = RULES[program]

                    if area > 0 and area < rule['min_area']:
                        issues.append(f"Area: '{room_name}' is {area:.1f} m² (minimum for {program} is {rule['min_area']} m²).")

                    if min_edge < rule['min_edge']:
                        issues.append(f"Dimension: '{room_name}' min edge is {min_edge:.1f}m (minimum for {program} is {rule['min_edge']}m).")

                    if ratio > rule['max_ratio']:
                        issues.append(f"Proportion: '{room_name}' ratio is {ratio:.1f}:1 (maximum for {program} is {rule['max_ratio']}:1).")

    return {
        "passed": len(issues) == 0,
        "issues": issues
    }

def summarize_evaluation(layout_data: dict, expected_topology_json: str = None) -> dict:
    eval_result = evaluate_layout(layout_data, expected_topology_json)
    rooms = layout_data.get('rooms', [])
    daylight_scores = []
    rooms_summary = {}
    for room in rooms:
        room_id = room.get('id')
        program = room.get('attributes', {}).get('program', 'unknown')
        daylight_score = room.get('attributes', {}).get('daylight', None)
        rooms_summary[room_id] = {
            "name": room.get('name', 'Unknown'),
            "program": program,
            "daylight": daylight_score
        }
        if isinstance(daylight_score, (int, float)):
            daylight_scores.append(daylight_score)
    daylight_stats = {}
    if daylight_scores:
        daylight_stats = {
            "min": min(daylight_scores),
            "max": max(daylight_scores),
            "avg": sum(daylight_scores) / len(daylight_scores),
        }
    area = layout_data.get('apartment', {}).get('attributes', {}).get('area', 'N/A')
    return {
        "passed": eval_result.get("passed", False),
        "evaluation_issues": eval_result.get("issues", []),
        "num_rooms": len(rooms),
        "area": area,
        "rooms": rooms_summary,
        "daylight_stats": daylight_stats,
    }


def compute_room_fit_score(layout_data: dict, topology_json: str | None) -> dict | None:
    """Score how many of the requested room programs are present in the layout."""
    if not topology_json:
        return None
    try:
        brief = json.loads(topology_json)
    except (json.JSONDecodeError, TypeError):
        return None

    graph = brief.get("graph", brief)
    requested_programs = graph.get("programs", [])
    if not requested_programs:
        return None

    from collections import Counter
    requested_counts = Counter(
        normalize_program(p) for p in requested_programs if isinstance(p, str) and p.strip()
    )
    if not requested_counts:
        return None

    rooms = layout_data.get("rooms", [])
    actual_counts = Counter(
        normalize_program(r.get("attributes", {}).get("program", ""))
        for r in rooms if isinstance(r, dict)
    )

    details: list[str] = []
    matched = 0
    total = 0
    for program, count in requested_counts.items():
        actual = actual_counts.get(program, 0)
        satisfied = min(actual, count)
        matched += satisfied
        total += count
        label = f"{program} × {count}" if count > 1 else program
        details.append(f"✓ {label}" if actual >= count else f"✗ {label}: {actual}/{count}")

    score = round(matched / total * 100) if total > 0 else 100
    return {"score": score, "details": details}


DAYLIGHT_WEIGHTS = {
    "living": 1.0,
    "bed": 0.8,
    "foyer": 0.3,
    "bath": 0.2,
    "extra": 0.1,
}


def compute_daylight_score(layout_data: dict) -> dict | None:
    """Deterministic daylight score from room daylight attributes.

    Returns None if no daylight data is present in the layout,
    so callers can tell the difference between 'no data' and 'score 0'.
    Rooms are weighted by type: living > bedroom > foyer > bathroom > extra.
    """
    rooms = layout_data.get("rooms", [])
    room_scores: list[dict] = []

    for room in rooms:
        attrs = room.get("attributes", {})
        daylight_val = attrs.get("daylight")
        if not isinstance(daylight_val, (int, float)):
            continue
        program = normalize_program(attrs.get("program", ""))
        threshold = DAYLIGHT_REQUIRED.get(program, 0.05)
        # Normalise: threshold → 50, 2× threshold → 100, 0 → 0
        room_score = min(100, int(daylight_val / threshold * 50)) if threshold > 0 else 50
        weight = DAYLIGHT_WEIGHTS.get(program, 0.5)
        room_scores.append({
            "name": room.get("name", room.get("id", "?")),
            "program": program,
            "value": round(daylight_val, 3),
            "score": room_score,
            "threshold": threshold,
            "meets_minimum": daylight_val >= threshold,
            "_weight": weight,
        })

    if not room_scores:
        return None

    total_weight = sum(r["_weight"] for r in room_scores)
    overall = round(sum(r["score"] * r["_weight"] for r in room_scores) / total_weight) if total_weight > 0 else 0

    # Remove internal weight field before returning
    clean_rooms = [{k: v for k, v in r.items() if k != "_weight"} for r in room_scores]
    return {
        "score": overall,
        "rooms": clean_rooms,
    }