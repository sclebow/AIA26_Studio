# Sensi — Week 8 presentation script

11-slide update deck. Heroes (give them the air): slides **5–6** (the Vision, before/after)
and **8–9** (benchmarking). Target ~4 min.
Build: `python team_02/docs/build_deck_week08.py` → `week08/Sensi-Presentation-week08.pdf`.
Fonts are embedded (Inter · JetBrains Mono · Caveat) — all selectable in Canva to edit.

---

**1 · Cover** *(steady)*
"Week 8 of Sensi. The thesis hasn't changed — the number isn't the lesson, the edges are.
What changed is that the space now becomes an *image*."

**2 · What shipped** *(quick — the map)*
"Six things: the Vision/Report, the before-after scrub, the benchmarking, a headless CLI,
checkpoints with multi-edit, and a batch of fine-tunings."
*Aside on the CLI:* it's a true headless mode — the layout is **injected via the session**
(not `ctx.layout_data`), and stdout carries a stable response block (diagnostics to stderr), so
another tool can drive Sensi as a component.

**3 · The graph** *(steady — architecture first)*
"One `action_classifier` picks one of 13 actions in a single LLM call, then a LangGraph pipeline
runs the right chain — analyze→score, detect→suggest, or the edit/insight paths, always ending
respond→evaluate. It's cache-aware, and edit→re-score→compare is the agentic ripple. FastAPI +
LangGraph + React; no Rhino or Grasshopper — it runs behind one link."

**4 · Edit engine + checkpoints** *(steady)*
"One instruction can carry several edits: `edit_planner` decomposes it, `apply_edits` mutates them
at one chokepoint, and we re-score once and compare. Editing is a live draft — you commit
milestones, git-like, and can restore any point. The Report's before/after reads the committed
checkpoint."

**5 · HERO — The Vision (Act 3)** *(slow — the payoff)*
"Now the output. Every room runs the same loop: its six-sense scores **become a prompt**, and the
prompt **becomes an image** — a first-person view of how the room *feels*."

**6 · HERO — What your changes did** *(slow)*
"Edit a room, commit, and the report shows the glow-up: one spine runs the whole card, and as you
drag, the render wipes **and** the sense-rose and the numbers morph with it."

**7 · Act 3 under the hood** *(steady — the mechanism)*
"How it's built: scores → prompt → render. The prompt is assembled deterministically — room,
floor, the *voiced* senses (only the extremes, below 0.45 or above 0.70), the furnishings, a
persona register. For before/after, the 'after' is the room's canonical render — the same image
the card shows — and the 'before' is that image edited by an explicit 'what changed' clause."
*Aside on consistency:* the image model has **no fixed seed**, so we hold the scene by anchoring
the 'before' on the 'after' image plus that imperative clause — ~80–90% perceptual consistency,
which is what a "vibe" render needs.

**8 · Benchmarking — node tiers** *(steady — the table)*
"We measured every node. Thirteen LLM nodes on two tiers: FAST (flash-lite) for
routing/classification, SMART (flash) for the reasoning you read. FAST averages 0.7 s and a
fraction of a cent; SMART is ~12× slower and ~11× costlier — so it only runs where quality
compounds. The reasoners are the budget; the slowest is suggestion-critic at 16 s."

**9 · Benchmarking — image provider** *(steady — the images)*
"Same prompt, two engines. Google's clean architectural daylight vs OpenAI's darker, cinematic
read — across all three rooms. Google's three times faster and a touch cheaper, so we stay on
Google; it's a one-line swap to change."

**10 · Fine-tunings** *(quick)*
"Polish: the canvas is orbs and ripples, not heavy fills; the chat linkifies rooms/senses/scores
and brushes the plan both ways; the system prompts were consolidated; and we cut redundancies."

**11 · What's next** *(steady → handoff)*
"Next: tune the loop; redesign the orbs into per-attribute orbs so every change is visible; and
add more agentic editing tools — add a window, change a wall material — while optimising the ones
we have. Same goal: keep the edges legible, now in pixels."

---

## Assets

- Screenshots in `team_02/docs/week08/shots/` (`vision-rooms-cards.png`, `before-after-screen.png`,
  `commit-changes.png` wired in). Benchmark thumbnails `bench-{google,openai}-{living,kitchen,bedroom}.png`
  are downscaled from `week08/benchmark/`.
- Fonts in `team_02/docs/fonts/` (Inter, JetBrains Mono, Caveat). To edit in Canva, pick the same three.
- Numbers: `bench_nodes.py` (node table) + `python -m imaging.benchmark` (image A/B).
