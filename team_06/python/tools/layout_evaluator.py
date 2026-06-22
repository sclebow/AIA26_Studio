import networkx as nx
import json
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
    "living":       1.0,
    "bed":          0.8,
    "walkincloset": 0.3,
    "circulation":  0.2,
    "bath":         0.2,
    "wc":           0.1,
    "storage":      0.1,
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


# ─── Access fit ───────────────────────────────────────────────────────────────

def _build_door_graph(layout_data: dict) -> dict[str, set[str]]:
    """Return {room_id: set of directly connected room_ids} from door data."""
    graph: dict[str, set[str]] = {}
    for door in layout_data.get("doors", []):
        connected = door.get("attributes", {}).get("connectsRooms", [])
        for rid in connected:
            for other in connected:
                if rid != other:
                    graph.setdefault(rid, set()).add(other)
    return graph


def compute_access_fit(layout_data: dict, topology_json: str | None) -> dict | None:
    """Score how many requested door-access pairs exist in the layout."""
    if not topology_json:
        return None
    try:
        brief = json.loads(topology_json)
    except (json.JSONDecodeError, TypeError):
        return None

    access_pairs = brief.get("graph", brief).get("access_pairs", [])
    if not access_pairs:
        return None

    room_program: dict[str, str] = {
        r["id"]: normalize_program(r.get("attributes", {}).get("program", ""))
        for r in layout_data.get("rooms", [])
        if r.get("id")
    }
    door_graph = _build_door_graph(layout_data)

    satisfied = 0
    details: list[str] = []
    for pair in access_pairs:
        if len(pair) != 2:
            continue
        pa, pb = normalize_program(str(pair[0])), normalize_program(str(pair[1]))
        rooms_a = {rid for rid, p in room_program.items() if p == pa}
        rooms_b = {rid for rid, p in room_program.items() if p == pb}
        found = any(other in door_graph.get(ra, set()) for ra in rooms_a for other in rooms_b)
        label = f"{pa} ↔ {pb}"
        if found:
            satisfied += 1
            details.append(f"✓ {label}")
        else:
            details.append(f"✗ {label}")

    total = len(access_pairs)
    if total == 0:
        return None
    return {"score": round(satisfied / total * 100), "details": details}


# ─── Adjacency fit ────────────────────────────────────────────────────────────

def _adjacent_program_pairs(layout_data: dict) -> set[tuple[str, str]]:
    """Return the set of (prog_a, prog_b) pairs that share a wall (≥2 shared vertices)."""
    rooms = layout_data.get("rooms", [])
    room_info: list[tuple[str, frozenset]] = []
    for room in rooms:
        prog = normalize_program(room.get("attributes", {}).get("program", ""))
        geom = room.get("geometry", [])
        if prog and len(geom) >= 3:
            verts = frozenset((round(p[0], 1), round(p[1], 1)) for p in geom if len(p) >= 2)
            room_info.append((prog, verts))

    pairs: set[tuple[str, str]] = set()
    for i in range(len(room_info)):
        for j in range(i + 1, len(room_info)):
            pa, va = room_info[i]
            pb, vb = room_info[j]
            if len(va & vb) >= 2:
                pairs.add((pa, pb))
                pairs.add((pb, pa))
    return pairs


def compute_adjacency_fit(layout_data: dict, topology_json: str | None) -> dict | None:
    """Score adjacency and separation constraints from the brief."""
    if not topology_json:
        return None
    try:
        brief = json.loads(topology_json)
    except (json.JSONDecodeError, TypeError):
        return None

    graph = brief.get("graph", brief)
    adj_pairs     = [(p, True)  for p in graph.get("adjacency_pairs", [])]
    not_adj_pairs = [(p, False) for p in graph.get("not_adjacency_pairs", [])]
    all_pairs = adj_pairs + not_adj_pairs
    if not all_pairs:
        return None

    actual_adj = _adjacent_program_pairs(layout_data)
    satisfied = 0
    details: list[str] = []

    for pair, should_adj in all_pairs:
        if len(pair) != 2:
            continue
        pa, pb = normalize_program(str(pair[0])), normalize_program(str(pair[1]))
        is_adj = (pa, pb) in actual_adj
        label = f"{pa} ~ {pb}" if should_adj else f"{pa} ✕ {pb}"
        if is_adj == should_adj:
            satisfied += 1
            details.append(f"✓ {label}")
        else:
            details.append(f"✗ {label}")

    total = len(all_pairs)
    if total == 0:
        return None
    return {"score": round(satisfied / total * 100), "details": details}


# ─── Size (room minimums + brief preferences) ─────────────────────────────────

SIZE_THRESHOLDS: dict[str, dict[str, float]] = {
    "living":       {"small": 12.0, "medium": 20.0, "large": 28.0},
    "bed":          {"small":  9.0, "medium": 12.0, "large": 16.0},
    "bath":         {"small":  3.0, "medium":  5.0, "large":  7.0},
    "wc":           {"small":  1.5, "medium":  2.5, "large":  4.0},
    "walkincloset": {"small":  2.5, "medium":  4.5, "large":  7.0},
    "storage":      {"small":  2.5, "medium":  5.0, "large":  8.0},
    "circulation":  {"small":  3.0, "medium":  6.0, "large": 10.0},
}


def compute_size_score(layout_data: dict, topology_json: str | None) -> dict | None:
    """Score room sizes against absolute minimums and brief-stated size preferences."""
    rooms = layout_data.get("rooms", [])
    if not rooms:
        return None

    details: list[str] = []
    satisfied = 0.0
    total = 0

    for room in rooms:
        program = normalize_program(room.get("attributes", {}).get("program", ""))
        if program not in RULES:
            continue
        rule = RULES[program]
        area = room.get("attributes", {}).get("area", 0.0)
        geom = room.get("geometry", [])
        room_name = room.get("name", room.get("id", "?"))
        total += 1
        room_issues: list[str] = []

        if area > 0 and area < rule["min_area"]:
            room_issues.append(f"area {area:.1f}<{rule['min_area']}m²")

        if geom and len(geom) >= 3:
            xs = [p[0] for p in geom]
            ys = [p[1] for p in geom]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            if w > 0 and h > 0:
                min_edge = min(w, h)
                ratio = max(w / h, h / w)
                if min_edge < rule["min_edge"]:
                    room_issues.append(f"edge {min_edge:.1f}<{rule['min_edge']}m")
                if ratio > rule["max_ratio"]:
                    room_issues.append(f"ratio {ratio:.1f}>{rule['max_ratio']}")

        if room_issues:
            details.append(f"✗ {room_name}: {', '.join(room_issues)}")
        else:
            satisfied += 1
            details.append(f"✓ {room_name}")

    if topology_json:
        try:
            brief = json.loads(topology_json)
            room_sizes = brief.get("graph", brief).get("room_sizes", [])
            for item in room_sizes:
                if len(item) != 2:
                    continue
                prog = normalize_program(str(item[0]))
                req_size = str(item[1]).lower()
                thresholds = SIZE_THRESHOLDS.get(prog, {})
                min_area_for_size = thresholds.get(req_size, 0.0)
                matching = [
                    r for r in rooms
                    if normalize_program(r.get("attributes", {}).get("program", "")) == prog
                ]
                total += 1
                if not matching:
                    details.append(f"✗ {prog} ({req_size}): not present")
                    continue
                best_area = max(r.get("attributes", {}).get("area", 0.0) for r in matching)
                if best_area >= min_area_for_size:
                    satisfied += 1
                    details.append(f"✓ {prog} {req_size} ({best_area:.1f}m²)")
                else:
                    details.append(f"✗ {prog}: {best_area:.1f}m² for {req_size} (min {min_area_for_size:.1f}m²)")
        except Exception:
            pass

    if total == 0:
        return None
    return {"score": round(satisfied / total * 100), "details": details}