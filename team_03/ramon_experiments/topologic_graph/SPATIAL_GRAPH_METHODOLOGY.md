# Spatial Graph Methodology

How to add a self-correcting spatial relationship graph to an LLM agent pipeline.
This document describes the methodology, not the specific codebase -- use it to replicate the graph in any project with minimal edits to existing nodes.

---

## The Problem

An LLM agent places objects in a floor plan and evaluates accessibility with analysis tools (collision, visibility, path, reachability, orientation). Without a graph, the LLM receives raw JSON coordinates and tool outputs as flat text. It has no structured understanding of:

- Which objects are near each other
- Which rooms connect through which doors
- What is blocking what
- How to fix a violation (direction + distance)

The LLM guesses positions instead of following computed vectors. It can't reason about topology.

---

## The Solution: A Spatial Relationship Graph

A **NetworkX MultiGraph** that encodes spatial relationships between layout elements. It exists in two phases within the same object:

### Phase 1: Base Graph (geometry only)

Built from the layout JSON before any analysis runs. Contains:

**Nodes** (only actionable elements):
| Type | Attributes | Source |
|------|-----------|--------|
| `room` | name, area, center (centroid) | `layout.rooms[]` |
| `door` | name, width (line length) | `layout.doors[]` |
| `furniture` | name, roomId, center, bbox_w, bbox_d | `layout.furniture[]` |
| `mep` | name, system, roomId, center | `layout.mep[]` |

Non-actionable elements (windows, structure, outline) are excluded -- the LLM can't move them.

**Edges** (structural relationships):
| Type | Meaning | How computed |
|------|---------|-------------|
| `contained_in` | furniture/mep belongs to a room | `attributes.roomId` match |
| `door_connects` | door links to a room | `attributes.connectsRooms` |
| `adjacent` | two rooms share a door | inferred from `door_connects` pairs |
| `near` | two furniture items < 3m apart, same room | Euclidean distance between centroids |

### Phase 2: Enriched Graph (after analysis)

The same graph object, with new attributes and edges added from tool results:

| Analysis Tool | What it adds to the graph |
|--------------|--------------------------|
| **Collision** | Node attrs: `clearance_ok`, `deficit_m`, `min_clearance_m`, `required_clearance_m`, `move_direction`, `move_distance_m`. Edge: `blocks` (when functional line is obstructed) |
| **Visibility** | Edge: `sightline` with `visible` bool and `blocked_by` |
| **Path** | Edge: `path` with `distance_m` and `reachable` bool |
| **Reachability** | Node attrs: `reachable`, `height_ok`, `radius_ok` |
| **Orientation** | Node attrs: `facing_ok`, `angle_diff` |

The enriched graph is what the LLM sees when deciding corrections.

---

## The Feedback Loop

This is the core methodology -- a **build-analyse-enrich-correct** cycle:

```
                    +------------------+
                    |  Build Base      |  <-- from layout JSON
                    |  Graph           |
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  LLM Reasons     |  <-- graph text in context
                    |  + Places Objects|
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  Analysis Tools  |  collision, visibility,
                    |  Run             |  path, reachability, orientation
                    +--------+---------+
                             |
                             v
                    +------------------+
                    |  Enrich Graph    |  <-- tool results -> node attrs + edges
                    |  + FINDINGS      |
                    +--------+---------+
                             |
                    +--------+---------+
                    |  Violations?     |
                    +---+----------+---+
                        |          |
                   YES  |          |  NO
                        v          v
              +-----------------+  +----------+
              | Inject          |  | Scoring  |
              | Correction Msg  |  | + User   |
              | -> back to LLM |  | Approval |
              +-----------------+  +----------+
                        |
                        v
              +-----------------+
              | Rebuild Graph   |  <-- fresh base from new layout
              | (after new      |
              |  placement)     |
              +-----------------+
                        |
                        +---> back to Analysis Tools
```

### Step by step:

1. **Build**: `build_graph_from_layout(layout_json)` creates the base graph
2. **Serialize**: `serialize_for_llm(G)` produces ~30-50 lines of compact text
3. **Inject**: The serialized text is prepended to the LLM's context in the reason node
4. **LLM acts**: Places or moves objects based on graph relationships and issues
5. **Rebuild**: After placement, `build_graph_from_layout(new_layout)` creates a fresh base graph (old analysis edges are discarded because positions changed)
6. **Analyse**: 5 tools run on the new layout
7. **Enrich**: `enrich_graph_from_analysis(G, ...)` adds tool findings as node attrs and edges
8. **Check**: Router examines graph for violations
9. **Correct or Score**: If violations exist AND objects were placed AND attempts < 3, inject a correction message and loop back to step 3. Otherwise proceed to scoring.

### The Correction Message

When violations are detected, the system builds an explicit message like:

```
AUTOMATIC CORRECTION (attempt 1/3)
The analysis found 3 issue(s) that need fixing:

- Toilet (currently at x=5.0, y=3.0): CLEARANCE VIOLATION (has 0.6m, needs 0.9m).
  Fix: move [+0.90, +0.40] by 0.4m
- Sink: UNREACHABLE (height out of reach range)
- Workbench BLOCKS the functional line of CNC Machine. Move Workbench out of the way.

Use the move vectors above to reposition objects.
Call place_object with the corrected coordinates.
Do NOT call analysis tools -- they run automatically after placement.
```

This message is injected into the conversation history as a user message. The LLM sees it as explicit instructions with computed vectors instead of having to guess.

### Fallback Move Direction

When collision detects a clearance violation but the object has no `use_point` (so collision.py can't compute a gradient-based suggestion), the graph computes a fallback:

- Direction: unit vector from object center toward room center (moves away from walls)
- Distance: deficit + 0.1m safety margin

This ensures every clearance violation always has a move vector.

---

## Integration Points (4 files to modify)

The graph module (`spatial_graph.py`) is self-contained. Integration requires touching only 4 files:

### 1. State definition (add 2 fields)

```python
# In your AgentState TypedDict:
spatial_graph:       Annotated[dict | None, _keep_last]   # node-link dict
spatial_graph_text:  Annotated[str | None,  _keep_last]   # compact text for LLM
```

The graph travels through the pipeline as a JSON-serializable dict (via `nx.node_link_data()`), not as a NetworkX object. This is required because LangGraph state must be serializable.

### 2. Initial state builder (build base graph at startup)

```python
from spatial_graph import build_graph_from_layout, graph_to_dict, serialize_for_llm

G = build_graph_from_layout(layout_data)
initial_state["spatial_graph"] = graph_to_dict(G)
initial_state["spatial_graph_text"] = serialize_for_llm(G)
```

### 3. Reason/LLM node (inject graph text into context)

```python
graph_text = state.get("spatial_graph_text")
if graph_text:
    context_injection += f"\n{graph_text}\n"
```

Add a section to the system prompt telling the LLM how to use the graph:

```
## SPATIAL GRAPH
You receive a SPATIAL RELATIONSHIP GRAPH showing element relationships.
Use it to:
- Check which objects have clearance violations and their suggested move directions
- See sightline connections between objects
- Know which objects are reachable vs unreachable
- Understand room connectivity through doors
- See proximity (near edges) between furniture

When placing or moving objects, ALWAYS check the ISSUES section first.
Follow move_direction vectors and deficit distances instead of guessing positions.
```

### 4. Object placement node (rebuild graph after each placement)

```python
from spatial_graph import build_graph_from_layout, graph_to_dict, serialize_for_llm

new_layout = json.loads(updated_layout_json_string)
G = build_graph_from_layout(new_layout)
updates["spatial_graph"] = graph_to_dict(G)
updates["spatial_graph_text"] = serialize_for_llm(G)
```

Rebuild from scratch -- don't try to update in-place. Old analysis edges are stale after positions change.

### 5. Enrich graph node (new node in the pipeline)

A new node that runs after all analysis tools and before the routing decision:

```python
def enrich_graph_node(state):
    G = dict_to_graph(state["spatial_graph"])
    G = enrich_graph_from_analysis(G,
        state.get("collision_results"),
        state.get("visibility_results"),
        state.get("path_results"),
        state.get("reachability_results"),
        state.get("orientation_results"))
    text = serialize_for_llm(G)

    updates = {
        "spatial_graph": graph_to_dict(G),
        "spatial_graph_text": text,
    }

    # If violations found + objects were placed, inject correction message
    if has_findings and state.get("last_placement_result"):
        updates["messages"] = [{"role": "user", "content": correction_msg}]

    return updates
```

**Wiring**: This node must run BEFORE the routing decision, not after it. The router reads the enriched graph to decide whether to loop back.

```
analysis_tools -> enrich_graph -> router -> [reason | scoring]
```

---

## Pipeline Wiring

```
START -> profile_agent -> space_type_agent -> reason
                                                |
                                   +------------+------------+
                                   v            v            v
                              add_objects    run_tool     finish
                                   |            |            |
                                   v            v            v
                              analysis_fan_out (no-op)   (same)
                                   |
                          +--------+--------+
                          v        v        v
                      collision visibility orientation    <-- Group 1 (parallel)
                          |        |        |
                          +--------+--------+
                                   v
                             group1_join
                                   |
                          hard violations? -> reason + correction (max 3)
                                   |
                                   v
                                 path                     <-- Group 2 (sequential)
                                   v
                             reachability
                                   v
                             enrich_graph  <-- ENRICHMENT HAPPENS HERE
                                   |
                          violations? -> reason + correction (max 3)
                                   |
                                   v
                               scoring -> user_checkpoint -> [approve | continue]
```

### Key wiring decisions:

1. **enrich_graph before router**: The router reads enriched data to decide adjust vs continue
2. **Rebuild after placement, enrich after analysis**: Two different operations on the same graph
3. **Max 3 adjustment loops**: Prevents infinite correction cycles for structural violations the agent can't fix (e.g., walls too close)
4. **Only loop if objects were placed**: Analysis-only runs (no furniture placed) skip correction even if violations exist -- there's nothing to adjust
5. **Correction message as user message**: Injected into conversation history so the LLM sees it as natural context, not as a system override

---

## LLM Serialization Format

The `serialize_for_llm()` function produces text like:

```
SPATIAL GRAPH (12 nodes, 18 edges)

ROOMS:
  room-1 "Workshop" area=140m2
  room-2 "Office" area=35m2
CONNECTIVITY:
  Workshop <--door-1(0.95m)--> Office
FURNITURE in Workshop:
  furn-1 "cnc_machine" at(5.0,3.0) clearance=OK reachable=YES
  furn-2 "workbench" at(8.0,4.0) clearance=FAIL(-0.3m)
RELATIONS:
  cnc_machine --near(1.2m)--> workbench
  cnc_machine --sightline(visible)--> workbench
  storage_rack --blocks--> cnc_machine
ISSUES:
  workbench: move [+0.5,+0.0] 0.4m to fix clearance (has 0.6m, needs 0.9m)
  furn-4: unreachable (height)
```

- Capped at 50 lines to stay within LLM context limits
- ISSUES section only lists problems (not OK items)
- Clearance shows actual vs required values, not just deficit
- Move vectors give direction and distance

---

## Data Lifecycle

```
spatial_graph.py (pure module, no side effects)
    |
    |-- build_graph_from_layout()    <- called at startup + after each placement
    |-- enrich_graph_from_analysis() <- called once per analysis cycle
    |-- serialize_for_llm()          <- called after build and after enrich
    |-- graph_to_dict() / dict_to_graph()  <- state transport
```

The graph lives **only in RAM** as part of the LangGraph state dict. It is never persisted to disk. When the agent session ends, the graph disappears. The layout JSON (which IS persisted) is the source of truth -- the graph can always be rebuilt from it.

### What is ephemeral vs persistent:

| Data | Storage | Lifetime |
|------|---------|----------|
| `spatial_graph` (dict) | LangGraph state (RAM) | Current agent run |
| `spatial_graph_text` (str) | LangGraph state (RAM) | Current agent run |
| `layout_json_string` | LangGraph state + `session_active.json` | Persisted across restarts |
| Analysis results | LangGraph state (RAM) | Current agent run |
| Final layout | `output/{name}_{timestamp}_final.json` | Permanent |

---

## How to Apply This to Another Project

### Prerequisites
- `pip install networkx` (matplotlib optional, only for visualization)
- A layout JSON with rooms, doors, furniture, mep layers
- A LangGraph (or similar) pipeline with analysis tools that return structured results
- An LLM reasoning node that accepts injected context

### Minimal steps (3 files):

1. **Copy `spatial_graph.py`** into your python directory. Adjust node types and edge types if your domain differs (the functions are generic).

2. **Add 2 state fields** to your AgentState: `spatial_graph` (dict) and `spatial_graph_text` (str).

3. **Add 3 integration calls**:
   - Startup: `build_graph_from_layout()` -> state
   - After placement: `build_graph_from_layout()` -> state (rebuild)
   - After analysis: `enrich_graph_from_analysis()` -> state (enrich)

4. **Inject `spatial_graph_text`** into your LLM's context.

5. **(Optional) Add auto-correction**: Build a correction message from ISSUES and inject it when the router loops back.

### What you should NOT need to change:
- Analysis tool nodes (collision, visibility, etc.) -- they don't know about the graph
- Scoring node -- it reads analysis results, not the graph
- MCP/tool execution -- completely independent
- Session management -- the graph is ephemeral

### What you WILL need to adapt:
- `enrich_graph_from_analysis()`: The field names it reads from tool results must match your tool output schema. If your collision tool returns `{violations: [{object_id, gap_m}]}` instead of `{objects: [{id, clearance_violation: {deficit_m}}]}`, update the parsing.
- `serialize_for_llm()`: Adjust the text format if your LLM responds better to different structures (e.g., JSON instead of text, or more/fewer sections).
- `NEAR_THRESHOLD_M`: The 3.0m threshold for "near" edges. Adjust for your domain (industrial spaces may need 5m+).

---

## Dependencies

```
networkx          # graph data structure (required)
matplotlib        # visualization only (optional, for test_spatial_graph.py)
```

NetworkX is the only runtime dependency. The graph module has zero coupling to LangGraph, MCP, or any LLM library -- it's pure data transformation: `dict in -> nx.MultiGraph -> dict/str out`.
