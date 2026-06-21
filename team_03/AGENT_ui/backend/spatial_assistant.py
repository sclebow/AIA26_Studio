"""
Spatial assistant — a lightweight, Rhino-free chat agent for observer / visibility
/ path questions in the AGENT_ui chat.

The LangGraph pipeline (agent_runner) needs Rhino+Swiftlet and is built for
placing/moving furniture. Observer + visibility + path analysis, by contrast, is
pure Python (isovist.py + adapters/analysis_adapter.py), so this module handles
those conversationally without the heavy pipeline:

  - It can PLACE a person or a path from a natural-language location
    ("center of the warehouse", "entrance of the workshop", "bathroom"),
  - run the visibility-obstruction analysis (which objects are visible/hidden and
    which furniture blocks the view), collisions and path analysis,
  - answer about an observer the user ALREADY placed in the viewport,
  - and drive the 3D viewport live (it emits the same `observer_result` message
    the manual observer uses, plus an `agentObserver` marker).

Uses Anthropic tool-use with the session's active model. Everything runs in the
backend; team_03/python/ stays read-only (only imported).
"""
from __future__ import annotations

import json
import math
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

import isovist
from adapters.analysis_adapter import run_collision, run_path_analysis

# ---------------------------------------------------------------------------
# Routing — is this chat message a spatial / observer / visibility question?
# ---------------------------------------------------------------------------

# STRONG signals are observer-specific: they should reach this assistant even when
# a LangGraph pipeline run is paused at a checkpoint (and abort that run), because
# they unambiguously mean "do something with the person/observer".
_STRONG_SPATIAL = (
    "person", "persona", "personaje", "observ", "observer",
    "isovist", "sightline", "line of sight", "line-of-sight",
    "linea de vista", "línea de vista",
)

# WEAK signals (visibility / path wording) are routed to this assistant only when
# NO pipeline run is active — otherwise they'd hijack a real checkpoint decision
# like "make the path wider".
_WEAK_SPATIAL = (
    "visibil", "visibility", "vista", "view", "se ve", "no se ve", "puedo ver",
    "que veo", "qué veo", "what can i see", "what do i see", "field of view",
    "oculta", "oculto", "ocultos", "ocultas", "obstru", "obstruct",
    "bloquea", "bloquean", "block my view", "blocks my view", "blocking",
    "tapan", "tapa la vista",
    "path", "camino", "ruta", "recorrido", "trayecto",
)


def is_strong_spatial_query(text: str) -> bool:
    """Observer-specific intent that should override / abort an active pipeline run."""
    if not text:
        return False
    t = f" {text.lower()} "
    return any(k in t for k in _STRONG_SPATIAL)


def is_spatial_query(text: str) -> bool:
    """Heuristic: does this message want observer/visibility/path analysis?
    (Used to route to this assistant when no pipeline run is active.)"""
    if not text:
        return False
    t = f" {text.lower()} "
    return any(k in t for k in _STRONG_SPATIAL) or any(k in t for k in _WEAK_SPATIAL)


# ---------------------------------------------------------------------------
# Location resolver — natural language → (x, y) in layout metres
# ---------------------------------------------------------------------------

# Spanish (and a few English) words → tokens likely to appear in room names.
_SYNONYMS = {
    "baño": "bath", "bano": "bath", "aseo": "bath", "sanitario": "bath",
    "almacen": "warehouse", "almacén": "warehouse", "bodega": "warehouse",
    "almacenamiento": "storage", "deposito": "storage", "depósito": "storage",
    "cocina": "kitchen", "oficina": "office", "taller": "workshop",
    "sala": "room", "habitacion": "room", "habitación": "room", "cuarto": "room",
    "ensamblaje": "assembly", "ensamble": "assembly", "montaje": "assembly",
    "empaque": "packaging", "empaquetado": "packaging", "embalaje": "packaging",
    "fabricacion": "fabrication", "fabricación": "fabrication",
    "carga": "loading", "produccion": "production", "producción": "production",
    "entrada": "entrance", "acceso": "entrance",
}

_DOOR_WORDS = ("entrance", "entry", "door", "gate",
               "puerta", "entrada", "acceso", "ingreso")
_CENTER_WORDS = ("center", "centre", "middle", "centro", "medio", "mitad")


def _expand(text: str) -> str:
    t = (text or "").lower()
    extra = [v for k, v in _SYNONYMS.items() if k in t]
    return t + " " + " ".join(extra)


def _room_centroid(room: dict) -> Optional[Tuple[float, float]]:
    return isovist._centroid(room.get("geometry"))


def _find_room(layout: dict, text: str) -> Optional[dict]:
    """Best room whose name overlaps the (synonym-expanded) text."""
    rooms = layout.get("rooms", []) or []
    if not rooms:
        return None
    t = _expand(text)
    t_tokens = [w for w in t.replace("-", " ").split() if len(w) >= 3]
    best: Optional[dict] = None
    best_score = 0
    for r in rooms:
        name = (r.get("name") or "").lower()
        if not name:
            continue
        score = 0
        # a room-name word appears in the (expanded) text
        for word in name.replace("-", " ").split():
            if len(word) >= 3 and word in t:
                score += 1
        # a text/synonym token appears inside the room name (e.g. "bath" → "bathroom")
        for tok in t_tokens:
            if tok in name:
                score += 1
        # whole name present → strong signal
        if name in t:
            score += 2
        if score > best_score:
            best_score, best = score, r
    return best if best_score > 0 else None


def _room_of(layout: dict, room_id: Any) -> Optional[dict]:
    for r in layout.get("rooms", []) or []:
        if r.get("id") == room_id:
            return r
    return None


def _door_point_for_room(layout: dict, room: dict) -> Optional[Tuple[float, float]]:
    """A point just inside `room` at one of its doors (prefer a door to outside)."""
    rid = room.get("id")
    centroid = _room_centroid(room)
    doors = layout.get("doors", []) or []
    candidates = []
    for d in doors:
        connects = (d.get("attributes") or {}).get("connectsRooms") or []
        if rid in connects:
            # prefer doors that lead outside (only one room, or a None/outside id)
            to_outside = len(connects) < 2 or any(
                c in (None, "", "outside", "exterior") for c in connects
            )
            candidates.append((to_outside, d))
    if not candidates:
        return centroid
    candidates.sort(key=lambda c: not c[0])  # outside-doors first
    door = candidates[0][1]
    mid = isovist._centroid(door.get("geometry"))
    if not mid:
        return centroid
    if not centroid:
        return mid
    # nudge ~0.6 m from the door toward the room centre so we're inside the room
    dx, dy = centroid[0] - mid[0], centroid[1] - mid[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return mid
    return (mid[0] + dx / n * 0.6, mid[1] + dy / n * 0.6)


def _find_object(layout: dict, text: str) -> Optional[Tuple[str, dict]]:
    """Best furniture/MEP item whose name overlaps the text (e.g. 'assembly
    station 1', 'the toilet'). Returns (type, item) or None."""
    t = (text or "").lower()
    best: Optional[Tuple[str, dict]] = None
    best_score = 0
    for ktype in ("furniture", "mep"):
        for o in layout.get(ktype, []) or []:
            name = (o.get("name") or "").lower()
            if not name:
                continue
            score = 0
            for w in name.replace("-", " ").split():
                if len(w) >= 3 and w in t:
                    score += 1
            if name in t:        # exact name present → strong disambiguator
                score += 3
            if score > best_score:
                best_score, best = score, (ktype, o)
    return best if best_score > 0 else None


def _object_point(layout: dict, item: dict) -> Optional[Tuple[float, float]]:
    """A point ~1.2 m from an object's centroid toward its room centre, so an
    observer stands NEXT to it (not inside its footprint, which would be blind)."""
    c = isovist._centroid(item.get("geometry"))
    if not c:
        return None
    rid = (item.get("attributes") or {}).get("roomId")
    room = _room_of(layout, rid) if rid else None
    rc = _room_centroid(room) if room else None
    if rc:
        dx, dy = rc[0] - c[0], rc[1] - c[1]
        n = math.hypot(dx, dy)
        if n > 1e-6:
            return (c[0] + dx / n * 1.2, c[1] + dy / n * 1.2)
    return (c[0] + 1.2, c[1])


def resolve_location(layout: dict, text: str) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    """Resolve a natural-language location to (x, y) + a human label."""
    t = (text or "").lower().strip()
    if not t:
        return None, None
    rooms = layout.get("rooms", []) or []

    room = _find_room(layout, t)
    wants_door = any(w in t for w in _DOOR_WORDS)

    if wants_door and room:
        p = _door_point_for_room(layout, room)
        if p:
            return p, f"entrance of {room.get('name')}"

    # A named furniture/MEP item ("assembly station 1", "the toilet") — stand next
    # to it. Checked before the room centroid so "near assembly station 1" wins.
    obj = _find_object(layout, t)
    if obj and not (room and room.get("name", "").lower() in t):
        p = _object_point(layout, obj[1])
        if p:
            return p, f"near {obj[1].get('name')}"

    if room:
        c = _room_centroid(room)
        if c:
            return c, f"center of {room.get('name')}"

    # "center of the room" with no specific name → first/only room
    if any(w in t for w in _CENTER_WORDS) and rooms:
        c = _room_centroid(rooms[0])
        if c:
            return c, f"center of {rooms[0].get('name')}"

    # bare door request, no room → first door
    if wants_door:
        doors = layout.get("doors", []) or []
        if doors:
            mid = isovist._centroid(doors[0].get("geometry"))
            if mid:
                return mid, "the entrance"

    return None, None


def _sample_line(p1: Tuple[float, float], p2: Tuple[float, float],
                 step: float = 1.0) -> List[Tuple[float, float]]:
    x1, y1 = p1
    x2, y2 = p2
    d = math.hypot(x2 - x1, y2 - y1)
    n = max(1, int(d // step))
    return [(x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n) for i in range(n + 1)]


# ---------------------------------------------------------------------------
# Tool execution — pure Python analysis + viewport emit
# ---------------------------------------------------------------------------

EmitFn = Callable[[Dict[str, Any]], Awaitable[None]]
SetObserverFn = Callable[[Optional[dict]], None]

_EYE = 1.7


def _trim(items: List[dict], n: int = 15) -> List[dict]:
    return items[:n]


async def _place_person(layout: dict, location: str, emit: EmitFn,
                        set_observer: SetObserverFn) -> Dict[str, Any]:
    pt, label = resolve_location(layout, location)
    if not pt:
        return {"error": f"Could not resolve the location '{location}'. "
                         f"Try a room name like 'workshop' or 'center of the warehouse'."}
    x, y = pt
    res = isovist.analyze_obstructions(layout, x, y, _EYE)
    iso = isovist.compute(layout, x, y, _EYE)
    point_str = f"{x:.2f},{y:.2f},{_EYE:.2f}"
    set_observer({"mode": "person", "point_str": point_str, "height": _EYE, "isovist": iso})
    await emit({
        "type": "observer_result", "mode": "person", "status": "ok",
        "isovist": iso, "agentObserver": {"mode": "person", "point": [round(x, 3), round(y, 3)]},
    })
    return {
        "placed_at": [round(x, 3), round(y, 3)], "location": label,
        "counts": res["counts"], "isovist_area_m2": res["isovist_area"],
        "blockers": _trim(res["blockers"]), "hidden": _trim(res["hidden"]),
        "visible_count": len(res["visible"]),
    }


async def _start_path(layout: dict, frm: str, to: str, emit: EmitFn,
                      set_observer: SetObserverFn) -> Dict[str, Any]:
    p1, l1 = resolve_location(layout, frm)
    p2, l2 = resolve_location(layout, to)
    if not p1 or not p2:
        miss = frm if not p1 else to
        return {"error": f"Could not resolve the location '{miss}'."}
    pts = _sample_line(p1, p2, step=1.0)
    vis = isovist.analyze_obstructions_path(layout, pts, _EYE)
    iso = isovist.compute_path(layout, pts, _EYE)
    path_str = ";".join(f"{px:.3f},{py:.3f}" for px, py in pts)
    set_observer({"mode": "path", "path_str": path_str, "height": _EYE, "isovist": iso})
    await emit({
        "type": "observer_result", "mode": "path", "status": "ok",
        "isovist": iso,
        "agentObserver": {"mode": "path", "path": [[round(px, 3), round(py, 3)] for px, py in pts]},
    })
    # Collisions + circulation along the current layout (path interruption / blockers).
    coll = run_collision(layout)
    return {
        "from": l1, "to": l2,
        "visibility": {"counts": vis["counts"], "isovist_area_m2": vis["isovist_area"],
                       "blockers": _trim(vis["blockers"]), "hidden": _trim(vis["hidden"])},
        "collisions": _summarize_collisions(coll),
    }


def _summarize_collisions(coll: dict) -> Dict[str, Any]:
    if coll.get("error"):
        return {"error": coll["error"]}
    viols = coll.get("violations", []) or []
    out: List[str] = []
    for v in viols[:12]:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            out.append(f"{v.get('type', '?')}: {v.get('description', v.get('object', ''))}")
    return {"summary": coll.get("summary", {}), "violations": out,
            "pass": coll.get("pass")}


async def _analyze_visibility(layout: dict, observer: Optional[dict], emit: EmitFn) -> Dict[str, Any]:
    if not observer:
        return {"error": "No person or path has been placed yet. Place a person first "
                         "(say e.g. 'place a person in the center of the workshop') or drop "
                         "one in the viewport."}
    mode = observer.get("mode")
    if mode == "person":
        ps = observer.get("point_str") or ""
        parts = [float(p) for p in str(ps).split(",") if p.strip()]
        if len(parts) < 2:
            return {"error": "The stored observer point is malformed."}
        x, y = parts[0], parts[1]
        h = parts[2] if len(parts) > 2 else _EYE
        res = isovist.analyze_obstructions(layout, x, y, h)
        iso = observer.get("isovist") or isovist.compute(layout, x, y, h)
        await emit({"type": "observer_result", "mode": "person", "status": "ok",
                    "isovist": iso,
                    "agentObserver": {"mode": "person", "point": [round(x, 3), round(y, 3)]}})
        return {"observer": "person", "placed_at": [round(x, 3), round(y, 3)],
                "counts": res["counts"], "isovist_area_m2": res["isovist_area"],
                "blockers": _trim(res["blockers"]), "hidden": _trim(res["hidden"]),
                "visible_count": len(res["visible"])}
    # path
    ps = observer.get("path_str") or ""
    pts: List[Tuple[float, float]] = []
    for chunk in ps.split(";"):
        c = [v for v in chunk.split(",") if v.strip()]
        if len(c) >= 2:
            pts.append((float(c[0]), float(c[1])))
    if not pts:
        return {"error": "The stored observer path is malformed."}
    res = isovist.analyze_obstructions_path(layout, pts, _EYE)
    await emit({"type": "observer_result", "mode": "path", "status": "ok",
                "isovist": observer.get("isovist"),
                "agentObserver": {"mode": "path", "path": [[round(px, 3), round(py, 3)] for px, py in pts]}})
    return {"observer": "path", "counts": res["counts"], "isovist_area_m2": res["isovist_area"],
            "blockers": _trim(res["blockers"]), "hidden": _trim(res["hidden"]),
            "visible_count": len(res["visible"])}


def _analyze_collisions(layout: dict) -> Dict[str, Any]:
    return _summarize_collisions(run_collision(layout))


def _analyze_path(layout: dict) -> Dict[str, Any]:
    res = run_path_analysis(layout)
    if res.get("error"):
        return {"error": res["error"]}
    pairs = res.get("pairs", []) or []
    blocked = [p for p in pairs if not p.get("reachable", True)]
    return {"worst_case": res.get("worst_case", {}),
            "pairs_count": len(pairs),
            "unreachable_pairs": _trim(blocked, 12)}


# ---------------------------------------------------------------------------
# Tool schema + LLM loop
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "place_person",
        "description": "Place OR MOVE the person/observer to a location and analyze visibility "
                       "(which objects are visible vs hidden, which furniture blocks the line of "
                       "sight). Re-placing moves the existing person — use this for 'place a "
                       "person in the center of the room', 'move the person to the warehouse "
                       "entrance', 'move the person near assembly station 1'. The location can be "
                       "a room, a door/entrance, or a furniture/MEP item by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string",
                             "description": "Natural-language location, e.g. 'center of the "
                                            "workshop', 'bathroom', 'entrance of the warehouse', "
                                            "'near assembly station 1', 'the toilet'."}
            },
            "required": ["location"],
        },
    },
    {
        "name": "start_path",
        "description": "Create a walking path between two locations and analyze, along the "
                       "route: visibility obstructions, collisions and clearance violations. "
                       "Use for 'start a path from the warehouse entrance to the bathroom and "
                       "tell me what blocks my view / collides'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from": {"type": "string", "description": "Start location."},
                "to": {"type": "string", "description": "End location."},
            },
            "required": ["from", "to"],
        },
    },
    {
        "name": "analyze_visibility",
        "description": "Analyze visibility from the person/observer ALREADY placed in the "
                       "viewport (no new placement). Use when the user says they just placed "
                       "the person and asks which furniture obstructs the view.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_collisions",
        "description": "Run clearance/collision analysis on the current layout and report "
                       "which objects collide or violate clearances.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "analyze_path",
        "description": "Run circulation/path analysis on the current layout (which room "
                       "pairs are reachable, worst-case egress distance).",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _system_prompt(layout: dict, observer: Optional[dict]) -> str:
    rooms = [r.get("name") for r in (layout.get("rooms") or []) if r.get("name")]
    nf = len(layout.get("furniture") or [])
    nm = len(layout.get("mep") or [])
    obs = "none placed yet"
    if observer:
        if observer.get("mode") == "person":
            obs = f"a person at {observer.get('point_str')}"
        else:
            obs = "a path"
    return (
        "You are the Spatial Vision assistant inside an industrial layout tool. You help the "
        "user reason about VISIBILITY (what a person can see), OBSERVER placement, and PATHS, "
        "plus collisions and circulation. You have tools that run REAL deterministic analysis "
        "on the live floor plan and draw the result in the 3D viewport.\n\n"
        f"Current layout rooms: {', '.join(rooms) or 'unknown'}. "
        f"Furniture items: {nf}, MEP items: {nm}. Observer currently: {obs}.\n\n"
        "Guidelines:\n"
        "- If the user asks about a person/observer they ALREADY placed (without naming a new "
        "spot), call analyze_visibility.\n"
        "- To place OR MOVE the person, call place_person with the destination — re-placing "
        "moves the existing person (e.g. 'move the person near assembly station 1' → "
        "place_person(location='assembly station 1')). To create a route, call start_path.\n"
        "- The location can be a room, an entrance/door, or a furniture/MEP item by name. If a "
        "destination is genuinely missing ('move the person there'), ask for it.\n"
        "- 'blockers' are movable furniture/MEP that hide other objects from the observer; "
        "'hidden' are objects with no clear line of sight.\n"
        "- After the tool runs, answer the user in clear, concise prose. Give concrete counts "
        "and name the specific objects (e.g. 'Conveyor Section 10 blocks Assembly Station 1'). "
        "Mention that the visibility surface is now shown in the viewport. Reply in the user's "
        "language."
    )


async def handle(
    message: str,
    history: List[Dict[str, str]],
    layout: dict,
    observer: Optional[dict],
    emit: EmitFn,
    set_observer: SetObserverFn,
    api_key: str,
    model: str,
) -> str:
    """Run the spatial assistant for one user turn. Executes tools (drawing results
    into the viewport via `emit`) and returns the final natural-language answer."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    system = _system_prompt(layout, observer)

    messages: List[Dict[str, Any]] = [
        {"role": m["role"], "content": m["content"]}
        for m in (history or [])
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": message})

    # The session observer can change as tools run (place_person/start_path).
    local_observer = {"v": observer}

    def _remember(obs: Optional[dict]) -> None:
        local_observer["v"] = obs
        set_observer(obs)

    async def _exec(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            if name == "place_person":
                return await _place_person(layout, args.get("location", ""), emit, _remember)
            if name == "start_path":
                return await _start_path(layout, args.get("from", ""), args.get("to", ""), emit, _remember)
            if name == "analyze_visibility":
                return await _analyze_visibility(layout, local_observer["v"], emit)
            if name == "analyze_collisions":
                return _analyze_collisions(layout)
            if name == "analyze_path":
                return _analyze_path(layout)
            return {"error": f"unknown tool {name}"}
        except Exception as exc:  # never crash the turn
            return {"error": f"{name} failed: {exc}"}

    for _ in range(6):  # bounded tool-use loop
        resp = await client.messages.create(
            model=model, max_tokens=1200, system=system, tools=TOOLS, messages=messages,
        )
        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip() \
                or "Done."
        # Append the assistant's tool-use turn, then run every requested tool.
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if getattr(block, "type", None) == "tool_use":
                out = await _exec(block.name, block.input or {})
                results.append({
                    "type": "tool_result", "tool_use_id": block.id,
                    "content": json.dumps(out, ensure_ascii=False),
                })
        messages.append({"role": "user", "content": results})

    return ("I ran several analyses but couldn't wrap up — check the viewport for the "
            "visibility result, or ask a more specific question.")
