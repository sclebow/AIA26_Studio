# Sensi — The Relationships Graph: Audit & Vision

> The graph is not a layer. It is the **relationship instrument**: what talks to
> what, how, and why — between senses, and between rooms — research-driven,
> data-driven, and personalized to *this layout · this persona · this analysis*.
> This document audits what the model already knows, what the UI currently shows,
> and how to close the gap. On the plan. Interactive. Layered by complexity.

Sources audited: `python/comfort/sense_model.py` (canonical model),
`docs/comfort-model-references.md` (research provenance),
`nodes/insights/topologic_analysis.py`, and the current surfaces
(`SenseGraph`, `canvas/TopologyLayer`, `canvas/FlowLayer`, `FocusCard`).

---

## 1. The relationship substrate — what actually exists in the model

There are **seven** distinct relationship families already encoded. Most are barely shown.

| # | Relationship | What it answers | Scope | Source | Surfaced today? |
|---|---|---|---|---|---|
| 1 | **Sense ↔ Sense couplings** (`SENSE_SENSE`, 7 edges) | what sense affects what, sign (+/−/±/0), direction, **why** (mechanism), confidence (tier) | universal model; *activates* per room when the source sense < 0.50 | Run A (verified) + physics (inferred) | ⚠️ SenseGraph drawer — **universal only**, hidden |
| 2 | **Lever → Sense couplings** (`LEVER_SENSE`, 15 edges) | what an **edit** moves (glazing→visual/thermal/acoustic, ventilation→olfactory/acoustic, material→tactile/acoustic/thermal, adjacency→acoustic/olfactory, plants→…) — the actionable "how to fix" | universal causal | Run A + physics | ❌ **nowhere** |
| 3 | **Cross-modal adjustments** (`apply_cross_modal` → `adjustments[]`) | the **realized** sense→sense effects *for this room, this persona*: `{sense, delta, from, mechanism, tier, basis}` | per room per analysis | derived | ⚠️ tiny provenance icons in FocusCard rows |
| 4 | **Room ↔ Room transmission** (`TRANSMISSIVE` across doors) | which room's acoustic/olfactory/thermal bleeds into which | per layout + scores | S5/S6 | ✅ Flow lens + topology edges |
| 5 | **Room topology / structure** (NetworkX) | hubs, **bridges**, isolated, **connected components / zones**, **betweenness** | per layout | R1 + graph theory | ⚠️ degree/bridge/isolated only; **betweenness & zones unused** |
| 6 | **Personality / arousal** (`apply_personality`) | how introvert/extrovert reshapes which senses matter (acoustic/visual/spatial) | per persona | R5 | ❌ only as an adjustment `basis` |
| 7 | **Personalization** (`threshold_from_weight`, `priority_order`, weighted veto) | what counts as a **good vs bad** relation *for this person* | per persona | S4/R1 | ⚠️ thresholds in FocusCard |

**Headline:** the model is rich and **research-grounded** (two adversarial fact-check
runs; every edge tagged verified/inferred with a mechanism). The UI expresses
roughly **10–15%** of it. We do **not** need more research — we need to *express the
research that's already encoded.* The two crown jewels currently hidden are the
**realized per-room/per-persona adjustments (#3)** and the **actionable lever layer (#2)**.

---

## 2. Critique of the current graph surfaces

**SenseGraph (drawer)** — 6 senses in a ring, node size = rooms failing, edges
solid/dashed by tier, click-to-solo. *Good:* shows tier confidence honestly.
*Missing:* it's the **universal** model, disconnected from the room you're reading;
no mechanism ("why"), no magnitude, no levers, no animation, hidden in a drawer.

**TopologyLayer / FlowLayer (on plan)** — adjacency + directional bleed. *Good:*
on the real geometry; conflict-colored. *Missing:* betweenness, zones/components,
**sensory-zoning quality** (is a noisy room badly placed next to a bedroom?),
good-vs-bad framing, node interactivity.

**FocusCard** — shows realized `adjustments` as base→effective deltas with
provenance icons. *This is the richest relationship view in the app* — but it's a
**list**, not a graph, and only for one room.

### The seven gaps (expert lens)
1. **Three disconnected graphs** (sense drawer vs room graphs) — no unified model; the sense graph never reflects the room you're inspecting.
2. **The lever layer is invisible** — the "how do I fix this relation" data (#2) is shown nowhere. Biggest missed opportunity for *actionable*.
3. **Universal, not realized** — we show the textbook model, not "in *this* kitchen, acoustic is dragging thermal down −0.05 (research)." The personalized instance is the powerful story.
4. **No "why"** — mechanisms + tiers are in the data, almost never surfaced.
5. **No good/bad valence** — relations aren't consistently coded helpful(+)/harmful(−)/trade-off(±). You explicitly want this.
6. **No interactivity/animation** — hovering a sense or room should *light up its relationships* (animated marching dashes = the app's existing provenance line language).
7. **No complexity control** — it's all-or-nothing; no way to go from "the essentials" to "everything."
8. **Sensory zoning (R1) unbuilt** — the research literally prescribes arranging/buffering rooms by stimulation; we don't show zones or buffering quality.

---

## 3. The vision — one Relationships instrument, on the plan

**One system, two planes, one visual language, adjustable depth.**

### Two planes (both anchored on the floor plan)
- **Room plane** — nodes = rooms (at centroids). Edges = transmission (directional
  acoustic/olfactory/thermal bleed) + structural adjacency. Answers *which room
  affects which*, good (buffered) vs bad (bleeding). Carries zoning + betweenness.
- **Sense plane** — nodes = the 6 senses (a compact constellation, **anchored to the
  focused room**). Edges = the couplings **active in this context** — i.e. the
  realized `adjustments` for that room (universal model when nothing is focused).
  Answers *what sense talks to what, how, why, on what basis*.
- **They connect:** selecting a room populates the sense plane with that room's
  realized relationships; hovering a sense highlights the rooms where it's a driver.

### One visual grammar (consistent everywhere)
- **Valence** (sign): + helps · − harms · ± trade-off · 0 none — encoded by
  **arrowhead + a +/−/± glyph + a restrained tint**, *not* a full green/red fill
  (senses already own hues — see Open Question).
- **Provenance** (tier/basis): research = solid · physics = dashed · personality =
  dotted (the app's existing line language).
- **Magnitude**: edge weight = the adjustment delta.
- **Activity**: **animated marching dashes on hover** — your idea — show influence flowing.

### Interactivity (progressive disclosure)
- Hover a node → its edges animate + a tooltip gives the **mechanism** ("noise
  degrades visual comfort — verified").
- Click → focus the room / solo the sense.
- Expand → a "relationship reading" panel narrating the room's story.

### Complexity tiers (the customization you asked for)
- **L1 · Essentials** — verified sense couplings + transmission only (high-confidence story).
- **L2 · Full model** — + inferred/physics couplings + the lever layer.
- **L3 · Deep** — + personality, + betweenness/zoning, + magnitudes & mechanisms.
Default L1–L2; "a work of art full of data" on demand, not overwhelming by default.

### Two bridges that make it matter
- **Sensory zoning** (R1): color rooms by stimulation zone; flag bad buffering (noisy
  kitchen against a bedroom) as a *bad relation*, good buffering as good.
- **Lever bridge** (#2): a bad relation surfaces the **lever that fixes it**, one click
  from the what-if edit — connecting the relationship graph to action.

---

## 4. Honesty to encode (don't over-claim)
- **spatial & tactile** rest on physics, not multi-domain studies → always render their
  edges as inferred (dashed), lower emphasis.
- **personality axis isn't captured in onboarding yet** (defaults to 0) → the
  personality plane is dormant until that's added; show it as such, don't fake it.
- magnitudes are **direction-of-effect**, not precise (research caveat) → present
  relative weight, avoid implying false precision.

---

## 5. Proposed build sequence (the lift)
1. **Realized sense-relationship graph for the focused room** — the personalized
   instance (#3), tied to room selection; mechanism + valence + provenance + animation.
2. **Room-plane upgrade** — directional transmission, sensory zoning + buffering
   quality, betweenness, good/bad coding.
3. **Interactivity + animation** — hover marching-dash highlight, why-tooltips, expand-to-read.
4. **Complexity tiers + lever bridge** — the depth control and the path to action.

---

## 5b. Inspiration synthesis → refined direction (the "galaxy")

Reference images the user likes: a dark-field **galaxy network** (glowing arced
edges, color-coded clusters, sized nodes, labeled hubs, dotted grid); a clustered
force graph; radial **dandelion** hub-spokes; a labeled hierarchical sitemap; and a
**world-map with glowing connection arcs**. Translated to our domain:

- **The dream is 2D, not 3D.** The galaxy look is a flat composition with depth-by-
  glow + zoom/pan. We get the "map you move around" feel **without Three.js** (which
  we deleted) and without losing the precise legibility relationship-reading needs.
  Literal 3D stays a far-future maybe.
- **Two projections of ONE graph:**
  - **Plan view** (analysis, default): rooms on the real geometry, with **arced,
    glowing relationship edges** (transmission + which-room-affects-which) and a
    per-room **sense hub** (dandelion) on focus. = world-map-arcs + dandelion.
  - **Galaxy view** (Explore, a toggle): the *same* relationship data as an abstract
    dark-field, force-clustered map — senses + rooms + levers as nodes, **clustered
    by sensory zone**, arced glowing edges, labeled hubs, zoom/pan. = galaxy + clusters.
- **Clusters are meaningful:** the galaxy's colored clusters = our **sensory zones /
  connected components** (already computed), not decoration.
- **Small but rich (honesty):** our graph is ~6 senses + ~8 rooms + ~15 levers, not
  500 nodes. Don't fake a hairball. Make ~30–40 nodes **dense with meaning**
  (mechanism · valence · provenance · magnitude) and **beautiful** (arcs, soft glow,
  edge-bundling). "Work of art full of data" = meaning-per-element × aesthetic, not count.
- **Edge aesthetic (shared by both views):** quadratic Bézier **arcs** + soft glow
  (layered strokes / blur), **marching dashes on hover** — this one change makes both
  views feel like the inspo (and fixes the earlier "flow too minimal").
- **Tech:** SVG is fine at our node count, even with subtle glow. If the galaxy ever
  wants hundreds of particles/bloom, move *that view* to canvas/WebGL — not the plan.

### Refined build sequence
1. **Plan view, lifted** — arced glowing relationship edges + per-room sense hub
   (anchored), valence glyph/arrow/tint, provenance line-style, mechanism-on-hover,
   marching animation. *(decision-stable; reuses current canvas)*
2. **Galaxy Explore view** — toggle into the abstract zone-clustered map of the full
   relationship graph (senses + rooms + levers), dark field, arcs, glow, labels.
3. **Zoom/pan + complexity dial + lever bridge + polish.**

## 6. Open questions (need a decision before the lift)
- **Valence vs hue clash:** senses own hues; if edges also use green/red for good/bad
  they compete. Recommend valence = arrowhead + +/−/± glyph + subtle tint; hue stays
  node identity. Agree?
- **Sense plane placement:** anchored beside the focused room, or a floating constellation in a corner?
- **Default complexity tier** for a first-time user: L1 or L2?
