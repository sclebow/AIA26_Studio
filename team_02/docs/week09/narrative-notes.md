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

## Session 5 — The edit-guide: from a marker to a focus of light

- **We stopped pointing AT the edit and started lighting it.** The old `MaterialLayer` was a
  lens — a glossy material "marble" floating in every room, on only when you toggled it. We
  killed the lens (the `material` toggle is gone) and asked a sharper question: how does the
  agent's edit announce *where + what* it changed, at a glance, without text on an already-dense
  plan? We explored hard — emissive orbs (depth, breath, a tether), then a whole family of
  non-orb ideas — through a design critique + two five-advisor design councils + a dozen live
  motion mockups, and landed on **Focus Pull**: when the agent edits, **the rest of the plan
  steps into shadow and a soft pool of light lands on exactly what changed.** No marker, no
  badge — the change is the only lit thing in a quiet room.

- **The light is precise, and material edits glow as themselves.** `EditFocusLayer` renders
  **nothing at rest**; on an edit it dims the plan (a masked scrim) and lights the change: an
  added window's glass, a placed plant's footprint, a removed door's dashed ghost all
  **ignite in place** on the wall, while room-wide edits (floor/ventilation) light the whole
  room — a material change glows in the *actual finish* (cork reads as cork). A breathing focal
  **iris** frames it, the **sense glyph** names the dimension, and per-edit life drifts within
  (air wafts motes, light glints). This needed a small backend resolver: the diff now carries
  an anchor `at` + the changed element's geometry `el`, so even *removals* (the element is gone
  from the new layout) light the exact spot.

- **Hover for the story, click to dive — and this closes B3 on the canvas.** Hover the focus and
  a card reads `wood → cork`, the affected senses (`○ visual + △ thermal`), and the **score
  impact** (`visual now 0.86`); click opens the room's full breakdown. B3 made edits sound and
  re-scored; Focus Pull makes them *felt*. Proved live: a floor edit lit the bedroom cork; a
  window lit the new glass on the wall; a two-part edit lit two zones under one shadow; a
  question-only turn left the plan bright. The whole arc — marker → orb → focus of light — is
  the session's story: the most on-brand answer was to add *no new shape at all*, only to move
  the light.

## Session 6 — The persona finally travels (and the math stops lying)

- **What you tell Sensi now reaches the room.** We audited the whole front door
  ([flow-audit.md](flow-audit.md)) and found the persona was a gate, not a companion: a
  stated *grandmother* barely reached layout mode and a *pet* was lost entirely (no keyword
  anywhere), while every layout node hand-rolled its own partial persona summary — household,
  age, non-negotiables and notes silently dropped on the way to the work. We added structured
  `household_members` capture (people **and** pets), one single-source persona formatter wired
  into every responder, and a labelled `apply_context` layer in the comfort engine so an elderly
  resident, children or a pet make a sensory *deficit* weigh a little heavier — visible and
  capped, never silent. Proved live end-to-end: onboarding "I live with my grandma and a cat" →
  the compiled description reads *"living with her grandmother and a cat"*, the Kitchen's acoustic
  is driven down, and when asked *"given who I live with, what should I prioritise?"* Sensi replies
  *"for your grandmother, consistent gentle warmth is key — she feels the cold more easily."* The
  4 demo layouts are byte-for-byte unchanged (a neutral persona triggers no context), so fidelity
  arrived without disturbing the demo.

- **The persona reveal stopped lying about its own math.** The reveal taught users a formula —
  `score = w × raw`, `C = Σ score`, `flag = |w−baseline| > 0.25` — that the engine has *never*
  computed. The real model (`sense_model.py`) keeps per-sense scores objective and blends a
  weighted mean **50/50 with your single worst sense** (a one-vote veto), with cross-modal,
  personality and now household layers on top. We rewrote "how Sensi scores your comfort" to the
  true model, sourced from the engine's own constants so the reveal can't drift again — the one
  place we teach the model now teaches the *real* one.

- **The persona became a companion, not a gate.** We pulled the reveal into a shared `PersonaCard`
  used both at the earned reveal (a single "this is me — start shaping" CTA; the redundant,
  read-only "tweak it" detour deleted) and inside an enriched, discoverable *profile* drawer you
  can reopen any time while shaping — the old drawer was a stub behind a mystery initial with a
  dead "full view" button. And we fixed a quietly-broken feature in passing: persona comparison
  keyed off a dead field and scored both sides identically (every room tied) — it now contrasts
  the user's real persona against a representative archetype.

- **And the persona is now a living thing you can refine by talking.** The reveal used to be a
  one-way snapshot — if it got something wrong, or life changed, you were stuck. The profile
  drawer now has a *refine* line: *"I just got a dog, and noise bothers me more"* → Sensi patches
  the relevant fields and leaves the rest alone (deterministic household/pet capture + a minimal
  LLM field-patch, weights clamped, baselines recomputed, persisted). Proved live: that exact
  sentence added a *dog* to the household and lifted acoustic 0.80 → 0.95 (now the top priority),
  and — because it rides the same fidelity plumbing — the change immediately flows into scoring
  and every answer. A quiet *redo onboarding* sits beside it. We deliberately said **no** to a
  slider/field editor: hand-dragging the weights would undercut the honest-math story we just
  shipped — you refine by telling your companion what changed, not by operating a control panel.

## Session 7 — The loop closes: the aesthetic you curated comes back

- **The moodboard finally has an afterlife.** Onboarding asks for real work — three rounds of
  picking images until a curated aesthetic signature emerges — and then, until now, that board
  *died at the front door*: it was stored in the session but never carried into Shape or the
  Report, so the output never answered the input. We traced the drop
  ([flow-audit.md §6](flow-audit.md)) and gave the curated board a home in the Report: a new
  **"the aesthetic you curated"** band replays the user's own six picks at the top of the
  deliverable. No new image-gen, no re-curation — the same data, surfaced where it pays off.
  Proved live end-to-end (a fresh "Maya" run, warm-minimalist board): the six images reappear in
  the Report, load cleanly, and survive both exports. Why it matters: the Report now visibly
  closes the circle — *this is the aesthetic you chose, and here is the dwelling read against it.*

- **The Report now opens by saying who it's for.** It used to be rooms-first — a stack of scores
  with no frame. We added a slim **persona header** ("shaped for **Maya** · client · lives with a
  partner · leads with thermal, olfactory, tactile"), built from the same shared `PersonaCard`
  vocabulary as the reveal and the layout drawer, so the persona reads as **one companion across
  all three acts** instead of a gate left behind at onboarding. It's a recap, deliberately *not*
  the full data-dump — meaning first, the math stays back in the profile. The header + board ride
  inside the export node, so the PNG and JSON artifacts now carry the persona and the aesthetic,
  not just the rooms.

- **The 10–30s render wait now reads as "working," not "broken."** A room's image is generated on
  demand (~10–30s); the old affordance was a static shimmer with a fixed "~20–40s" caption that
  read like a stall. We made it a **progressive reveal**: the scores and the prompt are already on
  screen, and the image cell cycles a quiet, poetic status over the shimmer ("composing the
  light…", "settling the quiet…", "letting the room breathe…") before the render fades in. Pure
  client-side, honours `prefers-reduced-motion`. The data path is deliberately minimal — the
  Report sources the board from the live session with a `persona.json` fallback, and a one-line
  **durability stamp** writes the board onto the persona on disk so it survives a restart or a
  returning user (verified: a fresh onboarding now leaves `moodboard_urls` in `persona.json`).

## Session 8 — The commit history reborn as a woven ripple of the senses

- **You can finally watch the senses rise, fall, and pull on each other.** The checkpoint strip
  from Task 3 was loved but flat: each milestone was a chip with one headline number, so the
  *shape* of the design process — where a decision lifted acoustic, where it cost thermal, and
  crucially *which senses dragged each other along* — was invisible. We reframed the timeline as a
  bold horizontal **ripple graph** (an expandable view of the strip): X = your commits in order,
  each sense a luminous strand on its **own auto-zoomed scale** so a 0.02 move reads as clearly as
  a 0.2 one, the strands **weaving and crossing**. The history stops being a list of save-points
  and becomes a *legible narrative*. Why it matters: the design **process** — and the coupling
  between senses that is Sensi's north star — becomes the artifact, not just the final plan.

- **The ripple is the point, and it's drawn from the real coupling model.** This is the heart:
  at each commit, where an edit made two **coupled** senses move together, a glowing valence-tinted
  arc braids them — green ＋ helped, amber ± trade-off, red − harmed — pulled straight from the
  canonical `SENSE_SENSE` matrix (acoustic↔thermal, thermal↔olfactory, tactile↔acoustic…). It's
  honest: an arc fires only when both its senses actually co-moved between commits ("potential
  ripple, grounded in what moved"), since the realized per-room adjustments aren't cheap to
  reconstruct at commit time. Reading aids are baked in — a one-line "how to read" caption and a
  sense glyph at each strand's end — so the weave never needs explaining.

- **Tiny backend, big legibility, and it stays navigable.** The data already existed (`_sense_means`
  per checkpoint); the change was ~12 lines (a `sense_means` field + a `live_head` helper for the
  dashed "now" node) and one hand-rolled SVG component, **no chart library**, reusing the app's own
  vocabulary (sense hues `SC/SI`, the `VALENCE` tints, the `.plan-tooltip` read-out). A node is
  still a commit you can **focus** (non-destructive) and confirm-gated **restore**. Verified live on
  a real four-commit session (initial → soft acoustics → plants → uncommitted oak floor): the
  acoustic strand steps up at the acoustics commit and a green ＋ arc braids it to tactile; hover any
  step for exact per-sense scores with ↑/↓. (We explored a vertical git-graph braid and dockable
  left/right panels first — a good detour — before landing on the bolder horizontal weave.)
