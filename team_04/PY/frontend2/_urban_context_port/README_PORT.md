# Urban Context Analysis — port package

These files are the **reference implementation** of the Urban Context Analysis
feature, built in the sibling project `AIA26_Studio - app version 1.2`
(`team_04/PY/frontend2`). Goal: bring this feature into **this** project's
`frontend2` ("app 1.0" / new version).

> ⚠️ This project's `frontend2` has **diverged** from the 1.2 version. It already
> has a `CONTEXT` stage and a `views/contextView.js`, plus extra features the 1.2
> build doesn't have (DECISION stage, `decisionGraphView.js`, `optimizeView.js`,
> `shapesView.js`, `agentClient.js`, `core/workflow.js`, `core/config.js`,
> `core/decisions.js`). So this is a **reconciliation**, not a clean copy. Do NOT
> overwrite this project's shared files (stages.js, store.js, explorer.js,
> center.js, copilotClient.js, boot.js, mapView.js, index.html) — adapt the
> wiring into the versions that are already here.

## Files in this folder

| File | What it is | How to use |
|------|------------|------------|
| `overpass.js` | **Self-contained core.** Overpass API fetch (2 km), layer classification (roads by hierarchy + all amenities), equirectangular projection, per-edge distance/"edge intelligence", the 10 context scores, the AI report generator, and a procedural fallback when Overpass is offline. Framework-agnostic. | Copy to `core/overpass.js` (or merge if one exists). Almost no changes needed. |
| `contextController.js` | Orchestrates the stage: triggers on boundary-confirm, runs `analyzeContext`, writes results to the store, posts the AI report into chat, asks the follow-up question, exposes `contextPayload()` for context-aware shape gen. Imports `store.js`, `stages.js`, `overpass.js`. | Copy to `core/contextController.js`, then fix imports/store calls to match THIS project's store + stage names. |
| `contextView.reference.js` | The Three.js digital-twin center view + HTML overlay (KPI cards, AI report, edge-hover HUD, road legend, loading shimmer). **This project already has its own `views/contextView.js`** — compare and merge; don't blindly replace. | Diff against the existing `views/contextView.js` and merge the missing capabilities. |
| `context.css` | Styles for KPI cards, report, edge HUD, legend, loading shimmer, Context Explorer tree leaves. | Copy to `styles/context.css` and link it from `index.html`. |
| `INTEGRATION_DIFFS.txt` | Unified diffs (this project's current shared files → the 1.2 files with the feature). Shows the exact wiring deltas to replicate. | Read it to see what each shared file needs. |

## The feature, end to end

1. New stage **Urban Context Analysis**, between BOUNDARY and SHAPES.
2. On boundary confirm → auto-run: fetch 2 km OSM context from the public
   Overpass API **in the browser** (3 mirror endpoints, with a synthetic
   fallback if all fail).
3. Classify into **Roads** (Primary/Secondary/Tertiary/Local, distinct colors)
   and amenities: Schools, Universities, Hospitals, Grocery, Shopping, Parks,
   Bus Stops, Metro, Train, Restaurants, Public Facilities.
4. **Context Explorer** tree in the left panel (Roads / Education /
   Transportation / Retail groups + Parks + Healthcare leaves); each layer has a
   **visibility toggle, count, and nearest-distance**.
5. **3D digital twin** center view: extruded OSM buildings, roads, parks,
   amenity pins, highlighted site with labelled edges + vertices, 2 km radius
   ring.
6. **Site Edge Intelligence**: hovering near a site edge shows nearest
   metro/park/road/school/etc. for that edge.
7. **AI Context Report** in chat + **10 scores** (Transit, Walkability,
   Education, Green Space, Retail, Healthcare, Accessibility, Connectivity,
   Amenity, Urban Vitality), 0–100, color-coded **KPI cards**.
8. After analysis the assistant asks: *"I've analyzed the surrounding urban
   context. Based on the site's accessibility, amenities, transportation
   network, and context scores, what type of building would you like me to
   generate?"*
9. `contextController.contextPayload()` returns scores + edge intelligence so
   shape generation / optimization can be context-aware.

## Suggested order of work

1. Read THIS project's `core/stages.js`, `core/store.js`, `panels/explorer.js`,
   `panels/center.js`, `views/contextView.js`, `copilotClient.js`, `boot.js`,
   `views/mapView.js` to understand what context support already exists here.
2. Drop in `overpass.js` (the engine). Wire `contextController.js` to this
   project's store/stage API.
3. Merge `contextView.reference.js` into the existing `views/contextView.js`.
4. Add the Context Explorer tree to `panels/explorer.js`; link `context.css`.
5. Trigger `runContextAnalysis()` when the boundary is confirmed (store watcher
   or the boundary-saved handler), and carry `contextPayload()` into copilot
   requests.
6. Test: confirm a boundary → context auto-loads → explorer populates → 3D twin
   renders → scores + report appear → follow-up question is asked.
