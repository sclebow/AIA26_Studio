# Decision Graph — Frontend Payload Contract

This is the **living contract** between the Team 04 backend (`backend/decision_graph.py`,
`backend/routers/chat.py`, `backend/routers/decisions.py`) and the React Flow decision-graph UI.
Each backend phase that adds a node type adds its row here in the **same commit** (see
`../README.md` for the lockstep rule).

Source of truth on the backend:
- Node shape — `DecisionNodeSchema` in `backend/schemas.py`.
- Node constructors — `make_intent_node`, `make_brief_node`, `make_action_node`,
  `make_branch_nodes`, `make_state_node` in `backend/decision_graph.py`.
- Streaming — the `decision` SSE event in `backend/routers/chat.py`.

---

## 1. Transport

### 1a. Full graph — `GET /sessions/{id}/decisions`

Returns the whole DAG, ready for React Flow with **no transformation** of edges:

```jsonc
{
  "nodes": [ DecisionNode, ... ],   // full nodes (incl. payload + timestamp)
  "edges": [ { "id": "<parent>-<child>", "source": "<parent_id>", "target": "<child_id>" } ],
  "head":  "<node_id>"              // current active leaf
}
```

### 1b. Live stream — `POST /sessions/{id}/chat` (SSE)

The `decision` event fires once per node as the agent runs. Its data is the **compact**
node (no `payload`/`timestamp` — fetch the full node from `/decisions` if the card needs
the payload, or keep a client-side cache keyed by `node_id`):

```jsonc
// event: decision
{ "node_id": "...", "type": "brief", "label": "...", "parent_id": "...", "is_selected": true }
```

Emission order per user turn: `intent → brief → [clarify] → action(s) → branch → … → state`.
The `brief` event arrives **right after `intent`, before the first `action`** — it is the
agent's comprehension step (`extract_brief` graph node). A `clarify` event may follow the brief
when the agent pauses to ask the user back (see §7); when it does, no actions run that turn.

The chat stream also emits a non-node `clarify` SSE event carrying the raw `ClarificationRequest`
(so the UI can pop the form without re-fetching): `event: clarify, data: <ClarificationRequest>`.

---

## 2. `DecisionNode` (full, from `/decisions`)

| field         | type                    | notes |
|---------------|-------------------------|-------|
| `node_id`     | `string` (uuid)         | React Flow node `id` |
| `parent_id`   | `string \| null`        | edge source; `null` only for the root |
| `type`        | `DecisionNodeType`      | `intent \| brief \| action \| branch \| select \| state` |
| `label`       | `string`                | ≤120 chars, human-readable |
| `timestamp`   | `string` (ISO-8601 UTC) | node creation time |
| `is_selected` | `boolean`               | on the active path; branch children start `false` |
| `payload`     | `object`                | type-specific — see below |

`type` is an **open string** on the wire (`DecisionNodeSchema.type: str`). The UI maps known
types to components and falls back to a generic node for anything unknown, so a new backend
phase never breaks an older frontend build.

---

## 3. Per-type `payload`

### `intent`
```ts
{ user_message: string }
```

### `brief`  — Phase 0 (BACKEND_PLAN §0)
The typed `DesignBrief` the agent comprehended from the prompt. This is the payload the
`BriefNode` renders.
```ts
{
  design_brief: {
    building_count: number,
    buildings: Array<{
      shape_preference: "I"|"L"|"T"|"U"|"H"|"Y"|"X"|"O"|"auto",
      footprint_area_sqm: number | null,
      storeys: number | null,
      use: string,                 // "residential" | "office" | "mixed" | ...
      intent_text: string
    }>,
    courtyard_requested: boolean,
    courtyard_qualities: string[], // e.g. ["quiet","sunny"]
    parking_requested: boolean,
    requested_rotation_deg: number | null,
    view_weight: number,           // 0..1
    sun_weight: number,            // 0..1
    alignment_weight: number,      // 0..1
    ambiguities: string[],         // things the agent could NOT infer (LLM path only)
    source: "llm" | "fallback"     // "fallback" = deterministic regex, no LLM
  }
}
```
Label format: `Brief: {count}x [{shape + shape + …}] ({source})`.

> **No-invention guarantee.** Vague prompts yield `shape_preference: "auto"` and
> `footprint_area_sqm: null` rather than fabricated values; genuinely unclear requests are
> listed in `ambiguities` (LLM path). The UI should render `auto`/`null` as "let the agent
> decide", not as an error, and surface `ambiguities` as a soft warning.

### `clarify`  — interactive clarification (BACKEND_PLAN §0, ask-back loop)
The agent paused to ask the user back. Payload holds the structured question the
`ClarifyPanel` renders as chips.
```ts
{
  clarification_request: {
    summary: string,
    fields: Array<{
      key: "shape"|"side"|"view_side"|"size"|"use"|"count",
      question: string,
      options: string[],      // suggested chips
      multi: boolean,         // multi- vs single-select
      allow_custom: boolean,  // free-text allowed
      critical: boolean       // placement-critical gap (vs nice-to-have)
    }>
  }
}
```

### `action`
```ts
{ tool_name: string, input_preview: string }   // input_preview ≤200 chars
```

### `branch`  — one child `state` node per Pareto option
```ts
{ option_count: number }
```

### `state`  (Pareto option child OR placed building)
```ts
// Pareto option child:
{ option_id: string, combined_score: number, boundary: number[][] | null,
  rotation_degrees: number | null, centroid_xy: [number, number] | null }
// Placed building:
{ building_count: number, building_snapshots: Array<{ label, boundary, area_sqm }> }
```

### `select`  (user picked an option in the explorer)
```ts
{ selected_option_id: string, reason?: string, backtrack?: boolean }
```

---

## 3b. Answering a clarification (§7 in full)

```
GET  /sessions/{id}/clarification   → { clarification_request: ClarificationRequest | null }
POST /sessions/{id}/clarify   { "answers": { "shape": "L", "side": "south",
                                              "view_side": ["south"], "size": "~900 m²",
                                              "use": "office", "count": "1" } }
→ { resolved: true, shapes, requested_positions, view_target_sides, next }
```
After POSTing answers, send a normal `/chat` turn to resume — the agent now has the answered
shape/side/view/size/use/count and will not re-ask. `ClarifyPanel` collects the answers; the
caller wires `onSubmit → api.submitClarification(id, answers) → api.chat(...)`.

## 4. Selecting a Pareto option

```
POST /sessions/{id}/decisions/{node_id}/select   { "reason": "..." }
→ { select_node, graph_head }     // re-fetch /decisions and re-render
```

---

## 5. Adding a node type in a later phase (checklist)

1. Backend: add a `make_<type>_node` constructor + emit it in `chat.py`; add the row to §3 here.
2. Frontend: add `<Type>Node.tsx`, register it in `nodeTypes.ts`, extend `types.ts`.
3. Same commit: tick the phase row in `PROGRESS.md` and update `ARCHITECTURE.md`.

Phase status: **`brief` shipped (Phase 0); sun overlay shipped (Phase 1, see §7).**
`intent/action/branch/select/state` predate Phase 0. Future overlays (roads, grid, parking,
circulation — Phases 2-5) attach to the **site/explorer** or **/tools** payloads, not the
decision graph, and get their own §7 sub-section.

---

## 6. Explorer & geometry payloads (`SiteCanvas` / `ExplorerPanel`)

These are the "what the agent has" payloads. Full TS types live in `../api/types.ts`; backend
source is `backend/schemas.py` + `backend/routers/explorer.py`.

`GET /sessions/{id}/explorer` → `ExplorerTree`:
```ts
{ session_id, site: SiteInfo | null, buildings: BuildingInfo[] }
SiteInfo     = { boundary, area_sqm, buildable_boundary, buildable_area_sqm, edge_count, site_context }
BuildingInfo = { building_id, label, building_type /* I|L|T|U|H|Y|X|O|null */, area_sqm,
                 boundary, centroid, height_m, wings: WingInfo[],
                 placement_options: PlacementOption[], view_score }
WingInfo     = { wing_index, role, area_sqm, centroid }       // per-wing massing (Phase 7 fills height)
```

`GET /sessions/{id}/buildings/{b}/options` → `PlacementOption[]` (the Pareto front from view analysis):
```ts
{ option_id, rank, combined_score, unblocked_view_score, attractor_view_score,
  rotation_degrees, centroid_xy, boundary, outside_area_sqm, fits_within_site }
```
`SiteCanvas` draws each option's `boundary` as a ghost; the selected one is highlighted.
`fits_within_site=false` options are flagged (red) in `ExplorerPanel`.

`GET /sessions/{id}/buildings/{b}/view` → `ViewAnalysisResult`
`{ view_score_3d, total_unblocked_rays, total_rays, n_floors, per_floor[] }` (on-demand 3D score).

> Coordinates are world metres `[x, y]` (z sometimes present and ignored in 2D). `SiteCanvas`
> auto-fits a north-up plan and colours buildings by `building_type` via `site/geometry.ts`.

---

## 7. Sun analysis overlay — Phase 1 (BACKEND_PLAN §1)

Sun analysis attaches to the **direct-tool** endpoints (`POST /tools/{name}`) rather than the
decision graph, so the UI can run an analysis without a chat turn. Backend source is
`agent/tools/sun_analysis.py`; TS types live in `../api/types.ts`; `site/SunOverlay.tsx` renders
the result. The `Team04Api` client wraps each call (`sunVectors`, `sunExposure`, `worstSunSide`).

The sun is **one dominant diagonal vector** (team method): a single azimuth (compass bearing,
CW from North) + altitude. Lower exposure = better (the objective is to *avoid* the worst sun).

```
POST /tools/sun_vectors      { worst_case_preset?: "summer_west"|...,           // default mode
                               latitude?, date?, hours? }   // multi-hour mode (preset=null)
→ SunVector[]   = { azimuth, altitude, weight, hour? }

POST /tools/sun_exposure     { building_boundary: number[][], sun_vectors: SunVector[],
                               obstacles?: (number[][] | {boundary,height})[] }
→ SunExposureResult = { sun_exposure_score /* 0..1, LOWER better */, max_possible_per_point,
                        test_point_count, sun_vectors, worst_point,
                        per_test_point: [{ point, outward_normal, normalized_exposure, ... }] }

POST /tools/worst_sun_side   { site_model: SiteModel, sun_vectors: SunVector[] }
→ WorstSunSide = { available, worst_side, best_side, worst_compass_sector,
                   per_side: [{ edge_index, compass_sector, sun_exposure_score, midpoint, ... }] }

POST /tools/sun_exposure_3d  { building_boundary, building_height, sun_vectors,
                               obstacles_with_heights: [{boundary, height}] }   // OTHER buildings + obstacles
→ { sun_exposure_score_3d /* 0..1, LOWER better */, n_floors,
    per_floor: [{ floor_number, z_level, sun_exposure_score }],
    cells: [{ ...facade cell, sun_exposure }] }   // real per-floor mutual shading; cells drive the 3D heatmap
```

The 3D path mirrors the view tools (`view_analysis` 2D ↔ `view_3d`): an obstacle of height `h`
only shades a facade cell at height `z` when `h > z`, so a tall building shades just the lower
floors of a shorter neighbour. The notebook renders it with `visualize_sun_3d` (plotly).

---

## 8. Site grid & side alignment overlay — Phase 3 (BACKEND_PLAN §3)

Like the sun overlay, grid alignment attaches to the **direct-tool** endpoints. Backend source is
`agent/tools/site_grid.py` + `view_optimizer.optimize_aligned_placement`; TS types in
`../api/types.ts`; `site/GridOverlay.tsx` renders it; `Team04Api` wraps it (`siteGrid`,
`alignedPlacement`). The key idea: buildings sit on a grid **parallel to a chosen side** — they
never rotate freely.

```
POST /tools/site_grid        { site_model: SiteModel, spacing?, alignment_side?, use_buildable_zone? }
→ SiteGrid = { available, origin, u_axis, v_axis, angle_deg, spacing,
               alignment_side_index, alignment_side_label,
               grid_nodes: number[][], grid_lines: [[x,y],[x,y]][], adjacent_sides, node_count }

POST /tools/aligned_placement { base_boundary, site_boundary, grid, use?,           // use drives objectives
                                sun_vectors?, sun_weight?, reference_line?, site_setbacks?,
                                other_buildings?, min_separation? }
→ AlignedPlacementResult = { optimized, use, objective_configs, candidate_count, feasible_count,
                             alignment_side_index, orientations: number[],
                             options: [{ option_id, rank, combined_score, alignment_score /* ~1 */,
                                         orientation_deg, centroid_xy, node_xy, boundary,
                                         boundary_proximity_score, ... }] }
```

`GridOverlay` draws the grid lines + nodes, the chosen side (frontage), and the ranked aligned
options (best solid). **Use-driven:** commercial/office/retail pick up a `boundary_proximity`
objective and hug the chosen frontage; residential leans on view + sun. Every option is grid-aligned
(`alignment_score ≈ 1`). `place_buildings_aligned` sequences several buildings, each clearing the
rest by `min_separation`.

`SunOverlay` draws: the sun arrow (light direction), each site side tinted/weighted by its
exposure with the worst side flagged `☀`, and the focused building's facade test points coloured
yellow (shaded) → red (hit). The same `sun_weight` (from the Phase 0 brief) that the UI shows is
what the optimizer uses for the `sun_avoidance` objective — the LLM only sets the weight.
