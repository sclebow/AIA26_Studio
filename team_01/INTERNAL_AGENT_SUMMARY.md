# Permanence_OS — Internal Agent Summary

**Branch:** `team_01` | **Last updated:** 2026-06-21 (session 3)

---

## What It Is

A conversational structural design agent for early architectural decision-making. Built on LangGraph. Connects optionally to a Grasshopper MCP server — all structural mathematics and the full evaluate/modify/comparison pipeline run in pure Python without it.

**The LLM handles language and routing only. All numbers come from Python.**

Supports both **single-level** and **multilevel** floor plan layouts from a single unified pipeline.

---

## LLM Integration — No Claude API

The agent uses **OpenAI-compatible endpoints** via `langchain_openai.ChatOpenAI`. Provider is set in `.env` (gitignored):

```
LLM_PROVIDER=openai   # or: local, cloudflare, google, anthropic
```

The `_runtime/config.py` scaffold accepts an `anthropic` option, but this uses the OpenAI-compatible shim (`ChatOpenAI` + `base_url="https://api.anthropic.com/v1/"`), **not** `langchain_anthropic`. **No Claude API calls exist in our team_01 additions.** Zero Claude/Anthropic imports in any `nodes/` or `graph.py` file. Which LLM runs is determined by `.env` — never pushed.

---

## Code Added / Modified vs `main` Branch

All Python was written from scratch — first push had only Grasshopper `.gh` files.

| File | Lines (current) | Changes this session |
|---|---|---|
| `nodes/evaluate.py` | ~1,917 | `_INTERPRET_SYSTEM` expanded (design intent, tradeoffs, level-by-level framing); `transfer_beams` added to summary dict and format table |
| `nodes/cost_flexibility.py` | ~1,349 | `total_build_cost_eur` added to each `cost_history` entry; multilevel element extraction fixed in `_detect_changes` and `cost_flexibility_node` |
| `nodes/tag_and_audit.py` | ~881 | Upper-level outline derivation from room geometry |
| `app.py` | ~1,586 | Streamlit UI standalone prototype (unchanged) |
| `graph.py` | ~677 | Headless/multilevel routing |
| `nodes/modify.py` | ~700 | Perimeter beam lock (single-level + multilevel); defensive removal verification; `→`→`->` encoding fix |
| `nodes/comparison.py` | ~234 | SYSTEM_PROMPT tradeoff framing; cost delta (previous→current total) added to LLM context |
| `nodes/reason.py` | ~152 | `→`→`->` encoding fix |
| `nodes/_layout.py` | ~138 | Multilevel utility module |
| `main.py` | ~44 | CLI entry |
| **Python source total** | **~7,668** | (excluding example layouts, app.py) |

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

## Layout Formats

### Single-level
```json
{ "layoutId": "...", "outline": [...], "rooms": [...], "structure": [...] }
```

### Multilevel
```json
{
  "layoutId": "...",
  "levels": {
    "level_01": { "outline": [...], "rooms": [...], "structure": [...] },
    "level_02": { "outline": [...], "rooms": [...], "structure": [...] }
  }
}
```

All nodes detect format via `nodes/_layout.py → is_multilevel()` and handle both transparently.

---

## Multilevel Rules

| Rule | Detail |
|---|---|
| Shared XY column grid | `level_01` generates the master grid; upper levels get a filtered subset (Shapely polygon containment) |
| Perimeter elements | Locked at every level — cannot be removed |
| Internal elements | Can be modified per level independently |
| Column loads | `load_multiplier = n_levels − level_index` (level_01 in 2-storey = ×2, top = ×1) |
| Cross-level removal | Removing a lower-level column when a column exists directly above is **allowed** — the spanning beam becomes a transfer beam |
| Material | One material applied to all levels (global, not per-level) |

---

## Transfer Beam Logic

When a column at `level_N` is removed and a column exists directly above it at `level_N+1`:
1. The two collinear beams flanking the removed column merge into one spanning beam
2. The merged beam carries a concentrated point load `P` at the position of the removed column (from the upper-level column's total load)
3. Structural check: simply-supported beam with UDL `w` + point load `P` at distance `a` from left

```
R_A = w·L/2 + P·(L−a)/L
R_B = w·L/2 + P·a/L
M_max = max(M at x=a, M at zero-shear locations)
Deflection by superposition: d_udl + d_point_load
```

The what-if display marks these as `[TRANSFER]` with `P=XkN@Ym`.

## Cascade Load Logic

When a column at an upper level (`level_02`) is removed:
- Beams that lose one support transfer a reaction to surviving endpoint columns
- `extra = (SDL+LL) × trib_width × orig_span / 2` per half-span
- The surviving endpoint column at `level_02` gets extra axial load
- This cascades to the `level_01` column at the same XY position
- Result appears in `sim_result["cascade"]`

---

## Nodes

### `nodes/_layout.py` — Utility Module (new)

Key functions used by all other nodes:
- `is_multilevel(layout)` — detects format
- `get_level_keys(layout)` — ordered list of level keys
- `get_structure(layout, level_key=None)` — flat structure list for one or all levels
- `iter_all_structure(layout)` — yields `(level_key, element)` for all levels
- `find_element_in_layout(layout, element_id)` — returns `(level_key, element)`
- `load_multiplier_for_level(layout, level_key)` — axial load scaling factor
- `has_column_above(layout, col_pos, level_key)` — checks for column at same XY in any upper level
- `get_all_rooms(layout)` — rooms across all levels
- `get_outline(layout)` — outline from level_01 or top-level

### reason
LLM reads layout summary + tool catalog. Decides: answer directly, call tag_and_audit, or defer to evaluate. Never calculates. Message history capped at 4 messages. Knows that removing a lower-level column creates a transfer beam (not blocked).

### modify
Two roles:
1. Executes MCP tool calls from reason (or calls `generate_structure` directly for tag_and_audit)
2. Dispatches `pending_structural_change` from evaluate:
   - `tier_upgrade` — applies new material tier to all elements (all levels)
   - `material_switch` — switches base material (all levels)
   - `upgrade_element` — single element section upgrade (all levels with same ID)
   - `midspan_column` — splits beam, inserts column at midpoint
   - `auto_upgrade_beams` — loops up to 6 passes until all beams pass
   - `auto_upgrade_columns` — same for columns
   - `find_minimum` — applies XS then upgrades element by element to first PASS
   - `remove_element` — removes column or beam; multilevel-aware; perimeter elements (columns AND beams) are locked at every level
   - `remove_elements` — batch version

Key fixes:
- Merged beam after column removal gets `"length"` updated to combined span (`math.dist(far1, far2)`), not the original stale value.
- Perimeter beams now locked in removal path (previously only perimeter columns were checked). Check runs for both multilevel and single-level paths.
- `UnicodeEncodeError` from `→` character in print statements (Windows cp1252 stdout) fixed — all `→` replaced with `->` across modify.py, evaluate.py, and comparison.py.
- Defensive check after `remove_element`: prints WARNING if element is still present after removal (detects silent failure).

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

**Cost history:** Each modify→cost_flex cycle appends to `state["cost_history"]`. The evaluation report shows a **Cumulative Modification Cost** table when more than one cycle ran, with per-cycle breakdown and total EUR. Each history entry now includes `total_build_cost_eur` (total structural frame cost at that cycle) — used by the comparison node to show previous→current cost delta.

**Cost in layout JSON:** The returned layout JSON carries `analysis.structure_cost` with the full cost_flexibility dict from the last cycle — available to the orchestrator without reading the report file.

**Multilevel cost fix (session 3):** `_detect_changes._struct_map` and the `cost_flexibility_node` both previously called `.get("structure", [])` on the top-level layout dict — which returns `[]` for multilevel layouts. This caused total build cost to show EUR 0 and all diffs to appear empty ("No structural changes") on any multilevel layout. Fix: both now check for a `"levels"` key and flatten all `levels.level_XX.structure` lists. The outline is taken from the first (ground) level.

### evaluate
Pure calculations, no mutations. Runs:
- Beam checks: bending, shear, LL deflection (L/360), TL deflection (L/250)
- Column checks: compressive stress, Euler buckling (SF ≥ 3.0)
- Multilevel: per-level checks with `load_multiplier` scaling for columns
- Transfer beam check: when removing lower-level column with upper column above (UDL + point load); uses the **shallower** of the two merging beams for a conservative section check
- Cascade check: when removing upper-level column, lower-level columns re-checked with extra load
- What-if column removal simulation (span extension + re-check; transfer beam pre-pass for multilevel)
- LLM advisor (`_interpret_evaluation`) with pre-computed removal hints and transfer beam data
- Unified "what next?" menu when structure passes
- Failure menu when structure fails (auto-upgrade, per-element, midspan column, material switch)
- **Report header always shows Layout ID**

Null material handling: `attrs.get("material") or "RCC"` — explicit `null` in JSON falls through to RCC default (pre-assignment state).

**LLM Advisor (`_INTERPRET_SYSTEM`) — session 2 additions:**
- **Design intent framing:** elements above 75% are called "load-path critical"; transfer beams are called "structurally defining" regardless of utilisation; advisor distinguishes "safe to remove" from "load-path critical even if lightly stressed".
- **Transfer beam surfacing:** `_interpret_evaluation` now includes a `transfer_beams` list in the summary dict (id, span, upper-column load in kN, utilisation). `_format_summary_for_llm` renders them in a dedicated section. The LLM is instructed never to suggest removing a transfer beam.
- **Level-by-level framing:** when transfer beams or multiple levels are present, advisor addresses ground-level load paths first, then upper-level elements.
- **Tradeoffs:** advisor explicitly names the relevant tradeoff (safety vs adaptability, adaptability vs cost, safety vs cost) for each observation.

Human-in-loop prompts:
1. Material selection — shows actual sections from live layout (not hardcoded defaults)
2. Floor build-up SDL (1.5 / 2.5 / 3.5 / 5.0 kN/m²)
3. Usage type LL (2.0 / 3.0 / 5.0 kN/m²)

### tag_and_audit
Structural grid generator. For multilevel layouts:
1. Generates the master column grid from `level_01` outline/rooms (same as single-level)
2. For each upper level, resolves the outline in priority order: (a) explicit `outline` in JSON, (b) convex hull of that level's `rooms[].geometry` points, (c) fallback to `level_01` outline
3. Filters columns to each upper level's outline via Shapely polygon containment
4. Perimeter / internal type assigned per level based on upper outline boundary
5. Beams filtered: both endpoints must be within the upper-level column set
6. Grid options are applied consistently across all levels

### comparison
Diffs `layout_before_change` vs current layout. Uses `get_structure()` to flatten multilevel. Groups changes by pattern. LLM writes 2–3 sentences with design meaning and one next-step suggestion. Fallback to built-in summary if LLM unavailable.

**Session 2 additions:**
- **Cost delta:** when `state["cost_history"]` has ≥2 entries, the LLM context includes `"Cost delta: previous total X EUR -> current total Y EUR (±Z EUR)"` so the comparison can quote before/after build cost explicitly. `cost_history` entries now include `total_build_cost_eur` (from `cost_flexibility.py`).
- **Tradeoff framing:** `SYSTEM_PROMPT` instructs the LLM to name at least one tradeoff (safety vs adaptability, adaptability vs cost, safety vs cost) in every comparison summary.

---

## Section-Persistence Fix

**Problem:** `apply_material_override()` reset ALL element sections to material defaults on every evaluate pass — even when just pressing Enter to keep the same material. Individually upgraded beams (e.g. 120×300) were silently overwritten with defaults (100×240).

**Fix (evaluate.py):** Skip `apply_material_override` when all elements already carry the target material:

```python
_existing_mats = {
    ((el.get("attributes") or {}).get("material") or "RCC").upper()
    for el in _gs_mat(json.loads(state["layout_json_string"]))
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
| `main.py` | CLI entry | ~41 |
| `graph.py` | LangGraph orchestration, routing, V4 report writer | ~673 |
| `nodes/_layout.py` | Multilevel utility — format detection, structure access, load multipliers | ~130 |
| `nodes/reason.py` | LLM reasoning + tool routing | ~153 |
| `nodes/evaluate.py` | Structural checks + HitL menus + advisor + transfer/cascade | ~1,920 |
| `nodes/modify.py` | Section constants + mutations + dispatch + multilevel remove | ~719 |
| `nodes/comparison.py` | Before/after diff + LLM summary | ~183 |
| `nodes/cost_flexibility.py` | V4 three-pillar cost model | ~1,349 |
| `nodes/tag_and_audit.py` | Structural grid generator (single + multilevel) | ~869 |
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

---

## Known Limitations

- **Total Structure Build Cost** is structural frame only (beams + columns), not full building.
- `app.py` Streamlit UI is a standalone prototype — not connected to the main agent graph.
- Material is global across all levels — per-level material selection not supported (by design: one material for simplicity).

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
11. Single-level and multilevel layouts handled by the same pipeline via `nodes/_layout.py`
12. Perimeter elements (columns AND beams) are locked at every level; cross-level column removal creates a transfer beam
13. Advisor names design intent (load-path critical, structurally defining) not just pass/fail — and always names the relevant tradeoff
14. Transfer beams are surfaced by name in the advisor with the upper-column load they carry
15. Cost delta (previous total → current total build cost) shown in comparison when ≥2 cycles have run
16. Cost node handles multilevel by flattening elements from all levels — never uses top-level `.get("structure", [])` which returns `[]` on multilevel layouts
