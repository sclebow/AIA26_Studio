# ADR-001: The Relationship Galaxy (3D explore mode)

**Status:** Accepted · **Date:** 2026-05-31 · **Deciders:** Emilie (product), Claude (impl)

## Context
The 2D on-plan graph is the *analysis* surface (precise, geometric). The user wants a
second, *experiential* mode — an immersive 3D "galaxy" you fly through and get lost in,
showing the **whole** relationship system at once. It must include all the data the model
holds (couplings, transmission, room→sense problems, lever→sense fixes, topology metrics,
mechanism/valence/provenance/magnitude), be fully interactive, and not bloat the app's
initial load. React 18 + Vite, dark dial aesthetic.

## Decision
Build it with **`3d-force-graph`** (Three.js WebGL force-directed graph) + `three-spritetext`
(labels) + `UnrealBloomPass` (glow), in a **lazy-loaded full-screen overlay**. Render one
multi-partite graph from a pure data builder (`lib/relationshipGraph.js`); the view
(`galaxy/RelationshipGalaxy.jsx`) only configures + interacts.

## Options considered
| Option | Complexity | Effort | Aesthetic | Verdict |
|---|---|---|---|---|
| **3d-force-graph** | Med | **Low** | matches inspo (bloom/particles built-in) | ✅ chosen |
| raw three.js / r3f | High | High | full control | rejected — reinvents force sim + camera + particles |
| 2.5D / stay 2D | Low | Low | no immersion | rejected — user explicitly wants 3D depth |

## Data model (one graph, all data)
**Nodes:** `sense:*` (6, hue+glyph, size = rooms failing) · `room:*` (size = degree, color =
zone, carries topology metrics) · `lever:*` (the actionable LEVER_SENSE levers).
**Links (4 types):**
- `coupling` sense↔sense (`SENSE_SENSE`) — universal; sign, tier, mechanism.
- `transmission` room→room (doors / `graph_data.edges`) — directional bleed, worst sense.
- `exhibits` room→sense — which rooms drive which sense problems (score < threshold).
- `lever` lever→sense (`LEVER_SENSE`) — how to fix.

## 3D encoding adaptations (the key design problem)
3D can't do dashed lines well, and hue is already "which sense," so:
| Channel | 2D | **3D galaxy** |
|---|---|---|
| identity | hue | node/link **hue** (sense) |
| magnitude | width | link **width** |
| direction/flow | arrow + march | **directional particles** + arrowhead |
| provenance | solid/dashed/dotted | link **opacity tier** (research 1.0 · physics 0.55 · personality 0.3) + legend |
| valence | glyph+tint | **arrowhead** + value in hover/click detail (kept out of the hue channel) |
| importance | size | node **size** + **bloom** picks out hubs |

## Interactivity
Orbit/zoom/pan (built-in) · hover node → highlight neighbours + HTML tooltip (metrics/
mechanism) · click node → camera flies to it + detail panel · directional particles animate
flow · **complexity dial L1/L2/L3** filters link types (L1 verified couplings + transmission;
L2 + inferred + levers + exhibits; L3 + personality + everything). Default **L3** ("the full life").

## Consequences
- **Easier:** a stunning, complete, navigable view of the model; reuses the relationship grammar.
- **Harder:** WebGL is heavier; mitigated by **lazy import** (three never enters the initial
  bundle). Provenance is less crisp in 3D (opacity, not line-style) — documented in-legend.
- **Revisit:** performance if the showpiece layout grows large (our graph is ~30–50 nodes — fine).

## Action items
1. [ ] `npm i three 3d-force-graph three-spritetext`
2. [ ] `lib/relationshipGraph.js` — pure builder → {nodes, links}
3. [ ] `galaxy/RelationshipGalaxy.jsx` — lazy full-screen view (config + bloom + interactions + L-dial)
4. [ ] Launch control in `LayoutModeScreen` (React.lazy + Suspense), gated on a scored turn
5. [ ] CSS: overlay, controls, tooltip, legend
