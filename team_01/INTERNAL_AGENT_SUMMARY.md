# Structural Design Agent — Internal Summary

## What it is

A conversational structural design agent for early architectural decision-making. Built on LangGraph. Connects optionally to a Grasshopper MCP server — all structural mathematics and the full evaluate/modify/comparison pipeline run in pure Python without it.

The LLM handles language and routing only. All numbers come from Python.

---

## Graph

```
START → reason
reason → modify        (LLM decided to call a tool)
reason → evaluate      (LLM set final_response="" for eval/computation request)
reason → END           (LLM answered a direct Q&A question)

modify → cost_flexibility   (always, except tag_and_audit → skips cost_flex)
modify → evaluate            (tag_and_audit path only)
cost_flexibility → evaluate

evaluate → modify       (pending_structural_change set by evaluate menu)
evaluate → comparison   (after modify/structural_change cycle)
evaluate → END          (plain evaluation, no pending change)

comparison → END
```

Routing guards:
- `_looks_like_eval` keyword set prevents tag_and_audit running on evaluation prompts
- `_route_from_modify` skips cost_flexibility for tag_and_audit
- Tier upgrade prompt suppressed when `came_from == "structural_change"`

---

## Nodes

### reason
LLM reads layout summary + tool catalog. Decides: answer directly, call tag_and_audit, or defer to evaluate. Never calculates. Message history capped at 4 messages (first message 2500 chars, rest 400 chars).

### modify
Two roles:
1. Executes MCP tool calls from reason (or calls `generate_structure` directly for tag_and_audit)
2. Dispatches `pending_structural_change` from evaluate:
   - `tier_upgrade` — applies new material tier to all elements
   - `material_switch` — switches base material
   - `upgrade_element` — single element section upgrade
   - `midspan_column` — splits beam, inserts column at midpoint
   - `auto_upgrade_beams` — loops up to 6 passes until all beams pass
   - `auto_upgrade_columns` — same for columns
   - `find_minimum` — applies XS then upgrades element by element to first PASS
   - `remove_element` — removes column (merges collinear beams) or beam
   - `remove_elements` — batch version of remove_element

### cost_flexibility
Independent node between modify and evaluate. Computes:
- Material cost USD (volume × unit rate: RCC $350, Steel $12k, Timber $800/m³)
- Flexibility score 0–10 (reversibility heuristic per element type and position)
- Disruption score 0–10 (construction impact)
- Spatial penalty 0–1 (mid-room column intrusion)

Skipped for tag_and_audit (no before/after diff). Result injected into comparison LLM prompt and evaluation report.

### evaluate
Pure calculations, no mutations. Runs:
- Beam checks: bending, shear, LL deflection (L/360), TL deflection (L/250)
- Column checks: compressive stress, Euler buckling (SF ≥ 3.0)
- What-if column removal simulation (span extension + re-check)
- LLM advisor interpretation (`_interpret_evaluation`) with pre-computed removal hints
- Unified "what next?" menu when structure passes (right-size + underutilised elements)
- Failure menu when structure fails (auto-upgrade, per-element, midspan column, material switch)
- Tier upgrade prompt only on first (fresh) evaluation — suppressed after modifications

Human-in-loop prompts:
1. Material selection (RCC / STEEL / TIMBER / Right-size)
2. Floor build-up SDL (1.5 / 2.5 / 3.5 / 5.0 kN/m²)
3. Usage type LL (2.0 / 3.0 / 5.0 kN/m²)
4. Tier upgrade offer (on fail, fresh evaluation only)
5. Unified pass menu: right-size + removals
6. Failure menu: numbered alternatives

### comparison
Diffs layout_before_change vs layout_json_string. Groups changes by pattern ("22× 200×200→175×175"). LLM writes 2–3 sentences with design meaning and next step suggestion. Has LLM-unavailable fallback. Appends cost/flex summary to LLM prompt.

---

## Advisor (LLM interpretation of evaluation results)

Runs after every structural check. Computes utilisation ratios in Python, pre-computes column removal hints (simulate_what_if_removal for each column below 50%), then calls LLM with structured summary.

Thresholds:
- Below 50%: over-engineered — suggest layout change (remove element, open space)
- 50–75%: working range — healthy
- Above 75%: approaching limit — flag

Output: one sentence verdict, 2–3 bullets with element IDs and numbers, one actionable next step.

---

## Section Tiers

| Tier | RCC beam/col | Steel beam/col | Timber beam/col |
|---|---|---|---|
| XS | 150×200 / 150×150 | IPE120 / HSS80×80×5 | 75×150 / 90×90 |
| S | 175×250 / 175×175 | IPE160 / HSS100×100×6 | 100×240 / 100×100 |
| M | 200×300 / 200×200 | IPE200 / HSS120×120×6 | 120×300 / 120×120 |
| L | 225×350 / 225×225 | IPE240 / HSS150×150×6 | 150×360 / 150×150 |
| XL | 250×400 / 250×250 | IPE300 / HSS180×180×8 | 200×480 / 200×200 |
| XXL | 275×450 / 275×275 | IPE360 / HSS200×200×8 | 250×600 / 250×250 |

Column upgrade chain (25mm steps): 150→175→200→225→250→275
Beam depth upgrade chain (50mm steps): 200→250→300→350→400→450

---

## Material Properties

| Material | E (MPa) | Allow. bend | Allow. comp | Allow. shear | Standard |
|---|---|---|---|---|---|
| RCC | 31,000 | 14.2 MPa | 14.2 MPa | 2.8 MPa | EC2 C25/30 |
| Steel | 200,000 | 235 MPa | 235 MPa | 135.7 MPa | EC3 S235 |
| Timber | 8,000 | 12.3 MPa | 10.5 MPa | 1.1 MPa | EN338 C16 |

---

## Files

| File | Role | Lines (approx) |
|---|---|---|
| `main.py` | CLI entry — untouched | 28 |
| `graph.py` | LangGraph orchestration, routing, report | ~480 |
| `nodes/reason.py` | LLM reasoning + tool routing | ~140 |
| `nodes/evaluate.py` | Structural calculations + HitL menus + advisor | ~1,200 |
| `nodes/modify.py` | All section constants + mutations + dispatch | ~670 |
| `nodes/comparison.py` | Before/after diff + LLM summary | ~140 |
| `nodes/cost_flexibility.py` | Cost + flexibility analysis node | ~390 |
| `nodes/tag_and_audit.py` | Structural grid generator (standalone) | ~860 |
| `_runtime/bootstrap.py` | Startup — MCP optional (commentable) | ~90 |

---

## Design Principles

1. LLM for language, Python for numbers — no LLM calculations
2. No hallucinated IDs — alternatives menu uses only IDs from actual failure data
3. Human in the loop at every decision — material, loads, tier, failure response, removals
4. Every change goes through the full pipeline: modify → cost_flex → evaluate → comparison
5. Loops until structure passes — auto_upgrade and find_minimum loop internally
6. Tier upgrade only on first evaluation — not repeated after modifications
7. Layout suggestions only when structure passes — not shown after structural changes
8. Runs without MCP — tag_and_audit, evaluate, and all optimisation are pure Python
9. SDL/LL persist across sessions via team_01_settings.json
10. Evaluation report captures material, SDL, LL, structural table, comparison, cost/flex

---

## Design Principles (Technical)

- `pending_structural_change` dict is the contract between evaluate and modify
- `came_from` field drives routing and conditional display logic
- `layout_before_change` snapshot enables before/after diff in comparison
- `removal_hints` pre-computed in Python (not by LLM) for accurate span impact
- `evaluate_fn` injected into modify enables atomic find_minimum and auto_upgrade loops
