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
