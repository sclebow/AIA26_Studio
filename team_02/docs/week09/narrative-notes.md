# Week 09 — Narrative notes

Plain bullets capturing what changed and why it matters to the story. The final
a-to-z deck assembles from these.

## Session 1 — Agentic loop audit & streaming

- **The agent now thinks out loud.** Before, a turn ran the whole LangGraph pipeline
  silently and dumped one block of text after 10-20s — the UI was frozen the entire
  time. We added a streaming endpoint (`/api/message/stream`, SSE) that reports each
  step as it happens ("Scoring the rooms", "Detecting conflicts", "Writing the
  summary") and then streams the final answer in. Time-to-first-feedback dropped from
  "nothing until the turn ends" to **~3s** (first progress label). Why it matters: the
  product finally *feels* like a live collaborator instead of a slow form submit.

- **Edits no longer answer with stale facts.** We found a real correctness bug: after
  you edit the layout, the old conflict/suggestion analysis was silently kept and a
  follow-up question ("why does the Kitchen have conflicts?") answered from data
  computed on the *pre-edit* layout. Now a re-scoring turn properly invalidates the
  derived analysis, and such a follow-up automatically re-detects on the *current*
  layout. Why it matters: the agent's reliability — when it speaks, it's about the
  layout in front of you, not a ghost of an earlier one.

- **Less wasted work per turn.** The LangGraph was being recompiled from scratch on
  every single message (~25 nodes, ~53ms each turn); now it's built once and reused.
  Streaming, cancellation (a Stop button), and graceful error handling were added with
  **zero change to the API contract** — the non-streaming endpoint still returns the
  exact same payload, so nothing downstream regressed.

## Session 2 — The example plans now read like an architect drew them

- **The demo layouts were quietly broken — as drawings.** The four built-in examples
  passed our existing topology check (rooms tile the plan, areas match, doors on shared
  walls) yet were full of the things a human reviewer catches in a second: beds parked
  0.2–0.5 m in front of bedroom doors, a door boxed in by a sofa on one side and a bed
  on the other with no clear swing, a wardrobe sitting flush over a bedroom window, a
  planter halving a 1 m hallway. We wrote a deterministic geometry checker
  (`check_layout_geometry.py`) that enumerates these — furniture overlaps, pieces
  through walls, blocked door swings, sub-standard door/circulation clearances, blocked
  windows — and it found **41 defects across the four layouts**. We then corrected the
  source files to **zero**, the minimal move each time (slide a bed to the far wall,
  shift a door along its wall, trim an oversized island).

- **Fixing them at the source raises the credibility of everything downstream.** Every
  render, every "the spatial score here is low" claim, every generated room image is
  read against the plan it sits on — a plan with a bed jammed through a doorway makes the
  whole analysis look careless. The fixes are also provably **score-neutral**: comfort
  scoring is attribute-driven (area, orientation, glazing, materials, adjacency, plant
  *count*) and never reads furniture geometry, so moving furniture changed **nothing** in
  the numbers (we diffed before/after — 201/202/203 identical; only 204's Hallway shifted,
  the one intended change from removing the corridor-blocking plant). So we improved the
  drawings the demo shows without disturbing the conflicts the demo is built to surface.

- **The checker is reusable infrastructure, not a one-off.** It's pure-stdlib and gates
  to a non-zero exit, so it can run in CI / pre-commit and catch a malformed plan — or a
  bad agent edit — before it ever reaches a user. Architectural soundness becomes a
  testable property of the layout data, not something we eyeball.

- **Then: valid wasn't the same as believable.** Clearing the collisions left plans that
  *passed* but still looked auto-generated — 3 m-wide "beds", 1.5 m-deep sofas, empty
  bathrooms, a desk parked 0.5 m off a bed. We taught the checker a second layer —
  realistic furniture *scale* (a footprint range per type), *required fixtures* (a
  bathroom must have a toilet + sink/vanity), *dead-space gaps* (too tight to use, too
  wide to be a pair), and *bed access* — which flagged **47 more issues**, then re-authored
  every layout's furniture: right-sized each piece, furnished all seven bathrooms
  (toilet/vanity/shower), added nightstands and kitchen sinks/fridges, and pushed the
  stray living-room plant into a corner. Now the plans read like an architect drew them.

- **Realism without breaking the demo.** We kept room attributes, adjacencies and plant
  counts fixed, so the comfort scores barely moved — the deltas are small tactile shifts
  in newly-furnished rooms (ceramic fixtures down, wood shelving up), overall scores ≤0.01,
  and the demo's headline thermal/acoustic/olfactory conflicts are untouched (every delta
  reported). The rules are now packaged as a reusable `floor-plan-review` skill so the next
  layout — generated or hand-drawn — gets the same scrutiny automatically.

## Session 3 — From bounding boxes to a drawing you can read

- **The plan now reads like an architect drew it, not like a stack of rectangles.** The
  canvas used to draw each room as its own bounding rectangle and each piece of furniture
  as an anonymous labelled box — a grid of overlapping rectangles with the word "bed" or
  "sofa" inside. We replaced that with real CAD linework: walls render as luminous bands
  with thickness, doors keep their swing, windows now *break* the wall with a glazing
  symbol, and every piece of furniture is a recognizable plan symbol (a bed with pillows,
  a sofa with arms, a toilet, an island with hobs; a plant became a soft glowing orb).
  Why it matters: the output stops looking auto-generated and starts looking *designed* —
  the same shift in credibility we made to the data last session, now made to the picture.

- **The walls had to be discovered, not read.** The layout JSON only lists a handful of
  named partitions in `structure` (3 walls for a 6-room flat), so the old renderer leaned
  on the room rectangles to show any interior divisions at all — which is *why* it looked
  boxy. We now derive the full wall network from the shared edges of the room polygons
  (merging the pieces of each wall line, tagging exterior vs interior), so the drawing's
  structure comes from the geometry itself and each wall is individually addressable —
  groundwork the upcoming wall/window **edit** tools (B3) will hook straight into.

- **CAD-accurate, but still unmistakably Sensi.** The hard constraint was to read like a
  real plan without becoming a heavy technical drawing — no black poché, no boxed
  callouts. Walls are a wide low-opacity "mass" glow under a crisp hairline (reusing the
  same luminous idiom as the relationship edges), the focused room lights with a soft
  inner glow instead of a hard outline, and the comfort lens reads *better* than before
  because the tint no longer fights a box border. The result holds from a 5-room studio
  up to a 13-room house, and the interactivity the rest of the app depends on (room
  selection, hover, comfort scoring) is untouched.

## Session 4 — The agent can now do what it advises

- **We picked the new edit tools by ROI, not by wishlist.** The agent could only do three
  things (add furniture, change glazing, change material) yet kept *suggesting* changes it
  couldn't execute — "add curtains to absorb sound", "upgrade the ventilation", "add a
  window". We audited every suggestion against (a) what actually moves the comfort scores
  and (b) how hard it is to build, and shipped the high-ROI set: **add a window, change a
  wall's material (room-scoped + visible), modify ventilation, add curtains, relocate a
  window, and a remove family (furniture / door / window)** — every one of them closing a
  "suggests-but-can't-do" gap. Crucially we also closed the *measurement* gap: the score
  model now credits soft furnishings (rugs, curtains) for sound absorption, reads wall
  finish per-room, and lets a window's orientation move thermal — so the loop is honest,
  *suggestion → edit → the score actually improves*. And when an edit fulfils a standing
  suggestion, that suggestion is crossed off the list in the panel.

- **Every edit now has architectural awareness baked in — floor-plan-review, live.** Edits
  used to commit blind: a plant landed dead-centre in the room, "change the walls" silently
  repainted *every* wall in the flat, nothing checked for overlaps. Now placement is sound
  *by construction* (Shapely finds a clear floor spot against a wall for a plant, a clear
  exterior span for a window, the window wall for a curtain), and the same architectural
  rules the `floor-plan-review` skill uses run **in-process after every op**: if an edit
  introduces a new collision, a blocked door, or a sealed-off room, that single op is
  reverted and the agent says why — the good edits in the same sentence still land.

- **The vocabulary got wider without a second pipeline.** All nine tools ride the exact same
  ripple as the original three — `edit_planner` decomposes one sentence into several ops,
  `apply_edits` mutates at the one chokepoint, the layout is re-scored **once**, and
  `compare_versions` reports the before→after delta. We proved it live: "change the kitchen
  walls to cork" tinted the walls cork and lifted tactile 0.40→0.70-band while crossing off
  its suggestion; "add a window to the master bedroom" placed a north-facing window and
  moved visual 0.63→0.70 — each in a single, sound, re-scored turn.
