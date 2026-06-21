# Week 08 — Image Output Phase 0: the edit-legible plan

**Status:** implemented & verified (browser) · **Date:** 2026-06-05 · **Layer:** frontend only (deterministic, no AI)

Phase 0 of the image-output feature. Directly addresses faculty feedback that **layout edits
weren't visible**, and turns the `SensePlan` floor plan into a real, exportable image artifact.
(Phases 1–2 — generative per-room renders + before/after — come next; see
[image-generation-research.md](image-generation-research.md).)

## What shipped

> **Design note:** a first cut used wall-to-wall hatch fills + a boxed callout. That was too heavy /
> CAD-like and fought Sensi's subtle, glowing, data-poetic language (a `/design-critique` confirmed it).
> Replaced with **floating material orbs** in the galaxy idiom.

1. **Material legibility — floating orbs.** A new **`material`** canvas lens renders one small soft
   3D orb (a radial-gradient sphere) per room, coloured by `attributes.floorMaterial`, with a faint
   halo + a faint mono label. No floor fills — the plan stays clean; comfort rings stay the heroes.
2. **Change = ripple + sense satellite.** When the latest `layout_diff` changed a room's material, its
   orb updates to the new material and emits a slow **ripple**, with an **affected-sense satellite**
   (coloured dot) orbiting it. Full *old → new · affects <sense>* detail shows on **hover** via the
   existing plan tooltip — no boxed callout.
3. **PNG export** — a visible **⤓ png** pill in the canvas control rail rasterizes the live plan
   (computed styles inlined so external CSS/CSS-vars survive) and downloads `Layout-XXX-plan.png`.

## Components

- New: `web/src/lib/materials.jsx` (palette + per-material radial-gradient `MaterialDefs` + helpers),
  `web/src/canvas/MaterialLayer.jsx` (the orbs + ripple + satellite).
- `web/src/canvas/SensePlan.jsx` is now `forwardRef`, exposing `exportPng()` so the control-rail pill
  can trigger export; renders `<MaterialDefs/>` + `<MaterialLayer/>`, and a `material` tooltip kind.
- `RoomsLayer.jsx` reverted to clean (orbs own material + change now).

Also: `web/src/lib/svgToPng.js` (export util), `LayoutModeScreen.jsx` (export pill + planRef, passes
`layout_diff`), `LayerToggles.jsx` (material pill). Backend untouched — `layout_diff` was already in the
turn payload.

## Verified (live, Google Gemini backend)

- Loaded layout 201 → 6 rooms; material lens shows 6 orbs, each a material sphere
  (wood/ceramic/carpet) with a faint label.
- "change the living room floor to concrete" → living-room orb becomes **concrete**, emits a ripple +
  an orbiting tactile satellite; chat reports the real tactile delta (0.58 → 0.48).
- Export pill rasterizes the live plan to a valid PNG in-browser.

## Note for Phase 2

The edit turn already reports a real before/after delta in chat (tactile 0.58 → 0.48). That delta isn't
yet structured in `layout_diff`, but surfacing it would let the orb's satellite show a ↑/↓ direction — a
cheap upgrade when we build the before/after comparison.
