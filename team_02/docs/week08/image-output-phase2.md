# Week 08 — Image Output Phase 2: before/after + score deltas

**Status:** implemented & verified (browser, OpenAI) · **Date:** 2026-06-05

Phase 2 unifies the "generated image" and "multi-change scoring comparison" goals: after you edit a
room, its FocusCard shows **what the change did** — visually (a before/after wipe slider) and
numerically (per-sense deltas). Auto-triggers when the focused room was the most recent edit.

## How it works

1. **`POST /api/compare-room`** (`api/server.py`): reads the session's last edit (`layout_diff`:
   attribute, old→new). AFTER = current layout + current scores. BEFORE = clone the layout, revert the
   attribute to `old_value`, **re-score via the comfort tool** (`compute_comfort_scores`, the same call
   the agent uses). Generates AFTER, then BEFORE **anchored on the AFTER image** for same-room
   consistency. Returns `{ before_image, after_image, deltas:{sense:{before,after}}, attribute,
   old/new }`. Cached per (provider, layout, room, attribute, old, new).
2. **Reference anchoring works on both providers:** Gemini via inline reference part; **OpenAI via
   `images.edit`** (added to `imaging/client.py`).
3. **FocusCard** (`web/src/components/FocusCard.jsx` + `BeforeAfterSlider.jsx`): when the focused room
   was just edited (`turn.layout_diff.room_name === activeRoom`), it auto-calls compare and shows a
   **vertical wipe slider** (drag to reveal before↔after) + **delta chips** (per sense, ↑/↓, colored).
   Non-edited rooms still get the Phase 1 single "how it feels" render.

## Verified (live, OpenAI)

- analysed 201 → "change the living room floor to concrete" → focused Living Room → auto before/after
  slider rendered, deltas **acoustic 0.37→0.36 ↓, tactile 0.68→0.58 ↓** (matches the concrete edit).
  No new console errors.

## Notes

- **Latency:** two image generations (~40s on OpenAI; ~16s on Gemini). On-demand-per-edit + cached.
  Switch `IMAGE_PROVIDER="google"` for noticeably faster, cheaper, and more consistent before/after.
- **Consistency caveat:** OpenAI `images.edit` anchoring is decent but not pixel-perfect; Gemini is
  better for "same room, one change" (per docs/week08/image-generation-research.md).
- Reverting handles attribute-on-`room.attributes` edits (floorMaterial, glazingRatio) directly;
  wall/furniture-material edits revert best-effort.

## Possible next

- Multi-change compare (apply several edits at once, compare cumulative deltas) — the original
  "multiple changes to see more scoring differences" idea; would extend the graph/preview path.
- Re-render control + a "keep this change / revert" action wired to the slider.
