# Team 03 — Industrial Spatial Flow Agent

> Canonical project documentation for the entire `team_03/` folder. Lives at
> `team_03/CLAUDE.md` (moved here from `ramon_experiments/conversations/`).
> Consolidates the former MASTER_CLAUDE.md and MASTER_CLAUDE_V2.md into a single
> source of truth. The agent is **industrial-only**.

## What this project does

An AI agent that optimizes **industrial** floor plan layouts by placing equipment and analyzing spatial quality against OSHA, NFPA, and ISO standards. It connects a Python LangGraph pipeline to a Grasshopper/Rhino simulation backend via MCP (Model Context Protocol), using Swiftlet as the MCP server. Scope is **industrial only** — factories, workshops, warehouses, assembly halls, fabrication areas, clean rooms. (Residential layouts may exist on disk but are out of scope.)

The agent accepts a natural-language prompt, reasons about the layout, calls Grasshopper tools to run simulations, places objects, runs a multi-tool analysis pipeline (collision, visibility, path, reachability, orientation), computes a weighted quality score, and presents a user checkpoint for approval or iterative refinement. Two preprocessing agents (Profile Agent and Space Type Agent) enrich the context with movement-profile and space-specific priorities before the main reasoning loop. An optional **Populate Agent** can fill an empty layout zone-by-zone from a single high-level prompt.

A **Spatial Relationship Graph** (NetworkX MultiGraph) gives the LLM structured spatial context instead of raw JSON. Instead of parsing raw coordinates, the LLM receives pre-computed topology (room connectivity, proximity relationships, containment) and actionable fix directives after each analysis cycle: `move [+0.9,+0.4] 0.4m to fix clearance (has 0.6m, needs 0.9m)`. When violations are detected after placement, the system auto-corrects by injecting a correction message with exact move vectors and loops back to the LLM (max 3 attempts).

---

## Architecture

```
main.py
    |
bootstrap (_runtime/bootstrap.py)
    | -- resolve layout, session, connect MCP, build LLM
    |
LangGraph (graph.py)
    |
    +-- profile_agent.py       (identify movement profile: forklift, worker, crane...)
    +-- space_type_agent.py    (detect space subtype: workshop, warehouse, assembly...)
    +-- populate_agent.py      (optional: zone-by-zone layout population)
    +-- memory.py              (per-layout durable memory + protected User Rules)
    +-- prompts.py             (SYSTEM_PROMPT, SPACE/PROFILE/POPULATE/MEMORY templates)
    +-- reason.py              (LLM decision: place / tool / query / final; injects
    |                           memory + spatial graph; captures agent_message narrative)
    +-- tools.py               (execute MCP tool calls)
    +-- add_objects.py         (place_objects MCP + spatial graph rebuild)
    |
    +-- fan_out.py             (analysis_fan_out_node: parallel trigger)
    |                          (group1_join_node: collision gate + correction)
    +-- Group 1 (parallel)
    |   +-- collision.py       (BFS grid analysis, clearance, functional lines)
    |   +-- visibility.py      (isovist + sightline analysis)
    |   +-- orientation.py     (facing direction check)
    |
    +-- Group 2 (sequential)
    |   +-- path_analysis.py   (BFS room-level + A* object-level)
    |   +-- reachability.py    (ergonomic reach envelope)
    |
    +-- graph.py: enrich_graph_node   (spatial graph enrichment + FINDINGS + correction)
    +-- scoring.py             (weighted 0-100 score, letter grade)
    +-- checkpoint.py          (user approval gate, viewport toggles, suggestions)
    +-- explain.py             (LLM summary of approved layout)
    +-- output.py              (save final layout, close session)
    |
    +-- spatial_graph.py       (NetworkX spatial relationship graph module)
    +-- query_agent.py         (analysis-only path, no placement)
    +-- visualize_interactive.py (live interactive HTML graph visualizer)
    |
    _runtime/
    +-- bootstrap.py           (Context dataclass, session init, MCP, LLM)
    +-- llm.py                 (call_llm, call_llm_simple, narrative capture, provider abstraction)
    +-- mcp_client.py          (HTTP JSON-RPC client for Swiftlet)
    +-- session.py             (create/save/close session_active.json)
    +-- utils.py               (_slim_layout, _format_tool_catalog)
    +-- config.py              (.env loader)
    |
    Grasshopper (Swiftlet @ localhost:3002)
```

---

## Graph Flow

```
START -> profile_agent -> space_type_agent -> populate_check
                                               |
                              populate prompt?  +-- YES -> populate_agent -> memory -> reason
                                                +-- NO  ----------------------> memory -> reason
                                               |
  memory: loads memory/<layout>.md, distills the latest user message into durable
          facts (User Rules block kept verbatim), injected into reason every turn.
          Runs on each user-message entry point (startup, populate, checkpoint
          "continue"); skipped on internal tool/adjustment loops.

reason:
                              +----------------+----------------+
                              v                v                v
                         add_objects       run_tool         query_agent
                              |                |                |
                              v                v                v
                         analysis_fan_out    reason         user_checkpoint
                              |                                  |
                 +------------+------------+               query_done -> END
                 v            v            v
             collision    visibility  orientation   <-- Group 1 (parallel)
                 |            |            |
                 +------------+------------+
                              v
                         group1_join
                              |
                 hard violations? + objects placed? + adj < 3?
                    YES -> reason + correction message
                    NO  -> path
                              |
                              v
                            path                   <-- Group 2 (sequential)
                              v
                        reachability
                              v
                        enrich_graph  <-- SPATIAL GRAPH ENRICHMENT + FINDINGS
                              |
                 violations? + objects placed? + adj < 3?
                    YES -> reason + correction message (from enrich_graph)
                    NO  -> scoring
                              v
                           scoring
                              v
                        user_checkpoint
                        | shows "Agent:" chat message + active User Rules
                        | 1=BEFORE  2=AFTER  3=collision  4=visibility  5=paths
                        | 0=clear overlays   s1..s5=smart suggestions
                        | rule:/mem:/remember: add rule   forget: <n|text|all> remove
                        +--------+--------+
                      approved        continue -> reason
                        |
                        v
                      explain -> output -> END
```

**Key routing rules:**
- `populate_check` routes to `populate_agent` if the prompt contains `populate`, `fill`, `set up`, `setup`, or `generate layout`; otherwise straight to `reason`. After populating the zone queue it always goes to `reason`.
- `adjust` only if `last_placement_result is not None` AND `adjustment_count < MAX_ADJUSTMENTS (3)`.
- `query_agent` path: analysis without placement, goes to `user_checkpoint` then `query_end` (no output saved).
- `enrich_graph` runs BEFORE the group2 routing decision so the graph has full analysis data when the correction message is built.

---

## Preprocessing & Population Agents

- **Profile Agent** (`nodes/profile_agent.py`) — Identifies the movement profile from the prompt (industrial profiles only). Outputs `profile_config` (reach envelope, min path width, turning radius). Default: `standard_worker`.
- **Space Type Agent** (`nodes/space_type_agent.py`) — Detects the industrial subtype (workshop, warehouse, assembly, fabrication, clean room...) and outputs `space_config` (analysis priorities, clearances, per-tool weight overrides).
- **Populate Agent** (`nodes/populate_agent.py`) — Optional zone-by-zone population flow. Splits a room into functional zones, then for each zone calls `calculate_zone_coordinates()` (LLM, `POPULATE_COORDS_PROMPT`) to compute x,y placements respecting clearance, doors, windows, and MEP. Fills the `zone_queue`; `reason` then drains it placement-by-placement. Always places with `standard_worker` profile.

---

## Conversational Memory & User Rules

Per-layout durable memory persisted to `team_03/memory/<layout_name>.md` (gitignored — it is per-user local data). The **Memory node** (`nodes/memory.py`) loads the file once per session, distills the latest user message into durable facts via `MEMORY_DISTILL_PROMPT`, and writes it back immediately (crash-safe). `reason.py` injects `state["memory_text"]` (via `MEMORY_CONTEXT_TEMPLATE`) on every turn so the LLM recalls facts and preferences across sessions.

### Two kinds of memory
| Kind | Heading | How saved | Distiller behavior |
|------|---------|-----------|--------------------|
| **User Rules** (binding) | `## User Rules` | `rule:` / `mem:` / `remember:` checkpoint command (verbatim) | **Protected** — `distill_memory` strips this block out before the LLM call and re-attaches it verbatim, so it can never be reworded, softened, or dropped |
| **Distilled facts** (soft) | `## Preferences`, `## Decisions`, … | Auto-distilled from each user message | Merged/deduplicated by the LLM each turn |

User Rules are presented to the reason LLM as **binding constraints** (`MEMORY_CONTEXT_TEMPLATE`): it must honor them on every placement/move, and if a request conflicts with a rule (or two rules conflict), it must surface the conflict and ask which takes priority rather than silently ignoring a rule.

### Checkpoint memory commands
- `rule: <text>` (aliases `mem:`, `remember:`) — add a binding rule, verbatim.
- `forget: <n>` — remove rule number n; `forget: <text>` — remove by substring; `forget: all` — clear all.
- `rules` / `mem` — list current rules without changing anything.
- Active User Rules are printed on every checkpoint under "Memory — active user rules (always enforced)".

Helpers live in `nodes/memory.py`: `split_rules`, `compose_memory`, `add_user_rule`, `remove_user_rule`, `list_user_rules`. Legacy `## User notes` headings are recognized and migrated to `## User Rules`.

### Onboarding profile → memory (AGENT_ui)
The AGENT_ui welcome flow (`OnboardingPage.tsx`) collects **User Profile** (role, experience, name) and **Space Profile** (layout status, workflow type, notes — button picks *and* free text). On completion the frontend `POST`s to **`/api/profile`** (`AGENT_ui/backend/api_routes.py`), which writes a single **global** file `team_03/memory/user_profile.md` (`## User Profile` + `## Space Profile`, labels resolved, overwritten each submit). It is global because onboarding happens before any layout is chosen.

On chat session start, `build_context` (`AGENT_ui/backend/pipeline_bridge.py`, `_inject_user_profile`) merges that profile into the **active layout's** `memory/<layout>.md` under the protected `## User Rules` block as `User profile — …` / `Space profile — …` lines — reusing the `nodes/memory.py` helpers, deduped, replacing any stale profile lines first. So the profile is recalled like any binding User Rule. It runs **before** the MCP probe and is wrapped in try/except, so it persists even if Rhino/Swiftlet is down and never breaks startup. (`team_03/python` is read-only; only its helpers are imported.)

Completing onboarding also marks the first two pipeline nodes done in the UI: `profile_agent` always, and `space_type_agent` only when the Space step wasn't skipped (`useAgentState.markNodesCompleted`). A later real pipeline run overwrites these via `agent_event`.

### Agent chat message
The reason LLM's human-readable narrative is captured every turn as `state["agent_message"]` — `final_response` on a `final` turn, or the prose surrounding the JSON on a `tool`/placement turn (extracted by `_extract_narrative` in `_runtime/llm.py`). The checkpoint renders it as an indented **"Agent:"** block right above the `Your decision:` prompt, so the agent's message is visible without scrolling up to the truncated `[anthropic] Raw response preview`.

---

## Analysis Pipeline (5 tools + scoring)

### 1. Collision (`nodes/collision.py`) — Weight 0.30
Pure Python BFS grid collision analysis (0.10m resolution). No Rhino dependency.
1. Rasterizes outline as free space, then walls (with thickness, split at doors), furniture, and MEP as obstacles.
2. Computes BFS brushfire distance field + nearest-obstacle attribution per cell.
3. Checks: body clearance, corridor width, door widths, turning radii, connectivity, use_point clearance/reachability, functional_line obstruction.
4. **Voronoi boundary method** computes real `min_clearance_m` (actual surface-to-surface gap between an object and its nearest obstacle), replacing the old per-cell minimum that always bottomed out at 0.1m. Objects touching another obstacle get `min_clearance_m = 0.0`.

**Violation types:** `BLOCKED`, `WARNING`, `CONNECTIVITY`, `DOOR_WIDTH`, `TURNING`, `USE_POINT`, `USE_POINT_UNREACHABLE`, `FUNCTIONAL_LINE`.

### 2. Visibility (`nodes/visibility.py`) — Weight 0.20
Isovist + sightline analysis. Casts 72 rays (every 5°) from each object's use_point. Mode 1 (no objects): centroid-to-centroid room pairs. Mode 2 (objects): use_point → functional_point pairs. Only same-room pairs are checked. Calls `visualize_visibility` MCP tool.

### 3. Path Analysis (`nodes/path_analysis.py`) — Weight 0.25
- **Mode 1 (no furniture):** BFS through door graph, all room pairs + worst-case egress (Shapely `representative_point()` for concave rooms).
- **Mode 2 (furniture):** A* on 0.5m grid per room, 8-directional, other furniture as obstacles, object-to-object distances.

### 4. Reachability (`nodes/reachability.py`) — Weight 0.15
Ergonomic reach envelope: `height_ok` (functional_point z within reach range) and `radius_ok` (2D distance from use_point ≤ reach_radius). Heights estimated from object-name keywords.

### 5. Orientation (`nodes/orientation.py`) — Weight 0.10
Facing-direction check for objects with an `orientation` field. Resolves targets from `target_direction` (angle/vector) or `target` (point or object ref). Tolerance: 45°.

### Scoring (`nodes/scoring.py`)
Weighted 0–100 score, letter grade A–F (A≥90, B≥75, C≥60, D≥40, F<40). **Structure (wall) violations penalized at 20%** (not actionable); **furniture/MEP at 100%** (actionable). Space config can override weights. The checkpoint shows ANSI-colored deltas (green ▲ / red ▼) vs `previous_scoring`.

---

## Spatial Graph Layer

A NetworkX MultiGraph that encodes relationships between layout elements. It lives in `AgentState` as `spatial_graph` (dict) and `spatial_graph_text` (str). The module (`spatial_graph.py`) is pure Python — no LangGraph/MCP/LLM dependencies — and the graph is ephemeral (RAM only), rebuilt from layout JSON after each placement.

### Base graph (built from layout JSON)
| Node type | Source |
|-----------|--------|
| `room` | `layout.rooms[]` |
| `door` | `layout.doors[]` |
| `wall` | `layout.structure[]` |
| `window` | `layout.windows[]` |
| `furniture` | `layout.furniture[]` |
| `mep` | `layout.mep[]` |

| Edge type | Meaning |
|-----------|---------|
| `contained_in` | furniture/mep/window → room |
| `door_connects` | door → rooms |
| `adjacent` | room ↔ room (shared door) |
| `near` | furniture ↔ furniture, same room, < 3m |
| `near_wall` | furniture ↔ wall, point-to-segment < 3m |
| `near_window` | furniture ↔ window, same room, point-to-segment < 3m |

### Enriched graph (after analysis tools)
| Source | Adds |
|--------|------|
| Collision | Node attrs: `clearance_ok`, `deficit_m`, `min_clearance_m`, `required_clearance_m`, `move_direction`, `move_distance_m`. Edge: `blocks` |
| Visibility | Edge: `sightline` (`visible` bool) |
| Path | Edge: `path` (`distance_m`, `reachable`) |
| Reachability | Node attrs: `reachable`, `height_ok`, `radius_ok` |
| Orientation | Node attrs: `facing_ok`, `angle_diff` |

`clearance_ok` is based on `deficit_m <= 0` (not just presence of a `clearance_violation` dict). Walls are skipped in collision enrichment (`_skip_ntypes = {"wall"}`) — structural, not movable.

### The feedback loop
```
build_graph_from_layout(layout)  -> serialize_for_llm(G)  -> LLM places/moves
        -> rebuild graph (add_objects.py)  -> 5 analysis tools
        -> enrich_graph_from_analysis(G)   -> FINDINGS printed (ANSI colored)
        -> violations + placement? YES -> _build_correction_message(G) -> reason
                                   NO  -> scoring
```
**Fallback move direction:** when collision detects a clearance violation but the object has no `use_point`, `spatial_graph.py` computes a unit vector from object center toward room center, distance = deficit + 0.1m safety margin.

---

## Interactive Graph Visualizer (`visualize_interactive.py`)

Standalone live HTML visualization of the spatial graph (Apple-minimalist aesthetic, vis.js, no pyvis/server framework dependency). A minimal localhost HTTP daemon on port **7477** (CORS `*`, `Cache-Control: no-store`) enables live change-detection polling (`file://` blocks `fetch()`).

| Feature | Description |
|---------|-------------|
| Architectural positions | Nodes at real layout coords (flipped Y), `physics: false`, `fixed: true` |
| Dark/Light theme | Toggle persists in `localStorage`; glass-morphism panels |
| Legend filtering | Click to filter by type (shift-click multi); non-matching fade to 8% |
| Detail panel | Click a node for type chip, all metadata, description, clickable neighbors |
| Drag snap-back | Draggable nodes spring back (550ms ease-out cubic) |
| New-element highlight | Recently added/changed get blue `#007AFF` border (fades 4s) + "new" badge |
| Live auto-refresh | HTTP smart detect (`PAGE_TS` compare) or blind `location.reload()` with adaptive 2–10s backoff |
| Viewport preservation | Zoom/pan saved to `sessionStorage`, restored via `network.moveTo()` |

```bash
cd team_03/python
python visualize_interactive.py --session     # live workspace (with placed furniture)
python visualize_interactive.py industrial_03 # specify base layout
python visualize_interactive.py --open        # re-open existing HTML
# Opens http://127.0.0.1:7477/spatial_graph_interactive.html
```

**Pipeline integration** — the graph auto-updates at three points: startup (`_build_initial_state`), after placement (`add_objects.py`, highlights via `viz_highlight_ids`), and after enrichment (`enrich_graph_node`, marks enrichment edges new).

There is also a standalone matplotlib visualizer, `test_spatial_graph.py` (`--session` / layout name / `--all`), for static inspection without a browser.

---

## Industrial User Profiles

| Profile | Min path (m) | Turning radius (m) | Reach min (m) | Reach max (m) |
|---------|-------------|-------------------|--------------|--------------|
| standard_worker | 0.90 | 0.60 | 0.50 | 2.00 |
| forklift | 3.05 | 2.50 | 0.00 | 6.00 |
| crane | 5.00 | 5.00 | 0.00 | 12.00 |
| pallet_jack | 1.50 | 1.50 | 0.20 | 1.20 |
| maintenance_worker | 0.90 | 0.60 | 0.30 | 2.20 |

Default: `standard_worker`. Detected from prompt keywords by the Profile Agent.

## Space Type Clearances

| Space type | Min clearance (m) | Standard |
|-----------|------------------|---------|
| workshop / fabrication | 1.20 | OSHA machinery clearance |
| warehouse / loading | 1.83 | OSHA forklift clearance lane |
| clean_room | 0.90 | Controlled access, no forklifts |
| assembly_hall | 1.20 | Standard industrial |

---

## Knowledge Base (RAG)

```
python/knowledge/
├── loader.py
├── general/
│   ├── accessibility_codes.json    # ADA 2010
│   └── spatial_ergonomics.json     # Neufert
└── industrial/
    ├── Equipment heights.json      # Machine heights by type
    ├── emergency_egress.json       # NFPA 101 egress requirements
    ├── equipment_zones.json        # Clearance zones by equipment class
    ├── fire_safety.json            # NFPA fire suppression clearances
    ├── forklift_operations.json    # ANSI B56.1 forklift specs
    ├── machinery_spacing.json      # ISO 13857 machine guards
    ├── osha_guidelines.json        # OSHA aisle widths, egress
    ├── worker_ergonomics.json      # ISO 11228 ergonomic reach
    └── workflow_patterns.json      # Industrial workflow / adjacency patterns
```

---

## MCP Tools (Grasshopper / Swiftlet)

- `place_objects` — place equipment in a room. Params: `layout_json`, `room_name`, `objects_list` (JSON array), `user_profile`, `clear_room`.
- `collision-detector-grid` — grid-based clearance field analysis + visualization push to GH.
- `visualize_visibility` — pushes isovist/sightline results to GH.
- `visualize_paths` — pushes path results to GH.
- `set_viewport` — lightweight layout renderer. Params: `layout_json`, `mode`. 10s timeout, auto-disabled on failure.
- `set_observer` — places a draggable 1.7m observer/person point. Params: `point` (`"x,y,h"` in layout metres), `height` (optional, default 1.7). Driven from the AGENT_ui viewport (not the agent pipeline); returns `info` JSON with the ground coords. See "Observer Point" below.
- `shortest_path`, `check_door_widths`, `widen_doors` — legacy tools.

All tool calls automatically receive `layout_json` (full layout, all 7 layers). `_slim_layout` (rooms+doors+furniture only) is used only in the LLM prompt.

---

## Grasshopper Scripts (GHPython Components)

The GH definition (`gh/team_03_working.gh`) contains GHPython scripts forming the simulation pipeline:

| Script | Purpose | Key I/O |
|--------|---------|---------|
| 1 — Shortest Path | BFS + door scoring | in: `json_str`, `start_room` → out: room depths, path_doors, scores |
| 2 — Path Polyline Builder | builds path geometry | in: script-1 output, `target_room`, `layout_json` → out: `polyline`, `points`, `info` |
| 3 — JSON File Reader | reads a layout file | in: `path` → out: `json_string` |
| 4 — Layout Geometry Visualizer | renders all layers | in: `json_str` → out: room/door/window/furniture/mep/structure curves + outline |
| 5 — Room Centroid Point | room center | in: `room_name` → out: `point` (Point3d) |
| 6 — Visibility Analysis (Isovist) | per-room visibility | in: `path`, `boundary`, `current_room` → out: visibility % |
| 7 — set_viewport | viewport toggle (`gh/set_viewport.py`) | in: `layout_json`, `mode` → out: per-layer curves + `info` JSON |
| 8 — set_observer | observer/person point (`gh/set_observer.py`) | in: `point` (`"x,y,h"`), `height` → out: `observer_point`/`observer_eye` (Point3d), `person_curve` (Curve), `info` JSON |

**set_viewport modes:** `all`, `rooms`, `furniture`, `doors`, `structure`, `outline_only`, `none`. The `info` output must be valid JSON for Swiftlet to return the MCP response; `none` clears all geometry (analysis-only views). To add it in GH: new GHPython component named `set_viewport`, inputs `layout_json`/`mode`, the per-layer outputs above, paste `gh/set_viewport.py`, restart Swiftlet (auto-discovers).

**set_observer wiring (Define Tool pattern):** unlike `set_viewport`, this tool is wired through the two Swiftlet clusters, not auto-discovered by component name. Inputs arrive **wired** (not injected), so `gh/set_observer.py` reads `point`/`height` as normal GH inputs.
- **Definition cluster** — `Define Tool` with N=`set_observer`, D=description, P=`Merge` of two `Define Tool Parameter` (`point` string/required, `height` string/optional). Param keys must match the MCP args sent by the UI (`point`, `height`).
- **Results cluster** — `Deconstruct Tool Call` → `A` (args) → two `Get JSON Object Key` (`point`, `height`) → `Read JSON Value` `S` → wired into `set_observer.point`/`.height`. Geometry outputs → Custom Preview; `info` → the shared `Merge`/Construct JSON → `Tool Response` (same return path as `set_viewport.info`). With a single shared Tool Response, gate by the Deconstruct's tool-name `T` output so only the active tool's `info` is returned.

---

## Observer Point (AGENT_ui viewport → MCP → Grasshopper)

A draggable point representing a 1.7m-tall person, placed interactively in the AGENT_ui 3D viewport and pushed to Grasshopper as an observer location (for visibility/isovist/sightline use). Independent of the LangGraph pipeline — driven straight from the UI.

**Flow:** toggle **Person** → click the floor to place (placement overlay captures the click so geometry doesn't react) → drag to fine-tune → on release the layout coords are sent. `"x,y,h"` string (metres, layout origin) → WebSocket `observer_point` → backend `mcp_bridge` → MCP tool `set_observer` → GH (Define Tool / Deconstruct Tool Call clusters, above).

**Coordinate basis:** the viewport floor (XZ plane) maps to layout X/Y. Coords are emitted in layout metres (origin bottom-left, same as the JSON and Rhino), not the centred-group world coords.

**Files:**
- Frontend: `AGENT_ui/frontend/src/components/ThreeViewport/ObserverMarker.tsx` (draggable person proxy, raycasts to the `y=0` plane), wired in `ThreeViewport.tsx` (Person toggle, placement overlay, output HUD, drag-selection guard), `App.tsx` (`onObserverPoint` → `ws.send`), `utils/wsProtocol.ts` (`ObserverPoint` message).
- Backend: `AGENT_ui/backend/mcp_bridge.py` (lazy MCP client reusing `_runtime/mcp_client.py` + `mcp.json` endpoint; calls `set_observer`; fails gracefully if Swiftlet is down), wired in `server.py` `/ws` handler, `observer_point` added to `websocket_manager.MessageType`.
- GH: `gh/set_observer.py`.

The output string also appears live in a viewport HUD (bottom-left, with copy button) for manual use.

**Chat-driven observer (AGENT_ui):** the observer is no longer UI-only. The AGENT_ui chat now
**auto-routes** observer/visibility/path questions to a Rhino-free **spatial assistant**
(`AGENT_ui/backend/spatial_assistant.py`) that can place a person / start a path from natural
language ("place a person in the center of the workshop", "start a path from the warehouse
entrance to the bathroom"), run a **visibility-obstruction analysis** (which furniture blocks
the view / which objects are hidden, via `isovist.analyze_obstructions`), and answer about an
observer the user **already placed** (persisted in `SessionManager.observer`). It draws the
isovist + a ghost marker live in the 3D viewport. See `AGENT_ui/CLAUDE.md` → "Spatial
assistant". (Pure Python — works even when Swiftlet/Rhino is down.)

---

## Configuration (`.env` at repo root)

| Variable | Description | Default |
|---------|-------------|---------|
| `LLM_PROVIDER` | `openai`, `anthropic`, `local`, `google`, `cloudflare` | required |
| `GOOGLE_API_KEY` | API key when provider is `google` | required if google |
| `GOOGLE_MODEL` | Model id when provider is `google` | `gemini-2.5-flash` |
| `ANTHROPIC_API_KEY` | Anthropic key — always required for AGENT_ui auxiliary features | required |
| `ANTHROPIC_MODEL` | Model id for AGENT_ui auxiliary features (pure_chat, spatial_assistant) | `claude-haiku-4-5` |
| `OPENAI_MODEL` / `CF_MODEL` | Model id for the matching provider | per provider |
| `LOCAL_LLM_ENDPOINT` | e.g. `http://localhost:1234/v1/` | required if local |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout for MCP + LLM | `120` |
| `MAX_ITERATIONS` | Max tool call cycles | `100` |
| `DEBUG_GRAPH` | Print graph debug info | `false` |
| `LAYOUT_FILE` | Layout name (env alt to `--layout`) | — |

**Provider architecture — hybrid Google + Anthropic (current setup):**

The pipeline runs in **hybrid mode**: the LangGraph agent uses Google Gemini as its
main LLM, while three AGENT_ui auxiliary features remain on Anthropic.

| Feature | Provider | Key used | Model |
|---------|----------|----------|-------|
| LangGraph agent pipeline (reason, profile, space_type, populate) | **Google** | `GOOGLE_API_KEY` | `GOOGLE_MODEL` |
| AGENT_ui pure_chat (direct chatbot) | **Anthropic** | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |
| AGENT_ui spatial_assistant (observer / visibility / path) | **Anthropic** | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` |
| AGENT_ui layout_generator (AI layout generation) | **Anthropic** | `ANTHROPIC_API_KEY` | `claude-sonnet-4-6` (or `LAYOUT_GEN_MODEL`) |

**Google Gemini specifics (`_runtime/llm.py`):** Gemini is routed through its
OpenAI-compatibility endpoint (`generativelanguage.googleapis.com/v1beta/openai`) via
`langchain_openai.ChatOpenAI`. Four Gemini-specific adjustments are applied (added
2026-06-19 to fix a bug where multi-object move/place requests silently did nothing):
- `max_tokens=8192` — a generous output budget. Gemini 2.5 enables "thinking" by
  default and those tokens count against `max_tokens` via the OpenAI-compat layer; with
  a small budget the decision JSON gets truncated mid-output (invalid JSON → tool calls
  silently dropped → placements vanish while the agent appears to "talk about" them).
- `reasoning_effort="low"` — caps Gemini's "thinking" so most of the budget goes to the
  actual decision JSON, not hidden reasoning. (Passed as an explicit `ChatOpenAI` param,
  not via `model_kwargs`, to avoid a LangChain warning. NOTE: `extra_body` with a
  `google.thinking_config` block is **rejected** by this endpoint — 400 "Unknown name
  google"; `reasoning_effort` is the correct knob.)
- **JSON mode** — `get_llm_response_format` returns `{"response_format": {"type":
  "json_object"}}` for `google` (NOT the strict `json_schema`, which Gemini's OpenAI-compat
  layer only partially honours). This forces syntactically valid JSON and stops the model
  rambling / dumping coordinates into prose. The SYSTEM_PROMPT already describes the
  decision shape; `_normalize_llm_decision` validates it.
- **Truncation detection** — `call_llm` checks `response_metadata.finish_reason`. On
  `"length"` it logs loudly and raises (so `reason.py`'s retry loop runs) instead of the
  old silent fallback in `_parse_llm_json` that treated a truncated reply as a plain
  conversational "final" with no tool calls.

For multi-step placement where Flash still misclassifies (e.g. picks the wrong object,
or chooses `action:query` for a move), the next lever is `GOOGLE_MODEL=gemini-2.5-pro`.

**UI provider + model switcher (pipeline only):** the AGENT_ui chat panel exposes a
**Provider** toggle (`Anthropic` | `Google`) and a dependent **Model** picker
(haiku/sonnet for Anthropic; flash/pro for Google). A `provider_switch` WebSocket
message calls `pipeline_bridge.set_pipeline_llm(provider, model_key)`, which validates
the provider's API key and sets the process-global `_pipeline_provider` /
`_pipeline_model` (`PIPELINE_MODELS` maps the UI model keys to full ids). `build_context`
then resolves that provider's own key/base_url/model (`resolve_provider_credentials` in
`_runtime/config.py`) and passes `provider=` explicitly to `create_chat_llm` /
`get_llm_response_format`. The switch **controls only the LangGraph pipeline** and applies
to the **next** chat session. `GET /api/llm-config` reports the active provider/model,
selectable models, and which providers have credentials so the UI starts in sync.

**Cerebro vs manos (what the toggle does and does NOT do):** the provider toggle only
changes *which LLM generates the decision* (`reason.py` → `_runtime/llm.py` `call_llm`).
It does **not** change the machinery that writes the JSON or moves the geometry — *that*
is always the same pipeline: `place_objects` (MCP) → `nodes/add_objects.py` →
`workspace/session_active.json` (via `_runtime/session.py`) → on approval,
`nodes/output.py` → `output/<layout>_*.json`. The provider only affects the
**quality/reliability** of the moves (a better model decides better; a truncated/invalid
JSON loses its `tool_calls` so nothing moves — see "Google Gemini specifics"), never the
mechanism.

**Credentials & graceful degradation:** both API keys are optional **except** the one for
the active `LLM_PROVIDER` — the app boots on the `.env` provider. If the *other* provider's
key is missing, toggling to it fails with a clear notice (`provider_switch_ack
status:"error"`, `missingKey`, `envPath`) telling the user to add
`GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` to the repo-root `.env` and restart the backend; the
pipeline keeps running on the provider that already worked. So a user with only the
Anthropic key runs fine on Anthropic and simply can't switch to Google until they add it.

**Auxiliary config helper:** `pipeline_bridge.anthropic_aux_config()` returns the
Anthropic key + model for the three auxiliary features, reading `ANTHROPIC_API_KEY` /
`ANTHROPIC_MODEL` directly from the repo-root `.env` regardless of `LLM_PROVIDER` and of the
pipeline toggle. The auxiliary features therefore **always** run on Anthropic; only its key
must be present in `.env` to use chat / spatial assistant / layout generator.

**Important:** Grasshopper tool calls can take >2 minutes. Set `REQUEST_TIMEOUT_SECONDS=300` or higher.

## MCP Server (`mcp.json` at repo root)

```json
{
  "mcpServers": {
    "Swiftlet": {
      "command": "C:\\Users\\gramo\\AppData\\Roaming\\McNeel\\Rhinoceros\\packages\\8.0\\swiftlet\\0.2.0\\SwiftletBridge.exe",
      "args": ["http://localhost:3002/mcp/"]
    }
  }
}
```

Swiftlet must be running in Rhino 8 before launching `main.py`.

---

## How to Run

```bash
cd team_03/python

# Industrial layout + user prompt (positional prompt still works)
python main.py --layout industrial_005 "place a cnc machine in the workshop"
python main.py --layout industrial_005 --prompt "check visibility in the fabrication hall"
python main.py --layout industrial_03  "place a forklift path through the loading bay"

# Populate an empty layout (triggers the Populate Agent)
python main.py --layout industrial_005 "populate the workshop"

# Layout via env (useful for VS Code launch configs)
LAYOUT_FILE=industrial_005 python main.py "analyse the workshop clearances"

# Visualize spatial graph (no Rhino needed)
python visualize_interactive.py --session     # interactive HTML, live
python test_spatial_graph.py --session        # static matplotlib

# Smoke test
python test_bootstrap.py --layout industrial_005
```

### Orchestrator CLI (subprocess)

`main.py` is also the CLI an external **orchestrator** calls as a subprocess. It takes
explicit flags and prints a stable, machine-readable block:

```bash
# Orchestrator-provided layout as a JSON string (no on-disk layout file needed)
python main.py --prompt "add a window to the south wall of the living room" \
               --layout_json '{ "layoutId": "Layout-101", "outline": [...], "rooms": [...], ... }'
```

- `--prompt` (required) — the instruction. A positional prompt is still accepted for
  back-compat (`main.py --layout industrial_005 "..."`).
- `--layout_json` (optional) — a full layout as a JSON string. When present it **overrides**
  the on-disk layout: `main.py` parses it (clear error + non-zero exit on bad JSON), writes
  it to the workspace session, and sets `ctx.layout_data` to it before `run_agent`. No
  `--layout` file lookup or "resume session?" prompt happens in this mode.
- **Output** (parse the markers):
  ```
  Final Response:
  <agent response>

  Edited Layout JSON:
  <edited layout JSON or "No layout changes">
  ```
  The edited layout is read back from `workspace/session_active.json` (or, if the run was
  approved and closed, the newest `output/<layoutId>_*.json`); if it equals the input it
  prints `No layout changes`.
- **Back-and-forth:** the agent's checkpoints still read from the console (`input()`), so the
  orchestrator can answer follow-up questions over stdin while the run is in progress.
- On any failure the CLI still prints the markers (`Final Response: Agent error: …` /
  `No layout changes`) and exits non-zero, so the orchestrator never gets a bare crash.

**Session management:** On startup, if `workspace/session_active.json` exists, the agent asks to resume or start fresh. Base layout files are never modified.

---

## Dependencies

```bash
pip install langchain-openai langchain-anthropic langgraph grandalf shapely httpx python-dotenv anthropic networkx matplotlib
```

---

## Known Issues

1. **Timeout on MCP tool calls (OPEN)** — GH simulations are slow. Use `REQUEST_TIMEOUT_SECONDS=300`. If it times out, check Rhino for red/orange GH components.
2. **`set_viewport` stays "pending" (PARTIALLY FIXED)** — Sometimes no response through Swiftlet. Checkpoint has 10s timeout + auto-fallback to `collision-detector-grid`. GH-side fix: wire the Result cluster.
3. **Viewport overlay not simultaneous (OPEN)** — Toggling to analysis views (3/4/5) may show only the analysis. Workaround: overlays use `collision-detector-grid` as base.
4. **`place_objects` format mismatch (FIXED)** — `_parse_objects_list` (`nodes/add_objects.py`) now accepts BOTH the colon form `name:WxDxH:x=X,y=Y` AND the JSON array the LLM often emits (`[{"name":..,"position":[x,y],"size":[w,d,h]}]`). Previously the JSON form parsed to nothing and silently placed no objects.
5. **`test_spatial_graph.py --session` shows 0 furniture for base layout** — Expected: `--session` reads the live workspace; without it the base layout has no furniture.
6. **`spatial_graph.py` import fails if networkx missing** — `pip install networkx`. All call sites are wrapped in try/except so it degrades gracefully.

---

## File Structure

```
team_03/
  CLAUDE.md                       # This document (canonical for all of team_03/)
  python/
    main.py                       # CLI entry point
    graph.py                      # LangGraph StateGraph, AgentState, enrich_graph_node
    prompts.py                    # SYSTEM/SPACE/PROFILE/POPULATE/MEMORY prompts
    spatial_graph.py              # NetworkX spatial relationship graph module
    visualize_interactive.py      # Interactive live HTML graph visualizer (port 7477)
    test_spatial_graph.py         # Standalone matplotlib graph visualizer
    test_bootstrap.py             # Smoke test
    nodes/
      profile_agent.py            # Industrial profile detection (forklift/worker/crane...)
      space_type_agent.py         # Space subtype detection (workshop/warehouse/assembly...)
      populate_agent.py           # Zone-by-zone layout population
      memory.py                   # Durable per-layout memory + protected User Rules
      reason.py                   # LLM decision node (injects memory + spatial graph)
      tools.py                    # Generic MCP tool execution
      add_objects.py              # Object placement + spatial graph rebuild
      fan_out.py                  # analysis_fan_out_node + group1_join_node
      collision.py                # BFS grid collision analysis (Voronoi clearance)
      visibility.py               # Isovist + sightline analysis
      path_analysis.py            # BFS + A* pathfinding
      reachability.py             # Ergonomic reach analysis
      orientation.py              # Facing direction analysis
      scoring.py                  # Weighted quality score (0-100, A-F)
      checkpoint.py               # User approval gate + viewport toggles + suggestions
      explain.py                  # Post-approval LLM summary
      output.py                   # Save final layout, close session
      query_agent.py              # Analysis-only path (no placement)
    knowledge/
      loader.py
      general/ ...                # accessibility_codes, spatial_ergonomics
      industrial/ ...            # OSHA / NFPA / ISO / forklift / workflow_patterns
    _runtime/
      bootstrap.py  config.py  llm.py  mcp_client.py  session.py  utils.py
  layout/
    industrial_100/               # Industrial layouts (in scope)
    residential_100/              # On disk but out of scope (agent is industrial-only)
  workspace/
    session_active.json           # Live session state (ephemeral)
  memory/
    <layout_name>.md              # Per-layout durable memory + User Rules (gitignored)
  output/                         # Timestamped final layouts
  gh/
    team_03_working.gh
    set_viewport.py               # GHPython viewport toggle script
    set_observer.py               # GHPython observer/person point script
    team_03_definition_cluster.ghcluster
    team_03_result_cluster.ghcluster
    SPATIAL_GRAPH_METHODOLOGY.md
  AGENT_ui/                       # Full-stack web UI (see AGENT_ui/CLAUDE.md)
  ramon_experiments/
    conversations/
      RAMY_CLAUDE.md
    topologic_graph/ ...          # Reference spatial graph + report
    python_tools/                 # Archived utility scripts
```

---

## Layout Schema Reference

Master schema for floor plans as JSON. 7 layers; all coordinates 2D `[x, y]` in meters.

```json
{ "layoutId": "string", "outline": [[x,y], ...],
  "rooms": [...], "doors": [...], "windows": [...],
  "furniture": [...], "mep": [...], "structure": [...] }
```

| Type | Format |
|------|--------|
| Closed polyline (areas) | Array of `[x,y]`, first = last |
| Open line (linear elements) | Exactly 2 `[x,y]` points |

**Layer specs**
- **rooms:** `id` (room-N), `name`, `geometry` (closed polyline), `attributes.area` (m²)
- **doors:** `id` (door-N), `name`, `geometry` (2-pt line on shared wall), `attributes.connectsRooms` ([room-A, room-B])
- **windows:** `id` (window-N), `name`, `geometry` (2-pt line), `attributes.roomId`
- **furniture:** `id` (furn-N), `name`, `geometry` (closed polyline), `attributes.roomId`. Optional: `use_point`, `functional_point`, `orientation`, `target`
- **mep:** `id` (mep-N), `name`, `geometry` (closed polyline), `attributes.system` (hvac/electrical/plumbing)
- **structure:** `id` (wall-N), `name`, `geometry` (2-pt centerline), `attributes.type` (load-bearing/partition), `attributes.material`

**Coordinate rules:** origin bottom-left `[0,0]`; meters; counter-clockwise winding for positive area; adjacent rooms share exact wall coordinates; doors/windows sit exactly on room boundary edges; all IDs unique within their layer.

| Layer | Pattern | | Layer | Pattern |
|-------|---------|-|-------|---------|
| rooms | room-N | | furniture | furn-N |
| doors | door-N | | mep | mep-N |
| windows | window-N | | structure | wall-N |
