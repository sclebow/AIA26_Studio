from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_TIME_SLOTS = [
    "06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
    "12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
    "18:00", "19:00", "20:00", "21:00", "22:00",
]

PERSONA_COLORS = [
    "#4A7CA8",
    "#F5A020",
    "#00C7D4",
    "#D94020",
    "#7A8FA3",
]

SYSTEM_PROMPT = (
    "You are generating a realistic residential daily routine for visualization. "
    "Return valid JSON with exactly this shape: "
    '{"time_slots":[],"personas":[{"persona":"","color":"","steps":[]}]}. '
    "Return only JSON, no explanation.\n\n"
    "Output format:\n"
    "- steps has one entry per time slot: null when the person is away, "
    'or {"room": "<room_id>", "label": "<activity>"} when at home. '
    "Only use room ids from the provided rooms list. "
    "Labels: sleeping, showering, working, studying, relaxing, cooking, playing, napping, dressing.\n"
    "- Do not use storage, walkincloset, or circulation as activity spaces.\n"
    "- Colors are hex strings.\n\n"
    "Schedule rules — STRICT PRIORITY ORDER:\n"
    "1. THE BRIEF IS ABSOLUTE. Read every word of the user brief and apply it exactly.\n"
    "   The defaults below are ONLY for time slots the brief does not mention.\n"
    "   If the brief says someone works from home, only THAT person gets a workspace during work hours —\n"
    "   the other adults follow their own stated schedule or the default away schedule.\n"
    "   Never assume a second person also works from home unless the brief says so.\n"
    "   - Person with a studio/office room: work in that specific room, slots 09:00–17:00 inclusive.\n"
    "   - Person described as WFH but no dedicated room: work in living or bedroom, 09:00–17:00 inclusive.\n"
    "   - 09:00–17:00 inclusive means the 09:00 slot AND the 17:00 slot are both labeled 'working'.\n"
    "   - Never put two people in the same room at the same time (exception: couple sleeping together).\n"
    "2. DEFAULTS — only for slots not covered by the brief:\n"
    "   - Adult going to office: null 08:00–17:00, home from 18:00.\n"
    "   - Adult working from home (stated in brief): working 09:00–17:00 inclusive.\n"
    "   - Child/teen: null during school hours, home from 15:00 or as stated.\n"
    "   - Baby/infant: sleeping and relaxing at home all day.\n"
    "   - Retired/stay-at-home: relaxing in living areas during the day.\n\n"
    "Sleep:\n"
    "- Couple share the largest bedroom. A studio/office bedroom is only used 09:00–17:00 — that person still sleeps in the couple's bedroom.\n"
    "- Each child gets their own bedroom if available; otherwise shares with another child.\n"
    "- Baby always sleeps in the parents' bedroom.\n\n"
    "Bathroom:\n"
    "- Never put two people in the same bathroom at the same time. Stagger visits.\n"
)


def _safe_json_loads(value: str | None) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _parse_household(topology_json: str | None) -> list[dict[str, str]]:
    payload = _safe_json_loads(topology_json)
    household_raw = payload.get("household") if isinstance(payload.get("household"), list) else []
    household: list[dict[str, str]] = []
    for member in household_raw:
        if not isinstance(member, dict):
            continue
        name = _string(member.get("name"))
        relationship = _string(member.get("relationship"))
        info = _string(member.get("info"))
        if not name and not relationship and not info:
            continue
        household.append({"name": name, "relationship": relationship, "info": info})
    return household


def _parse_description(topology_json: str | None) -> str:
    payload = _safe_json_loads(topology_json)
    return _string(payload.get("description"))


def _layout_rooms(layout_data: dict[str, Any]) -> list[dict[str, str | None]]:
    rooms_raw = layout_data.get("rooms") if isinstance(layout_data.get("rooms"), list) else []
    rooms: list[dict[str, str | None]] = []
    for room in rooms_raw:
        if not isinstance(room, dict):
            continue
        room_id = room.get("id")
        attributes = room.get("attributes") if isinstance(room.get("attributes"), dict) else {}
        program = _string(attributes.get("program")).lower() or None
        name = _string(room.get("name")) or None
        area = attributes.get("area") if isinstance(attributes.get("area"), (int, float)) else None
        if room_id is None:
            continue
        rooms.append({"id": str(room_id), "program": program, "name": name, "area": area})
    return rooms


def _first_room_id(rooms: list[dict[str, str | None]], *programs: str) -> str | None:
    for program in programs:
        for room in rooms:
            if room.get("program") == program:
                room_id = room.get("id")
                if isinstance(room_id, str) and room_id:
                    return room_id
    return None


def _fallback_room(*room_ids: str | None) -> str | None:
    for room_id in room_ids:
        if isinstance(room_id, str) and room_id:
            return room_id
    return None


def _member_label(member: dict[str, str], index: int) -> str:
    name = _string(member.get("name"))
    relationship = _string(member.get("relationship"))
    if name:
        return name
    if relationship:
        return relationship.title()
    return f"Resident {index + 1}"


def _is_baby(member: dict[str, str]) -> bool:
    text = " ".join([member.get("relationship", ""), member.get("info", "")]).lower()
    return bool(re.search(r"\b(baby|babies|infant|newborn)\b", text)) or bool(
        re.search(r"\b\d+\s*months?\s*(?:old)?\b", text)
    )


def _member_profile(member: dict[str, str]) -> str:
    if _is_baby(member):
        return "baby"
    text = " ".join([_string(member.get("relationship")), _string(member.get("info"))]).lower()
    if re.search(r"\b(child|kid|toddler|teen|student|school|daughter|son|girl|boy)\b", text):
        return "child_school"
    # age under 18 expressed as "N years old" or "N-year-old"
    age_match = re.search(r"\b(\d+)\s*[-\s]?years?\s*[-\s]?old\b", text)
    if age_match and int(age_match.group(1)) < 18:
        return "child_school"
    if re.search(r"\b(retired|elderly|senior|older|mobility)\b", text):
        return "adult_home"
    if re.search(r"\b(work from home|works from home|wfh|remote|home office|studio)\b", text):
        return "adult_home"
    return "adult_default"


def _study_implies_home_worker(description: str) -> bool:
    lower = description.lower()
    return bool(re.search(r"\b(study|office|workspace|studio)\b", lower)) or \
           bool(re.search(r"\bwork[s]?\s+from\s+home\b|\bwfh\b|\bremote\s+work\b", lower))


def _home_worker_index(household: list[dict[str, str]], description: str) -> int | None:
    """Return the index of the household member linked to a home workspace in the description.

    Tries name matching first (e.g. "James's studio" → James).
    Falls back to the first adult without an explicit wfh profile.
    """
    if not _study_implies_home_worker(description):
        return None
    desc_lower = description.lower()
    for i, member in enumerate(household):
        name = _string(member.get("name"))
        if name and name.lower() in desc_lower:
            return i
    adult_indexes = _adult_member_indexes(household)
    for i in adult_indexes:
        if _member_profile(household[i]) != "adult_home":
            return i
    return None


def _sorted_bedrooms(rooms: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    return sorted(
        [r for r in rooms if r.get("program") == "bed"],
        key=lambda r: float(r.get("area") or 0.0),
        reverse=True,
    )


def _office_room_id(rooms: list[dict[str, str | None]]) -> str | None:
    ranked_beds = _sorted_bedrooms(rooms)
    if len(ranked_beds) >= 2:
        room_id = ranked_beds[1].get("id")
        if isinstance(room_id, str) and room_id:
            return room_id
    living = _first_room_id(rooms, "living")
    if living:
        return living
    if ranked_beds:
        room_id = ranked_beds[0].get("id")
        if isinstance(room_id, str) and room_id:
            return room_id
    return None


def _adult_member_indexes(household: list[dict[str, str]]) -> list[int]:
    return [
        i for i, m in enumerate(household)
        if _member_profile(m) not in ("child_school", "baby")
    ]


def _profiles_for_household(household: list[dict[str, str]], description: str) -> list[str]:
    profiles = [_member_profile(m) for m in household]
    idx = _home_worker_index(household, description)
    if idx is not None and profiles[idx] != "adult_home":
        profiles[idx] = "adult_home"
    return profiles


_COUPLE_RE = re.compile(
    r"\b(partner|spouse|husband|wife|boyfriend|girlfriend|parent|mother|father|mom|dad)\b"
)
_SOLO_RE = re.compile(
    r"\b(friend|roommate|student|tenant|colleague|housemate|flatmate)\b"
)


def _is_couple_member(member: dict[str, str]) -> bool:
    text = " ".join([member.get("relationship", ""), member.get("info", "")]).lower()
    return bool(_COUPLE_RE.search(text))


def _is_solo_adult(member: dict[str, str]) -> bool:
    text = " ".join([member.get("relationship", ""), member.get("info", "")]).lower()
    return bool(_SOLO_RE.search(text))


def _assign_sleep_rooms(
    household: list[dict[str, str]],
    rooms: list[dict[str, str | None]],
    description: str,
) -> list[str | None]:
    """Return a bedroom ID for each household member's sleep slot.

    Rules:
    - Couple (partners/parents) share the largest bedroom.
    - Babies sleep in the parents'/couple's bedroom.
    - Each child gets their own bedroom; falls back to sharing with other children
      if there are not enough rooms.
    - Solo adults (friends, students, roommates) each get their own bedroom.
    - Home office bedroom excluded from sleep assignment.
    """
    bed_rooms = _sorted_bedrooms(rooms)
    if not bed_rooms:
        return [None] * len(household)

    office_id: str | None = _office_room_id(rooms) if _study_implies_home_worker(description) else None
    available = [r for r in bed_rooms if r.get("id") != office_id] or bed_rooms
    room_queue: list[str] = [r["id"] for r in available if isinstance(r.get("id"), str)]

    babies: list[int] = []
    children: list[int] = []
    all_adults: list[int] = []
    for i, member in enumerate(household):
        if _is_baby(member):
            babies.append(i)
        elif _member_profile(member) == "child_school":
            children.append(i)
        else:
            all_adults.append(i)

    # Identify couple: adults with partner/parent keywords
    couple_candidates = [i for i in all_adults if _is_couple_member(household[i])]
    # If exactly 2 adults and neither is explicitly solo → treat as couple
    if not couple_candidates and len(all_adults) == 2 and not any(_is_solo_adult(household[i]) for i in all_adults):
        couple_candidates = list(all_adults)
    couple = couple_candidates[:2]
    solo_adults = [i for i in all_adults if i not in couple]

    assignment: list[str | None] = [None] * len(household)

    # Couple → largest room
    couple_room = room_queue.pop(0) if room_queue else None
    for i in couple:
        assignment[i] = couple_room
    # Babies → couple's room
    for i in babies:
        assignment[i] = couple_room

    # Children → one room each; share with each other if rooms run out
    first_child_room: str | None = None
    for i in children:
        if room_queue:
            rid = room_queue.pop(0)
            assignment[i] = rid
            if first_child_room is None:
                first_child_room = rid
        else:
            assignment[i] = first_child_room or couple_room

    # Solo adults (friends/students) → one room each
    for i in solo_adults:
        if room_queue:
            assignment[i] = room_queue.pop(0)
        else:
            assignment[i] = couple_room

    return assignment


def _default_steps(
    profile: str,
    rooms: list[dict[str, str | None]],
    bedroom_id: str | None = None,
) -> list[Step]:
    bed    = bedroom_id or _first_room_id(rooms, "bed")
    bath   = _first_room_id(rooms, "bath")
    living = _first_room_id(rooms, "living")
    office = _office_room_id(rooms)

    if profile == "baby":
        return [
            _step(_fallback_room(bed, living),   "sleeping"),   # 06:00
            _step(_fallback_room(bed, living),   "sleeping"),   # 07:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 08:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 09:00
            _step(_fallback_room(bed, living),   "napping"),    # 10:00
            _step(_fallback_room(bed, living),   "napping"),    # 11:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 12:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 13:00
            _step(_fallback_room(bed, living),   "napping"),    # 14:00
            _step(_fallback_room(bed, living),   "napping"),    # 15:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 16:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 17:00
            _step(_fallback_room(living, bed),   "relaxing"),   # 18:00
            _step(_fallback_room(bed, living),   "sleeping"),   # 19:00
            _step(_fallback_room(bed, living),   "sleeping"),   # 20:00
            _step(_fallback_room(bed, living),   "sleeping"),   # 21:00
            _step(_fallback_room(bed, living),   "sleeping"),   # 22:00
        ]

    if profile == "child_school":
        return [
            _step(_fallback_room(bed, living),  "sleeping"),   # 06:00
            _step(_fallback_room(bath, bed),    "showering"),  # 07:00
            None,                                              # 08:00 school
            None,                                              # 09:00
            None,                                              # 10:00
            None,                                              # 11:00
            None,                                              # 12:00
            None,                                              # 13:00
            None,                                              # 14:00
            None,                                              # 15:00
            _step(_fallback_room(living, bed),  "relaxing"),   # 16:00 home
            _step(_fallback_room(living, bed),  "relaxing"),   # 17:00
            _step(_fallback_room(living, bed),  "relaxing"),   # 18:00
            _step(_fallback_room(living, bed),  "relaxing"),   # 19:00
            _step(_fallback_room(living, bed),  "relaxing"),   # 20:00
            _step(_fallback_room(bed, living),  "sleeping"),   # 21:00
            _step(_fallback_room(bed, living),  "sleeping"),   # 22:00
        ]

    if profile == "adult_home":
        return [
            _step(_fallback_room(bed, living),         "sleeping"),  # 06:00
            _step(_fallback_room(bath, living, bed),   "showering"), # 07:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 08:00 breakfast/getting ready
            _step(_fallback_room(office, living, bed), "working"),   # 09:00
            _step(_fallback_room(office, living, bed), "working"),   # 10:00
            _step(_fallback_room(office, living, bed), "working"),   # 11:00
            _step(_fallback_room(living, office, bed), "relaxing"),  # 12:00 lunch
            _step(_fallback_room(office, living, bed), "working"),   # 13:00
            _step(_fallback_room(office, living, bed), "working"),   # 14:00
            _step(_fallback_room(office, living, bed), "working"),   # 15:00
            _step(_fallback_room(office, living, bed), "working"),   # 16:00
            _step(_fallback_room(office, living, bed), "working"),   # 17:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 18:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 19:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 20:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 21:00
            _step(_fallback_room(bed, living),         "sleeping"),  # 22:00
        ]

    # adult_default
    return [
        _step(_fallback_room(bed, living),       "sleeping"),  # 06:00
        _step(_fallback_room(bath, living, bed), "showering"), # 07:00
        None,                                                  # 08:00 away
        None,                                                  # 09:00
        None,                                                  # 10:00
        None,                                                  # 11:00
        None,                                                  # 12:00
        None,                                                  # 13:00
        None,                                                  # 14:00
        None,                                                  # 15:00
        None,                                                  # 16:00
        None,                                                  # 17:00 commute
        _step(_fallback_room(living, bed),       "relaxing"),  # 18:00 home
        _step(_fallback_room(living, bed),       "relaxing"),  # 19:00
        _step(_fallback_room(living, bed),       "relaxing"),  # 20:00
        _step(_fallback_room(living, bed),       "relaxing"),  # 21:00
        _step(_fallback_room(bed, living),       "sleeping"),  # 22:00
    ]


Step = dict[str, str] | None  # {"room": "...", "label": "..."} or None


def _step(room_id: str | None, label: str) -> Step:
    return {"room": room_id, "label": label} if room_id else None


def _step_room(step: Step) -> str | None:
    if step is None:
        return None
    if isinstance(step, dict):
        return step.get("room")
    return str(step)  # backward compat with plain string


def _reassign_from_bathroom(steps: list[Step], step_index: int, rooms: list[dict[str, str | None]]) -> Step:
    bed    = _first_room_id(rooms, "bed")
    living = _first_room_id(rooms, "living")
    prev_room = _step_room(steps[step_index - 1]) if step_index > 0 else None
    new_room = _fallback_room(prev_room, bed, living)
    return _step(new_room, "at home")


def _enforce_bathroom_spacing(personas: list[dict[str, Any]], rooms: list[dict[str, str | None]]) -> list[dict[str, Any]]:
    bathroom_ids = [r["id"] for r in rooms if r.get("program") == "bath" and isinstance(r.get("id"), str)]
    bathroom_set = set(bathroom_ids)
    if not bathroom_ids:
        return personas
    for slot in range(len(DEFAULT_TIME_SLOTS)):
        occupied: set[str] = set()
        for persona in personas:
            steps = persona.get("steps") if isinstance(persona.get("steps"), list) else []
            if slot >= len(steps):
                continue
            room_id = _step_room(steps[slot])
            if room_id not in bathroom_set:
                continue
            if room_id not in occupied:
                occupied.add(room_id)
            else:
                free = next((b for b in bathroom_ids if b not in occupied), None)
                if free:
                    steps[slot] = _step(free, "showering")
                    occupied.add(free)
                else:
                    steps[slot] = _reassign_from_bathroom(steps, slot, rooms)
    return personas


def _fallback_routine(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    rooms = _layout_rooms(layout_data)
    household = _parse_household(topology_json)
    description = _parse_description(topology_json)
    profiles = _profiles_for_household(household, description)
    sleep_rooms = _assign_sleep_rooms(household, rooms, description)

    personas = []
    for index, member in enumerate(household):
        personas.append({
            "persona": _member_label(member, index),
            "color": PERSONA_COLORS[index % len(PERSONA_COLORS)],
            "steps": _default_steps(profiles[index], rooms, sleep_rooms[index]),
        })

    personas = _enforce_bathroom_spacing(personas, rooms)
    return {"time_slots": list(DEFAULT_TIME_SLOTS), "personas": personas}


def _stable_color_personas(
    personas: list[dict[str, Any]],
    topology_json: str | None,
) -> list[dict[str, Any]]:
    """Reorder personas to match household order and assign colors by household index.

    This keeps colors stable across routine regenerations even when the LLM
    returns personas in a different order.
    """
    household = _parse_household(topology_json)
    if not household:
        return [
            {**p, "color": PERSONA_COLORS[i % len(PERSONA_COLORS)]}
            for i, p in enumerate(personas)
        ]

    # Build name→index map from LLM personas (lowercase for fuzzy match)
    name_to_idx: dict[str, int] = {}
    for i, p in enumerate(personas):
        name = (p.get("persona") or "").strip().lower()
        if name:
            name_to_idx[name] = i

    used: set[int] = set()
    ordered: list[dict[str, Any]] = []

    for hi, member in enumerate(household):
        color = PERSONA_COLORS[hi % len(PERSONA_COLORS)]
        member_name = _string(member.get("name")).lower()
        member_rel = _string(member.get("relationship")).lower()

        idx = name_to_idx.get(member_name)
        if idx is None:
            idx = name_to_idx.get(member_rel)

        if idx is not None and idx not in used:
            ordered.append({**personas[idx], "color": color})
            used.add(idx)
        else:
            # fallback: next unused persona in LLM order
            for j, p in enumerate(personas):
                if j not in used:
                    ordered.append({**p, "color": color})
                    used.add(j)
                    break

    # append any leftover personas the LLM added beyond household size
    for j, p in enumerate(personas):
        if j not in used:
            ordered.append({**p, "color": PERSONA_COLORS[j % len(PERSONA_COLORS)]})

    return ordered


def _normalize_routine(value: Any, layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    """Validate the LLM-generated routine: keep LLM decisions, only reject invalid room IDs."""
    rooms = _layout_rooms(layout_data)
    valid_room_ids = {r["id"] for r in rooms if isinstance(r.get("id"), str)}

    if not isinstance(value, dict):
        return _fallback_routine(layout_data, topology_json)

    time_slots = value.get("time_slots") if isinstance(value.get("time_slots"), list) else []
    normalized_time_slots = [s.strip() for s in time_slots if isinstance(s, str) and s.strip()]
    if len(normalized_time_slots) != len(DEFAULT_TIME_SLOTS):
        normalized_time_slots = list(DEFAULT_TIME_SLOTS)

    room_program = {r["id"]: r.get("program", "") for r in rooms if isinstance(r.get("id"), str)}
    _PROGRAM_LABEL = {
        "bed": "sleeping", "bath": "showering", "walkincloset": "dressing",
        "living": "relaxing", "wc": "bathroom", "circulation": "at home", "storage": "at home",
    }

    personas_raw = value.get("personas") if isinstance(value.get("personas"), list) else []
    personas = []
    for index, item in enumerate(personas_raw):
        if not isinstance(item, dict):
            continue
        persona = _string(item.get("persona")) or f"Resident {index + 1}"
        steps_raw = item.get("steps") if isinstance(item.get("steps"), list) else []
        steps: list[Step] = []
        for i in range(len(DEFAULT_TIME_SLOTS)):
            raw = steps_raw[i] if i < len(steps_raw) else None
            if raw is None:
                steps.append(None)
            elif isinstance(raw, dict):
                room_id = str(raw.get("room", "")).strip()
                label   = str(raw.get("label", "")).strip()
                if not label:
                    label = _PROGRAM_LABEL.get(room_program.get(room_id, ""), "at home")
                steps.append({"room": room_id, "label": label} if room_id in valid_room_ids else None)
            elif isinstance(raw, str):
                room_id = raw.strip()
                if room_id in valid_room_ids:
                    label = _PROGRAM_LABEL.get(room_program.get(room_id, ""), "at home")
                    steps.append({"room": room_id, "label": label})
                else:
                    steps.append(None)
            else:
                steps.append(None)
        personas.append({"persona": persona, "steps": steps})

    if not personas:
        return _fallback_routine(layout_data, topology_json)

    personas = _stable_color_personas(personas, topology_json)
    personas = _enforce_bathroom_spacing(personas, rooms)
    return {"time_slots": normalized_time_slots, "personas": personas}


def _format_household_notes(topology_json: str | None) -> str | None:
    """Return a named, per-person list of schedule facts from household[].info."""
    payload = _safe_json_loads(topology_json)
    members = payload.get("household", [])
    if not isinstance(members, list):
        return None
    lines = []
    for m in members:
        if not isinstance(m, dict):
            continue
        info = (m.get("info") or "").strip()
        if not info:
            continue
        name = (m.get("name") or "").strip()
        rel  = (m.get("relationship") or "").strip()
        label = f"{name} ({rel})" if name and rel else (name or rel or "household member")
        lines.append(f"- {label}: {info}")
    return "\n".join(lines) if lines else None



def _parse_routine_json(content: str) -> dict[str, Any]:
    import ast
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
        try:
            return ast.literal_eval(match.group(0))
        except (ValueError, SyntaxError):
            pass
    raise ValueError(f"Cannot parse routine LLM response: {content[:120]}")


def build_routine_node(llm: Any) -> Any:
    def routine(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        topology_json = state.get("topology_graph_json_string")
        user_prompt = state.get("user_prompt", "")
        feedback_history = state.get("feedback_history", [])
        iteration = state.get("iteration", 0)

        if not layout_json:
            return {"routine_json_string": None, "iteration": iteration + 1}

        # Build the full brief from all conversation turns so nothing is lost.
        all_turns = [t for t in feedback_history if isinstance(t, str) and t.strip()]
        if user_prompt.strip() and user_prompt.strip() not in all_turns:
            all_turns.append(user_prompt.strip())
        full_brief = "\n\n".join(all_turns) if all_turns else "(none)"

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            if not isinstance(layout_data, dict):
                raise ValueError("Routine layout is not valid JSON.")

            rooms = _layout_rooms(layout_data)

            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"User brief (full conversation — apply every detail literally):\n{full_brief}\n\n"
                    f"Available rooms (use only these IDs in steps):\n{json.dumps(rooms, indent=2)}\n\n"
                    f"Time slots: {', '.join(DEFAULT_TIME_SLOTS)}\n\n"
                    "Generate the daily routine for every person mentioned in the brief. Return only the required JSON."
                )},
            ]
            response = llm.invoke(llm_messages)
            raw = response.content
            if isinstance(raw, str) and '"final_response"' in raw:
                try:
                    wrapper = json.loads(raw)
                    raw = wrapper.get("final_response", raw)
                except Exception:
                    pass
            parsed = _parse_routine_json(raw if isinstance(raw, str) else json.dumps(raw))
            routine_payload = _normalize_routine(parsed, layout_data, topology_json)
            return {"routine_json_string": json.dumps(routine_payload), "iteration": iteration + 1}
        except Exception as e:
            print(f"[routine] LLM failed, using fallback: {e}", flush=True)
            fallback = _fallback_routine(
                json.loads(layout_json) if isinstance(layout_json, str) else layout_json,
                topology_json,
            )
            return {"routine_json_string": json.dumps(fallback), "iteration": iteration + 1}

    return routine
