from __future__ import annotations

import json
import re
from typing import Any
from _runtime.llm import get_response_text


DEFAULT_TIME_SLOTS = [
    "06:00", "07:00", "08:00", "09:00", "10:00", "11:00",
    "12:00", "13:00", "14:00", "15:00", "16:00", "17:00",
    "18:00", "19:00", "20:00", "21:00", "22:00",
]

PERSONA_COLORS = ["#4A7CA8", "#F5A020", "#00C7D4", "#D94020", "#7A8FA3"]

SYSTEM_PROMPT = (
    "You are generating a realistic residential daily routine for visualization.\n"
    "Return compact JSON (no whitespace, no newlines) with exactly this shape:\n"
    '{"time_slots":[],"personas":[{"persona":"","color":"","steps":[]}]}\n'
    "Return only JSON, no explanation.\n\n"

    "FORMAT RULES — never break these:\n"
    "- steps MUST have EXACTLY 17 entries, one per time slot, in order. Do not skip any slot.\n"
    "- null = person is away from home that hour.\n"
    '- ["<room_id>","<activity>"] = person is at home in that room that hour.\n'
    "- ONLY use room ids from the provided rooms list. NEVER invent a room id.\n"
    "- FORBIDDEN rooms — NEVER place anyone in: circulation, hallway, corridor, storage, walkincloset. Use bed/bath/living instead.\n"
    "- Activity values: sleeping, showering, working, studying, relaxing, cooking, playing, dressing. Outdoor activities are always null, not an activity value.\n"
    "- Colors are hex strings.\n\n"

    "DEFAULT SCHEDULE — apply this for every adult not described otherwise in the brief:\n"
    "  06:00 → sleeping in bedroom\n"
    "  07:00 → showering in bathroom\n"
    "  08:00 → null (left for work)\n"
    "  09:00 → null\n"
    "  10:00 → null\n"
    "  11:00 → null\n"
    "  12:00 → null\n"
    "  13:00 → null\n"
    "  14:00 → null\n"
    "  15:00 → null\n"
    "  16:00 → null\n"
    "  17:00 → null (still at work)\n"
    "  18:00 → relaxing in living room\n"
    "  19:00 → relaxing in living room\n"
    "  20:00 → relaxing in living room\n"
    "  21:00 → showering in bathroom\n"
    "  22:00 → sleeping in bedroom\n\n"

    "EXCEPTIONS — only apply when the brief explicitly states it:\n"
    "- WFH/works from home: replace null 09:00–17:00 with working in office/studio or living room.\n"
    "- Child/teen: null 08:00–14:00 (school), home relaxing from 15:00, sleeping by 21:00.\n"
    "- Retired/stay-at-home adult: replace all nulls with relaxing in living room.\n"
    "- Baby/infant: sleeping in bedroom all day, never null.\n\n"

    "SLEEP:\n"
    "- Couple/partners share the largest bedroom.\n"
    "- Each child gets their own bedroom; shares only if rooms run out.\n"
    "- Baby always sleeps in the parents' bedroom.\n\n"

    "CONFLICTS:\n"
    "- Never put two people in the same room at the same time (exception: couple sleeping together).\n"
    "- Never put two people in the same bathroom at the same time — stagger shower times by 1 hour.\n\n"

    "OUTDOORS:\n"
    "- Any activity that happens outside the home (walk, going out, shopping, errand, outing) must be null — the person is not in any room.\n"
    "- 'Going for a walk', 'taking the dog out', 'going outside' = null for that hour for EVERY person AND pet involved.\n\n"

    "PETS:\n"
    "- Include dogs, cats, and other pets mentioned in the brief as their own personas.\n"
    "- Name pet personas using only their name (e.g. 'Sky', 'Pixel') — do not append the species.\n"
    "- Pet schedule: sleeping in bedroom 06:00–07:00, playing or relaxing in living room during the day, sleeping in bedroom at 22:00.\n"
    "- PET WALK SYNC — CRITICAL: when a person takes the dog for a walk, the dog's steps must be null for exactly the same time slots as that person. They leave together and return together.\n"
    "- When the pet is home alone (owner away for work etc.), the pet relaxes in the living room — not null.\n"
    "- Never place a pet in a bathroom or wc.\n"
)


Step = dict[str, str] | None


def _layout_rooms(layout_data: dict[str, Any]) -> list[dict[str, Any]]:
    rooms_raw = layout_data.get("rooms") if isinstance(layout_data.get("rooms"), list) else []
    rooms = []
    for room in rooms_raw:
        if not isinstance(room, dict):
            continue
        room_id = room.get("id")
        if room_id is None:
            continue
        attributes = room.get("attributes") if isinstance(room.get("attributes"), dict) else {}
        rooms.append({
            "id": str(room_id),
            "program": (attributes.get("program") or "").lower() or None,
            "name": room.get("name") or None,
            "area": attributes.get("area") if isinstance(attributes.get("area"), (int, float)) else None,
        })
    return rooms


def _step_room(step: Step) -> str | None:
    return step.get("room") if isinstance(step, dict) else None


def _enforce_bathroom_spacing(personas: list[dict[str, Any]], rooms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bathroom_ids = [r["id"] for r in rooms if r.get("program") == "bath" and isinstance(r.get("id"), str)]
    if not bathroom_ids:
        return personas
    bathroom_set = set(bathroom_ids)
    fallback_room = next((r["id"] for r in rooms if r.get("program") in ("bed", "living")), None)
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
                    steps[slot] = {"room": free, "label": "showering"}
                    occupied.add(free)
                elif fallback_room:
                    steps[slot] = {"room": fallback_room, "label": "at home"}
                else:
                    steps[slot] = None
    return personas


def _stable_color_personas(personas: list[dict[str, Any]], topology_json: str | None) -> list[dict[str, Any]]:
    """Reorder personas to match household order and assign stable colors by household index."""
    household: list[dict] = []
    if topology_json:
        try:
            payload = json.loads(topology_json)
            household = payload.get("household", []) if isinstance(payload.get("household"), list) else []
        except Exception:
            pass

    if not household:
        return [{**p, "color": PERSONA_COLORS[i % len(PERSONA_COLORS)]} for i, p in enumerate(personas)]

    name_to_idx: dict[str, int] = {
        (p.get("persona") or "").strip().lower(): i for i, p in enumerate(personas)
    }
    used: set[int] = set()
    ordered: list[dict[str, Any]] = []

    for hi, member in enumerate(household):
        color = PERSONA_COLORS[hi % len(PERSONA_COLORS)]
        member_name = (member.get("name") or "").strip().lower()
        member_rel = (member.get("relationship") or "").strip().lower()
        kind = "dog" if any(w in member_rel for w in ("dog", "puppy", "hound")) else "cat" if any(w in member_rel for w in ("cat", "kitty", "feline")) else "person"
        idx = name_to_idx.get(member_name) if member_name else None
        if idx is None:
            idx = name_to_idx.get(member_rel)
        if idx is not None and idx not in used:
            ordered.append({**personas[idx], "color": color, "kind": kind})
            used.add(idx)
        else:
            for j, p in enumerate(personas):
                if j not in used:
                    ordered.append({**p, "color": color, "kind": kind})
                    used.add(j)
                    break

    for j, p in enumerate(personas):
        if j not in used:
            ordered.append({**p, "color": PERSONA_COLORS[j % len(PERSONA_COLORS)]})

    # Correction pass: cascade mismatches can assign the wrong kind.
    # Re-apply kind directly from household for any persona whose name matches a pet.
    pet_kind_by_name: dict[str, str] = {}
    for m in household:
        if not isinstance(m, dict):
            continue
        mname = (m.get("name") or "").strip().lower()
        mrel = (m.get("relationship") or "").strip().lower()
        if not mname:
            continue
        if any(w in mrel for w in ("dog", "puppy", "hound")):
            pet_kind_by_name[mname] = "dog"
        elif any(w in mrel for w in ("cat", "kitty", "feline")):
            pet_kind_by_name[mname] = "cat"

    for p in ordered:
        pname = (p.get("persona") or "").strip().lower()
        matched = pet_kind_by_name.get(pname) or next(
            (k for pet_name, k in pet_kind_by_name.items() if pet_name in pname), None
        )
        if matched:
            p["kind"] = matched

    return ordered


_FORBIDDEN_PROGRAMS = {"circulation", "storage"}

def _normalize_routine(value: Any, layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    """Validate LLM-generated routine: keep LLM decisions, reject invalid/forbidden room IDs."""
    rooms = _layout_rooms(layout_data)
    valid_ids = {r["id"] for r in rooms}
    room_program = {r["id"]: r.get("program", "") for r in rooms}
    _PROGRAM_LABEL = {
        "bed": "sleeping", "bath": "showering", "walkincloset": "dressing",
        "living": "relaxing", "wc": "showering",
    }

    def _is_valid_step(room_id: str) -> bool:
        return room_id in valid_ids and room_program.get(room_id, "") not in _FORBIDDEN_PROGRAMS

    if not isinstance(value, dict):
        return _fallback_routine(layout_data, topology_json)

    time_slots = value.get("time_slots")
    if not isinstance(time_slots, list) or len(time_slots) != len(DEFAULT_TIME_SLOTS):
        time_slots = list(DEFAULT_TIME_SLOTS)

    personas_raw = value.get("personas") if isinstance(value.get("personas"), list) else []
    personas = []
    for idx, item in enumerate(personas_raw):
        if not isinstance(item, dict):
            continue
        persona = (item.get("persona") or f"Resident {idx + 1}").strip()
        steps_raw = item.get("steps") if isinstance(item.get("steps"), list) else []
        steps: list[Step] = []
        for i in range(len(DEFAULT_TIME_SLOTS)):
            raw = steps_raw[i] if i < len(steps_raw) else None
            if raw is None:
                steps.append(None)
            elif isinstance(raw, list) and raw:
                room_id = str(raw[0]).strip()
                label = str(raw[1]).strip() if len(raw) >= 2 else ""
                label = label or _PROGRAM_LABEL.get(room_program.get(room_id, ""), "relaxing")
                steps.append({"room": room_id, "label": label} if _is_valid_step(room_id) else None)
            elif isinstance(raw, dict):
                room_id = str(raw.get("room", "")).strip()
                label = str(raw.get("label", "")).strip() or _PROGRAM_LABEL.get(room_program.get(room_id, ""), "relaxing")
                steps.append({"room": room_id, "label": label} if _is_valid_step(room_id) else None)
            elif isinstance(raw, str):
                room_id = raw.strip()
                label = _PROGRAM_LABEL.get(room_program.get(room_id, ""), "relaxing")
                steps.append({"room": room_id, "label": label} if _is_valid_step(room_id) else None)
            else:
                steps.append(None)
        personas.append({"persona": persona, "steps": steps})

    if not personas:
        return _fallback_routine(layout_data, topology_json)

    personas = _stable_color_personas(personas, topology_json)
    personas = _enforce_bathroom_spacing(personas, rooms)
    return {"time_slots": time_slots, "personas": personas}


def _fallback_routine(layout_data: dict[str, Any], topology_json: str | None) -> dict[str, Any]:
    """Basic fallback when LLM fails: keeps people visible at home."""
    rooms = _layout_rooms(layout_data)
    bed_id    = next((r["id"] for r in rooms if r.get("program") == "bed"),    None)
    bath_id   = next((r["id"] for r in rooms if r.get("program") == "bath"),   None)
    living_id = next((r["id"] for r in rooms if r.get("program") == "living"), None)
    home = living_id or bed_id

    def _home_steps() -> list[Step]:
        steps: list[Step] = []
        for slot in DEFAULT_TIME_SLOTS:
            hour = int(slot.split(":")[0])
            if hour <= 6 or hour >= 22:
                steps.append({"room": bed_id,               "label": "sleeping"}  if bed_id             else None)
            elif hour == 7:
                steps.append({"room": bath_id or home,      "label": "showering"} if (bath_id or home)  else None)
            elif hour == 21:
                steps.append({"room": bath_id or home,      "label": "showering"} if (bath_id or home)  else None)
            else:
                steps.append({"room": home,                 "label": "relaxing"}  if home               else None)
        return steps

    household: list[dict] = []
    if topology_json:
        try:
            payload = json.loads(topology_json)
            household = payload.get("household", []) if isinstance(payload.get("household"), list) else []
        except Exception:
            pass

    def _member_kind(m: dict) -> str:
        rel = (m.get("relationship") or "").strip().lower()
        return "dog" if rel in ("dog", "puppy") else "cat" if rel in ("cat", "kitty", "feline") else "person"

    personas = [
        {
            "persona": (m.get("name") or m.get("relationship") or f"Resident {i + 1}"),
            "color": PERSONA_COLORS[i % len(PERSONA_COLORS)],
            "kind": _member_kind(m),
            "steps": _home_steps(),
        }
        for i, m in enumerate(household)
    ] or [{"persona": "Resident 1", "color": PERSONA_COLORS[0], "kind": "person", "steps": _home_steps()}]

    return {"time_slots": list(DEFAULT_TIME_SLOTS), "personas": personas}


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

        all_turns = [t for t in feedback_history if isinstance(t, str) and t.strip()]
        if user_prompt.strip() and user_prompt.strip() not in all_turns:
            all_turns.append(user_prompt.strip())
        full_brief = "\n\n".join(all_turns) if all_turns else "(none)"

        try:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            if not isinstance(layout_data, dict):
                raise ValueError("Routine layout is not valid JSON.")

            rooms = _layout_rooms(layout_data)
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    f"User brief (full conversation — apply every detail literally):\n{full_brief}\n\n"
                    f"Available rooms (use only these IDs in steps):\n{json.dumps(rooms, separators=(',', ':'))}\n\n"
                    f"Time slots: {', '.join(DEFAULT_TIME_SLOTS)}\n\n"
                    "Generate the daily routine for every person and pet mentioned in the brief. Return only compact JSON."
                )},
            ]
            response = llm.invoke(messages)
            raw = get_response_text(response)
            if '"final_response"' in raw:
                try:
                    wrapper = json.loads(raw)
                    raw = wrapper.get("final_response", raw)
                except Exception:
                    pass
            parsed = _parse_routine_json(raw)
            payload = _normalize_routine(parsed, layout_data, topology_json)
            return {"routine_json_string": json.dumps(payload), "routine_warning": None, "iteration": iteration + 1}

        except Exception as e:
            layout_data = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            return {
                "routine_json_string": json.dumps(_fallback_routine(layout_data, topology_json)),
                "routine_warning": f"Routine generation encountered an issue ({type(e).__name__}: {e}). Showing a basic schedule.",
                "iteration": iteration + 1,
            }

    return routine
