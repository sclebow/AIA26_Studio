# Concept — The Ripple: senses talking to each other

**The north star for Sensi's scoring, relationships graph, and 3D galaxy.** Everything
below is the *why*; the ADRs and audits are the *how*. Read this first.

## The core idea

> **The overall number isn't a grade to inflate — it's the weakest teacher in the
> system. The real lesson lives in the edges: how a change to one sense ripples to
> another.** That's exactly what the relationships-graph work is building toward.

Sensi's job is **not** to hand someone a comfort score to chase. It's to teach how the
senses *talk to each other* — and how to improve them. A single aggregate number is the
least educational artifact we can show; it's designed to be stable, so on its own it
reads as "nothing changed." The teaching happens in the **edges**, not the nodes.

## What this means in practice

- **Don't inflate the score.** A whole-dwelling comfort index *should* be stable — that's
  what makes it trustworthy. Inflating it to make changes "feel" bigger destroys the one
  thing the score is for: telling a good layout from a bad one. The aggregate is a status
  light, not the headline.
- **The lesson is the ripple.** When you change one thing — a material, a plant, a window —
  the interesting story is **how a change to one sense ripples to another**: tactile lifts
  acoustic (soft surfaces absorb sound), olfactory lifts thermal, a failing sense drags its
  neighbours down. Comfort spreads, not just discomfort.
- **Make the ripple visible, interactive, and predictable.** The user explores, the agent
  acts, and both watch the ripple — which is simultaneously the agent's planning signal,
  the user's feedback, and the lesson. Teaching is an *emergent property* of a legible,
  agentic feedback loop, not a separate mode.

## How the system embodies it

| Surface | How it carries the ripple |
|---|---|
| **Scoring** (`comfort/sense_model.py`) | Non-additive (veto floor keeps the aggregate honest) **and symmetric** — a strong sense radiates *comfort* to its `+`-coupled partners, not only discomfort. So an edit moves 2–3 senses, and the change is real but un-gameable. |
| **Sense hub** (`canvas/SenseHub.jsx`) | Each cross-modal adjustment animates as a pulse travelling source→target — **green for a lift, red for a drag** — with the origin sense node pulsing as it "fires." |
| **Predictive preview** (`nodes/editing/preview.py`) | A no-commit "what if" — score a hypothetical edit, show the predicted ripple and forecast number, change nothing until the user commits. The agent's forecast and the user's sandbox. |
| **The Relationship Galaxy** (`docs/adr-relationship-galaxy.md`) | The immersive 3D mode — the *whole* relationship system at once, the full life of the edges. The ripple, flown through. |

## Vocabulary (keep these phrases)

- **"the relationship galaxy"** — the 3D explore mode showing the whole system of edges.
- **"how a change to one sense ripples to another"** — the one-sentence statement of what
  we teach.
- **"the overall number isn't a grade to inflate, it's the weakest teacher in the system —
  the real lesson lives in the edges."** — the scoring philosophy in one line.

## See also
- [`adr-relationship-galaxy.md`](adr-relationship-galaxy.md) — the 3D galaxy decision.
- [`graph-relationships-audit.md`](graph-relationships-audit.md) — the relationships-graph audit.
- [`comfort-model-references.md`](comfort-model-references.md) — the research grounding the couplings.
