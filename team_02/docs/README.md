# Team 02 — Docs

Map of this folder. **Frozen deliverables** are grouped by week; **evergreen reference** docs live in
`reference/` because they are week-independent.

```
docs/
├── reference/        evergreen concept & research (not tied to a week)
├── week07/           frozen week-7 deliverables
├── week08/           CLI + benchmarking
└── week09/           final review: deck, scripts, PDF (in deliverables/)
```

## reference/ — evergreen
- [concept-the-ripple.md](reference/concept-the-ripple.md) — the core "ripple" concept.
- [comfort-model-references.md](reference/comfort-model-references.md) — sources behind the comfort model.
- [adr-relationship-galaxy.md](reference/adr-relationship-galaxy.md) — ADR for the relationship galaxy.
- [graph-relationships-audit.md](reference/graph-relationships-audit.md) — graph/topology audit.

## week07/ — frozen deliverables
- [Sensi-Presentation-week07.pdf](week07/Sensi-Presentation-week07.pdf) — the week-7 deck.
- [presentation-script-week07.md](week07/presentation-script-week07.md) — the week-7 talk script.

## week08/
- [cli-changes.md](week08/cli-changes.md) — CLI for the orchestrator (faculty notes).
- [benchmarking-findings.md](week08/benchmarking-findings.md) — per-node model tiering (Gemini FAST/SMART) + rationale.
- [image-generation-research.md](week08/image-generation-research.md) — deep-research findings (consistency, score-conditioning, edit legibility).
- [image-output-phase0.md](week08/image-output-phase0.md) — the edit-legible plan: material orbs + ripple, PNG export.
- [image-output-phase1.md](week08/image-output-phase1.md) — generative per-room "feeling" render (FocusCard), IMAGE_PROVIDER google/openai.
- [image-output-phase2.md](week08/image-output-phase2.md) — before/after wipe slider + per-sense deltas (historical; the per-edit `/api/compare-room` it describes was later removed — before/after is now always initial → now via `/api/compare-initial`).
- [image-provider-benchmark.md](week08/image-provider-benchmark.md) — Google vs OpenAI head-to-head (latency/cost/visual); committed to Google. Samples in benchmark/.
- [edit-checkpoints-interactive.md](week08/edit-checkpoints-interactive.md) — multi-edit (edit_planner→apply_edits), Checkpoints (working draft → commit/restore, Vision = committed), and interactive answers (linkify + bidirectional cross-highlighting).
- [reference/report-vision-pipeline.md](reference/report-vision-pipeline.md) — current consolidated overview of the Report/Vision (model, prompts, scoring, before/after, exports).

## week09/ — final review (current)
- [deliverables/](week09/deliverables/) — the live deck (`deck/index.html`), its PDF export (`Sensi-FinalReview-week09.pdf`, rebuilt with `deck/make-pdf.py`), and the spoken scripts (`presentation-script-week09.md`, `demo-scripts-week09.md`).
- [models-and-benchmarks.md](week09/models-and-benchmarks.md) — current Gemini 3.x models + refreshed benchmarks; samples in `week09/benchmark/`.
- `demo-runbook-week09.md`, `narrative-notes.md`, `flow-audit.md` — recording runbook and session working notes.

> Convention going forward: each week's **frozen outputs** (decks, scripts, findings) go in a
> `weekNN/` folder. Evergreen reference material stays in `reference/`.
