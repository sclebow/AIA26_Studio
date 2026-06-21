# Deck asset library (self-contained)

Everything the deck (`../index.html`) loads lives here, so the `deck/` folder is portable —
open `index.html` directly (file://) or serve any parent folder; all paths are relative.

## Contents
- `logo.svg` — the Sensi six-sense ring mark (from `web/src/components/SensiAvatar.jsx`).
- `bench-old-living.png` / `bench-new-living.png` — real benchmark renders (old Gemini 2.5
  vs new 3.x) shown on slide 13. Copied from `../../benchmark/`.
- `clips/` — the 3 demo videos: `onboard.mp4`, `shape.mp4`, `report.mp4`. Drop them here;
  until present, each clip page shows a placeholder. See `clips/HOWTO.md`.
- `shots/` — the before/after stills the deck embeds on slide 11: `report-before.png`
  + `report-after.png`. See `shots/HOWTO.md`. (The close + Grounded use authored SVG; no photo needed.)

## Brand tokens (from the app)
canvas `#0D0D0D` · text `#F0EDE8` · muted `#9a978f` · thermal `#E8836A` △ · visual `#D4B96A` ○ ·
acoustic `#9B8FD4` ∿ · spatial `#6AB8C8` □ · olfactory `#8BB88A` ≈ · tactile `#C4A882` ∶ ·
pass `#3FB97A` · warn `#E0A92E` · fail `#E0524A`. Type: Inter · JetBrains Mono · Caveat.

The deck's other visuals (the 3-zone diagram, the weights/veto bars, the ripple diagram) are
authored inline as SVG in `index.html`, mirroring the app's `SenseSignature` / `SenseGraph`.
