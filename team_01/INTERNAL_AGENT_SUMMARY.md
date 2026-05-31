# Structural Design Agent — Summary

## What it is

A conversational structural design agent for early architectural decision-making. The architect types a plain-language instruction — "add a structural grid", "what if we remove column C_2", "evaluate the layout" — and the agent reasons about consequences, runs structural calculations, modifies the layout if needed, and returns a written response with a full evaluation table.

It is built on LangGraph, connects to a Grasshopper MCP server for geometry tools, and uses an LLM only for reasoning and communication — all structural mathematics is computed directly in Python, not by the model.

---

## Pipeline

The agent runs as a directed graph with four nodes:

```
CLI prompt --> bootstrap() --> run_agent()
                                    |
               +-------- reason --------+
               |    LLM decides:        |
               |  answer OR call tool   |
               +------------------------+
                        | tool called?
         YES (tag_and_audit) --> modify --> evaluate --> END  (confirmation only)
         YES (other tool)    --> modify --> evaluate --> comparison --> reason (max 2 cycles)
         NO                  -->            evaluate --> END  (direct — no redundant reason call)

         Structural change chosen at evaluate menu:
         evaluate (sets pending_structural_change) --> modify --> evaluate --> comparison --> reason
         (repeats until PASS or user presses Enter)
```

**Reason** — the LLM reads the current layout summary and tool catalog. It decides whether to answer directly or call a tool. It never invents geometry — it works only with element IDs and attributes that exist in the JSON.

**Modify** — two roles: (1) sends GH MCP tool calls from reason; (2) executes structural changes packaged by evaluate (`pending_structural_change`). Owns all section constants and mutation functions. Sets `came_from` to `"tag_and_audit"`, `"modify"`, or `"structural_change"` for routing.

**Evaluate** — calculations only. No mutations. If `came_from == "tag_and_audit"`, returns immediately. Otherwise: runs first-principles checks, prompts for material + tier upgrade, shows alternatives menu. Each chosen option packages a `pending_structural_change` dict and returns — the graph routes back to modify for execution.

**Comparison** — runs after every modify/structural-change cycle. Uses `layout_before_change` as the before-snapshot when `came_from == "structural_change"`, prints the diff, then asks the LLM to summarise. Increments the cycle counter (max 2 LLM cycles).

---

## Human-in-the-Loop Interactions

### 1. Material selection (every evaluate pass, skipped only after structural changes)

```
Material (current: RCC_L [L tier]):
  1. RCC    — beam 300x600mm | col 300x300mm  <-- active [L tier]
  2. STEEL  — beam 82x160mm  | col 100x100mm
  3. TIMBER — beam 100x240mm | col 100x100mm
  4. Find minimum — start XS, auto-upgrade to first PASS
  [Enter] — keep current
Choice [1/2/3/4 or RCC/STEEL/TIMBER]:
```

Option 4 (Find minimum): applies XS tier sections, then auto-upgrades each failing element one step at a time until all pass. The entire loop runs atomically inside modify.py (using the injected `evaluate_fn`).

**Auto-detect**: if the user's prompt explicitly names a material ("find minimum sections for steel"), the material picker is skipped entirely — the agent prints `[auto] Find minimum sections for STEEL` and jumps straight to SDL/LL.

### 2. Load selection (every evaluate pass — asked immediately after material)

```
Superimposed dead load (SDL) [current: 3.5 kN/m²]:
  1. Timber  — 1.5 kN/m²  (wood structure + light finishes)
  2. Light   — 2.5 kN/m²  (lightweight slab, minimal finishes)
  3. Standard— 3.5 kN/m²  (125mm slab + finishes + partitions)
  4. Heavy   — 5.0 kN/m²  (thick slab, heavy finishes, raised floor)
  [Enter] — keep current
SDL choice [1-4 or Enter]:

Live load (use type) [current: 2.0 kN/m²]:
  1. Residential — 2.0 kN/m²
  2. Office      — 3.0 kN/m²
  3. Retail/Public— 5.0 kN/m²
  [Enter] — keep current
LL choice [1-3 or Enter]:
```

Both values are stored in `AgentState` and saved to `team_01/team_01_settings.json` after each prompt. On the next `python main.py "..."` invocation, they are restored from disk — pressing Enter always keeps the last run's values, not hardcoded defaults.

### 3. Global section upgrade (on FAIL, one tier at a time — each accepted upgrade is one modify cycle)

```
Structural FAIL with STEEL. Upgrade to STEEL M (beam 100x200mm | col 120x120mm)?
Upgrade? [y/N]:
```

### 4. Alternatives menu (on any remaining FAIL)

Options are computed from actual failure data — no hallucinated IDs. Order:

```
Structural issues detected. Choose an action:
  1. Auto-upgrade 3 failing beams through section sizes until PASS
  2. Upgrade CD_1 from IPE160 to IPE200
  3. Add midspan column under beam CD_1 (span 6.0m → 3.0m each side)
  4. Switch all framing to TIMBER
  [Enter or text] — describe a custom change
Choice:
```

**Option 1 — Auto-upgrade beams** packages `{"type": "auto_upgrade_beams"}` → routes to modify, which loops up to 6 passes using `evaluate_fn` until all beams pass (not just one step). If still failing after the loop, the menu re-appears.

**Option 2 — Per-element upgrade** packages `{"type": "upgrade_element", "element_id": ..., "new_section": ...}` → same modify → evaluate → comparison cycle.

**Option 3 — Midspan column** packages `{"type": "midspan_column", "beam_id": ..., "material": ...}` → modify splits the beam and inserts a new column.

**Option 4 — Global material switch** packages `{"type": "material_switch", "material": ...}` → modify applies the new material to all elements.

**Auto-upgrade columns** appears as option 1 when only columns fail. Loops to PASS using the same `evaluate_fn` mechanism. All options also available for columns (per-element column upgrade uses `COL_SECTION_UPGRADE` / `COL_DIM_UPGRADE` chains).

Each option causes **one modify → evaluate → comparison cycle**. The menu re-appears on the next evaluate pass if failures remain. Enter with no input exits to the reason node with the current (possibly still-failing) layout.

### 5. Permanent element removal (after any what-if simulation)

```
What-if result: FAIL. Apply removal of C_2 permanently?
  Connected beams will be merged across the removed column.
Apply? [y/N]:

# or for a beam:
What-if result: PASS. Remove beam AB_1 permanently?
  Adjacent parallel beams will carry additional tributary load.
Remove? [y/N]:
```

Offered immediately after the what-if result, regardless of PASS/FAIL. On `y`: packages `{"type": "remove_element", "element_id": ...}` → modify → evaluate → comparison.

- **Column removal**: `remove_element` deletes the column, finds all beams touching its position, pairs collinear beams and merges each pair into one longer beam (using the first beam's ID and attributes). Dead-end beams with no collinear partner are also removed.
- **Beam removal**: simply deletes the beam from the structure array.

### 6. Optimize after PASS

```
All checks pass. Optimize — find minimum sufficient sections? [y/N]:
```

Offered once when all checks pass. Accepts `y` to reuse the `find_minimum` flow: applies XS sections then upgrades element by element until PASS — finds the smallest passing sections for the current load and material.

---

## First Principles Structural Calculations

### Loads

- **Self-weight** — material density × cross-section area × span
- **Superimposed dead load (SDL)** — user-selected per session: 1.5 / 2.5 / 3.5 (default) / 5.0 kN/m²
- **Live load (LL)** — user-selected per session: 2.0 (default, residential) / 3.0 (office) / 5.0 (retail) kN/m²

Both SDL and LL are stored in `AgentState` and propagated to all beam checks, column checks, what-if simulations, and auto-upgrade loops in that session.

Tributary widths for beams (half-spacing to nearest parallel beam). Voronoi-like tributary area for columns.

### Beam checks (four per beam)

| Check | Formula | Limit |
|-------|---------|-------|
| Bending stress | S = M/Wy, M = wL²/8 | allowable bending MPa |
| Shear stress | T = V/A, V = wL/2 | allowable shear MPa |
| Live-load deflection | d_LL = 5·w_LL·L⁴/(384·E·I) | L/360 |
| Total-load deflection | d_TL = 5·w_tot·L⁴/(384·E·I) | L/250 |

For Steel: A, I, Wy from real IPE property tables. For RCC/Timber: solid rectangle.

### Column checks (two per column)

| Check | Formula | Limit |
|-------|---------|-------|
| Compressive stress | S = P/A | allowable comp MPa |
| Euler buckling | SF = P_cr/P, P_cr = pi²·E·I_min/Le², Le=0.65H | SF ≥ 3.0 |

For Steel HSS: I_min and r from real section property tables.

### What-if simulation

**Column removal:** Traces the beam chain from the removed column's endpoint through any other removed positions to the nearest remaining column, giving an extended effective span. Re-runs all four beam checks at the extended span. A what-if failure propagates to `summary.overall_PASS = False`.

**Beam removal:** No span-extension calculation — removing a beam eliminates a load path. The evaluate node shows a warning and offers permanent removal; adjacent beams' increased tributary load is revealed by the re-evaluation that follows.

---

## Material System

| Material | E (MPa) | Allow. bending | Allow. compression | Allow. shear | Standard |
|----------|---------|----------------|--------------------|--------------|---------|
| RCC | 31,000 | 14.2 MPa | 14.2 MPa | 2.8 MPa | EC2, C25/30 |
| Steel | 200,000 | 235 MPa | 235 MPa | 135.7 MPa | EC3, S235 |
| Timber | 8,000 | 12.3 MPa | 10.5 MPa | 1.1 MPa | EN338, C16 |

### Section tiers (6 tiers per material = 18 total)

```
_XS tier:  RCC 150x200mm / STEEL IPE120 / TIMBER 75x150mm  (find-minimum start)
Base:      RCC 200x300mm / STEEL IPE160 / TIMBER 100x240mm
_M tier:   RCC 250x450mm / STEEL IPE200 / TIMBER 120x300mm
_L tier:   RCC 300x600mm / STEEL IPE240 / TIMBER 150x360mm
_XL tier:  RCC 350x700mm / STEEL IPE300 / TIMBER 200x480mm
_XXL tier: RCC 400x800mm / STEEL IPE360 / TIMBER 250x600mm
```

Global upgrade chain: RCC_XS → RCC → RCC_M → RCC_L → RCC_XL → RCC_XXL  
(same pattern for STEEL and TIMBER)

Per-element upgrade chains (BEAM_DIM_UPGRADE / BEAM_SECTION_UPGRADE):
- RCC:    150x200 → 200x300 → 250x450 → 300x600 → 350x700 → 400x800
- Steel:  IPE120 → IPE160 → IPE200 → IPE240 → IPE300 → IPE360
- Timber: 75x150 → 100x240 → 120x300 → 150x360 → 200x480 → 250x600

---

## LLM Reasoning Rules

### tag_and_audit
Always call with `typology="column_grid"` and `grid_spacing=4.0` unless user specifies otherwise. Call only when `structure_count=0`. Never call if `structure_count > 0`.

### What-if removal (two-step)
Step 1: User asks "what if we remove X" → `action="final"`, `final_response=""`. Evaluate runs the simulation.
Step 2: Evaluate appends "STRUCTURAL FAIL after removing…" → LLM writes three-option response using exact IDs from the message.

### Regular structural failure
LLM reads failing IDs from evaluation text and writes failure-type-specific options. Never invents element IDs.

### General questions
Answered directly from layout JSON. No tool call.

---

## Code Summary

### Unchanged from original template

| File | Lines | Notes |
|------|-------|-------|
| `main.py` | 28 | CLI entry point — untouched by design |
| `_runtime/llm.py` | 245 | LLM wrapper |
| `_runtime/mcp_client.py` | 82 | HTTP client to GH MCP server |
| `_runtime/config.py` | 142 | .env settings |
| `_runtime/bootstrap.py` | 60 | +2 lines framework fix (instructor) |
| `nodes/tools.py` | 81 | Legacy executor, minor logging only |

### Modified (existed in original)

| File | Original | Current | Net change |
|------|----------|---------|------------|
| `graph.py` | 122 | **396** | +274 net |
| `nodes/reason.py` | 57 | **133** | +76 net |

### Created from scratch

| File | Lines | Role |
|------|-------|------|
| `nodes/evaluate.py` | **1,034** | Structural calculations + HitL menus (no mutations) |
| `nodes/modify.py` | **617** | All constants, mutations, structural change dispatch |
| `nodes/comparison.py` | **135** | Layout diff + LLM summary |

### Grand total

| Category | Lines |
|----------|-------|
| Created new | **1,786** |
| Added to existing files (net) | **+350** |
| **Net new lines from template** | **~2,136** |
| Unchanged | ~638 |

---

### evaluate.py breakdown (971 lines — calculations + HitL menus)

| Section | Purpose |
|---------|---------|
| Imports from `nodes.modify` | All section tables, mutation functions, and `remove_element` |
| `MATERIALS` | RCC / Steel / Timber allowable stresses and E values (EC2/EC3/EN338) |
| `SDL_KNM2`, `LL_KNM2`, deflection limits | Default load constants (overridden by user selection) |
| `_beam_trib_widths` | Half-spacing tributary width geometry |
| `_column_trib_areas` | Voronoi-like tributary area per column |
| `_check_beams(…, ll_kNm2, sdl_kNm2)` | Bending, shear, LL deflection, TL deflection per beam |
| `_check_columns(…, ll_kNm2, sdl_kNm2)` | Compressive stress + Euler buckling per column |
| `_extract_removal_ids` | Regex extraction of removal intent from messages |
| `simulate_what_if_removal(…, ll_kNm2, sdl_kNm2)` | Beam chain trace + re-check at extended span |
| `evaluate_structure(…, ll_kNm2, sdl_kNm2)` | Public API — assembles full result dict |
| `_build_failure_alternatives` | Alternatives menu: auto-upgrade, per-element, midspan, global switch |
| `build_evaluate_node` | SDL+LL prompt, material prompt, HitL menus; what-if block handles columns (span simulation) and beams (warning only) separately; both offer permanent removal |

### modify.py breakdown (612 lines — constants + mutations + dispatch)

| Section | Purpose |
|---------|---------|
| `STEEL_BEAM_PROPS` / `STEEL_COL_PROPS` | Real IPE and HSS section property lookup tables |
| `DEFAULT_SECTIONS` | 18 material tiers (XS/S/M/L/XL/XXL × RCC/STEEL/TIMBER) |
| `SECTION_UPGRADE_MAP` | Global upgrade chain per material |
| `BEAM_SECTION_UPGRADE` / `COL_SECTION_UPGRADE` | Per-element Steel IPE + HSS chains |
| `BEAM_DIM_UPGRADE` / `COL_DIM_UPGRADE` | Per-element RCC/Timber upgrade chains |
| `apply_material_override` | Patches all structure elements with chosen material tier |
| `upgrade_element_section` | Single-element section upgrade (Steel IPE, RCC dims, Timber dims) |
| `add_midspan_column` | Splits beam at midpoint, inserts column, creates two half-beams |
| `apply_minimum_sections` | Applies XS tier to all elements (find-minimum start point) |
| `_upgrade_one_pass` | Upgrades each failing element one step (used by find-minimum loop) |
| `_pt_eq` | Point equality helper with tolerance (used by `remove_element`) |
| `remove_element` | Removes column (merges collinear beams through it) or beam from structure |
| `_generate_column_grid` | Python fallback grid generator when GH returns empty |
| `build_modify_node` | GH MCP tool calls + `pending_structural_change` dispatch (all 8 change types); auto_upgrade_beams/columns loop to PASS using `evaluate_fn(layout, ll, sdl)` |

### graph.py key changes (394 lines)

| Change | Purpose |
|--------|---------|
| `pending_structural_change: dict \| None` | New state field — evaluate packages a change, modify executes it |
| `layout_before_change: str \| None` | New state field — snapshot before a structural change for diff |
| `live_load_kNm2: float \| None` | New state field — user-selected LL, persists across all cycles |
| `sdl_kNm2: float \| None` | New state field — user-selected SDL, persists across all cycles |
| `_route_from_reason` with `_looks_like_eval` guard | If `final_response` is set for a Q&A, goes to END; if it was an eval request (keyword-matched), overrides to evaluate |
| `_route_from_evaluate` shortcut | Routes evaluate → END directly after a plain evaluation — removes redundant second reason call |
| `_route_from_evaluate` with `pending_structural_change` | Routes evaluate → modify when a change is queued |
| `came_from == "structural_change"` → comparison | Structural change cycles also run through comparison |
| `evaluate_fn=evaluate_structure` in `build_modify_node` | Enables atomic find-minimum and auto-upgrade loops in modify node |
| Per-element layout context | `beams` and `columns` arrays with id/material/section/span sent to LLM so it can answer questions directly |
| `_settings_load` + settings at startup | SDL/LL loaded from `team_01_settings.json` at `_build_initial_state` — persists across runs |
| Material persistence | Reads from `final_state["layout_json_string"]`, preserves per-element upgrades |
| `_write_evaluation_report` | Saves `team_01_evaluation_report.md` after every run |
| Before/after snapshot | Copies current JSON to `_before.json` at run start for IDE diff |

### reason.py key changes (133 lines)

| Change | Purpose |
|--------|---------|
| tag_and_audit defaults | Always pass `typology="column_grid"`, `grid_spacing=4.0` |
| Asymmetric message cap | First message (layout context): 2500 chars; subsequent messages: 400 chars — prevents layout context from being truncated |
| Evaluation routing rules in SYSTEM_PROMPT | Explicit instruction to output `final_response=""` for evaluation/structural requests — prevents local LLM from answering directly |

### comparison.py key changes (135 lines)

| Change | Purpose |
|--------|---------|
| `_slim_diff_for_llm` | Groups changes by section/material pattern and counts — replaces raw JSON diff (3000+ chars → ~200 chars) |
| `_fallback_summary` delegates to `_slim_diff_for_llm` | When LLM unavailable, shows grouped diff ("17x IPE120→IPE160") instead of "35 elements updated" |
| Compact `SYSTEM_PROMPT` | Reduced to single line to maximise token budget on local model |

---

## Example prompts

```
python main.py "add a structural grid to layout-1-large"
python main.py "evaluate the structural layout"
python main.py "what if we remove column C_2"
python main.py "what if we remove column B_3"
python main.py "what structural conflicts exist in the layout"
```

At material picker:  
`1` RCC · `2` STEEL · `3` TIMBER · `4` Find minimum · Enter to keep.

At tier upgrade prompt: `y` to upgrade one tier (runs one modify→evaluate→comparison cycle).

At alternatives menu: number to pick (each triggers one modify cycle), or free text to pass a custom instruction to the reason node.

---

## GH / MCP notes

- GH file: `team_01/gh/team_01_working.gh` must be open and running for `tag_and_audit` to return geometry
- If GH returns empty, `modify.py` falls back to Python grid generation automatically
- The `tag_and_audit` tool requires `typology` and `grid_spacing`; reason node always supplies defaults
- Other MCP tools (`delete_room_01`, `add_window_01`, `classify_element_permanence`) still require GH

---

## Design principles

1. **LLM for language, Python for numbers.** The LLM never calculates — it reads deterministic results and writes plain-language responses.
2. **No hallucinated IDs.** The reason prompt forbids inventing element IDs. The alternatives menu uses only IDs from actual failure data.
3. **Human in the loop at every decision point.** Material, SDL, LL, tier upgrade, failure response, and element removal are all interactive menus — asked once per session, stored in state.
4. **Every structural change goes through the full pipeline.** Modify applies mutations, evaluate re-calculates, comparison diffs and summarises. No inline mutations in evaluate.py.
5. **Clear separation of concerns.** `modify.py` = mutations + constants. `evaluate.py` = calculations + menus. `comparison.py` = diffs + LLM summary. `graph.py` = routing.
6. **Per-element control.** Upgrade a single failing beam, add a midspan column, remove a column or beam, or auto-upgrade all failing elements without touching passing ones.
7. **Find minimum mode.** Applies XS tier first, then upgrades element by element until PASS — finds the smallest passing section without manual iteration.
8. **Auto-upgrade loops to PASS.** `auto_upgrade_beams` and `auto_upgrade_columns` run up to 6 passes using `evaluate_fn` until all targeted elements pass — not just one step per cycle.
9. **What-if failure is a real failure.** A failing what-if simulation sets `summary.overall_PASS = False`, triggering the full alternatives menu just like a primary structural failure.
10. **What-if always offers permanent removal.** After any what-if simulation (PASS or FAIL, column or beam), the user is offered the option to apply the removal permanently — routes through the full modify → evaluate → comparison pipeline.
11. **Column removal merges beams.** `remove_element` pairs collinear beams through the removed column and merges each pair into one longer beam. Dead-end beams are also removed.
12. **Q&A bypasses evaluate.** When the reason node answers directly (general questions, layout queries), the graph skips evaluate entirely — no material/load prompts, no calculations.
13. **Layout context is per-element.** The LLM receives a compact per-element list (id, material, section, span) so it can answer questions about specific beams, columns, sections, and spans without a tool call.
14. **Material, SDL, LL, and per-element upgrades persist.** Stored in AgentState + embedded in layout JSON. Per-element upgrades survive global tier and material changes.
15. **GH fallback.** If Grasshopper returns empty, Python generates the column grid so the full pipeline still runs.
16. **tag_and_audit fast exit.** Grid generation skips evaluate, comparison, and reason — returns a single confirmation line immediately.
17. **Comparison never crashes.** If the LLM is unavailable (context overflow or error), comparison falls back to a built-in text summary so the pipeline always completes.
18. **Evaluation report saved per run.** `_write_evaluation_report` writes `team_01_evaluation_report.md` with timestamp, prompt, structural check table, and LLM comparison summary.
19. **_runtime/ and main.py are read-only.** All intelligence is in the five writable files: graph.py, reason.py, modify.py, evaluate.py, comparison.py.
20. **SDL/LL persist across sessions.** After each prompt, `_ask_sdl_ll` saves to `team_01_settings.json`. At startup, `_build_initial_state` loads them — Enter always keeps the last run's values.
21. **Evaluation routing is keyword-guarded in code.** `_looks_like_eval` checks the user's original prompt against `_EVAL_KEYWORDS` so structural requests always reach evaluate even when the local LLM bypasses it with a direct answer. `_get_user_request` is a shared helper used by both graph.py and evaluate.py.
22. **Plain evaluation ends at END directly.** `_route_from_evaluate` shortcuts to END when `evaluation_result is not None` and no structural change is pending — removes the redundant second reason LLM call from every plain evaluate run.
23. **GH timeout handled gracefully.** The MCP `call_tool` is wrapped in try/except; any network/timeout exception is treated as empty output and the Python column-grid fallback runs immediately.
