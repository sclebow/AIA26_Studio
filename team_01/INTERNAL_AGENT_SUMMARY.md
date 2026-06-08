# Permanence_OS — Internal Agent Summary

**Branch:** `team_01` | **Last updated:** 2026-06-07

---

## What It Is

A conversational structural design agent for early architectural decision-making. Built on LangGraph. Connects optionally to a Grasshopper MCP server — all structural mathematics and the full evaluate/modify/comparison pipeline run in pure Python without it.

**The LLM handles language and routing only. All numbers come from Python.**

---

## LLM Integration — No Claude API

The agent uses **OpenAI-compatible endpoints** via `langchain_openai.ChatOpenAI`. Provider is set in `.env` (gitignored):

```
LLM_PROVIDER=openai   # or: local, cloudflare, google, anthropic
```

The `_runtime/config.py` scaffold accepts an `anthropic` option, but this uses the OpenAI-compatible shim (`ChatOpenAI` + `base_url="https://api.anthropic.com/v1/"`), **not** `langchain_anthropic`. **No Claude API calls exist in our team_01 additions.** Zero Claude/Anthropic imports in any `nodes/` or `graph.py` file. Which LLM runs is determined by `.env` — never pushed.

---

## Code Added / Modified vs `main` Branch

| File | Insertions | Deletions | Note |
|---|---|---|---|
| `nodes/cost_flexibility.py` | +1,402 | −473 | Full V4 rewrite (~400 → ~1,800 lines) |
| `app.py` | +1,586 | 0 | New Streamlit UI (standalone prototype) |
| `graph.py` | +140 | −30 | V4 report writer, section-persistence, headless CLI support |
| `nodes/evaluate.py` | +90 | −15 | Section-persistence fix, headless input, prompt keyword parsing |
| `main.py` | +25 | −12 | Full CLI rewrite: flags, JSON parse, structured output |
| `nodes/comparison.py` | +5 | −1 | V4 system prompt |
| `nodes/reason.py` | 0 | −8 | Removed stale routing code |
| **Python total** | **~3,248** | **~539** | **Net ~2,709 new lines** |

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
LLM reads layout summary + tool catalog. Decides: answer directly, call tag_and_audit, or defer to evaluate. Never calculates. Message history capped at 4 messages.

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
   - `remove_elements` — batch version

### cost_flexibility (V4 — Three-Pillar Model)

**Pillar 1 — Financial Cost (components A–H)**

| Code | Component |
|---|---|
| A | Material supply |
| B | Labour (installation) |
| C | Demolition / removal |
| D | Temporary works |
| E | Professional fees (12%) |
| F | Municipal permit (€1,200 base) |
| G | Transport / logistics |
| H | Mobilisation overhead |

**Total Structure Build Cost** = volume × (material rate + install rate) × location factor + 18% fees + €1,200 permits. CYPE 2024 Barcelona reference rates:

| Material | Supply | Install | Total |
|---|---|---|---|
| RCC | €350/m³ | €800/m³ | €1,150/m³ |
| STEEL | €12,000/m³ | €3,000/m³ | €15,000/m³ |
| TIMBER (GL24h) | €950/m³ | €1,500/m³ | €2,450/m³ |

Location multipliers: Barcelona 1.0, London 1.35, NYC 1.55, Dubai 0.90, Singapore 1.25.

**Design-Phase Saving** = avoided new-build cost of removed elements (vs renovation removal cost later).

**Pillar 2 — Administrative Burden (P0–P9):** Ten regulatory processes scored. Critical-path weeks shown. Dominant process identified (typically P2 — Municipal Building Permit for residential).

**Pillar 3 — Adaptability (SC/CR/LPS/RF):** Structural Complexity, Change Reversibility, Long-term Planning Score, Regulatory Footprint → rolled into High/Medium/Low + confidence level.

Note: Total Structure Build Cost covers **structural frame only** (beams + columns). Slabs, walls, foundations, MEP are not included.

### evaluate
Pure calculations, no mutations. Runs:
- Beam checks: bending, shear, LL deflection (L/360), TL deflection (L/250)
- Column checks: compressive stress, Euler buckling (SF ≥ 3.0)
- What-if column removal simulation (span extension + re-check)
- LLM advisor interpretation with pre-computed removal hints
- Unified "what next?" menu when structure passes (right-size + underutilised elements)
- Failure menu when structure fails (auto-upgrade, per-element, midspan column, material switch)

Human-in-loop prompts:
1. Material selection — shows actual sections from live layout (not hardcoded defaults)
2. Floor build-up SDL (1.5 / 2.5 / 3.5 / 5.0 kN/m²)
3. Usage type LL (2.0 / 3.0 / 5.0 kN/m²)

### comparison
Diffs `layout_before_change` vs current layout. Groups changes by pattern. LLM writes 2–3 sentences with design meaning and one next-step suggestion. Fallback to built-in summary if LLM unavailable.

---

## Section-Persistence Fix

**Problem:** `apply_material_override()` reset ALL element sections to material defaults on every evaluate pass — even when just pressing Enter to keep the same material. Individually upgraded beams (e.g. 120×300) were silently overwritten with defaults (100×240).

**Fix (evaluate.py ~line 1008):** Skip `apply_material_override` when all elements already carry the target material:

```python
_existing_mats = {
    ((el.get("attributes") or {}).get("material") or "RCC").upper()
    for el in json.loads(state["layout_json_string"]).get("structure", [])
}
if _existing_mats <= {material_override.upper()}:
    layout_str = state["layout_json_string"]   # preserve upgrades
else:
    layout_str = apply_material_override(...)   # material is actually changing
```

---

## Section Tiers

| Tier | RCC beam/col | Steel beam/col | Timber beam/col |
|---|---|---|---|
| XS | 150×200 / 150×150 | IPE120 / HSS80×80×5 | 75×150 / 90×90 |
| S (default) | 175×250 / 175×175 | IPE160 / HSS100×100×6 | 100×240 / 100×100 |
| M | 200×300 / 200×200 | IPE200 / HSS120×120×6 | 120×300 / 120×120 |
| L | 225×350 / 225×225 | IPE240 / HSS150×150×6 | 150×360 / 150×150 |
| XL | 250×400 / 250×250 | IPE300 / HSS180×180×8 | 200×480 / 200×200 |
| XXL | 275×450 / 275×275 | IPE360 / HSS200×200×8 | 250×600 / 250×250 |

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
| `main.py` | CLI entry | 28 |
| `graph.py` | LangGraph orchestration, routing, V4 report writer | ~480 |
| `nodes/reason.py` | LLM reasoning + tool routing | ~140 |
| `nodes/evaluate.py` | Structural checks + HitL menus + advisor | ~1,340 |
| `nodes/modify.py` | Section constants + mutations + dispatch | ~670 |
| `nodes/comparison.py` | Before/after diff + LLM summary | ~180 |
| `nodes/cost_flexibility.py` | V4 three-pillar cost model | ~1,800 |
| `nodes/tag_and_audit.py` | Structural grid generator | ~860 |
| `app.py` | Streamlit UI prototype (not wired to graph) | ~1,586 |
| `_runtime/bootstrap.py` | Startup — MCP optional | ~90 |

---

## CLI Interface

```
# Interactive (human at terminal — all prompts appear as normal)
python main.py --prompt "tag and audit"
python main.py --prompt "evaluate the structural layout"

# Orchestrator / headless (no terminal — defaults used silently)
python main.py --prompt "evaluate as TIMBER for residential use" --layout_json '{ ... }'
```

Output format:
```
Final Response:
<agent reply>

Edited Layout JSON:
<full layout JSON or "No layout changes">
```

Headless defaults (activated when `sys.stdin.isatty()` is False):

| Prompt | Default |
|---|---|
| Material | Keep current (or keyword from prompt: RCC / STEEL / TIMBER) |
| SDL | Keep current (or keyword: light timber/wood → 1.5, light concrete → 2.5, standard → 3.5, heavy → 5.0) |
| LL | Keep current (or keyword: residential → 2.0, office → 3.0, retail → 5.0) |
| Grid option | Option 1 |
| Tier upgrade | `y` (auto-upgrade) |
| Column/beam removal confirm | `n` (don't remove) |
| Pass menu | Enter (return results as-is) |
| Failure menu | `1` (auto-upgrade all failing elements) |

## Known Limitations

- **Last Modification Cost** shows only the final upgrade cycle — not cumulative cost of all cycles to achieve PASS.
- **Total Structure Build Cost** is structural frame only (beams + columns), not full building.
- `app.py` Streamlit UI is a standalone prototype — not connected to the main agent graph.
- `analysis.structure_cost` is not yet injected into the returned layout JSON (cost data is in the report file only).

---

## Design Principles

1. LLM for language, Python for numbers — no LLM calculations
2. No hallucinated IDs — menus use only IDs from actual failure data
3. Human in the loop at every decision
4. Every change goes through the full pipeline: modify → cost_flex → evaluate → comparison
5. Loops until structure passes — auto_upgrade and find_minimum loop internally
6. Tier upgrade only on first evaluation — not repeated after modifications
7. Layout suggestions only when structure passes
8. Runs without MCP — tag_and_audit, evaluate, and all optimisation are pure Python
9. SDL/LL persist across sessions via `team_01_settings.json`
10. `came_from` field controls routing; `pending_structural_change` is the modify contract
