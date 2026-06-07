from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_TIME_SLOTS = [
    "06:00",
    "08:00",
    "10:00",
    "12:00",
    "14:00",
    "16:00",
    "18:00",
    "20:00",
    "22:00",
]

PERSONA_COLORS = [
    "#4A7CA8",
    "#F5A020",
    "#00C7D4",
    "#D94020",
    "#7A8FA3",
]

SYSTEM_PROMPT = (
    "You are generating a simple residential daily routine for visualization. "
    "Return valid JSON with exactly this shape: "
    '{"time_slots":[],"personas":[{"persona":"","color":"","steps":[]}]}.'
    "\nRules:\n"
    "- Return only JSON, no explanation.\n"
    "- Use the provided layout as the source of truth for available rooms.\n"
    "- steps must be a list with one entry per time slot. Each step must be a room id string from the layout, or null when the person is away.\n"
    "- Use neutral, common-sense weekday routines.\n"
    "- Do not make assumptions based on gender, names, or relationship labels.\n"
    "- Never infer that one person stays home, works outside, cooks, or cares for others because of sex, gender, or name.\n"
    "- Only use explicit information from the household description.\n"
    "- If role or schedule details are missing, use conservative neutral defaults. Adults without stated differences should receive comparable default weekday patterns.\n"
    "- Prefer bedroom at night, bathroom in the morning, living in the evening, and null for away periods when appropriate.\n"
    "- Do not place multiple people in the bathroom at the same time slot unless the input explicitly requires shared bathroom use.\n"
    "- If a couple is present, prefer the largest available bedroom for that couple.\n"
    "- If the brief says that one bedroom is used as a study, interpret that as at least one resident working from home during the day when household information does not contradict it.\n"
    "- If the layout has an extra room and the brief explicitly suggests work-from-home, study, or a dedicated quiet activity, that extra room may be used during the day.\n"
    "- Do not use room ids that do not exist.\n"
    "- Keep colors as simple hex strings.\n"
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
        household.append({
            "name": name,
            "relationship": relationship,
            "info": info,
        })
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
        rooms.append({
            "id": str(room_id),
            "program": program,
            "name": name,
            "area": area,
        })
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
    info = _string(member.get("info"))
    if name:
        return name
    if relationship:
        return relationship.title()
    if info:
        return f"Resident {index + 1}"
    return f"Resident {index + 1}"


def _member_profile(member: dict[str, str]) -> str:
    text = " ".join([
        _string(member.get("relationship")),
        _string(member.get("info")),
    ]).lower()

    if re.search(r"\b(child|kid|toddler|teen|student|school)\b", text):
        return "child_school"
    if re.search(r"\b(retired|elderly|senior|older|mobility)\b", text):
        return "adult_home"
    if re.search(r"\b(work from home|works from home|wfh|remote|home office)\b", text):
        return "adult_home"
    return "adult_default"


def _study_implies_home_worker(description: str) -> bool:
    text = description.lower()
    return bool(re.search(r"\b(study|office|workspace)\b", text))


def _largest_bedroom_id(rooms: list[dict[str, str | None]]) -> str | None:
    bed_rooms = [room for room in rooms if room.get("program") == "bed"]
    if not bed_rooms:
        return None
    ranked = sorted(
        bed_rooms,
        key=lambda room: float(room.get("area") or 0.0),
        reverse=True,
    )
    room_id = ranked[0].get("id")
    return room_id if isinstance(room_id, str) and room_id else None


def _adult_member_indexes(household: list[dict[str, str]]) -> list[int]:
    indexes: list[int] = []
    for index, member in enumerate(household):
        if _member_profile(member) != "child_school":
            indexes.append(index)
    return indexes


def _profiles_for_household(household: list[dict[str, str]], description: str) -> list[str]:
    profiles = [_member_profile(member) for member in household]
    if _study_implies_home_worker(description):
        adult_indexes = _adult_member_indexes(household)
        if adult_indexes and all(profiles[index] != "adult_home" for index in adult_indexes):
            profiles[adult_indexes[0]] = "adult_home"
    return profiles


def _default_steps(profile: str, rooms: list[dict[str, str | None]]) -> list[str | None]:
    bed = _first_room_id(rooms, "bed")
    bath = _first_room_id(rooms, "bath")
    living = _first_room_id(rooms, "living")
    extra = _first_room_id(rooms, "extra")
    foyer = _first_room_id(rooms, "foyer")

    if profile == "child_school":
        return [
            _fallback_room(bed, living),
            _fallback_room(bath, bed, living),
            None,
            None,
            None,
            _fallback_room(living, extra, bed),
            _fallback_room(living, bed, extra),
            _fallback_room(living, bed),
            _fallback_room(bed, living),
        ]

    if profile == "adult_home":
        return [
            _fallback_room(bed, living),
            _fallback_room(bath, living, bed),
            _fallback_room(extra, living, bed),
            _fallback_room(living, extra, bed),
            _fallback_room(extra, living, bed),
            _fallback_room(living, extra, bed),
            _fallback_room(living, extra, bed),
            _fallback_room(living, bed),
            _fallback_room(bed, living),
        ]

    return [
        _fallback_room(bed, living),
        _fallback_room(bath, living, bed),
        None,
        None,
        None,
        _fallback_room(foyer, living, extra),
        _fallback_room(living, extra, bed),
        _fallback_room(living, bed),
        _fallback_room(bed, living),
    ]


def _reassign_from_bathroom(steps: list[str | None], step_index: int, rooms: list[dict[str, str | None]]) -> str | None:
    bed = _first_room_id(rooms, "bed")
    living = _first_room_id(rooms, "living")
    extra = _first_room_id(rooms, "extra")
    foyer = _first_room_id(rooms, "foyer")
    current = steps[step_index] if step_index < len(steps) else None
    previous = steps[step_index - 1] if step_index > 0 else None
    return _fallback_room(previous, current, bed, living, extra, foyer)


def _enforce_bathroom_spacing(personas: list[dict[str, Any]], rooms: list[dict[str, str | None]]) -> list[dict[str, Any]]:
    bathroom_ids = {room["id"] for room in rooms if room.get("program") == "bath" and isinstance(room.get("id"), str)}
    if not bathroom_ids:
        return personas

    for step_index in range(len(DEFAULT_TIME_SLOTS)):
        occupied: set[str] = set()
        for persona in personas:
            steps = persona.get("steps") if isinstance(persona.get("steps"), list) else []
            if step_index >= len(steps):
                continue
            room_id = steps[step_index]
            if room_id not in bathroom_ids:
                continue
            if room_id in occupied:
                steps[step_index] = _reassign_from_bathroom(steps, step_index, rooms)
            else:
                occupied.add(room_id)
    return personas


def _shared_sleeping_indexes(personas: list[dict[str, Any]], rooms: list[dict[str, str | None]]) -> list[int]:
    bedroom_ids = {room["id"] for room in rooms if room.get("program") == "bed" and isinstance(room.get("id"), str)}
    if not bedroom_ids:
        return []

    sleep_slots = [0, len(DEFAULT_TIME_SLOTS) - 1]
    shared_indexes: set[int] = set()
    for slot in sleep_slots:
        occupancy: dict[str, list[int]] = {}
        for index, persona in enumerate(personas):
            steps = persona.get("steps") if isinstance(persona.get("steps"), list) else []
            if slot >= len(steps):
                continue
            room_id = steps[slot]
            if room_id not in bedroom_ids:
                continue
            occupancy.setdefault(room_id, []).append(index)
        for indexes in occupancy.values():
            if len(indexes) >= 2:
                shared_indexes.update(indexes)

    return sorted(shared_indexes)


def _apply_shared_sleeping_bedroom_rule(personas: list[dict[str, Any]], rooms: list[dict[str, str | None]]) -> list[dict[str, Any]]:
    shared_sleepers = _shared_sleeping_indexes(personas, rooms)
    largest_bedroom = _largest_bedroom_id(rooms)
    if not shared_sleepers or not largest_bedroom:
        return personas

    sleep_slots = [0, len(DEFAULT_TIME_SLOTS) - 1]
    for index in shared_sleepers:
        if index >= len(personas):
            continue
        steps = personas[index].get("steps") if isinstance(personas[index].get("steps"), list) else []
        for slot in sleep_slots:
            if slot < len(steps):
                steps[slot] = largest_bedroom
    return personas


def _fallback_routine(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    rooms = _layout_rooms(layout_data)
    household = _parse_household(topology_json)
    description = _parse_description(topology_json)
    profiles = _profiles_for_household(household, description)

    personas = []
    for index, member in enumerate(household):
        personas.append({
            "persona": _member_label(member, index),
            "color": PERSONA_COLORS[index % len(PERSONA_COLORS)],
            "steps": _default_steps(profiles[index], rooms),
        })

    personas = _apply_shared_sleeping_bedroom_rule(personas, rooms)
    personas = _enforce_bathroom_spacing(personas, rooms)

    return {
        "time_slots": list(DEFAULT_TIME_SLOTS),
        "personas": personas,
    }


def _normalize_routine(value: Any, layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    fallback = _fallback_routine(layout_data, topology_json)
    rooms = _layout_rooms(layout_data)
    valid_room_ids = {room["id"] for room in rooms if isinstance(room.get("id"), str)}
    fallback_personas = fallback["personas"]

    if not isinstance(value, dict):
        return fallback

    time_slots = value.get("time_slots") if isinstance(value.get("time_slots"), list) else []
    normalized_time_slots = [slot.strip() for slot in time_slots if isinstance(slot, str) and slot.strip()]
    if len(normalized_time_slots) != len(DEFAULT_TIME_SLOTS):
        normalized_time_slots = list(DEFAULT_TIME_SLOTS)

    personas_raw = value.get("personas") if isinstance(value.get("personas"), list) else []
    personas = []
    for index, item in enumerate(personas_raw):
        if not isinstance(item, dict):
            continue
        fallback_member = fallback_personas[index] if index < len(fallback_personas) else {
            "persona": f"Resident {index + 1}",
            "color": PERSONA_COLORS[index % len(PERSONA_COLORS)],
            "steps": _default_steps("adult_default", rooms),
        }
        persona = _string(item.get("persona")) or fallback_member["persona"]
        color = _string(item.get("color")) or fallback_member["color"]
        steps_raw = item.get("steps") if isinstance(item.get("steps"), list) else []
        steps: list[str | None] = []
        for step_index in range(len(DEFAULT_TIME_SLOTS)):
            raw_step = steps_raw[step_index] if step_index < len(steps_raw) else None
            if raw_step is None:
                steps.append(fallback_member["steps"][step_index])
                continue
            room_id = str(raw_step).strip()
            if room_id in valid_room_ids:
                steps.append(room_id)
            else:
                steps.append(fallback_member["steps"][step_index])
        personas.append({
            "persona": persona,
            "color": color,
            "steps": steps,
        })

    if not personas:
        personas = fallback_personas

    personas = _apply_shared_sleeping_bedroom_rule(personas, rooms)
    personas = _enforce_bathroom_spacing(personas, rooms)

    return {
        "time_slots": normalized_time_slots,
        "personas": personas,
    }


def _llm_payload(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    payload = _safe_json_loads(topology_json)
    return {
        "layoutId": layout_data.get("layoutId"),
        "rooms": _layout_rooms(layout_data),
        "brief": {
            "household": payload.get("household", []),
            "description": payload.get("description", ""),
        },
        "default_time_slots": list(DEFAULT_TIME_SLOTS),
    }


def build_routine_node(llm: Any) -> Any:
    def routine(state: dict) -> dict:
        layout_json = state.get("layout_json_string")
        topology_json = state.get("topology_graph_json_string")
        iteration = state.get("iteration", 0)
        household = _parse_household(topology_json)

        if not layout_json or not household:
            return {
                "routine_json_string": None,
                "iteration": iteration + 1,
            }

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            if not isinstance(layout_data, dict):
                raise ValueError("Routine layout is not valid JSON.")

            llm_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"Routine input payload: {json.dumps(_llm_payload(layout_data, topology_json))}\n"
                    "Generate a neutral weekday routine for visualization. If information is missing, use conservative defaults. Return only the required JSON."
                )},
            ]
            response = llm.invoke(llm_messages)
            parsed = json.loads(response.content.strip())
            routine_payload = _normalize_routine(parsed, layout_data, topology_json)
            return {
                "routine_json_string": json.dumps(routine_payload),
                "iteration": iteration + 1,
            }
        except Exception:
            fallback = _fallback_routine(
                json.loads(layout_json) if isinstance(layout_json, str) else layout_json,
                topology_json,
            )
            return {
                "routine_json_string": json.dumps(fallback),
                "iteration": iteration + 1,
            }

    return routine