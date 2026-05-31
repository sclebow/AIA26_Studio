# Team 03 — Industrial Spatial Flow Agent (V2)

> This document supersedes MASTER_CLAUDE.md. Updated after Ramy's refactoring commit (ba8b99f), the re-implementation of the spatial graph layer, and the collision clearance fix (2026-05-22).

## What this project does

An AI agent that optimizes industrial floor plan layouts by placing equipment and analyzing spatial quality against OSHA, NFPA, and ISO standards. The agent connects a Python LangGraph pipeline to a Grasshopper/Rhino simulation backend via MCP (Swiftlet). The system is **industrial-only** — factories, workshops, warehouses, assembly halls, fabrication areas, clean rooms.

A **Spatial Relationship Graph** (NetworkX MultiGraph) gives the LLM structured spatial context. Instead of parsing raw coordinates, the LLM receives pre-computed topology (room connectivity, proximity relationships, containment) and actionable fix directives after each analysis cycle: `move [+0.9,+0.4] 0.4m to fix clearance (has 0.6m, needs 0.9m)`. When violations are detected after placement, the system auto-corrects by injecting a correction message with exact move vectors and loops back to the LLM (max 3 attempts).

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
    +-- prompts.py             (SYSTEM_PROMPT, SPACE_CONTEXT_TEMPLATE, PROFILE_CONTEXT_TEMPLATE)
    +-- reason.py              (LLM decision: place / tool / query / final)
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
    |
    _runtime/
    +-- bootstrap.py           (Context dataclass, session init, MCP, LLM)
    +-- llm.py                 (call_llm, call_llm_simple, LLM provider abstraction)
    +-- mcp_client.py          (HTTP JSON-RPC client for Swiftlet)
    +-- session.py             (create/save/close session_active.json)
    +-- utils.py               (_slim_layout, _format_tool_catalog)
    +-- config.py              (.env loader)
    |
    Grasshopper (Swiftlet @ localhost:3002)
```

---

## Phase 3 Graph Flow

```
START -> profile_agent -> space_type_agent -> reason
                                               |
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
                        | 1=BEFORE  2=AFTER  3=collision  4=visibility  5=paths
                        | 0=clear overlays   s1..s5=smart suggestions
                        +--------+--------+
                      approved        continue -> reason
                        |
                        v
                      explain -> output -> END
```

**Key routing rules:**
- `adjust` only if `last_placement_result is not None` AND `adjustment_count < MAX_ADJUSTMENTS (3)`
- `query_agent` path: analysis without placement, goes to `user_checkpoint` then `query_end` (no output saved)
- `enrich_graph` runs BEFORE the group2 routing decision so the graph has full analysis data when the correction message is built

---

## Spatial Graph Layer

The spatial graph is a NetworkX MultiGraph that encodes relationships between layout elements. It lives in `AgentState` as `spatial_graph` (dict) and `spatial_graph_text` (str).

### Two phases of the same graph object

**Base graph** (built from layout JSON):
| Node type | Attributes | Source |
|-----------|-----------|--------|
| `room` | name, area, center | `layout.rooms[]` |
| `door` | name, width, connects | `layout.doors[]` |
| `wall` | name, wall_type, material, length, p1/p2 | `layout.structure[]` |
| `window` | name, window_type, roomId, width, p1/p2 | `layout.windows[]` |
| `furniture` | name, roomId, center, bbox_w/d | `layout.furniture[]` |
| `mep` | name, system, roomId, center | `layout.mep[]` |

| Edge type | Meaning |
|-----------|---------|
| `contained_in` | furniture/mep/window -> room |
| `door_connects` | door -> rooms |
| `adjacent` | room <-> room (inferred from shared door) |
| `near` | furniture <-> furniture, same room, < 3m |
| `near_wall` | furniture <-> wall, point-to-segment distance < 3m |
| `near_window` | furniture <-> window, same room, point-to-segment < 3m |

**Enriched graph** (after analysis tools):
| Source | Adds to graph |
|--------|--------------|
| Collision | Node attrs: `clearance_ok`, `deficit_m`, `min_clearance_m`, `required_clearance_m`, `move_direction`, `move_distance_m`. Edge: `blocks` |
| Visibility | Edge: `sightline` with `visible` bool |
| Path | Edge: `path` with `distance_m`, `reachable` |
| Reachability | Node attrs: `reachable`, `height_ok`, `radius_ok` |
| Orientation | Node attrs: `facing_ok`, `angle_diff` |

### The feedback loop

```
build_graph_from_layout(layout)     <- startup + after each placement
        |
serialize_for_llm(G)                <- text injected into LLM context
        |
LLM places/moves objects
        |
rebuild graph from new layout       <- add_objects.py (2 locations)
        |
analysis tools run (5 tools)
        |
enrich_graph_from_analysis(G, ...)  <- enrich_graph_node in graph.py
        |
FINDINGS printed to terminal        <- ANSI colored: red=critical, yellow=warning
        |
violations + placement occurred?
    YES -> _build_correction_message(G)
           injected as "user" message
           router -> reason -> LLM sees exact fix instructions
    NO  -> scoring
```

### Fallback move direction
When collision detects a clearance violation but the object has no `use_point` (so collision.py can't compute a gradient-based suggestion), `spatial_graph.py` computes a fallback: unit vector from object center toward room center, distance = deficit + 0.1m safety margin.

### Terminal output example
```
[spatial_graph] Initial graph: 46 nodes, 180 edges
SPATIAL GRAPH (46 nodes, 180 edges)
ROOMS:
  room-1 "Bathroom" area=45.5m2
  room-2 "Clean Room" area=812.5m2
CONNECTIVITY:
  Bathroom <--door-1(0.9m)--> Clean Room
STRUCTURE:
  wall-1 "South Exterior Wall" load-bearing 48.0m
  wall-5 "Bathroom Partition" partition 7.0m
WINDOWS: Clean Room: 14 (10x awning, 4x sliding); Bathroom: 2 (2x fixed)
FURNITURE in Clean Room:
  furn-3 "Assembly Station 1" at(7.1,10.5) clearance=FAIL(-0.05m) reachable=YES
  ...
RELATIONS:
  Assembly Station 1 --near_wall(1.2m)--> South Exterior Wall
  Toilet --near_window(0.8m)--> Bathroom Window 1
  ...

[enrich_graph] === FINDINGS (2) ===
  CLEARANCE  cnc_machine: has 0.35m, needs 0.4m -> move [+0.0,+0.9] 0.15m
  UNREACH    storage_rack: height
[tip] python test_spatial_graph.py --session
```

---

## Component Descriptions

- **`main.py`** — CLI entry. Takes `prompt` (required) and `--layout <name>` (optional). Bootstrap -> run_agent -> print response. Always closes MCP client in finally block.

- **`graph.py`** — LangGraph StateGraph wiring. Contains `AgentState` TypedDict with `_keep_last` reducers for parallel branches. Routing functions: `_route_after_reason`, `_route_after_group1`, `_route_after_group2`, `_route_after_checkpoint`. Inline nodes: `enrich_graph_node`, `_build_correction_message`, `query_end_node`. `_build_initial_state` builds the initial spatial graph at startup.

- **`prompts.py`** — All system prompts in one file. `SYSTEM_PROMPT`: industrial-only scope guard, placement workflow (STEP 1-4 coordinate calculation), move_object instructions, query action, SPATIAL GRAPH section. `SPACE_TYPE_SYSTEM_PROMPT` and `PROFILE_SYSTEM_PROMPT` for pre-agents. `SPACE_CONTEXT_TEMPLATE` and `PROFILE_CONTEXT_TEMPLATE` injected by reason.py each turn.

- **`spatial_graph.py`** — NetworkX MultiGraph module. Pure Python, no LangGraph/MCP/LLM dependencies. `build_graph_from_layout()` (rooms, doors, walls, windows, furniture, mep + near/near_wall/near_window edges), `enrich_graph_from_analysis()`, `serialize_for_llm()`, `graph_to_dict()`, `dict_to_graph()`. Uses `_point_to_segment_distance()` for accurate furniture-to-wall/window proximity. `clearance_ok` is based on `deficit_m > 0` (not just presence of `clearance_violation`). Graph is ephemeral (RAM only), rebuilt from layout JSON after each placement.

- **`test_spatial_graph.py`** — Standalone visualization. `--session` reads `workspace/session_active.json` (live with placed furniture); layout name reads base layout; `--all` tests all layouts. Uses matplotlib, dark theme, nodes/edges colored by type. Legend includes edge descriptions (e.g. `near_wall (12) — furniture < 3m from wall`). Node types: room (blue), door (orange), wall (gray), window (cyan), furniture (green), mep (red).

- **`nodes/reason.py`** — LLM brain. Reads full conversation + tool results. Decides: `action=tool` (place_object -> add_objects, other tools -> tools.py), `action=query` -> query_agent, `action=final` -> end loop. Injects `space_config`, `profile_config`, and `spatial_graph_text` as context before each LLM call. 3 retry attempts with backoff.

- **`nodes/add_objects.py`** — Object placement via MCP `place_objects`. Parses `name:WxDxH:x=X,y=Y` regex format. Merges missing layers (doors/windows/mep/structure/outline) from current state after MCP response. Door clearance check (1.0m OSHA), window clearance check (0.5m NFPA 101). Tracks placement_history. **Rebuilds spatial graph (base only) after both MCP and fallback paths.** Processes object_queue for multi-placement requests.

- **`nodes/fan_out.py`** — Two pass-through nodes. `analysis_fan_out_node`: no-op fan-out before parallel Group 1. `group1_join_node`: convergence after collision/visibility/orientation; if hard collisions + objects placed -> increment adjustment_count + inject basic correction message.

- **`nodes/checkpoint.py`** — Interactive user approval gate. Shows score breakdown with colored deltas vs previous visit. Shows placement history with coordinates. Viewport toggles 1-5, 0. Smart suggestions s1-s5 (generated from lowest-scoring tools). Structural integrity check restores missing layers from original_layout. Sends layout to viewport on arrival via `set_viewport` (10s timeout) or `collision-detector-grid` fallback.

- **`nodes/query_agent.py`** — Analysis-only path (no placement, no output saved). Detects which tools to run from user prompt keywords. Runs collision/path/reachability/visibility independently. Returns markdown report as final_response. Routes to user_checkpoint then query_end (no file saved).

- **`nodes/explain.py`** — Post-approval LLM summary. Builds compact text from scoring + top collision violations + worst path distance. Generates 3-5 sentence explanation with specific object names and distances.

- **`nodes/output.py`** — Terminal node. Calls `close_session()` to write timestamped final layout to `output/` and delete session_active.json.

- **`nodes/visibility.py`** — Isovist + sightline analysis. Casts 72 rays (every 5 degrees) from each object's use_point. Mode 1 (no objects): centroid-to-centroid room pairs. Mode 2 (objects): use_point -> functional_point pairs. Calls `visualize_visibility` MCP tool.

- **`nodes/collision.py`** — Pure Python BFS grid collision analysis. 0.10m grid resolution. Checks: body clearance, corridor width, door widths, turning radii, use_point clearance, functional_line obstruction. Violation types: BLOCKED, WARNING, DOOR_WIDTH, TURNING, USE_POINT, FUNCTIONAL_LINE. **Voronoi boundary method** computes real `min_clearance_m` as the actual gap between each object and its nearest other obstacle (wall/furniture/mep), replacing the old per-cell minimum that always bottomed out at 0.1m (1 grid cell).

- **`nodes/path_analysis.py`** — BFS (room-level) + A* (object-level) pathfinding. Mode 1: BFS through door graph, all room pairs. Mode 2: A* on 0.5m grid, object-to-object within each room.

- **`nodes/reachability.py`** — Ergonomic reach envelope check. `height_ok` (functional_point z in reach range), `radius_ok` (2D distance from use_point <= reach_radius). Heights estimated from object name keywords.

- **`nodes/orientation.py`** — Facing direction check. Resolves target from `target_direction`, `target` (point or object ref). Tolerance: 45 degrees.

- **`nodes/scoring.py`** — Weighted 0-100 score, letter grade A-F. Structure violations penalized at 20% (not actionable), furniture/MEP at 100% (actionable). Space config can override weights.

- **`nodes/tools.py`** — Generic MCP tool execution. Auto-injects `layout_json`. Special handling for `collision-detector-grid` (forces correct profile format). Merges missing layers if result has rooms. Updates viewport after layout changes.

- **`nodes/profile_agent.py`** — Identifies movement profile from prompt. Industrial profiles only.

- **`nodes/space_type_agent.py`** — Detects industrial subtype (workshop, warehouse, assembly, etc.) and outputs analysis priorities + clearances + tool weights.

- **`_runtime/bootstrap.py`** — Context dataclass + `bootstrap()` function. Resolves layout by name (rglob under `layout/`). Handles existing session (resume/fresh). Connects to MCP, lists tools, builds LLM.

- **`_runtime/utils.py`** — `_slim_layout()` (strips windows/MEP/structure for LLM tokens), `_format_tool_catalog()`.

- **`_runtime/llm.py`** — `call_llm()` for main agent, `call_llm_simple()` for pre-agents. Supports multiple providers (openai, anthropic, local). Handles LLM format variations.

- **`_runtime/mcp_client.py`** — HTTP JSON-RPC Swiftlet client. `call_tool(name, args, timeout=None)`.

- **`_runtime/session.py`** — `create_session()`, `save_session()`, `close_session()`, `detect_existing_session()`.

---

## Industrial User Profiles

| Profile | Min path (m) | Turning radius (m) | Reach min (m) | Reach max (m) |
|---------|-------------|-------------------|--------------|--------------|
| standard_worker | 0.90 | 0.60 | 0.50 | 2.00 |
| forklift | 3.05 | 2.50 | 0.00 | 6.00 |
| crane | 5.00 | 5.00 | 0.00 | 12.00 |
| pallet_jack | 1.50 | 1.50 | 0.20 | 1.20 |
| maintenance_worker | 0.90 | 0.60 | 0.30 | 2.20 |

Default: `standard_worker`. Detected from prompt keywords by Profile Agent.

---

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
    └── worker_ergonomics.json      # ISO 11228 ergonomic reach
```

---

## MCP Tools (Grasshopper / Swiftlet)

- `place_objects` — place equipment in a room. Params: `layout_json`, `room_name`, `objects_list` (JSON array), `user_profile`, `clear_room`
- `collision-detector-grid` — grid-based clearance field analysis + visualization push to GH
- `visualize_visibility` — pushes isovist/sightline results to GH
- `visualize_paths` — pushes path results to GH
- `set_viewport` — lightweight layout renderer. Params: `layout_json`, `mode`. 10s timeout, auto-disabled on failure.
- `shortest_path`, `check_door_widths`, `widen_doors` — legacy tools

All tool calls automatically receive `layout_json` (full layout, all 7 layers). `_slim_layout` (rooms+doors+furniture only) is used only in the LLM prompt.

---

## Configuration

| Variable | Description | Default |
|---------|-------------|---------|
| `LLM_PROVIDER` | `openai`, `anthropic`, `local`, `google`, `cloudflare` | required |
| `LOCAL_LLM_ENDPOINT` | e.g. `http://localhost:1234/v1/` | required if local |
| `REQUEST_TIMEOUT_SECONDS` | HTTP timeout for MCP + LLM | `120` |
| `MAX_ITERATIONS` | Max tool call cycles | `100` |
| `LAYOUT_FILE` | Layout name (env alt to `--layout`) | — |

## MCP Server

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

# Layout via env (useful for VS Code launch configs)
LAYOUT_FILE=industrial_005 python main.py "analyse the workshop clearances"

# Visualize spatial graph (no Rhino needed)
python test_spatial_graph.py --session       # live workspace (with placed furniture)
python test_spatial_graph.py industrial_005  # base layout (no furniture)
python test_spatial_graph.py --all           # all layouts

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

### 1. Timeout on MCP tool calls (OPEN)
Grasshopper simulations are slow. Use `REQUEST_TIMEOUT_SECONDS=300`. If it times out, check Rhino for red/orange GH components.

### 2. `set_viewport` MCP tool stays "pending" (PARTIALLY FIXED)
`set_viewport` sometimes doesn't return a response through Swiftlet. Checkpoint has 10s timeout + auto-fallback to `collision-detector-grid`. Fix (GH side): wire the Result cluster in the GH definition.

### 3. Viewport overlay: layout + analysis not simultaneously visible (OPEN)
When toggling to analysis views (3/4/5), `set_viewport` failures mean only the analysis is visible, not the layout. Workaround: overlays use `collision-detector-grid` as base (provides spatial context).

### 4. `place_objects` MCP format mismatch (OPEN)
LLM sometimes sends malformed `objects_list`. The regex parser in `add_objects.py` silently yields no results. A warning is printed. Use the `name:WxDxH:x=X,y=Y` format exactly.

### 5. `test_spatial_graph.py --session` shows 0 furniture for base layout
Expected behavior: `--session` reads `workspace/session_active.json` (with furniture placed by agent). Without `--session`, the base layout file has no furniture. Always use `--session` when the agent is running.

### 6. spatial_graph.py import fails if networkx not installed
Run `pip install networkx`. The graph module is wrapped in try/except in all call sites so it degrades gracefully (graph features disabled, rest of pipeline unaffected).

---

## File Structure

```
team_03/
  python/
    main.py                       # CLI entry point
    graph.py                      # LangGraph StateGraph, AgentState, enrich_graph_node
    prompts.py                    # SYSTEM_PROMPT, SPACE_TYPE_SYSTEM_PROMPT, PROFILE_SYSTEM_PROMPT
    spatial_graph.py              # NetworkX spatial relationship graph module
    test_spatial_graph.py         # Standalone graph visualizer (--session / name / --all)
    test_bootstrap.py             # Smoke test
    nodes/
      profile_agent.py            # Industrial profile detection (forklift/worker/crane...)
      space_type_agent.py         # Space subtype detection (workshop/warehouse/assembly...)
      reason.py                   # LLM decision node (injects spatial_graph_text)
      tools.py                    # Generic MCP tool execution
      add_objects.py              # Object placement + spatial graph rebuild
      fan_out.py                  # analysis_fan_out_node + group1_join_node
      collision.py                # BFS grid collision analysis
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
      general/
        accessibility_codes.json
        spatial_ergonomics.json
      industrial/
        Equipment heights.json
        emergency_egress.json
        equipment_zones.json
        fire_safety.json
        forklift_operations.json
        machinery_spacing.json
        osha_guidelines.json
        worker_ergonomics.json
    _runtime/
      bootstrap.py
      config.py
      llm.py
      mcp_client.py
      session.py
      utils.py                    # _slim_layout, _format_tool_catalog
  layout/
    industrial_100/
      industrial_005.json
      industrial_01.json
      industrial_02.json
      industrial_03.json
    residential_100/              # Layout files (agent is industrial-only)
  workspace/
    session_active.json           # Live session state (ephemeral)
  output/                         # Timestamped final layouts
  gh/
    team_03_working.gh
    set_viewport.py               # GHPython viewport toggle script
    team_03_definition_cluster.ghcluster
    team_03_result_cluster.ghcluster
    SPATIAL_GRAPH_METHODOLOGY.md  # How to replicate spatial graph in other projects
  ramon_experiments/
    conversations/
      MASTER_CLAUDE.md            # Previous documentation (superseded)
      MASTER_CLAUDE_V2.md         # This document
      RAMY_CLAUDE.md
    topologic_graph/
      spatial_graph.py            # Reference (old version, may differ)
      spatial_graph_report.pdf    # Technical report
      SPATIAL_GRAPH_METHODOLOGY.md  # Integration methodology guide
      generate_report.py          # PDF report generator
    python_tools/                 # Archived utility scripts
```

---

## Layout Schema Reference

This is the master schema for defining architectural floor plans as JSON.

### Top-level structure

```json
{
  "layoutId": "string",
  "outline": [[x,y], ...],
  "rooms": [...],
  "doors": [...],
  "windows": [...],
  "furniture": [...],
  "mep": [...],
  "structure": [...]
}
```

7 layers. All coordinates are 2D `[x, y]` in meters.

### Geometry conventions

| Type | Format |
|------|--------|
| Closed polyline (areas) | Array of `[x,y]`, first = last |
| Open line (linear elements) | Exactly 2 `[x,y]` points |

### Layer specs

**rooms:** `id` (room-N), `name`, `geometry` (closed polyline), `attributes.area` (m2)

**doors:** `id` (door-N), `name`, `geometry` (2-point line on shared wall), `attributes.connectsRooms` ([room-A, room-B])

**windows:** `id` (window-N), `name`, `geometry` (2-point line), `attributes.roomId`

**furniture:** `id` (furn-N), `name`, `geometry` (closed polyline), `attributes.roomId`. Optional: `use_point`, `functional_point`, `orientation`, `target`

**mep:** `id` (mep-N), `name`, `geometry` (closed polyline), `attributes.system` (hvac/electrical/plumbing)

**structure:** `id` (wall-N), `name`, `geometry` (2-point centerline), `attributes.type` (load-bearing/partition), `attributes.material` (concrete/drywall)

### Coordinate rules

- Origin: bottom-left at `[0.0, 0.0]`
- Units: meters
- Winding: counter-clockwise for positive area
- Adjacent rooms share exact wall coordinates
- Doors/windows sit exactly on room boundary edges
- All IDs unique within their layer

### ID naming

| Layer | Pattern | Example |
|-------|---------|---------|
| rooms | room-N | room-1 |
| doors | door-N | door-1 |
| windows | window-N | window-1 |
| furniture | furn-N | furn-1 |
| mep | mep-N | mep-1 |
| structure | wall-N | wall-1 |

---

## Changelog

### 2026-05-22 — Spatial graph layer + collision clearance fix

**`spatial_graph.py`** — NEW: NetworkX spatial relationship graph module
- Pure Python module (~570 lines), no LangGraph/MCP/LLM dependencies
- `build_graph_from_layout()`: 6 node types (room, door, wall, window, furniture, mep), 6 edge types (contained_in, door_connects, adjacent, near, near_wall, near_window)
- `enrich_graph_from_analysis()`: adds collision/visibility/path/reachability/orientation data as node attrs and edges (blocks, sightline, path)
- `serialize_for_llm()`: compact text (ROOMS, CONNECTIVITY, STRUCTURE, WINDOWS, FURNITURE, MEP, RELATIONS, ISSUES) capped at 80 lines
- `graph_to_dict()` / `dict_to_graph()`: JSON-serializable roundtrip via `nx.node_link_data`
- `_point_to_segment_distance()`: orthogonal projection + clamp for furniture-to-wall/window proximity
- Walls skipped in collision enrichment (`_skip_ntypes = {"wall"}`) — structural, not movable
- `clearance_ok` based on `deficit_m <= 0` (not just presence of `clearance_violation` dict)
- Fallback move direction: unit vector toward room center when collision.py has no `use_point` gradient

**`test_spatial_graph.py`** — NEW: standalone graph visualizer
- Dark theme matplotlib, nodes colored by type (room=blue, door=orange, wall=gray, window=cyan, furniture=green, mep=red)
- Edge styles by type (solid/dashed/dotted/dashdot), with descriptive legend (e.g. `near_wall (12) — furniture < 3m from wall`)
- Modes: `--session` (live workspace), layout name (base), `--all` (all layouts)
- Spatial positions from geometry, spring layout fallback for missing positions

**`graph.py`** — Spatial graph integration into LangGraph pipeline
- `AgentState`: added `spatial_graph: dict | None` and `spatial_graph_text: str | None` (both `_keep_last`)
- `enrich_graph_node`: deserializes graph, calls `enrich_graph_from_analysis()` with all 5 tool results, prints ANSI-colored FINDINGS (walls filtered), injects correction message when violations found after placement
- `_build_correction_message()`: builds explicit fix instructions with move vectors, positions, clearance details for LLM consumption
- Wiring: `reachability -> enrich_graph -> _route_after_group2 -> {reason, scoring}` (enrich runs BEFORE routing)
- `_build_initial_state()`: builds initial spatial graph from base layout at startup

**`nodes/reason.py`** — Spatial graph context injection
- Injects `spatial_graph_text` into LLM context before each call (after profile/space config)

**`prompts.py`** — SPATIAL GRAPH section in SYSTEM_PROMPT
- Instructs LLM to check ISSUES section for violations with exact move vectors
- Directs LLM to use `move_object` with vectors from ISSUES, not guess positions

**`nodes/add_objects.py`** — Graph rebuild after placement
- Rebuilds spatial graph (base edges only, no analysis enrichment) after both MCP and fallback placement paths
- Uses try/except so graph failure doesn't break placement pipeline

**`nodes/collision.py`** — Voronoi boundary method for real clearance
- Old: `min_clearance_m` measured distance from free cells to nearest obstacle surface, always 0.1m (1 grid cell)
- New: scans Voronoi boundaries (adjacent free cells with different nearest-obstacle attribution) to compute actual surface-to-surface gap: `gap = (dist[a] + dist[b]) * cell_size`
- Objects touching another obstacle directly get `min_clearance_m = 0.0`
- No GH changes needed — Python is authoritative, GH only visualizes

**`generate_session_report.py`** — NEW: PDF report generator
- 3 diagrams (full graph visualization, Voronoi concept before/after)
- Sections: summary, collision fix, walls/windows, graph visualization, LLM serialization, clearance_ok fix, files modified
- Output: `session_report_2026-05-22.pdf`
