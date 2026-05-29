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

**set_viewport modes:** `all`, `rooms`, `furniture`, `doors`, `structure`, `outline_only`, `none`. The `info` output must be valid JSON for Swiftlet to return the MCP response; `none` clears all geometry (analysis-only views). To add it in GH: new GHPython component named `set_viewport`, inputs `layout_json`/`mode`, the per-layer outputs above, paste `gh/set_viewport.py`, restart Swiftlet (auto-discovers).

---

## Configuration (`.env` at repo root)

| Variable | Description | Default |
|---------|-------------|---------|
| `LLM_PROVIDER` | `openai`, `anthropic`, `local`, `google`, `cloudflare` | required |
| `LOCAL_LLM_ENDPOINT` | e.g. `http://localhost:1234/v1/` | required if local |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout for MCP + LLM | `120` |
| `MAX_ITERATIONS` | Max tool call cycles | `100` |
| `DEBUG_GRAPH` | Print graph debug info | `false` |
| `LAYOUT_FILE` | Layout name (env alt to `--layout`) | — |

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

# Industrial layout + user prompt
python main.py --layout industrial_005 "place a cnc machine in the workshop"
python main.py --layout industrial_005 "check visibility in the fabrication hall"
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
4. **`place_objects` format mismatch (OPEN)** — LLM sometimes sends malformed `objects_list`; the regex parser yields nothing (a warning prints). Use the `name:WxDxH:x=X,y=Y` format exactly.
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
