# Team 02 — Docs

Map of this folder. **Frozen deliverables** are grouped by week; **evergreen reference** docs and the
**deck tooling** live at the root because they are week-independent.

```
docs/
├── reference/        evergreen concept & research (not tied to a week)
├── week07/           frozen week-7 deliverables
├── week08/           current week — CLI + benchmarking
├── build_deck.py     deck generator (reads shots/, writes Sensi-Presentation.pdf)
├── render_mermaid.py renders ../python/sensi_graph.mermaid → shots/03-graph.png
└── shots/            working screenshots used by the deck tooling
```

## reference/ — evergreen
- [concept-the-ripple.md](reference/concept-the-ripple.md) — the core "ripple" concept.
- [comfort-model-references.md](reference/comfort-model-references.md) — sources behind the comfort model.
- [adr-relationship-galaxy.md](reference/adr-relationship-galaxy.md) — ADR for the relationship galaxy.
- [graph-relationships-audit.md](reference/graph-relationships-audit.md) — graph/topology audit.

## week07/ — frozen deliverables
- [Sensi-Presentation-week07.pdf](week07/Sensi-Presentation-week07.pdf) — the week-7 deck.
- [presentation-script-week07.md](week07/presentation-script-week07.md) — the week-7 talk script.

## week08/ — current week
- [cli-changes.md](week08/cli-changes.md) — CLI for the orchestrator (faculty notes).
- [benchmarking-findings.md](week08/benchmarking-findings.md) — per-node model tiering (Gemini FAST/SMART) + rationale.

## Tooling (root)
- `build_deck.py` — regenerates the deck PDF from `shots/`. Run from this folder.
- `render_mermaid.py` — regenerates the architecture diagram into `shots/`.
- `shots/` — input/output assets for the two scripts above (regenerable, not a deliverable).

> Convention going forward: each week's **frozen outputs** (decks, scripts, findings) go in a
> `weekNN/` folder. Reusable tooling and evergreen reference material stay at the root or in
> `reference/`.
