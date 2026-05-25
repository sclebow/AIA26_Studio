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
         NO                  -->            evaluate --> reason --> END
```

**Reason** — the LLM reads the current layout summary and tool catalog. It decides whether to answer directly or call a tool. It never invents geometry — it works only with element IDs and attributes that exist in the JSON.

**Modify** — sends the tool call to the Grasshopper MCP server and saves the result to disk. If GH returns empty for `tag_and_audit`, a Python fallback generates the column grid directly from the layout outline. Sets `came_from` to distinguish `tag_and_audit` from other tool calls.

**Evaluate** — the structural calculation node. No LLM. If `came_from == "tag_and_audit"`, returns a single confirmation line and exits immediately. Otherwise: runs first-principles checks on every beam and column, including human-in-the-loop material selection, section upgrade offers, per-element upgrade options, auto-upgrade loop, midspan column insertion, and a global material switch.

**Comparison** — runs only after non-tag_and_audit modify cycles. Computes a diff of what changed and asks the LLM to summarise it in plain language. Increments the cycle counter (max 2 cycles).

---

## Human-in-the-Loop Interactions

### 1. Material selection (always, first evaluate pass only)

```
Material (current: RCC):
  1. RCC    — beam 200x300mm | col 200x200mm  <-- active
  2. STEEL  — beam 82x160mm  | col 100x100mm
  3. TIMBER — beam 100x240mm | col 100x100mm
  [Enter] — keep current
Choice [1/2/3 or RCC/STEEL/TIMBER]:
```

### 2. Global section upgrade (on FAIL, loops through all tiers automatically)

```
Structural FAIL with STEEL. Upgrade to STEEL M (beam 100x200mm | col 120x120mm)?
Upgrade? [y/N]:
```

### 3. Alternatives menu (on any remaining FAIL)

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

**Option 1 — Auto-upgrade** loops through every failing beam, tries the next section in the chain, re-evaluates, and repeats until all beams pass or every beam has reached its top tier. Prints each step:
```
  Auto-upgrade CD_1: 100x240 → 120x300
  Auto-upgrade AB_2: 100x240 → 120x300
Re-evaluated: FAIL
  Auto-upgrade CD_1: 120x300 → 150x360
Re-evaluated: PASS
```

**Option 2 — Per-element upgrade** upgrades only the named failing beam/column to the next section without touching others.

**Option 3 — Midspan column** splits the failing beam at its midpoint and inserts a new column, creating two half-beams.

**Option 4 — Global material switch** replaces all framing elements with the chosen material's base sections and re-evaluates.

All four options are handled inline in Python — no LLM call, no tool call. The layout JSON is updated and re-evaluated immediately. The menu loops until PASS or the architect presses Enter to pass a custom instruction to the reason node.

---

## First Principles Structural Calculations

### Loads

- **Self-weight** — material density x cross-section area x span
- **Superimposed dead load** — 3.5 kN/m² (125mm slab + finishes + partitions, IS 875)
- **Live load** — 2.0 kN/m² (residential, IS 875 Part 2)

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

Traces the beam chain from a removed column's endpoint through any removed positions to the nearest remaining column, giving an extended effective span. Re-runs all four beam checks at the extended span.

---

## Material System

| Material | E (MPa) | Allow. bending | Allow. compression | Allow. shear | Standard |
|----------|---------|----------------|--------------------|--------------|---------|
| RCC | 25,000 | 8.5 MPa | 6.0 MPa | 2.8 MPa | IS 456, M25 |
| Steel | 200,000 | 165 MPa | 150 MPa | 100 MPa | IS 800, Fe250 |
| Timber | 12,500 | 12.0 MPa | 8.0 MPa | 1.5 MPa | IS 883, Group B |

### Section tiers (9 tiers + TIMBER_XL = 10 total)

```
Base:      RCC 200x300mm / STEEL IPE160 / TIMBER 100x240mm
_M tier:   RCC 250x450mm / STEEL IPE200 / TIMBER 120x300mm
_L tier:   RCC 300x600mm / STEEL IPE240 / TIMBER 150x360mm
_XL tier:  TIMBER only   — beam 200x480mm | col 200x200mm
```

Global upgrade chain: RCC → RCC_M → RCC_L | STEEL → STEEL_M → STEEL_L | TIMBER → TIMBER_M → TIMBER_L → TIMBER_XL

Per-element upgrade chains (BEAM_DIM_UPGRADE / BEAM_SECTION_UPGRADE):
- RCC:    100x240 → 250x450 → 300x600
- Steel:  IPE160 → IPE200 → IPE240
- Timber: 100x240 → 120x300 → 150x360 → 200x480

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

| File | Original | Current | Lines added |
|------|----------|---------|-------------|
| `graph.py` | 122 | **285** | +226 added, −62 removed |
| `nodes/reason.py` | 57 | **123** | +93 added, −26 removed |

### Created from scratch

| File | Lines | Role |
|------|-------|------|
| `nodes/evaluate.py` | **1,111** | All structural intelligence |
| `nodes/modify.py` | **157** | MCP tool call + Python grid fallback |
| `nodes/comparison.py` | **87** | Layout diff + LLM summary |

### Grand total

| Category | Lines |
|----------|-------|
| Created new | **1,355** |
| Added to existing files | **+319** |
| Removed from existing files | −88 |
| **Net new lines written** | **~1,586** |
| Unchanged | ~830 |

---

### evaluate.py breakdown (1,111 lines)

| Section | Purpose |
|---------|---------|
| `MATERIALS` | RCC / Steel / Timber allowable stresses and E values |
| `STEEL_BEAM_PROPS` / `STEEL_COL_PROPS` | Real IPE and HSS section property lookup tables |
| `DEFAULT_SECTIONS` | 10 material tiers including TIMBER_XL |
| `SECTION_UPGRADE_MAP` | Global upgrade chain per material |
| `BEAM_SECTION_UPGRADE` | Per-element Steel IPE chain (IPE160→IPE200→IPE240) |
| `COL_SECTION_UPGRADE` | Per-element HSS chain |
| `BEAM_DIM_UPGRADE` | Per-element RCC/Timber beam dim chain (fixed keys to match actual labels) |
| `COL_DIM_UPGRADE` | Per-element RCC/Timber column dim chain + TIMBER_XL entry |
| `_beam_trib_widths` | Half-spacing tributary width geometry |
| `_column_trib_areas` | Voronoi-like tributary area per column |
| `_check_beams` | Bending, shear, LL deflection, TL deflection per beam |
| `_check_columns` | Compressive stress + Euler buckling per column |
| `_extract_removal_ids` | Regex extraction of removal intent |
| `simulate_what_if_removal` | Beam chain trace + re-check at extended span |
| `evaluate_structure` | Public API — assembles full result dict |
| `_apply_material_override` | Patches all structure elements with chosen material |
| `_upgrade_element_section` | Single-element section upgrade (Steel IPE, RCC dims, Timber dims) |
| `_add_midspan_column` | Splits beam at midpoint, inserts column, creates two half-beams |
| `_switch_element_material` | Changes one element's material + section |
| `_auto_upgrade_failing_beams` | Loops through all failing beams, tries each next section until PASS |
| `_build_failure_alternatives` | Alternatives menu: auto-upgrade, per-element, midspan, global switch |
| `build_evaluate_node` | Full evaluate node with all human-in-the-loop interactions |

### modify.py key additions (157 lines)

| Addition | Purpose |
|---------|---------|
| `_generate_column_grid` | Python fallback grid generator when GH returns empty |
| `last_tool` tracking | Sets `came_from = "tag_and_audit"` vs `"modify"` for routing |
| Empty output guard | Calls Python fallback instead of leaving layout unchanged |

### graph.py key changes (285 lines)

| Change | Purpose |
|--------|---------|
| `came_from == "tag_and_audit"` → END | Skips evaluate pipeline after grid generation |
| `_route_from_evaluate` + END mapping | Routes to END when tag_and_audit ran |
| Unicode replacements | S/d/T instead of σ/δ/τ — avoids ASCII encoding errors |
| Material persistence | Reads from `final_state["layout_json_string"]`, preserves per-element upgrades |
| `attrs.pop("section", None)` | Clears stale Steel section attribute when switching to Timber/RCC |

### reason.py key changes (123 lines)

| Change | Purpose |
|--------|---------|
| tag_and_audit defaults | Always pass `typology="column_grid"`, `grid_spacing=4.0` |

---

## Example prompts

```
python main.py "add a structural grid to layout-1-large"
python main.py "evaluate the structural layout"
python main.py "what if we remove column C_2"
python main.py "what if we remove column B_3"
python main.py "what structural conflicts exist in the layout"
```

At material picker: `1` RCC · `2` STEEL · `3` TIMBER · Enter to keep.
At alternatives menu: number to pick, or free text for a custom instruction.

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
3. **Human in the loop at every decision point.** Material, tier upgrade, and failure response are all interactive menus.
4. **Per-element control.** The architect can upgrade a single failing beam, add a midspan column, or run auto-upgrade through the size chain without affecting the rest of the structure.
5. **Auto-upgrade loop.** When multiple beams fail, a single selection cycles through all failing elements and all available section sizes automatically.
6. **Material persists across modify cycles.** Stored in AgentState, written to JSON after the graph completes. Per-element upgrades are preserved (not overwritten by the global tier).
7. **GH fallback.** If Grasshopper returns empty, Python generates the column grid so the full pipeline still runs.
8. **tag_and_audit fast exit.** Grid generation skips evaluate, comparison, and reason — returns a single confirmation line immediately.
9. **_runtime/ is read-only.** All intelligence is in the five writable files.
