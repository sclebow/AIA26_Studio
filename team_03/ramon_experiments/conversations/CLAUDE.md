# Team 03 — Accessibility Agent

## What this project does

An AI agent that evaluates residential and industrial floor plans for spatial accessibility. It connects a Python LangGraph agent to a Grasshopper/Rhino simulation backend via MCP (Model Context Protocol), using Swiftlet as the MCP server.

The agent accepts a natural-language prompt, reasons about the layout, calls Grasshopper tools to run simulations, places objects, runs a multi-tool analysis pipeline (collision, visibility, path, reachability, orientation), computes a weighted quality score, and presents a user checkpoint for approval or iterative refinement. Two preprocessing agents (Profile Agent and Space Type Agent) enrich the context with user-specific constraints and space-specific priorities before the main reasoning loop.

## Architecture

```
main.py  →  graph.py (LangGraph)  →  nodes/profile_agent.py    (user profiling + RAG)
                                  →  nodes/space_type_agent.py  (space analysis + RAG)
                                  →  nodes/reason.py            (LLM decision)
                                  →  nodes/tools.py             (MCP tool calls)
                                  →  nodes/add_objects.py        (object placement via MCP)
                                  →  nodes/collision.py          (grid-based collision analysis)
                                  →  nodes/visibility.py         (line-of-sight analysis)
                                  →  nodes/path_analysis.py      (BFS + A* pathfinding)
                                  →  nodes/reachability.py       (ergonomic reach analysis)
                                  →  nodes/orientation.py        (facing direction analysis)
                                  →  nodes/scoring.py            (weighted quality score)
                                  →  graph.py: user_checkpoint   (human approval gate)
                                  →  graph.py: explain_node      (LLM summary generation)
                                  →  graph.py: output_node       (save final layout)
                                  →  visualize_interactive.py    (live HTML graph visualizer)
                                  →  _runtime/mcp_client.py → Grasshopper (Swiftlet @ localhost:3002)
                                  →  _runtime/session.py         (workspace session lifecycle)
```

### Phase 3 Graph Flow

```
START → profile_agent → space_type_agent → reason
                                             │
                              ┌──────────────┼──────────────┐
                              ▼              ▼              ▼
                         add_objects     run_tool       finish
                              │              │              │
                              ▼              ▼              ▼
                    ┌─── Group 1 (parallel) ──┐        visibility
                    │  collision              │             │
                    │  visibility             │             ▼
                    │  orientation             │         (same as
                    └─────────────────────────┘          Group 1→2)
                              │
                    collision gates: hard violations → reason (only if objects placed)
                              │ pass / analysis-only
                              ▼
                    Group 2 (sequential)
                    path → reachability
                              │
                    reachability gates: >30% unreachable → reason (only if objects placed)
                              │ pass
                              ▼
                           scoring
                              │
                              ▼
                       user_checkpoint (interactive toggle + suggestions)
                        │  1=BEFORE  2=AFTER  3=collision  4=visibility  5=paths
                        │  0=clear overlays  s1..s5=smart suggestions
                        ┌────┴────┐
                     approved   continue → reason (new round)
                        │
                        ▼
                      explain → output → END
```

- **`main.py`** — CLI entry point, takes a prompt and `--layout <name>` argument
- **`graph.py`** — Phase 3 LangGraph StateGraph with parallel analysis groups, conditional routing, user checkpoint, and output pipeline. Contains `AgentState` (TypedDict with `_keep_last` reducers for parallel writes, includes `viz_highlight_ids: Annotated[list[str] | None, _keep_last]` for carrying highlight state across pipeline steps), routing functions, `build_user_checkpoint_node(mcp_client)` (factory with viewport toggles + smart suggestions), `explain_node`, and `output_node`. Generates interactive graph visualization at startup (`_build_initial_state`) and updates it after enrichment (`enrich_graph_node` passes carry-over IDs via `update_from_enriched_graph`). `layout_json_string` stores the **full** layout (all 7 layers) for MCP tools; `_slim_layout` is used only in the LLM prompt message to save tokens. The checkpoint node features:
  - **Viewport toggles:** `1`=BEFORE, `2`=AFTER (disabled if no changes), `3`=collision overlay, `4`=visibility overlay, `5`=path overlay, `0`=clear overlays. Overlays (3/4/5) use `collision-detector-grid` as layout base (always works) + the analysis tool on top. Tracks which layout is "active" (before/after) — overlays apply to the active layout.
  - **Smart suggestions:** Auto-generated `s1`..`s5` prompts based on lowest-scoring tools. Mentions specific furniture names from collision violations. Selecting a suggestion sends it as a user instruction to the reason node.
  - **Score comparison:** ANSI-colored output with ▲/▼ deltas vs previous checkpoint visit. Per-tool breakdown with color coding (green >=80, yellow 50-79, red <50).
  - **Structural integrity:** Auto-restores doors/windows/mep/structure if lost during pipeline.
  - **MCP timeout:** `set_viewport` calls use 10s timeout; auto-disabled for session if it fails. Falls back to `collision-detector-grid`.
- **`nodes/profile_agent.py`** — LLM-based node that analyses user needs and outputs a structured profile (reach, path width, turning radius, etc.) using RAG knowledge base
- **`nodes/space_type_agent.py`** — LLM-based node that detects space type (residential/industrial) and outputs analysis priorities, clearances, and tool weights using RAG knowledge base
- **`nodes/reason.py`** — calls the LLM with system prompt + profile/space context + conversation history, decides next action. Sets `object_to_place`, `pending_tool_calls`, or `final_response` to control routing.
- **`nodes/tools.py`** — executes MCP tool calls, injects `layout_json` into every call
- **`visualize_interactive.py`** — Live interactive graph visualizer (Apple-minimalist aesthetic). Generates raw HTML + vis.js 9.1.2 with: fixed architectural node positions (no physics), dark/light theme toggle, clickable legend filtering, detail panel on node click (metadata, type description, connected neighbors), draggable nodes with spring snap-back animation, live auto-refresh via embedded HTTP server (port 7477) with smart change detection (PAGE_TS comparison) and dual-mode fallback (adaptive backoff for `file://` origins). Includes `build_interactive_graph()` (main API, accepts layout dict or nx.MultiGraph), `update_from_enriched_graph()` (marks enrichment edges as new, merges carry-over highlight IDs), `_ensure_server()` (background HTTP daemon with CORS), and `http_url()` (returns browsable URL). Output: `view_graph/spatial_graph_interactive.html`.
- **`nodes/add_objects.py`** — places objects via MCP `place_objects` tool. Parses LLM's compact string format (`name:WxDxH:x=X,y=Y`) into JSON arrays. Saves session after each placement. After placement, rebuilds spatial graph and regenerates interactive HTML visualization with new/moved furniture highlighted via `viz_highlight_ids`.
- **`nodes/collision.py`** — Pure Python grid-based collision analysis (no Rhino dependency). Rasterizes layout onto grid, computes BFS distance field, checks clearance thresholds, door widths, turning radii, use_point clearance/reachability, functional_line obstruction. Also pushes visualization to GH via MCP.
- **`nodes/visibility.py`** — Line-of-sight analysis using Shapely. Mode 1 (no objects): room-to-room centroids. Mode 2 (objects placed): use_point to functional_point pairs within same room.
- **`nodes/path_analysis.py`** — Mode 1 (no furniture): BFS through door graph between all room pairs with polylabel interior points. Mode 2 (furniture): A* on per-room 2D grid between object centroids. Reports worst-case egress distance.
- **`nodes/reachability.py`** — Ergonomic reach analysis. Checks functional_point height within reach envelope and 2D distance from use_point to functional_point within reach_radius. Estimates heights from object type names.
- **`nodes/orientation.py`** — Facing direction analysis. Checks if object `orientation` angle matches `target_direction` or computed angle to `target` (point or object reference). Tolerance: 45 degrees default.
- **`nodes/scoring.py`** — Weighted multi-tool quality score (0-100) with letter grade (A-F). Default weights: collision 0.30, path 0.25, visibility 0.20, reachability 0.15, orientation 0.10. Space config can override weights.
- **`_runtime/bootstrap.py`** — `Context` dataclass. Loads settings, resolves layout by name via `rglob`, manages session lifecycle, connects to MCP, builds LLM. `--layout` takes a name (e.g. `industrial_005`), not a file path.
- **`_runtime/llm.py`** — LangChain `ChatOpenAI` wrapper with structured JSON output schema + `call_llm_simple()` for preprocessing agents. Includes `_extract_tool_name()` and `_normalize_tool_calls()` helpers to handle LLM format variations (`name` vs `tool_name` vs `function`). Anthropic path handles both dict and LangChain message objects, maps `"human"`→`"user"` and `"ai"`→`"assistant"` roles.
- **`_runtime/mcp_client.py`** — HTTP JSON-RPC client for the Swiftlet MCP server. `call_tool()` accepts optional `timeout` parameter (overrides global httpx timeout for that call).
- **`_runtime/config.py`** — loads `.env` from repo root
- **`_runtime/session.py`** — Workspace session lifecycle: `create_session()` copies base layout to `workspace/session_active.json`, `save_session()` persists state after each mutation, `close_session()` writes timestamped final layout to `output/` and cleans up, `detect_existing_session()` checks for resumable sessions.

## MCP Tools (Grasshopper)

Discovered at runtime from Swiftlet. Currently:
- `get_visibility` — visibility analysis between rooms
- `collision_detector_sphere` — checks if a sphere (representing a wheelchair/person) collides along a path
- `collision-detector-grid` — grid-based clearance field analysis (visualization push from collision node)
- `shortest_path` — computes the shortest navigable path between rooms
- `check_door_widths` — validates door widths against a minimum
- `widen_doors` — modifies door widths
- `place_objects` — places objects in a room. Params: `layout_json`, `room_name`, `objects_list` (JSON array of `{name, position, size}`), `user_profile`, `clear_room`
- `visualize_visibility` — pushes visibility results to GH for rendering
- `visualize_paths` — pushes path results to GH for rendering
- `set_viewport` — lightweight layout renderer for viewport toggles (no analysis). Params: `layout_json`, `mode` (`"all"`, `"rooms"`, `"furniture"`, `"doors"`, `"structure"`, `"outline_only"`, `"none"`). GHPython script at `gh/set_viewport.py`. Mode `"none"` clears all geometry outputs. Used by checkpoint for layout-only views (1/2/0). **Note:** may stay "pending" in Swiftlet if the Result cluster isn't wired — checkpoint has 10s timeout + auto-fallback to `collision-detector-grid`.

All tool calls automatically receive `layout_json` (current layout state) injected by `nodes/tools.py` or `nodes/add_objects.py`.

**Important:** GH components require the **full** layout JSON (all 7 layers). `collision-detector-grid` needs `outline`, `structure`, and `mep` for grid rasterization. `layout_json_string` in state stores the full layout; `_slim_layout` (rooms + doors + furniture only) is used only in the LLM prompt to save tokens.

## Layout Files

| File | Content | Use |
|---|---|---|
| `team_03/layout/industrial_100/` | Industrial warehouse layouts (currently 4 files: `industrial_005.json`, `industrial_01..03.json`). | Active test layouts for the agent pipeline |
| `team_03/layout/residential_100/` | Residential house layouts (currently 3 files: `residential_01..03.json`). | Active test layouts for the agent pipeline |
| `team_03/workspace/session_active.json` | Live session file — copy of base layout, updated after every object placement or analysis. Deleted when session is approved. | Working state for the current agent run |
| `team_03/output/` | Timestamped final approved layouts (`{name}_{datetime}_final.json`). Created by `close_session()`. | Permanent output of completed runs |

### Archived / Experiment Files (`ramon_experiments/`)

Scripts from earlier phases and conversation analysis, moved out of the active pipeline:

- `python_tools/` — archived Python scripts (layout generators, GH scripts, utilities)
- `conversations/` — Ramy's debugging conversation analysis (`RAMY_CLAUDE.md`), raw exports, and documentation snapshots

### Room names (valid values)

**Residential:** `corridor`, `kitchen`, `living`, `dining`, `bedroom1`, `bedroom2`, `wc1`, `wc2`, `wc3`, `Entrance Hall`, `Living Room`, `Dining Room`, `Kitchen`, `Laundry`, `Corridor`, `Master Bedroom`, `Master Bathroom`, `Bedroom 2`, `Bathroom 2`, `Bedroom 3`

**Industrial:** `Main Warehouse`, `Production Floor`, `Assembly Hall`, `Workshop`, `Manufacturing Area`, `Loading Bay`, `Shipping Area`, `Receiving Area`, `Fabrication Hall`, `Processing Floor`, `Distribution Floor`, `Packaging Area`, `Inspection Hall`, `Testing Floor`, `Staging Area`, `Office`, `Restroom`, `Storage Room`, `Break Room`, `Reception`, `Meeting Room`, `Utility Room`, `Bathroom`, `Clean Room` (and variants)

## Preprocessing Agents

Two LLM-based preprocessing nodes run before the main reason/tool loop. They use a RAG knowledge base (`python/knowledge/`) with real accessibility data (ADA, OSHA, Neufert, ISO) to ground their outputs. Both always run and fall back to hardcoded defaults if the LLM call fails.

### Profile Agent (`nodes/profile_agent.py`)

Analyses user needs/constraints from the prompt and outputs a structured profile:

```json
{
  "profile_type": "wheelchair_user",
  "reach_height_min": 0.38,
  "reach_height_max": 1.22,
  "reach_radius": 0.60,
  "min_path_width": 0.90,
  "turning_radius": 0.75,
  "seated_height": 1.10,
  "notes": "Standard manual wheelchair user (ADA baseline)."
}
```

Supported profiles: `wheelchair_user`, `elderly`, `stroller`, `autistic`, `visually_impaired`, `forklift`, `crane`. Detected from prompt keywords. Default: `wheelchair_user`.

### Space Type Agent (`nodes/space_type_agent.py`)

Detects space type from prompt keywords + `layoutId` and outputs analysis priorities and tool weights:

```json
{
  "space_type": "industrial",
  "priorities": ["collision", "path_analysis", "visibility", "reachability"],
  "clearance": 1.20,
  "tool_weights": {
    "collision": 0.30,
    "visibility": 0.20,
    "path": 0.25,
    "reachability": 0.15,
    "orientation": 0.10
  },
  "use_clearance": true,
  "orientation_required": true
}
```

Detects `industrial` or `residential` from layout metadata and prompt. Default: `residential`.

### Knowledge Base (RAG)

```
python/knowledge/
├── loader.py                         # Keyword-based file search + formatting
├── general/
│   ├── accessibility_codes.json      # ADA 2010 key dimensions (corridors, doors, reach, ramps)
│   └── spatial_ergonomics.json       # Neufert anthropometric data (body dims, clearances)
├── residential/
│   ├── ada_clearances.json           # Residential ADA (kitchen, bathroom, bedroom)
│   └── furniture_clearances.json     # Standard furniture clearances (Neufert)
└── industrial/
    ├── osha_guidelines.json          # OSHA aisle widths, egress, panel clearances
    └── machinery_spacing.json        # ISO 13857 machine guards, forklift turning, racks
```

Each file contains structured facts with `rule`, `value_m`, and `context` fields. The loader matches files by keyword against filenames and concatenates relevant content into the LLM prompt.

## Analysis Pipeline (6 Tools)

### 1. Collision (`nodes/collision.py`) — Weight: 0.30

Pure Python grid-based collision analysis. No Rhino dependency.

**Algorithm:**
1. Rasterizes outline as free space, then walls (with thickness, split at doors), furniture, and MEP as obstacles.
2. Computes BFS brushfire distance field from all obstacle cells.
3. Computes nearest-obstacle attribution for each cell.
4. Checks: body clearance, corridor width, door widths, turning radii, connectivity, use_point clearance/reachability, functional_line obstruction.
5. Generates per-object violation reports with move suggestions (distance field gradient).

**Violation types:** `BLOCKED`, `WARNING`, `CONNECTIVITY`, `DOOR_WIDTH`, `TURNING`, `USE_POINT`, `USE_POINT_UNREACHABLE`, `FUNCTIONAL_LINE`

**Profiles (collision-specific):**

| Profile | Min door (m) | Min corridor (m) | Turning radius (m) | Body width (m) |
|---|---|---|---|---|
| wheelchair | 0.85 | 0.90 | 1.50 | 0.70 |
| elderly | 0.80 | 0.85 | 1.20 | 0.60 |
| stroller | 0.80 | 0.90 | 1.30 | 0.65 |
| autistic | 0.75 | 0.80 | 1.00 | 0.55 |
| visually_impaired | 0.80 | 0.90 | 1.20 | 0.60 |
| forklift | 2.50 | 3.00 | 3.50 | 1.20 |
| crane | 4.00 | 5.00 | 5.00 | 2.00 |

### 2. Visibility (`nodes/visibility.py`) — Weight: 0.20

Line-of-sight analysis using Shapely. Checks if sightlines between object pairs cross room walls (excluding walls near doors). Only pairs within the same room are checked.

### 3. Path Analysis (`nodes/path_analysis.py`) — Weight: 0.25

- **Mode 1 (no furniture):** BFS through door graph. Uses Shapely `representative_point()` for concave rooms. Reports all room pairs + worst-case egress.
- **Mode 2 (furniture):** A* on 0.5m grid per room. Marks other furniture as obstacles. 8-directional movement. Reports object-to-object distances within each room.

Dependencies: `shapely`

### 4. Reachability (`nodes/reachability.py`) — Weight: 0.15

Checks if objects can be physically reached: `height_ok` (functional_point z within reach envelope) and `radius_ok` (2D distance from use_point to functional_point within reach_radius). Estimates heights from object type keywords (shelf=1.6m, table=0.85m, machine=1.0m).

### 5. Orientation (`nodes/orientation.py`) — Weight: 0.10

Checks facing direction for objects with an `orientation` field. Resolves targets from `target_direction` (angle/vector), `target` (point or object reference). Tolerance: 45 degrees. Objects without orientation are skipped.

### 6. Scoring (`nodes/scoring.py`)

Aggregates all tool results into a weighted 0-100 score with letter grade (A/B/C/D/F). Grades: A>=90, B>=75, C>=60, D>=40, F<40. Space config can override default weights.

**Structure vs Furniture scoring:** Collision violations caused by **structure** (walls) are penalized at 20% weight because the agent can't move them. **Furniture/MEP** violations get full penalty (actionable). This prevents wall-adjacent clearance violations from dominating the score.

**Score comparison:** The checkpoint displays ANSI-colored deltas (green ▲/red ▼) comparing current vs previous score, both total and per-tool. Previous scoring stored in `previous_scoring` state field, updated each checkpoint exit.

## User Profiles

Defined in `nodes/profile_agent.py` → `DEFAULT_PROFILES`. Detected automatically from the prompt by the Profile Agent. Default: `wheelchair_user`.

| Profile | Min path (m) | Turning radius (m) | Reach min (m) | Reach max (m) | Seated height (m) |
|---|---|---|---|---|---|
| wheelchair_user | 0.90 | 0.75 | 0.38 | 1.22 | 1.10 |
| elderly | 0.85 | 0.60 | 0.50 | 1.50 | — |
| stroller | 0.90 | 0.65 | 0.40 | 1.60 | — |
| autistic | 0.80 | 0.50 | 0.40 | 1.60 | — |
| visually_impaired | 0.90 | 0.60 | 0.40 | 1.60 | — |
| forklift | 3.05 | 2.50 | 0.00 | 6.00 | 1.50 |
| crane | 5.00 | 5.00 | 0.00 | 12.00 | — |

## Configuration (`.env` at repo root)

| Variable | Description | Default |
|---|---|---|
| `LLM_PROVIDER` | `local`, `openai`, `anthropic`, `google`, `cloudflare` | required |
| `LOCAL_LLM_ENDPOINT` | e.g. `http://localhost:1234/v1/` | required if local |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout for MCP + LLM calls | `120` |
| `MAX_ITERATIONS` | Max tool call cycles | `100` |
| `DEBUG_GRAPH` | Print graph debug info | `false` |
| `LAYOUT_FILE` | Layout name (env alternative to `--layout` CLI arg) | — |

**Important:** Grasshopper tool calls (especially `shortest_path`, `collision_detector_sphere`) can take >2 minutes. Set `REQUEST_TIMEOUT_SECONDS=300` or higher.

## Interactive Graph Visualizer (`visualize_interactive.py`)

Live HTML visualization of the spatial graph with Apple-minimalist aesthetic. Generates raw HTML + vis.js 9.1.2 (no pyvis dependency).

### Features

| Feature | Description |
|---------|-------------|
| **Architectural positions** | Nodes placed at real layout coordinates (flipped Y), not force-directed. `physics: false`, `fixed: true` |
| **Dark/Light theme** | Toggle button (top-right), persists in `localStorage`. CSS custom properties + glass-morphism panels |
| **Legend filtering** | Click legend items to filter by type (shift-click for multi-select). Non-matching elements fade to 8% opacity |
| **Detail panel** | Click any node to open right-side panel with: type chip, all metadata attributes, type description, connected neighbors (clickable to navigate) |
| **Drag snap-back** | Nodes are draggable but spring back to original position on release (550ms ease-out cubic animation via `requestAnimationFrame`) |
| **New element highlights** | Recently added/changed elements get blue `#007AFF` border that fades after 4s. "new" badge on highlighted nodes |
| **Live auto-refresh** | Active by default. Dual-mode: HTTP smart detection (compares `PAGE_TS` timestamp via `fetch()`) or blind `location.reload()` fallback with adaptive backoff (2-10s via `sessionStorage`) |
| **HTTP server** | Background daemon on port 7477 with CORS `*` and `Cache-Control: no-store`. Started automatically by `_ensure_server()` |
| **Viewport preservation** | Zoom/pan state saved to `sessionStorage` before reload, restored via `network.moveTo()` |

### How to open

```bash
# Best: via CLI (starts HTTP server, keeps it alive)
cd team_03/python
python visualize_interactive.py --session
# Opens http://127.0.0.1:7477/spatial_graph_interactive.html

# Alternative: double-click view_graph/spatial_graph_interactive.html
# Uses file:// protocol — live refresh falls back to blind reload with adaptive backoff
```

### Pipeline integration

The graph auto-updates at three points:
1. **Startup** (`_build_initial_state` in `graph.py`): generates initial HTML from base layout
2. **After placement** (`add_objects.py`): rebuilds graph, highlights new/moved furniture via `viz_highlight_ids`
3. **After enrichment** (`enrich_graph_node` in `graph.py`): marks enrichment edges as new, merges carry-over highlights from `viz_highlight_ids`

### Node color palette (muted, low saturation)

| Type | Dark | Light | Radius |
|------|------|-------|--------|
| room | `#6B9BD2` | `#4A7FB5` | 14 |
| door | `#D4A574` | `#B8865A` | 9 |
| wall | `#8B9DAF` | `#6B7D8F` | 8 |
| window | `#7BC4C4` | `#5AA8A8` | 8 |
| furniture | `#7DB87D` | `#5A9B5A` | 11 |
| mep | `#C47070` | `#A85050` | 10 |

All nodes use `shape: "dot"` (uniform circles). Edges at 40% opacity, 0.8px width.

## Known Issues & Fixes

### 1. Timeout on MCP tool calls
Grasshopper simulations are computationally heavy. Default 30s is not enough. Use `REQUEST_TIMEOUT_SECONDS=120` or higher. If it still times out, the Grasshopper component may be stuck (check Rhino for red/orange components).

### 2. Layout overwrite bug (FIXED)
`nodes/tools.py` used to replace `layout_json_string` with any valid JSON returned by a tool (e.g. `{"visibility_result": null}`). This caused subsequent tool calls to fail with `'rooms'` key error. Fix: only update layout if the result contains a `"rooms"` key.

### 3. `call_llm_simple` always falling back to defaults (FIXED — 2026-05-17)
`call_llm_simple()` in `llm.py` routed through `_call_anthropic()` → `_normalize_llm_decision()`, which expected `{"action": "final", "tool_calls": [...]}` schema. Pre-agents return free-form JSON (e.g. `{"profile_type": ...}`), so `_normalize_llm_decision` always raised RuntimeError, silently caught by the outer try/except. Both pre-agents fell back to hardcoded defaults every time. Fix: Anthropic path in `call_llm_simple` now calls the API directly and parses as free-form JSON, bypassing `_normalize_llm_decision`.

### 4. LangGraph parallel state deadlock (FIXED)
When `reason` routed to `"finish"`, it only triggered `visibility`, but `group1_join` waited for all 3 Group 1 nodes (collision + visibility + orientation). Since collision and orientation never started, LangGraph deadlocked. Fix: added `analysis_fan_out_node` (no-op fan-out) and `group1_join_node` (no-op join). Both `finish` and `add_objects` routes go through the same fan-out.

### 5. State mutation in parallel nodes (FIXED)
All nodes mutated state directly (`state["x"] = y`) instead of returning partial update dicts. This caused `InvalidUpdateError` in parallel execution. Fix: all 12 node files refactored to return update dicts. `_keep_last` reducers on all `AgentState` fields.

### 6. Router infinite loop (FIXED)
`_route_after_reason` checked `final_response is not None` but stale values survived the `_keep_last` reducer when set to `None`. Fix: use `""` (empty string) instead of `None` when clearing `final_response`, check `fr is not None and fr != ""`.

### 7. Unhandled exceptions crashing the graph (FIXED — 2026-05-17)
Multiple nodes had unhandled exceptions that killed the entire graph: `call_llm()` in `reason.py`, `mcp_client.call_tool()` in `tools.py` and `add_objects.py`, analysis functions in all 5 analysis nodes, `call_llm()` in `explain_node`. Fix: all wrapped in try/except with graceful fallbacks (empty results, error messages in state).

### 8. `_call_anthropic` message format mismatch (FIXED — 2026-05-17)
`_call_anthropic()` called `msg.get("role")` which fails on LangChain `HumanMessage` objects (produced by the `add_messages` reducer). Fix: handle both dicts and message objects, map `"human"` role to `"user"`.

### 9. `tools.py` crashes on `None` pending_tool_calls (FIXED — 2026-05-17)
If `pending_tool_calls` was `None` or empty, `for call in None` crashed. Fix: guard at the top of `tool_node` returns early with no changes.

### 10. Scoring weights not normalized (FIXED — 2026-05-17)
`space_config` could inject `tool_weights` that don't sum to 1.0, skewing the total score. Fix: normalize weights after merging.

### 11. `explain_node` crash on `.format()` (FIXED)
Python `.format()` choked on `{}` braces in JSON content. Fix: use string concatenation instead of `.format()`.

### 12. `get_visibility` returns `null`
The visibility MCP tool requires a valid isovist boundary curve computed in Grasshopper. If the upstream component hasn't computed it, it returns `{"visibility_result": null}`.

### 13. Orientation/Reachability MCP placeholders
`visualize_orientation` and `visualize_reachability` MCP tools are not yet implemented in the GH server. The nodes print placeholder messages and store results in state only.

### 14. `place_objects` MCP format mismatch (OPEN)
The LLM sometimes sends extra parameters or uses wrong format for the `place_objects` MCP tool. `add_objects.py` parses the compact string format (`name:WxDxH:x=X,y=Y`) but malformed input silently yields no regex matches. A warning is now logged when this happens.

### 15. `_slim_layout` stripping fields needed by GH components (FIXED — 2026-05-17)
`graph.py:_build_initial_state()` stored `json.dumps(_slim_layout(...))` in `layout_json_string`. `_slim_layout` strips `outline`, `structure`, `mep`, and `windows` — but GH components need them. `collision-detector-grid` needs `outline` (grid bounds), `structure` (wall obstacles), and `mep` (obstacles). `visualize_visibility` needs full layout geometry. Only `visualize_paths` worked because it only needs `rooms` + `doors`. Fix: `layout_json_string` now stores the **full** `ctx.layout_data`; the slim version is used only in the LLM prompt message to save tokens.

### 16. Collision node profile format mismatch with GH script (FIXED — 2026-05-17)
`collision.py` sent `profile_config` as-is to the `collision-detector-grid` GH component. Profile agent outputs `{"profile_type": "wheelchair_user", "min_path_width": 0.90, "turning_radius": 0.75}` but the GH script expects `{"user_type": "wheelchair", "min_corridor_width_m": 0.90, "turning_radius_m": 1.50}`. Key name and value format mismatches. Fix: collision node now maps profile keys: `profile_type` → `user_type` (with `_user` suffix stripped), `min_path_width` → `min_corridor_width_m`, `turning_radius` → `turning_radius_m`, etc.

### 17. Pre-agents failing on nested LLM responses (FIXED — 2026-05-17)
LLM sometimes wraps profile/space config in extra layers like `{"accessibility_analysis": {"profile": {"profile_type": ...}}}`. Both `profile_agent.py` and `space_type_agent.py` only checked for top-level `profile_type`/`space_type` keys, so nested responses fell back to defaults. Fix: both agents now search up to 2 levels deep for the dict containing the expected keys.

### 18. `_normalize_llm_decision` KeyError on `tool_name` vs `name` (FIXED — 2026-05-17)
LLM returned `"tool_name"` instead of `"name"` in tool call dicts, causing KeyError. Fix: added `_extract_tool_name()` helper that checks `name`, `tool_name`, and `function` keys. Added `_normalize_tool_calls()` to standardize all tool call formats.

### 19. Infinite loop: collision violations in analysis-only runs (FIXED — 2026-05-17)
When the LLM says `"action": "final"` (analysis-only, no object placement), the graph routes to `analysis_fan_out` → Group 1. If collision detects `hard_violations > 0`, `_route_after_group1` returned `"adjust"` → back to `reason`. The LLM says `"final"` again → same cycle forever. The layout has inherent violations that can't be fixed by reasoning alone — no objects were placed, so there's nothing to adjust. Fix: `_route_after_group1` and `_route_after_group2` now only return `"adjust"` if the agent actually placed objects (`last_placement_result is not None`). Analysis-only runs always continue to scoring → user_checkpoint.

### 20. `layout_json_string` not propagating through parallel nodes (FIXED — 2026-05-17)
After `add_objects.py` updated furniture positions in `layout_json_string`, the updated value was lost by the time collision/visibility/path nodes ran. Root cause: `layout_json_string` was typed as `str` in `AgentState` without the `_keep_last` reducer annotation, so LangGraph's parallel fan-out/fan-in dropped updates from non-primary branches. Fix: changed to `Annotated[str, _keep_last]` in `AgentState`.

### 21. Placement history not shown at checkpoint (FIXED — 2026-05-17)
After the agent moved furniture, the user had no way to see what objects were moved, from where, to where, or by how much before approving. Fix: `add_objects.py` now tracks placement history (`action: moved/added`, `from: [x,y]`, `to: [x,y]`, `size: [w,d]`, `room: name`). `user_checkpoint_node` in `graph.py` displays score breakdown per tool, collision violations, and full placement history with old→new coordinates before asking for approval. Added `placement_history: Annotated[list[dict] | None, _keep_last]` to `AgentState`.

### 22. Infinite adjustment loop after placement (FIXED — 2026-05-17)
After placing objects, if collision violations persisted (e.g. structural issues like bathroom turning radius), the graph looped infinitely: collision → adjust → reason → place → collision → same violations → adjust → forever. Fix: added `adjustment_count: Annotated[int, _keep_last]` to `AgentState` and `MAX_ADJUSTMENTS = 3` constant. `group1_join_node` increments `adjustment_count` when hard collisions exist after placement. Routing functions only return `"adjust"` if `adjustment_count < MAX_ADJUSTMENTS`. After 3 attempts, the graph continues to scoring regardless.

### 23. `explain_node` crash on `.format()` with JSON content (FIXED — 2026-05-17)
`call_llm()` and `_call_anthropic()` used `system_prompt.format(tool_catalog=tool_catalog)` which crashes with `"unmatched '{' in format spec"` when the system prompt contains JSON with `{}` braces (e.g. layout data, collision results). Fix: both functions changed to `system_prompt.replace("{tool_catalog}", tool_catalog)` in `_runtime/llm.py`.

### 24. `object_to_place` / `pending_tool_calls` never clearing — `_keep_last` reducer bug (FIXED — 2026-05-17)
`_keep_last(old, None) = old` — setting state fields to `None` doesn't clear them. `reason.py` set `object_to_place = None` and `pending_tool_calls = None` to indicate "no action", but the old values persisted, causing duplicate placements and stale tool calls. Fix: use `{}` for dicts and `[]` for lists instead of `None` in `reason.py` and `add_objects.py`.

### 25. Doors lost after furniture placement (FIXED — 2026-05-17)
When `place_objects` MCP tool returned a full layout, it sometimes omitted doors/windows/mep/structure/outline. The state's `layout_json_string` was overwritten with this incomplete layout, losing 3 doors → 0 doors. Fix: both `add_objects.py` and `tools.py` now merge missing layers from the current state before updating. Checkpoint node has structural integrity check that auto-restores lost layers from `original_layout`.

### 26. Collision score dominated by wall violations (FIXED — 2026-05-17)
The collision scoring treated all `blocked_area_m2` equally — walls generated huge clearance violation zones along the entire perimeter, making scores very low even with good furniture placement. Fix: `scoring.py` now separates violations by `object_type`: **structure** violations penalized at 20% weight (not actionable), **furniture/MEP** at full weight (actionable by the agent).

### 27. `set_viewport` MCP tool stays "pending" (PARTIALLY FIXED — 2026-05-17)
The `set_viewport` GHPython component never returned a response through Swiftlet, blocking the pipeline indefinitely. Root causes: (a) `info` output was a plain string, not valid JSON — Swiftlet couldn't parse it as an MCP response; (b) the Swiftlet Result cluster may not be wired. Fix (a): all `info` outputs now return `json.dumps({...})`. Fix (b): requires GH-side wiring of the Result cluster. Mitigation: `mcp_client.call_tool()` now accepts optional `timeout` parameter; `set_viewport` calls use 10s timeout; auto-disabled for the session after first failure, falls back to `collision-detector-grid`.

### 28. Viewport overlay: layout + analysis not visible simultaneously (OPEN — 2026-05-17)
When toggling to analysis views (3/4/5), both `set_viewport` (layout) and the analysis tool should show simultaneously via separate GH Custom Preview components. In practice, `set_viewport` often fails (issue #27), leaving only the analysis visible. Current workaround: overlays (3/4/5) use `collision-detector-grid` as the layout base (its clearance mesh provides spatial context) instead of relying on `set_viewport`. Full fix requires `set_viewport` working reliably as an MCP tool (Result cluster wiring in GH).

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

**Swiftlet must be running in Rhino 8 before launching `main.py`.**

## How to run

```bash
cd team_03/python

# Specify a layout by name (searches layout/ recursively)
python main.py --layout industrial_005 "analyse this layout for a wheelchair user"
python main.py --layout industrial_03 "place objects in the clean room for forklift use"
python main.py --layout residential_01 "analyse for elderly"

# Layout name via environment variable (useful for VS Code launch configs)
LAYOUT_FILE=industrial_005 python main.py "analyse for wheelchair"

# Run smoke test (requires MCP + GH running)
python test_bootstrap.py --layout industrial_005
```

**Session management:** On startup, if `workspace/session_active.json` exists from a previous run, the agent asks whether to resume or start fresh. The base layout file is never modified.

## Dependencies

```bash
pip install langchain-openai langchain-anthropic langgraph grandalf shapely httpx python-dotenv anthropic
```

## Grasshopper Scripts (GHPython Components)

The Grasshopper definition (`gh/team_03_working.gh`) contains GHPython scripts that form the simulation pipeline:

### Script 1 — Shortest Path (BFS + Door Scoring)
**Input:** `json_str` (layout with doors), `start_room` (string)
**Output:** `a` (JSON with room depths, path_doors, and door position scores)

### Script 2 — Path Polyline Builder
**Input:** `json_str` (output from Script 1), `target_room` (string), `layout_json` (layout with doors+geometry)
**Output:** `polyline`, `points`, `info`

### Script 3 — JSON File Reader
**Input:** `path` (file path string)
**Output:** `json_string`

### Script 4 — Layout Geometry Visualizer
**Input:** `json_str` (full layout JSON with geometry)
**Output:** `a`-`m` (room_names, room_curves, door_names, door_curves, window/furniture/mep/structure curves, outline)

### Script 5 — Room Centroid Point
**Input:** `room_name` (string)
**Output:** `point` (Rhino Point3d)

### Script 7 — set_viewport (Viewport Toggle)
**Source:** `gh/set_viewport.py`
**Input:** `layout_json` (full layout JSON string), `mode` (string: `"all"`, `"rooms"`, `"furniture"`, `"doors"`, `"structure"`, `"outline_only"`, `"none"`)
**Output:** `room_curves`, `room_names`, `door_curves`, `door_names`, `furniture_curves`, `furniture_names`, `window_curves`, `structure_curves`, `mep_curves`, `outline_curve`, `info` (JSON string)
**Note:** `info` output must be valid JSON (e.g. `{"status":"ok","mode":"all",...}`) for Swiftlet to return the MCP response. Mode `"none"` clears all geometry outputs (used when switching to analysis-only views).

**Setup in GH:**
1. Add a new GHPython component to `team_03_working.gh`
2. Rename the component to `set_viewport` (this becomes the MCP tool name)
3. Add input parameters: `layout_json` (str), `mode` (str)
4. Add output parameters: `room_curves`, `room_names`, `door_curves`, `door_names`, `furniture_curves`, `furniture_names`, `window_curves`, `structure_curves`, `mep_curves`, `outline_curve`, `info`
5. Paste the contents of `gh/set_viewport.py` into the GHPython editor
6. Connect outputs to Preview/Custom Preview components
7. Restart Swiftlet — the tool auto-discovers

### Script 6 — Visibility Analysis (Isovist)
**Input:** `path` (to layout.json), `boundary` (Rhino curve — isovist boundary), `current_room` (string)
**Output:** `a` (JSON with visibility percentages per room)

---

### Data Flow Summary

```
Python Agent (main.py --layout <name>)
    │ prompt + layout name
    ▼
Bootstrap → resolve layout, create session, connect MCP
    │
    ▼
Profile Agent ── LLM + RAG → profile_config (reach, path width, turning radius)
    │
    ▼
Space Type Agent ── LLM + RAG → space_config (priorities, clearances, tool weights)
    │
    ▼
LangGraph (reason node) ── decides: place object / call tool / finish reasoning
    │
    ├── add_objects → place_objects MCP call → save session
    │       │
    │       ▼
    │   Group 1 (parallel): collision + visibility + orientation
    │       │
    │       ▼ (hard collision violations → back to reason, ONLY if objects were placed)
    │   Group 2 (sequential): path → reachability
    │       │
    │       ▼ (poor connectivity → back to reason, ONLY if objects were placed)
    │   Scoring → weighted 0-100 score + grade
    │       │
    │       ▼
    │   User Checkpoint → approve or request changes
    │       │
    │       ├── approved → explain (LLM summary) → output (save final) → END
    │       └── continue → reason (new iteration round)
    │
    ├── tool → MCP call → result back to reason
    │
    └── finish → start analysis pipeline (visibility entry point)
```

## File structure

```
team_03/
  python/
    main.py                         # CLI entry point (--layout name)
    graph.py                        # Phase 3 LangGraph StateGraph wiring
    test_bootstrap.py               # Smoke test for all nodes
    nodes/
      profile_agent.py              # Profile Agent — user profiling + RAG
      space_type_agent.py           # Space Type Agent — space analysis + RAG
      reason.py                     # LLM node + system prompt (receives profile/space context)
      tools.py                      # MCP tool execution node
      add_objects.py                # Object placement via MCP place_objects
      collision.py                  # Pure Python grid-based collision analysis
      visibility.py                 # Shapely line-of-sight analysis
      path_analysis.py              # BFS (room-level) + A* (object-level) pathfinding
      reachability.py               # Ergonomic reach envelope analysis
      orientation.py                # Facing direction analysis
      scoring.py                    # Weighted multi-tool quality score + grade
    knowledge/                      # RAG knowledge base
      loader.py                     # Keyword-based file search + formatting
      general/                      # ADA, Neufert — universal accessibility data
      residential/                  # Residential-specific clearances
      industrial/                   # OSHA, ISO — industrial safety data
    view_graph/
      spatial_graph_interactive.html  # Generated live HTML graph (auto-updated by pipeline)
      lib/vis-9.1.2/                  # Local vis.js 9.1.2 (network + CSS)
      lib/bindings/                   # vis.js bindings utilities
      lib/tom-select/                 # Tom Select library
    _runtime/
      bootstrap.py                  # Context dataclass, session init, MCP connect, LLM build
      config.py
      llm.py                        # ChatOpenAI wrapper + call_llm_simple()
      mcp_client.py
      session.py                    # Session lifecycle: create, save, close, detect
  layout/
    industrial_100/                 # Industrial layouts (4 files currently)
      industrial_005.json, industrial_01..03.json
    residential_100/                # Residential layouts (3 files currently)
      residential_01..03.json
  workspace/
    session_active.json             # Live session state (overwritten on each update)
  output/                           # Final approved layouts (timestamped)
  gh/
    team_03_working.gh              # Main Grasshopper definition
    set_viewport.py                 # GHPython script for viewport toggle MCP tool
    team_03_definition_cluster.ghcluster
    team_03_result_cluster.ghcluster
  ramon_experiments/                # Archived scripts and conversation analysis
    python_tools/                   # Scripts from earlier phases
      generate_industrial_100.py    # 100-layout generator (industrial)
      generate_residential.py       # 100-layout generator (residential)
      layout_visualizer.py          # Layout JSON → Rhino geometry
      read_layout_relative.py       # Relative JSON loader for GH
      layout_grid_viewer.py         # Grid arranger for side-by-side comparison
      fill_connects.py              # Door connectsRooms utility
      extract_rooms_ramon.py        # Room extraction utility
      path_ramon.py                 # Path builder utility
      path_polyline.py              # Polyline builder
      read_json_string.py           # Simple JSON file reader
      shortest_path_hani_edited.py  # BFS shortest path (GH version)
    conversations/                  # Conversation analysis and documentation
      RAMY_CLAUDE.md                # Analysis of Ramy's debugging session
      Ramy_conversation.txt         # Raw conversation export (786 messages)
      _extracted_msgs.txt           # Extracted human-readable messages
      CLAUDE.md                     # Snapshot of CLAUDE.md at time of analysis
      layout_generator-context_claude.txt  # Context for Claude layout generation
```

---

## Layout Schema Reference (`layout_input/layout_schema.json`)

This is the **master schema** for defining architectural floor plans as JSON. Use it as a template to create new `geometry.json` files for any floor plan.

### 1. Top-level structure

```json
{
  "layoutId": "string",        // Unique identifier for the layout
  "outline": [[x,y], ...],    // Exterior boundary of the entire unit
  "rooms": [...],              // Habitable spaces
  "doors": [...],              // Door openings
  "windows": [...],            // Window openings
  "furniture": [...],          // Furniture pieces
  "mep": [...],                // Mechanical/Electrical/Plumbing elements
  "structure": [...]           // Structural elements (walls, columns)
}
```

**7 layers** in total. All coordinates are 2D `[x, y]` in **meters**, on the XY plane (Z=0 implied).

### 2. Geometry conventions

| Type | Geometry format | Example |
|---|---|---|
| **Closed polyline** (areas) | Array of `[x,y]` where first point = last point | outline, rooms, furniture, mep |
| **Open line** (linear elements) | Array of exactly 2 `[x,y]` points | doors, windows, structure |

- Closed polylines define **areas** — the polygon they enclose is the usable space.
- Open lines define **linear elements** — their length is the element's dimension (door width, window width, wall length).

### 3. Layer-by-layer specification

#### 3.1 `outline` — Exterior boundary
```json
"outline": [[0.0, 0.0], [9.0, 0.0], [9.0, 5.0], [0.0, 5.0], [0.0, 0.0]]
```
- Closed polyline defining the outer perimeter of the entire dwelling.
- Sum of all room areas should approximate the outline area.

#### 3.2 `rooms` — Habitable spaces
```json
{
  "id": "room-1",                    // Unique ID, pattern: room-N
  "name": "Living Room",             // Human-readable name
  "geometry": [[x,y], ...],          // Closed polyline (first=last)
  "attributes": {
    "area": 25.0                     // Area in m² (should match polygon area)
  }
}
```
- Adjacent rooms **share edges** (e.g., Living ends at X=5.0, Bedroom starts at X=5.0).
- Room polygons should tile to fill the outline without gaps or overlaps.
- `area` is stated explicitly but should be consistent with the polygon geometry.

#### 3.3 `doors` — Door openings
```json
{
  "id": "door-1",                    // Unique ID, pattern: door-N
  "type": "wooden",                  // Door type (wooden, sliding, glass, etc.)
  "name": "Bedroom Door",            // Human-readable name
  "geometry": [[5.0, 2.0], [5.0, 2.9]],  // Line segment (2 points)
  "attributes": {
    "connectsRooms": ["room-1", "room-2"]  // Which two rooms the door connects
  }
}
```
- The **line segment sits on a shared wall** between two rooms.
- Door **width** = distance between the 2 points (e.g., 2.9 - 2.0 = **0.9 m**).
- `connectsRooms` defines the adjacency graph — critical for pathfinding (BFS).
- A door on an exterior wall would connect a room to `"exterior"` or have only one room ID.

#### 3.4 `windows` — Window openings
```json
{
  "id": "window-1",                  // Unique ID, pattern: window-N
  "type": "sliding",                 // Window type (sliding, casement, fixed, etc.)
  "name": "Living Room Window",
  "geometry": [[0.0, 2.0], [0.0, 3.5]],  // Line segment (2 points)
  "attributes": {
    "roomId": "room-1"              // Which room the window belongs to
  }
}
```
- Line segment sits on a wall (exterior or interior).
- Window **width** = distance between the 2 points (e.g., 3.5 - 2.0 = **1.5 m**).
- Unlike doors, windows reference a **single room** via `roomId`.

#### 3.5 `furniture` — Furniture pieces
```json
{
  "id": "furn-1",                    // Unique ID, pattern: furn-N
  "name": "Main Couch",
  "geometry": [[2.0, 3.0], [4.0, 3.0], [4.0, 4.0], [2.0, 4.0], [2.0, 3.0]],
  "attributes": {
    "roomId": "room-1"              // Which room contains this furniture
  }
}
```
- **Closed polyline** (footprint of the furniture).
- Must be **contained within** the parent room's geometry.
- Useful for collision detection and accessible path analysis.
- Optional fields: `use_point` (`[x, y]` — where person stands/sits to use), `functional_point` (`[x, y]` — what object points at), `orientation` (facing angle or `[x, y]` vector), `target` (object id/name or `[x, y]` point).

#### 3.6 `mep` — Mechanical, Electrical, Plumbing
```json
{
  "id": "mep-1",                     // Unique ID, pattern: mep-N
  "name": "Living Room AC",
  "geometry": [[2.5, 4.5], [3.5, 4.5], [3.5, 4.8], [2.5, 4.8], [2.5, 4.5]],
  "attributes": {
    "system": "hvac"                 // System type: hvac, electrical, plumbing
  }
}
```
- **Closed polyline** (footprint/bounding box of the element).
- `system` field categorizes the MEP element.
- Important for spatial conflicts — MEP elements occupy space that may block circulation.

#### 3.7 `structure` — Structural elements
```json
{
  "id": "wall-1",                    // Unique ID, pattern: wall-N
  "name": "North Interior Wall",
  "geometry": [[5.0, 0.0], [5.0, 5.0]],  // Line segment (2 points)
  "attributes": {}
}
```
- **Open line** representing a wall centerline, column line, or beam.
- Wall **thickness is not encoded** — the line is the centerline.
- Structural walls vs partitions could be differentiated via `attributes`.

### 4. Coordinate system rules

- **Origin**: bottom-left corner of the floor plan is typically `[0.0, 0.0]`.
- **Units**: meters (decimal, e.g., `2.9` not `2900mm`).
- **Winding**: closed polylines go **counter-clockwise** (standard for positive area).
- **Shared edges**: adjacent rooms share exact coordinates on their common wall (no gaps, no overlaps).
- **Elements on walls**: doors, windows, and structure lines must lie exactly on a room boundary edge.

### 5. ID naming conventions

| Layer | Pattern | Example |
|---|---|---|
| rooms | `room-N` | `room-1`, `room-2` |
| doors | `door-N` | `door-1`, `door-2` |
| windows | `window-N` | `window-1` |
| furniture | `furn-N` | `furn-1` |
| mep | `mep-N` | `mep-1`, `mep-2` |
| structure | `wall-N` | `wall-1` |

### 6. Relationship model

```
outline (contains all rooms)
  └── rooms
        ├── doors (connectsRooms: [room-A, room-B])  ← adjacency graph
        ├── windows (roomId: room-A)                  ← belongs to one room
        ├── furniture (roomId: room-A)                ← belongs to one room
        └── mep (system: hvac|electrical|plumbing)    ← categorized by system
structure (independent — walls/columns that define room boundaries)
```

### 7. How to create a new floor plan

1. **Define the outline** — exterior boundary as a closed polyline.
2. **Subdivide into rooms** — partition the outline into closed polylines. Ensure shared edges match exactly.
3. **Place doors** — line segments on shared walls. Set `connectsRooms` to the two adjacent room IDs.
4. **Place windows** — line segments on walls (usually exterior). Set `roomId`.
5. **Add furniture** — closed polylines inside rooms. Set `roomId`.
6. **Add MEP** — closed polylines for HVAC, electrical, plumbing elements. Set `system`.
7. **Add structure** — line segments for walls, columns. These are the load-bearing elements.
8. **Validate**:
   - All closed polylines have first point = last point.
   - Room areas tile to fill the outline.
   - Doors/windows sit on actual wall edges.
   - Furniture/MEP are within their parent room.
   - All IDs are unique within their layer.
   - `connectsRooms` references valid room IDs.
