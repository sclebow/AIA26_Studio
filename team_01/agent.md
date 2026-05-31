# Permanence_OS — Structural Design Agent

## Description

Permanence_OS is a conversational structural design agent for early architectural decision-making. The architect types a plain-language prompt and the agent generates structural grids, runs first-principles calculations, proposes design modifications, and explains consequences — all without needing Grasshopper or MCP connected.

All structural mathematics runs directly in Python (no LLM calculations). The LLM is used only for reasoning, routing, and plain-language responses.

---

## What It Can Do

### 1. Generate a structural grid
Reads the floor plan walls and room corners, derives a column/beam grid, and presents layout options for the architect to choose from.

```
python main.py "tag and audit"
```

### 2. Evaluate the structure
Prompts for material, floor build-up, and usage type, then runs first-principles checks on every beam and column. Shows a full pass/fail table and an [Advisor] interpretation in plain language.

```
python main.py "evaluate the structural layout"
```

At the evaluation prompts:
- **Material**: RCC / STEEL / TIMBER / Right-size sections
- **Floor build-up**: Light timber (1.5) / Light concrete (2.5) / Standard (3.5) / Heavy (5.0) kN/m²
- **Usage**: Homes (2.0) / Offices (3.0) / Retail (5.0) kN/m²

### 3. Fix failing elements
When checks fail, the agent offers a numbered menu:
1. Increase all failing beams/columns to the next size — auto-loops until pass
2. Upgrade a specific element (e.g. beam A1-A3 from 200×300 to 225×350)
3. Add a midspan column under a failing beam
4. Switch all framing to a different material

The agent loops back through the checks automatically until the structure passes.

### 4. Optimise passing elements
When the structure passes, a unified menu offers:
1. **Right-size all sections** — starts at minimum (XS) and upgrades element by element to the smallest that still works
2. **Remove underutilised columns** — pre-computes whether removal is safe and what the span impact would be
3. **Remove underutilised beams** — flags redundant short connections
4. Multiple selections accepted (e.g. `2,4` or `2-5`)

Underutilisation thresholds: below 50% = over-engineered (suggest layout change). Above 75% = approaching limit (flag to architect).

### 5. What-if column removal
Simulates removing a column: traces connected beams to the nearest remaining support, re-evaluates the extended span, and shows whether the structure would still hold.

```
python main.py "what if we remove column C2"
```

### 6. Compare before and after
After every structural change (upgrade, removal, right-sizing), the agent shows exactly what changed and by how much — element by element — and writes an LLM summary of what the change means for the design.

### 7. Cost and flexibility analysis
After every modification:
- **Material cost** in USD (volume × rate: RCC $350/m³, Steel $12,000/m³, Timber $800/m³)
- **Flexibility score** 0–10 (how reversible the change is)
- **Disruption score** 0–10 (construction impact)
- **Spatial penalty** for mid-room column additions

### 8. Answer layout questions
Direct questions about the layout are answered without running any calculations.

```
python main.py "what rooms exist in this layout"
python main.py "which beam has the longest span"
```

---

## Structural Checks

| Check | Method | Limit |
|---|---|---|
| Beam bending | M = wL²/8, S = M/Wy | Material allowable MPa |
| Beam shear | T = V/A, V = wL/2 | Material allowable MPa |
| Beam deflection (live) | 5wL⁴/384EI | L/360 |
| Beam deflection (total) | 5wL⁴/384EI | L/250 |
| Column stress | P/A | Material allowable MPa |
| Column buckling | SF = P_cr/P | SF ≥ 3.0 |

Materials: RCC (EC2 C25/30), Steel (EC3 S235), Timber (EN338 C16)

---

## Section Tiers

| Tier | RCC beam | RCC col | Steel beam | Steel col | Timber beam | Timber col |
|---|---|---|---|---|---|---|
| XS | 150×200 | 150×150 | IPE120 | HSS80×80×5 | 75×150 | 90×90 |
| S (default) | 175×250 | 175×175 | IPE160 | HSS100×100×6 | 100×240 | 100×100 |
| M | 200×300 | 200×200 | IPE200 | HSS120×120×6 | 120×300 | 120×120 |
| L | 225×350 | 225×225 | IPE240 | HSS150×150×6 | 150×360 | 150×150 |
| XL | 250×400 | 250×250 | IPE300 | HSS180×180×8 | 200×480 | 200×200 |
| XXL | 275×450 | 275×275 | IPE360 | HSS200×200×8 | 250×600 | 250×250 |

---

## Test Prompts

```
python main.py "tag and audit"
python main.py "evaluate the structural layout"
python main.py "what if we remove column C2"
python main.py "what structural elements exist in this layout"
python main.py "which beam has the longest span"
```

---

## Output Files

| File | Contents |
|---|---|
| `team_01_edited_layout.json` | Current layout with structure |
| `team_01_edited_layout_before.json` | Snapshot before last run |
| `team_01_evaluation_report.md` | Analysis parameters, structural table, change summary, cost/flexibility |
| `team_01_settings.json` | Saved SDL and live load from last run |
| `output/*.png` | Structural grid diagrams (one per layout option) |

---

## Runs Without Grasshopper

`tag and audit`, `evaluate`, and all optimisation flows work without Grasshopper running. MCP is only needed for `delete_room`, `add_window`, and other geometry tools. To re-enable MCP, uncomment four lines in `_runtime/bootstrap.py`.
