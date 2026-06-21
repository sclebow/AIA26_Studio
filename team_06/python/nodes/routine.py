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
    '{"time_slots":[],"personas":[{"persona":"","color":"","steps":[]}]}.'
    "\n\nRules:\n"
    "- Return only JSON, no explanation.\n"
    '- steps is a list with one entry per time slot: null when the person is away, '
    'or an object {"room": "<room_id>", "label": "<activity>"} when they are home. '
    "room must be a valid room id from the rooms list. "
    "label is a short human-readable activity: sleeping, showering, working, studying, relaxing, cooking, playing, napping, dressing, etc.\n"
    "- Only use room ids that appear in the provided rooms list.\n"
    "- The available room programs are: bed, bath, wc, living, circulation, storage, walkincloset.\n"
    "- Do not use storage, walkincloset, or circulation as living or working spaces.\n"
    "- Keep colors as simple hex strings.\n"
    "\nSleep rules:\n"
    "- A couple or partners share the LARGEST bedroom (first in bedrooms_by_area).\n"
    "- A baby or infant always sleeps in the same bedroom as the parent(s) — never alone in a separate room.\n"
    "- Each child gets their own bedroom if one is available (next in bedrooms_by_area after the couple's). "
    "If no separate bedroom is available, children share the parents' bedroom.\n"
    "- Friends, students, or roommates each get their own bedroom.\n"
    "- Use bedrooms_by_area (largest first) to assign in this order: couple, then children, then solo adults.\n"
    "\nBathroom rules:\n"
    "- Every person must appear in a bathroom room (program: bath) for at least one slot between 06:00 and 09:00.\n"
    "- Never assign two people to the same bathroom at the same time slot.\n"
    "- Stagger visits across consecutive slots (person A at 07:00, person B at 08:00) "
    "or place two people in two different bathrooms at the same slot if the layout has two.\n"
    "\nSchedule — build each person's routine in this order:\n"
    "1. EXPLICIT CONSTRAINTS FIRST: read the description carefully and extract every time-specific or "
    "activity-specific detail per person (e.g. 'Susan returns at 14:00', 'James works from home in his studio', "
    "'Sarah studies in her room after school'). These are hard — apply them exactly.\n"
    "2. FILL GAPS WITH DEFAULTS: for any slot not covered by an explicit constraint, apply sensible defaults "
    "based on the person's role:\n"
    "   - couple/parents at home: sleeping at night, showering in the morning, working from home or away during the day, relaxing in the evening\n"
    "   - children/teens: sleeping at night, showering in the morning, at school (null) during the day, home in the afternoon\n"
    "   - babies: sleeping at night and for naps, relaxing at home the rest of the day\n"
    "   - adults away for work: null during work hours, home in the evening\n"
    "   - retired/stay-at-home: mostly at home in living areas during the day\n"
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
    # routine_description is schedule-focused with person names — prefer it for routine generation
    return _string(payload.get("routine_description")) or _string(payload.get("description"))


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
    if re.search(r"\b(child|kid|toddler|teen|student|school)\b", text):
        return "child_school"
    if re.search(r"\b(retired|elderly|senior|older|mobility)\b", text):
        return "adult_home"
    if re.search(r"\b(work from home|works from home|wfh|remote|home office|studio)\b", text):
        return "adult_home"
    return "adult_default"


def _study_implies_home_worker(description: str) -> bool:
    return bool(re.search(r"\b(study|office|workspace|studio)\b", description.lower()))


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
            _step(_fallback_room(office, living, bed), "working"),   # 08:00
            _step(_fallback_room(office, living, bed), "working"),   # 09:00
            _step(_fallback_room(office, living, bed), "working"),   # 10:00
            _step(_fallback_room(office, living, bed), "working"),   # 11:00
            _step(_fallback_room(living, office, bed), "relaxing"),  # 12:00 lunch
            _step(_fallback_room(office, living, bed), "working"),   # 13:00
            _step(_fallback_room(office, living, bed), "working"),   # 14:00
            _step(_fallback_room(office, living, bed), "working"),   # 15:00
            _step(_fallback_room(living, office, bed), "relaxing"),  # 16:00
            _step(_fallback_room(living, bed),         "relaxing"),  # 17:00
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

    personas_raw = value.get("personas") if isinstance(value.get("personas"), list) else []
    personas = []
    for index, item in enumerate(personas_raw):
        if not isinstance(item, dict):
            continue
        persona = _string(item.get("persona")) or f"Resident {index + 1}"
        color = _string(item.get("color")) or PERSONA_COLORS[index % len(PERSONA_COLORS)]
        steps_raw = item.get("steps") if isinstance(item.get("steps"), list) else []
        steps: list[Step] = []
        for i in range(len(DEFAULT_TIME_SLOTS)):
            raw = steps_raw[i] if i < len(steps_raw) else None
            if raw is None:
                steps.append(None)
            elif isinstance(raw, dict):
                room_id = str(raw.get("room", "")).strip()
                label   = str(raw.get("label", "")).strip()
                steps.append({"room": room_id, "label": label} if room_id in valid_room_ids else None)
            elif isinstance(raw, str):
                room_id = raw.strip()
                steps.append({"room": room_id, "label": ""} if room_id in valid_room_ids else None)
            else:
                steps.append(None)
        personas.append({"persona": persona, "color": color, "steps": steps})

    if not personas:
        return _fallback_routine(layout_data, topology_json)

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


def _llm_payload(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    payload = _safe_json_loads(topology_json)
    rooms = _layout_rooms(layout_data)
    bed_rooms = _sorted_bedrooms(rooms)

    bathrooms = [
        {"id": r["id"], "name": r["name"]}
        for r in rooms if r.get("program") == "bath" and isinstance(r.get("id"), str)
    ]

    return {
        "layoutId": layout_data.get("layoutId"),
        "rooms": rooms,
        "bedrooms_by_area": [
            {"id": r["id"], "name": r["name"], "area": r["area"]}
            for r in bed_rooms
        ],
        "bathrooms": bathrooms,
        "brief": {
            "household": payload.get("household", []),
            "description": payload.get("description", ""),
        },
        "time_slots": list(DEFAULT_TIME_SLOTS),
    }


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
        iteration = state.get("iteration", 0)
        household = _parse_household(topology_json)

        if not layout_json or not household:
            return {"routine_json_string": None, "iteration": iteration + 1}

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            if not isinstance(layout_data, dict):
                raise ValueError("Routine layout is not valid JSON.")

            household_notes = _format_household_notes(topology_json)
            description = _parse_description(topology_json)
            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    "=== PER-PERSON SCHEDULE CONSTRAINTS (hard — apply these exactly) ===\n"
                    + (household_notes or "(none)")
                    + "\n\n"
                    + (f"Additional household context:\n{description}\n\n" if description else "")
                    + f"Layout context:\n{json.dumps(_llm_payload(layout_data, topology_json))}\n\n"
                    "Generate a realistic weekday routine for each household member. "
                    "Every person must have at least one bathroom slot in their morning (between 06:00 and 09:00). "
                    "Use the bedrooms_by_area list to assign sleep rooms correctly. "
                    "Return only the required JSON."
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
        except Exception:
            fallback = _fallback_routine(
                json.loads(layout_json) if isinstance(layout_json, str) else layout_json,
                topology_json,
            )
            return {"routine_json_string": json.dumps(fallback), "iteration": iteration + 1}

    return routine
