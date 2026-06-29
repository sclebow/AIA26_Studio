from __future__ import annotations

import json
import re
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from _runtime.bootstrap import bootstrap
from utils.logger import log_run
from graph import run_agent


MAX_UNIQUE_SEARCH_RESULTS = 4

PROGRAM_ALIASES = {
    "living": ["living", "living room", "living area"],
    "bed": ["bed", "bedroom"],
    "bath": ["bath", "bathroom"],
    "foyer": ["foyer", "entry", "entrance", "entrance hall", "hall"],
    "extra": ["extra", "storage", "study", "office", "workspace"],
}

PROGRAM_ALIAS_LOOKUP = {
    alias: canonical
    for canonical, aliases in PROGRAM_ALIASES.items()
    for alias in aliases
}


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _format_programs(programs: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for program in programs:
        if not isinstance(program, str) or not program.strip():
            continue
        normalized = PROGRAM_ALIAS_LOOKUP.get(program.strip().lower(), program.strip().lower())
        counts[normalized] = counts.get(normalized, 0) + 1

    return [
        {
            "name": program,
            "count": count,
            "label": f"{count} x {program}" if count > 1 else program,
        }
        for program, count in counts.items()
    ]


def _format_pairs(pairs: Any) -> list[str]:
    if not isinstance(pairs, list):
        return []

    formatted: list[str] = []
    for pair in pairs:
        if not isinstance(pair, list) or len(pair) != 2:
            continue
        left, right = pair
        if isinstance(left, str) and left.strip() and isinstance(right, str) and right.strip():
            formatted.append(f"{left.strip()} - {right.strip()}")
    return formatted


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip(" ,.;:")


def _extract_fact_markers(text: str) -> set[str]:
    normalized = _normalize_whitespace(text.lower())
    markers: set[str] = set()

    age_match = re.search(r"\b(?:is\s+)?(\d{1,3})(?:\s+years?\s+old)?\b", normalized)
    if age_match and any(token in normalized for token in ["year", "old", "is "]):
        markers.add(f"age:{age_match.group(1)}")

    if re.search(r"\b(lives?|living) alone\b", normalized):
        markers.add("living:alone")

    if re.search(r"\b(works?|working) from home\b|\bwfh\b|\bremote\b", normalized):
        markers.add("work:home")

    pet_patterns = {
        "cat": r"\b(cat|cats)\b",
        "dog": r"\b(dog|dogs)\b",
        "pet": r"\bpet|pets\b",
    }
    if re.search(r"\b(has|have|with)\b", normalized):
        for pet_type, pattern in pet_patterns.items():
            if re.search(pattern, normalized):
                markers.add(f"pet:{pet_type}")

    return markers


def _is_redundant_fact_clause(candidate: str, existing_clauses: list[str]) -> bool:
    candidate_markers = _extract_fact_markers(candidate)
    if not candidate_markers:
        return False

    existing_markers: set[str] = set()
    for clause in existing_clauses:
        existing_markers.update(_extract_fact_markers(clause))
    return candidate_markers.issubset(existing_markers)


def _is_graph_like_item(text: str, programs: list[str]) -> bool:
    normalized = _normalize_whitespace(text.lower())
    normalized = re.sub(r"^(?:the user|they)\s+", "", normalized)
    normalized = re.sub(r"^(?:require|requires|need|needs|want|wants|include|includes)\s+", "", normalized)
    if not normalized:
        return False

    for program in {program for program in programs if isinstance(program, str)}:
        aliases = PROGRAM_ALIASES.get(program, [program])
        for alias in aliases:
            pattern = rf"^(?:an?\s+|one\s+|two\s+|three\s+|\d+\s+)?{re.escape(alias)}s?$"
            if re.fullmatch(pattern, normalized):
                return True
    return False


def _is_graph_restatement_clause(clause: str, programs: list[str]) -> bool:
    if not clause:
        return False

    text = _normalize_whitespace(clause.lower())
    if not text:
        return False

    item_patterns: list[str] = []
    seen_programs = {program for program in programs if isinstance(program, str)}
    for program in seen_programs:
        aliases = PROGRAM_ALIASES.get(program, [program])
        alias_group = "|".join(re.escape(alias) for alias in aliases)
        item_patterns.append(rf"(?:an?\s+|one\s+|two\s+|three\s+|\d+\s+)?(?:{alias_group})s?")

    if not item_patterns:
        return False

    joined_pattern = r"^(?:" + "|".join(item_patterns) + r")(?:\s*(?:,|and)\s*(?:" + "|".join(item_patterns) + r"))*$"
    return bool(re.fullmatch(joined_pattern, text))


def _build_household_description(household: list[dict[str, Any]]) -> list[str]:
    if not household:
        return []

    fragments: list[str] = []
    if len(household) == 1:
        fragments.append("lives alone")

    for member in household:
        if not isinstance(member, dict):
            continue
        relationship = member.get("relationship", "")
        info = member.get("info", "")
        relation_text = relationship.strip().lower() if isinstance(relationship, str) else ""
        info_text = _normalize_whitespace(info) if isinstance(info, str) else ""
        if relation_text and relation_text not in {"self", "me", "i"}:
            fragments.append(relation_text)
        if info_text:
            fragments.append(info_text)

    deduped: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        key = fragment.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fragment)
    return deduped


def _strip_graph_requirements(clause: str, programs: list[str]) -> str:
    lowered = clause.lower()
    if not any(token in lowered for token in ["require", "requires", "need", "needs", "want", "wants", "include", "includes"]):
        return clause

    fragments = [
        _normalize_whitespace(part)
        for part in re.split(r",|\band\b", clause, flags=re.IGNORECASE)
    ]
    kept = [fragment for fragment in fragments if fragment and not _is_graph_like_item(fragment, programs)]
    if not kept or len(kept) == len(fragments):
        return clause
    return "; ".join(kept)


def _is_internal_mapping_clause(clause: str) -> bool:
    text = clause.lower()
    return any(
        phrase in text
        for phrase in [
            "considered as an additional bedroom",
            "to be considered as an additional bedroom",
            "represented as an additional bedroom",
            "represented as an additional bed",
            "translated to extra",
            "translated to bed",
        ]
    )


def _clean_description(description: str, programs: list[str], household: list[dict[str, Any]]) -> str:
    clauses = re.split(r"(?<=[.;])\s+|\s*;\s*", description)
    kept_clauses: list[str] = []
    seen: set[str] = set()
    for clause in clauses:
        cleaned = _normalize_whitespace(_strip_graph_requirements(clause, programs))
        if not cleaned or _is_graph_restatement_clause(cleaned, programs):
            continue
        if _is_internal_mapping_clause(cleaned):
            continue
        if _is_redundant_fact_clause(cleaned, kept_clauses):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        kept_clauses.append(cleaned)

    for household_clause in _build_household_description(household):
        key = household_clause.lower()
        if key in seen:
            continue
        if any(key in clause.lower() for clause in kept_clauses):
            continue
        if _is_redundant_fact_clause(household_clause, kept_clauses):
            continue
        seen.add(key)
        kept_clauses.append(household_clause)

    return "; ".join(kept_clauses)


def _build_specifications(description: str) -> list[str]:
    if not description:
        return []

    raw_parts = re.split(r"(?<=[.;])\s+|\s*;\s*|\s*,\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", description)
    specs: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        cleaned = _normalize_whitespace(part)
        if not cleaned:
            continue
        cleaned = re.sub(r"^(the user|they)\s+", "", cleaned, flags=re.IGNORECASE)
        if _is_redundant_fact_clause(cleaned, specs):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        specs.append(cleaned)
    return specs


def _build_brief(topology_graph_json_string: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(topology_graph_json_string)
    graph = payload.get("graph") if isinstance(payload.get("graph"), dict) else {}
    household = payload.get("household") if isinstance(payload.get("household"), list) else []
    raw_description = payload.get("description") if isinstance(payload.get("description"), str) else ""

    programs = graph.get("programs") if isinstance(graph.get("programs"), list) else []
    description = _clean_description(raw_description, programs, household)
    specifications = _build_specifications(description)
    brief = {
        "rooms": _format_programs(programs),
        "household": [
            {
                "name": member.get("name", "").strip() if isinstance(member, dict) and isinstance(member.get("name"), str) else "",
                "relationship": member.get("relationship", "").strip() if isinstance(member, dict) and isinstance(member.get("relationship"), str) else "",
                "info": member.get("info", "").strip() if isinstance(member, dict) and isinstance(member.get("info"), str) else "",
            }
            for member in household
            if isinstance(member, dict)
            and any(
                isinstance(member.get(field), str) and member.get(field).strip()
                for field in ("name", "relationship", "info")
            )
        ],
        "access": _format_pairs(graph.get("access_pairs")),
        "adjacency": _format_pairs(graph.get("adjacency_pairs")),
        "separation": _format_pairs(graph.get("not_adjacency_pairs")),
        "description": description,
        "summary": description,
        "specifications": specifications,
    }

    has_content = any(
        [brief["rooms"], brief["household"], brief["access"], brief["adjacency"], brief["separation"], brief["description"], brief["specifications"]]
    )
    return brief if has_content else None


def _parse_layout(raw_layout: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(raw_layout)
    return payload or None


def _parse_evaluation(raw_evaluation: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(raw_evaluation)
    return payload or None


def _parse_routine(raw_routine: str | None) -> dict[str, Any] | None:
    payload = _safe_json_loads(raw_routine)
    return payload or None


def _load_layout_by_id(layout_id: str) -> dict[str, Any] | None:
    repo_root = Path(__file__).resolve().parent.parent
    pf_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons" / f"{layout_id}.json"
    if not pf_path.exists():
        return None
    try:
        payload = json.loads(pf_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _rounded_points(points: Any) -> list[list[float]]:
    if not isinstance(points, list):
        return []

    rounded: list[list[float]] = []
    for point in points:
        if not isinstance(point, list) or len(point) < 2:
            continue
        x, y = point[0], point[1]
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        rounded.append([round(float(x), 1), round(float(y), 1)])
    return rounded


def _layout_signature(layout: dict[str, Any]) -> str:
    rooms = layout.get("rooms") if isinstance(layout.get("rooms"), list) else []

    normalized_rooms: list[dict[str, Any]] = []
    for room in rooms:
        if not isinstance(room, dict):
            continue
        attributes = room.get("attributes") if isinstance(room.get("attributes"), dict) else {}
        normalized_rooms.append({
            "program": attributes.get("program"),
            "area": round(float(attributes.get("area")), 1) if isinstance(attributes.get("area"), (int, float)) else None,
            "geometry": _rounded_points(room.get("geometry")),
        })

    normalized_rooms.sort(key=lambda item: json.dumps(item, sort_keys=True))

    payload = {
        "outline": _rounded_points(layout.get("outline")),
        "rooms": normalized_rooms,
    }
    return json.dumps(payload, sort_keys=True)


def _parse_embedding_map(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _parse_search_results(raw_search_results: str | None) -> list[dict[str, Any]]:
    if not raw_search_results:
        return []

    try:
        payload = json.loads(raw_search_results)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    results: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    for candidate in payload:
        if not isinstance(candidate, dict):
            continue

        layout_id = candidate.get("layoutId") or candidate.get("id")
        if not isinstance(layout_id, str) or not layout_id.strip():
            continue

        layout = _load_layout_by_id(layout_id.strip())
        if not layout:
            continue

        signature = _layout_signature(layout)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)

        score = candidate.get("score")
        try:
            numeric_score = float(score)
        except (TypeError, ValueError):
            numeric_score = None

        results.append({
            "layoutId": layout_id.strip(),
            "score": round(numeric_score * 100) if numeric_score is not None and numeric_score <= 1 else round(numeric_score) if numeric_score is not None else None,
            "raw_score": numeric_score,
            "layout": layout,
            "name": candidate.get("name"),
        })

        if len(results) >= MAX_UNIQUE_SEARCH_RESULTS:
            break

    return results


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class LayoutRequest(BaseModel):
    session_id: str
    layout_json: str | None = None


class LayoutSelectRequest(BaseModel):
    session_id: str
    layout_id: str


class SessionRequest(BaseModel):
    session_id: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    app.state.ctx = bootstrap()
    app.state.sessions = {}
    app.state.chat_runs = {}
    try:
        yield
    finally:
        app.state.ctx.mcp_client.close()


app = FastAPI(title="inHabit Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session_store() -> dict[str, dict[str, Any]]:
    return app.state.sessions


def _chat_run_store() -> dict[str, dict[str, Any]]:
    return app.state.chat_runs


def _get_or_create_session(session_id: str | None) -> tuple[str, dict[str, Any]]:
    sid = session_id or str(uuid4())
    sessions = _session_store()
    session = sessions.setdefault(sid, {"feedback_history": []})
    session.setdefault("feedback_history", [])
    return sid, session


def _build_chat_payload(session_id: str, response: str, updated_session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "message": response,
        "brief": _build_brief(updated_session.get("topology_graph_json_string")),
        "layout": _parse_layout(updated_session.get("layout_json_string")),
        "evaluation": _parse_evaluation(updated_session.get("evaluation_json_string")),
        "routine": _parse_routine(updated_session.get("routine_json_string")),
        "search_results": _parse_search_results(updated_session.get("search_results_json_string")),
        "embedding_map": _parse_embedding_map(updated_session.get("embedding_map_json_string")),
        "needs_user_input": updated_session.get("needs_user_input", False),
        "status_messages": updated_session.get("status_messages", []),
    }


def _build_partial_payload(session_id: str, updated_session: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "brief": _build_brief(updated_session.get("topology_graph_json_string")),
        "layout": _parse_layout(updated_session.get("layout_json_string")),
        "evaluation": _parse_evaluation(updated_session.get("evaluation_json_string")),
        "routine": _parse_routine(updated_session.get("routine_json_string")),
        "search_results": _parse_search_results(updated_session.get("search_results_json_string")),
        "embedding_map": _parse_embedding_map(updated_session.get("embedding_map_json_string")),
        "needs_user_input": updated_session.get("needs_user_input", False),
        "status_messages": updated_session.get("status_messages", []),
    }


def _run_chat_in_background(session_id: str, message: str) -> None:
    run_state = _chat_run_store()[session_id]
    t_start = time.time()

    def on_status(messages: list[str], partial_session: dict[str, Any] | None = None) -> None:
        run_state["status"] = "running"
        run_state["status_messages"] = list(messages)
        if partial_session is not None:
            partial_session = {**partial_session, "status_messages": list(messages)}
            run_state["partial_result"] = _build_partial_payload(session_id, partial_session)

    try:
        _, session = _get_or_create_session(session_id)
        response, updated_session = run_agent(message, app.state.ctx, session, status_callback=on_status)
        _session_store()[session_id] = updated_session
        run_state["status"] = "completed"
        run_state["status_messages"] = updated_session.get("status_messages", [])
        run_state["result"] = _build_chat_payload(session_id, response, updated_session)
        run_state["error"] = None

        # Extract brief fields (left sidebar)
        brief = _build_brief(updated_session.get("topology_graph_json_string")) or {}
        specifications = brief.get("specifications", [])
        rooms = [r["label"] for r in brief.get("rooms", []) if isinstance(r, dict)]
        household = [m["name"] for m in brief.get("household", []) if isinstance(m, dict) and m.get("name")]

        # Extract routine fields
        routine_warning = updated_session.get("routine_warning")
        routine_raw = _parse_routine(updated_session.get("routine_json_string"))
        routine_personas = [
            p["persona"] for p in (routine_raw or {}).get("personas", [])
            if isinstance(p, dict) and p.get("persona")
        ]

        # Extract evaluation summary
        evaluation = _parse_evaluation(updated_session.get("evaluation_json_string"))
        evaluation_summary = evaluation.get("chat_summary") if isinstance(evaluation, dict) else None

        log_run(
            session_id=session_id,
            user_prompt=message,
            llm_provider=app.state.ctx.llm_provider,
            llm_model=app.state.ctx.llm_model,
            nodes_executed=updated_session.get("nodes_executed", []),
            selected_layout_id=updated_session.get("layout_id"),
            agent_response=response,
            specifications=specifications,
            rooms=rooms,
            household=household,
            routine_status="warning" if routine_warning else "success",
            routine_personas=routine_personas,
            routine_warning=routine_warning,
            evaluation_summary=evaluation_summary,
            duration_seconds=time.time() - t_start,
            status="success",
        )
    except Exception as exc:
        log_run(
            session_id=session_id,
            user_prompt=message,
            llm_provider=getattr(app.state.ctx, "llm_provider", "unknown"),
            llm_model=getattr(app.state.ctx, "llm_model", "unknown"),
            nodes_executed=[],
            selected_layout_id=None,
            agent_response=None,
            specifications=[],
            rooms=[],
            household=[],
            routine_status="error",
            routine_personas=[],
            routine_warning=None,
            evaluation_summary=None,
            duration_seconds=time.time() - t_start,
            status="error",
            error=str(exc),
        )
        run_state["status"] = "failed"
        run_state["error"] = str(exc)


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatRequest) -> dict[str, Any]:
    sid, session = _get_or_create_session(body.session_id)
    response, updated_session = run_agent(body.message, app.state.ctx, session)
    _session_store()[sid] = updated_session

    return _build_chat_payload(sid, response, updated_session)


@app.post("/chat/start")
def start_chat(body: ChatRequest) -> dict[str, Any]:
    sid, _ = _get_or_create_session(body.session_id)
    existing_run = _chat_run_store().get(sid)
    if existing_run and existing_run.get("status") == "running":
        return {
            "session_id": sid,
            "status": "running",
            "status_messages": existing_run.get("status_messages", []),
        }

    _chat_run_store()[sid] = {
        "status": "running",
        "status_messages": [],
        "partial_result": None,
        "result": None,
        "error": None,
    }
    worker = threading.Thread(target=_run_chat_in_background, args=(sid, body.message), daemon=True)
    worker.start()
    return {"session_id": sid, "status": "running", "status_messages": []}


@app.get("/chat/status/{session_id}")
def get_chat_status(session_id: str) -> dict[str, Any]:
    run_state = _chat_run_store().get(session_id)
    if run_state is None:
        raise HTTPException(status_code=404, detail="No active chat run for this session")

    payload = {
        "session_id": session_id,
        "status": run_state.get("status", "running"),
        "status_messages": run_state.get("status_messages", []),
    }
    if run_state.get("partial_result") is not None:
        payload["partial_result"] = run_state.get("partial_result")
    if run_state.get("status") == "completed":
        payload["result"] = run_state.get("result")
    if run_state.get("status") == "failed":
        payload["error"] = run_state.get("error") or "Chat run failed"
    return payload


@app.post("/upload-layout")
async def upload_layout(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        session_id = form.get("session_id")
        file = form.get("file")
        if file is None:
            raise HTTPException(status_code=400, detail="Missing layout file")
        raw_bytes = await file.read()
        try:
            layout_payload = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"Invalid layout JSON: {exc}") from exc
        layout_json = json.dumps(layout_payload)
    else:
        body = LayoutRequest.model_validate(await request.json())
        session_id = body.session_id
        layout_json = body.layout_json

    sid, session = _get_or_create_session(session_id)

    session["input_layout_json_string"] = layout_json
    _session_store()[sid] = session

    layout = _parse_layout(layout_json)
    return {
        "ok": True,
        "session_id": sid,
        "layoutId": (layout or {}).get("layoutId", "uploaded") if layout_json else None,
    }


@app.post("/restore-layout")
def restore_layout(body: LayoutRequest) -> dict[str, Any]:
    sid, session = _get_or_create_session(body.session_id)
    session["layout_json_string"] = body.layout_json
    _session_store()[sid] = session
    return {"ok": True, "session_id": sid}


@app.post("/select-layout")
def select_layout(body: LayoutSelectRequest) -> dict[str, Any]:
    sid, session = _get_or_create_session(body.session_id)
    session["forced_layout_id"] = body.layout_id
    response, updated_session = run_agent(f"select {body.layout_id}", app.state.ctx, session)
    _session_store()[sid] = updated_session
    return _build_chat_payload(sid, response, updated_session)


@app.get("/layout/{layout_id}")
def get_layout_by_id(layout_id: str) -> dict[str, Any]:
    layout = _load_layout_by_id(layout_id)
    if not layout:
        raise HTTPException(status_code=404, detail=f"Layout {layout_id} not found")
    return {"layoutId": layout_id, "layout": layout}


@app.delete("/session")
def clear_session(body: SessionRequest) -> dict[str, bool]:
    _session_store().pop(body.session_id, None)
    _chat_run_store().pop(body.session_id, None)
    return {"ok": True}