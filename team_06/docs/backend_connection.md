# Backend Connection Guide

How to connect the Vue 3 frontend to the Python agent backend via Flask or FastAPI.

---

## Architecture Overview

```
Frontend (Vue 3 / Vite)          Backend (Flask or FastAPI)
─────────────────────            ──────────────────────────
App.vue                  ←────→  POST /chat
  chatHistory                    POST /upload-layout
  agentState                     GET  /session
  boundary (input layout)        DELETE /session
  layoutHistory
```

The backend owns the **agent session** (LangGraph state between turns).  
The frontend owns the **UI history** (list of received layouts for display).

---

## Session Model

Each browser session maps to a server-side session dict that persists across turns:

```python
# graph.py — what survives between turns (returned by run_agent)
session = {
    "layout_json_string":          str,   # current working layout
  "input_layout_json_string":    str,   # uploaded boundary / outline JSON
    "topology_graph_json_string":  str,   # topology for search
    "search_results_json_string":  str,   # scored candidates
    "feedback_history":            list,  # all user messages so far
}
```

Use a **session ID** (UUID generated on first load, stored in `sessionStorage`) sent as a header or cookie so the server can look up the right session.

---

## API Endpoints

### `POST /chat`

Main turn endpoint. Accepts a user message plus optional session context.

**Request**
```json
{
  "session_id": "abc-123",
  "message": "I want 2 bedrooms and a study"
}
```

**Response**
```json
{
  "session_id": "abc-123",
  "message": "Here is a layout with 2 bedrooms…",
  "brief": {
    "rooms": [
      { "name": "bedroom", "count": 2, "label": "2 x bedroom" },
      { "name": "study", "count": 1, "label": "study" }
    ],
    "access": ["bedroom - bathroom"],
    "adjacency": ["kitchen - dining"],
    "separation": [],
    "description": "workspace for two adults",
    "summary": "workspace for two adults"
  },
  "layout": {
    "layoutId": "Layout-001",
    "outline": [[0,0],[10,0],[10,8],[0,8]],
    "rooms": [
      {
        "id": "r1", "name": "Bedroom 1",
        "geometry": [[…]],
        "attributes": { "program": "bed", "area": 14.5, "daylight": 1.2 }
      }
    ],
    "attributes": { "description": "2 bedrooms, 1 study" }
  },
  "suggested_prompts": [
    "Make the bedrooms larger",
    "Add a bathroom"
  ]
}
```

- `layout` is `null` if the agent is still asking clarification questions.
- `brief` is `null` until the reason node produces useful topology/search input.
- The frontend Brief tab should only display rooms, room relationships, and description.
- Household-specific fields and routine output are intentionally out of scope for the current backend contract.

---

### `POST /upload-layout`

Called when the user uploads a boundary JSON file via the toolbar.  
Stores it in the session as `input_layout_json_string` (the outline/constraints the agent must respect).

**Request** — `multipart/form-data`
```
session_id: abc-123
file: <layout.json>
```

or as JSON:
```json
{
  "session_id": "abc-123",
  "layout_json": "{ \"outline\": [[0,0],[10,0],...], \"rooms\": [...] }"
}
```

**Response**
```json
{ "ok": true, "layoutId": "L_L12.0_W10.5_…" }
```

**Backend behaviour**
```python
# In the session dict:
session["input_layout_json_string"] = json.dumps(uploaded_layout)
# graph.py reads this value from the session in _build_initial_state
```

---

### `POST /restore-layout`

Called when the user clicks a layout in the History tab to restore it as the current working layout.

**Request**
```json
{
  "session_id": "abc-123",
  "layout_json": "{ … full layout JSON … }"
}
```

**Response**
```json
{ "ok": true }
```

**Backend behaviour**
```python
session["layout_json_string"] = request.json["layout_json"]
```

This replaces the working layout in state so the next `/chat` turn starts from that layout.

---

### `DELETE /session`

Clears the server-side session (called by frontend "New Chat").

**Request**
```json
{ "session_id": "abc-123" }
```

**Response**
```json
{ "ok": true }
```

---

## History: Frontend vs Backend

| Concern | Owner | Rationale |
|---|---|---|
| Layout history list (UI) | **Frontend** | Pure display, no agent logic needed |
| Current working layout | **Backend session** | Agent must read/write it across turns |
| Input boundary layout | **Backend session** | Agent needs it on every turn |
| Chat message history (UI) | **Frontend** | Display only |
| `feedback_history` (agent reasoning) | **Backend session** | Used by LangGraph nodes to avoid repeating questions |
| Past sessions (cross-reload) | Neither (future) | Requires DB; skip for now |

The frontend `layoutHistory` array in `App.vue` is populated whenever a layout arrives from the backend — it is **never sent back** to the backend (except via `/restore-layout` when the user explicitly restores one). Uploaded boundary files should not be added to history.

---

## Current Team 06 Contract

- Backend entrypoint: `team_06/python/app.py`
- Frontend API client: `team_06/frontend/src/api/agentClient.js`
- `/chat` returns `brief`, not `parsed_prompt`
- `brief` is derived from `topology_graph_json_string`
- Routine visualization stays disabled for now

### Run Locally

Backend:
```powershell
cd team_06/python
..\..\.venv\Scripts\python.exe -m uvicorn app:app --reload
```

Frontend:
```powershell
cd team_06/frontend
npm run dev
```

Optional frontend env override:
```powershell
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"
```

---

## Flask Implementation Sketch

```python
# app.py
from flask import Flask, request, jsonify, session
from graph import run_agent
from _runtime.bootstrap import bootstrap
import json, uuid

app = Flask(__name__)
app.secret_key = "change-me"

_sessions: dict[str, dict] = {}   # in-memory; replace with Redis for production
ctx = bootstrap()

@app.route("/chat", methods=["POST"])
def chat():
    body = request.json
    sid = body["session_id"]
    sess = _sessions.setdefault(sid, {"feedback_history": []})
    
    response, sess = run_agent(body["message"], ctx, sess)
    _sessions[sid] = sess
    
    layout_raw = sess.get("layout_json_string")
    layout = json.loads(layout_raw) if layout_raw else None
    
    parsed_raw = sess.get("parsed_prompt")
    parsed = json.loads(parsed_raw) if parsed_raw else None

    return jsonify({
        "message": response,
        "parsed_prompt": parsed,
        "layout": layout,
        "suggested_prompts": []   # TODO: generate from agent
    })

@app.route("/upload-layout", methods=["POST"])
def upload_layout():
    body = request.json
    sid = body["session_id"]
    sess = _sessions.setdefault(sid, {"feedback_history": []})
    sess["input_layout_json_string"] = body["layout_json"]
    _sessions[sid] = sess
    layout = json.loads(body["layout_json"])
    return jsonify({"ok": True, "layoutId": layout.get("layoutId", "uploaded")})

@app.route("/restore-layout", methods=["POST"])
def restore_layout():
    body = request.json
    sid = body["session_id"]
    sess = _sessions.setdefault(sid, {"feedback_history": []})
    sess["layout_json_string"] = body["layout_json"]
    _sessions[sid] = sess
    return jsonify({"ok": True})

@app.route("/session", methods=["DELETE"])
def clear_session():
    sid = request.json["session_id"]
    _sessions.pop(sid, None)
    return jsonify({"ok": True})
```

---

## FastAPI Implementation Sketch

```python
# app.py
from fastapi import FastAPI
from pydantic import BaseModel
from graph import run_agent
from _runtime.bootstrap import bootstrap
import json

app = FastAPI()
ctx = bootstrap()
_sessions: dict[str, dict] = {}

class ChatRequest(BaseModel):
    session_id: str
    message: str

class UploadLayoutRequest(BaseModel):
    session_id: str
    layout_json: str

class RestoreLayoutRequest(BaseModel):
    session_id: str
    layout_json: str

class ClearSessionRequest(BaseModel):
    session_id: str

@app.post("/chat")
def chat(req: ChatRequest):
    sess = _sessions.setdefault(req.session_id, {"feedback_history": []})
    response, sess = run_agent(req.message, ctx, sess)
    _sessions[req.session_id] = sess

    layout_raw = sess.get("layout_json_string")
    layout = json.loads(layout_raw) if layout_raw else None
    parsed_raw = sess.get("parsed_prompt")
    parsed = json.loads(parsed_raw) if parsed_raw else None

    return {
        "message": response,
        "parsed_prompt": parsed,
        "layout": layout,
        "suggested_prompts": []
    }

@app.post("/upload-layout")
def upload_layout(req: UploadLayoutRequest):
    sess = _sessions.setdefault(req.session_id, {"feedback_history": []})
    sess["input_layout_json_string"] = req.layout_json
    layout = json.loads(req.layout_json)
    return {"ok": True, "layoutId": layout.get("layoutId", "uploaded")}

@app.post("/restore-layout")
def restore_layout(req: RestoreLayoutRequest):
    sess = _sessions.setdefault(req.session_id, {"feedback_history": []})
    sess["layout_json_string"] = req.layout_json
    return {"ok": True}

@app.delete("/session")
def clear_session(req: ClearSessionRequest):
    _sessions.pop(req.session_id, None)
    return {"ok": True}
```

---

## Frontend Changes Required

### 1. Session ID (App.vue)

```js
// Generate once per browser session
const sessionId = sessionStorage.getItem('sessionId') ?? (() => {
  const id = crypto.randomUUID()
  sessionStorage.setItem('sessionId', id)
  return id
})()
```

### 2. Replace `getAgentResponse` mock (App.vue)

```js
// src/api/agentClient.js  (new file)
const BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export async function sendMessage(sessionId, message) {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, message })
  })
  return res.json()   // { session_id, message, brief, layout }
}

export async function uploadLayout(sessionId, layoutJson) {
  const res = await fetch(`${BASE}/upload-layout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, layout_json: layoutJson })
  })
  return res.json()
}

export async function restoreLayout(sessionId, layoutJson) {
  await fetch(`${BASE}/restore-layout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, layout_json: layoutJson })
  })
}

export async function clearSession(sessionId) {
  await fetch(`${BASE}/session`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId })
  })
}
```

### 3. `handleLayoutLoaded` — upload on file load

```js
async function handleLayoutLoaded(json) {
  boundary.value = json
  if (json) {
    await uploadLayout(sessionId, JSON.stringify(json))
    agentState.value = { layoutId: json.layoutId || 'Boundary', … }
    layoutHistory.value.push({ …agentState.value, _savedAt: new Date().toISOString() })
  } else {
    agentState.value = null
  }
}
```

### 4. `handleRestore` — sync working layout to backend

```js
async function handleRestore(layout) {
  agentState.value = layout
  await restoreLayout(sessionId, JSON.stringify(layout))
}
```

### 5. `handleNewChat` — clear server session

```js
async function handleNewChat() {
  await clearSession(sessionId)
  sessionStorage.removeItem('sessionId')   // forces new ID on next turn
  chatHistory.value = []
  agentState.value = null
  parsedInput.value = null
  boundary.value = null
}
```

### 6. `.env` file (frontend)

```
VITE_API_BASE_URL=http://127.0.0.1:8000
```

---

## CORS (required for local dev)

**Flask**
```python
from flask_cors import CORS
CORS(app, origins=["http://localhost:5173"])
```

**FastAPI**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
```

---

## Frontend Data Contract (what the backend must return)

This section documents exactly what the Vue frontend expects to receive from the backend.
The mock in `src/mock/agentMock.js` is the source of truth for shape; this section is its authoritative description.

---

### Top-level response shape

Every `/chat` and `/sidebar-add` response must follow this shape:

```json
{
  "message":          "string — agent reply shown in chat",
  "suggestedPrompts": ["string", "…"],
  "parsedInput":      { … } | null,
  "layout":           { … } | null
}
```

- `parsedInput: null` → frontend keeps the previous value unchanged.
- `layout: null` → frontend keeps the previous layout unchanged.

---

### `brief` object

```json
{
  "rooms": [
    { "name": "kitchen", "count": 1, "label": "kitchen" },
    { "name": "bedroom", "count": 2, "label": "2 x bedroom" }
  ],
  "access": ["kitchen - living"],
  "adjacency": ["bedroom - bathroom"],
  "separation": ["bedroom - kitchen"],
  "description": "quiet workspace and natural light",
  "summary": "quiet workspace and natural light"
}
```
Routine output is intentionally omitted for now. The toolbar entry can remain visible but disabled until the backend exposes a dedicated routine payload again.

#### `steps` array

- **Length: 9** — one entry per time slot.
- **Time slots** (index → label):

  | Index | Time  |
  |-------|-------|
  | 0     | 06:00 |
  | 1     | 08:00 |
  | 2     | 10:00 |
  | 3     | 12:00 |
  | 4     | 14:00 |
  | 5     | 16:00 |
  | 6     | 18:00 |
  | 7     | 20:00 |
  | 8     | 22:00 |

- Each entry is either a **room id string** (matching `layout.rooms[].id`) or **`null`** meaning the persona is away / not at home.
- `color` is a hex string; the frontend uses it for the persona circle on the canvas and the persona dot in the sidebar legend. The frontend also has a fallback palette (`PERSONA_COLORS` in `src/utils/roomAnalysis.js`) if color is omitted.

---

### `layout` object

```json
{
  "layoutId": "Layout-001",
  "attributes": {
    "description": "1 kitchen, 1 living, 2 bedrooms, 1 bathroom"
  },
  "outline": [[0,0],[13,0],[13,7],[0,7],[0,0]],
  "rooms": [
    {
      "id": "1",
      "name": "Kitchen",
      "geometry": [[0,0],[0,4],[4,4],[4,0],[0,0]],
      "attributes": {
        "program":  "kitchen",
        "area":     16,
        "daylight": 4.4
      }
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `layoutId` | yes | Shown in the sidebar card title |
| `rooms[].id` | yes | Must be a **string**; used as key for routine `steps` lookup |
| `rooms[].geometry` | yes | Array of `[x, y]` pairs (closed polygon, last point = first point) |
| `rooms[].attributes.program` | yes | One of: `bed`, `bath`, `kitchen`, `living`, `foyer`, `study`, `extra` |
| `rooms[].attributes.area` | recommended | Shown in layout/daylight sidebar |
| `rooms[].attributes.daylight` | optional | DA value 0–5; enables the Daylight view mode tab |
| `outline` | optional | Boundary polygon; shown when `rooms` is empty |

---

### View modes driven by data

| View mode tab | Enabled when | Data required |
|---|---|---|
| Layout | always (if layout exists) | `layout.rooms` |
| Daylight | any room has `attributes.daylight` | `rooms[].attributes.daylight` |
| Routine (clock icon) | `parsedInput.routine` is present and non-empty | `parsedInput.routine` |

---

### Sidebar add endpoint (`/sidebar-add`)

The frontend sidebar lets users add rooms/people/activities via buttons without typing.
This maps to `getAgentResponseForSidebarAdd(section, item, state)` in the mock.

```
POST /sidebar-add
{
  "session_id": "abc-123",
  "section":    "rooms" | "households" | "activities",
  "item":       "Bedroom" | "Anna" | "Yoga",
  "state":      { … current parsedInput … }
}
```

Response shape is identical to `/chat`.
The backend should update the working state, regenerate the layout if a room was added, and return a new `routine` inside `parsedInput` if applicable.

---

### Routine regeneration triggers

The backend should return a fresh `routine` whenever any of the following change:

- A room is added or removed (room IDs change)
- A household member is added
- A `workStyle` is updated for any persona
- A work-related activity is added or removed

The frontend will automatically switch to the Routine view tab if `parsedInput.routine` arrives for the first time.
