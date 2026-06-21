# Structural Agent — CLI & Team Handoff Summary

*Team 01 · AIA26 Studio · June 21 2026*

## What this is about (in one line)

We gave our agent a clean "front door" so the orchestrator can run it
automatically, hand it a floor plan, and read back our answer.

## Why we need it

The agent was interactive — a person types into it. The orchestrator
is a program, not a person. A program needs:

1. A fixed way to **send** input (the instruction + the floor plan).
2. A fixed way to **read** output (our reply + the edited floor plan).

That fixed input/output shape is the CLI (command-line interface).

## What we implemented

### 1. `main.py` — new front door

Switched from one positional argument to two named flags:

```
python main.py --prompt "evaluate structure as TIMBER for residential use"
python main.py --prompt "tag and audit" --layout_json '{ ... }'
```

- `--prompt` (required) — the instruction.
- `--layout_json` (optional) — the floor plan as a JSON string.
- Accepts both **single-level** and **multilevel** layout JSON (see formats below).
- Bad JSON fails loudly with exit code 1 instead of crashing later.
- MCP connection close is now guarded — no crash when MCP isn't running.
- Output is stable and machine-readable:

```
Final Response:
<agent reply>

Edited Layout JSON:
<full layout JSON with structure, or "No layout changes">
```

### 2. `graph.py` — use the incoming layout, return the edited one

- When `--layout_json` is provided, it wins over the saved file on disk
  and the layout picker menu is skipped entirely — fully headless.
- `run_agent()` now returns `(response_text, edited_layout_json_string)`
  so the orchestrator gets both the text reply and the updated floor plan.
- Layout picker and grid option picker both use safe defaults in headless mode.

### 3. `evaluate.py` — headless-safe prompts with prompt-driven defaults

All `input()` calls replaced with `_safe_input()`. When stdin is not a
terminal (orchestrator mode), defaults are used silently:

| Prompt | Headless default |
|--------|-----------------|
| Material | Keep current (from settings or layout) |
| Floor build-up (SDL) | Keep current |
| Live load (LL) | Keep current |
| Tier upgrade offer | `y` — auto-upgrade |
| Column removal confirm | `n` — don't remove |
| Beam removal confirm | `n` — don't remove |
| Pass menu | Enter — return results as-is |
| Failure menu | `1` — auto-upgrade all failing elements |

**Prompt-driven overrides:** material, SDL, and LL can be set via natural
language in the `--prompt` string. The agent reads keywords before showing
the menu, so in headless mode these are picked up automatically:

```
--prompt "evaluate as STEEL for office use"
→ material: STEEL, LL: 3.0 kN/m²

--prompt "evaluate structure as TIMBER for residential with heavy floor"
→ material: TIMBER, SDL: 5.0 kN/m², LL: 2.0 kN/m²

--prompt "evaluate for retail use"
→ LL: 5.0 kN/m², material: keep current
```

Keywords detected:
- **Material**: `RCC`, `STEEL`, `TIMBER` (exact word match)
- **SDL**: `light timber/wood floor` → 1.5 | `light concrete` → 2.5 | `standard` → 3.5 | `heavy floor/slab` → 5.0
- **LL**: `residential/apartments/homes/domestic` → 2.0 | `office/offices/workplace` → 3.0 | `retail/shop/public/commercial` → 5.0

Interactive use is **unchanged** — all prompts appear and wait for keyboard
input when run from a terminal.

---

## Layout Formats Accepted

### Single-level
```json
{
  "layoutId": "Layout-2BHK-01",
  "outline": [[0,0], [10,0], ...],
  "rooms": [...],
  "structure": [...]
}
```

### Multilevel
```json
{
  "layoutId": "Layout-2BHK-01",
  "levels": {
    "level_01": {
      "outline": [...], "rooms": [...], "structure": [...]
    },
    "level_02": {
      "outline": [...], "rooms": [...], "structure": [...]
    }
  }
}
```

Both formats go through the same pipeline. The agent detects the format
automatically. All structural operations (evaluate, remove, upgrade, tag and audit)
work on either format with no change to the prompt.

**Multilevel structural rules the orchestrator should know:**
- Column loads accumulate downward: ground floor carries load from all floors above
- Perimeter columns/beams are locked at every level
- Removing a lower-floor column when an upper-floor column sits above it creates a **transfer beam** (allowed — the what-if simulation handles it)
- One material applies to all levels (no per-level material selection)
- The evaluation report header always shows the layout ID

---

## How we work with the other teams

| Direction | Team | What flows | Where it lives |
|-----------|------|-----------|----------------|
| Input | Use / Inhabit | The floor plan (rooms, outline, doors, etc.) | We receive it via `--layout_json` |
| Output | Everyone | The final floor plan **with our structure added** | The JSON we print back |

**Our minimum requirement on the incoming layout:**
- `outline` (polygon of the floor footprint) — required for grid generation
- `rooms` (array of room objects with corners) — required for element naming
- For multilevel: each level needs its own `outline` and `rooms`
- We only add/edit the `structure` array — we never touch rooms, doors, or windows

---

## What's still to do

- [ ] Pin versions in `app_requirements.txt` (`langgraph`, `langchain-openai`).
- [ ] Confirm layout schema with Use/Inhabit team (`outline` + `rooms` required at each level for multilevel; outline can now be omitted if rooms are present — derived automatically).
- [ ] Later: let heritage status and floor level come from the orchestrator
      instead of only our local settings file.

## What's done (resolved limitations)

- [x] `analysis.structure_cost` is now injected into the returned layout JSON — cost data travels with the layout to the orchestrator.
- [x] Cumulative modification cost tracked across upgrade cycles — evaluation report shows per-cycle breakdown and EUR total when more than one cycle ran.
- [x] Upper-level outlines derived automatically from room geometry if `outline` key is absent — orchestrator does not need to pre-compute footprints for upper levels.
- [x] Transfer beam check uses the shallower of the two merging beams — conservative section capacity, not arbitrary first-found.
- [x] **Perimeter beam lock** — perimeter beams are now locked in the removal path at every level (previously only perimeter columns were blocked).
- [x] **Advisor design intent** — advisor now says what the architect should preserve or reconsider, not just pass/fail. Elements above 75% are "load-path critical"; transfer beams are called "structurally defining."
- [x] **Transfer beams surfaced in advisor** — each transfer beam is named with its span, upper-column load (kN), and utilisation. The LLM is instructed never to suggest removing one.
- [x] **Level-by-level framing** — advisor addresses ground-level load paths first, then upper-level elements, whenever transfer beams or multilevel data are present.
- [x] **Tradeoff language** — advisor and comparison summary explicitly name the tradeoff created by each design decision (safety vs adaptability, adaptability vs cost, safety vs cost).
- [x] **Cost delta in comparison** — after ≥2 modify cycles, the comparison summary includes previous total → current total build cost (± EUR). `cost_history` entries now carry `total_build_cost_eur` per cycle.
- [x] **Windows encoding fix** — `→` characters in print statements caused silent `UnicodeEncodeError` on Windows cp1252 stdout (piped/headless contexts), leaving layout changes uncommitted. All `→` replaced with `->` across modify.py, evaluate.py, and comparison.py.
- [x] **Multilevel cost fix** — `cost_flexibility.py` was calling `.get("structure", [])` on the top-level layout dict, which returns `[]` for multilevel layouts (structure lives under `levels.level_01.structure` etc.). Both `_detect_changes` and the node's element extraction now flatten all levels. Before this fix: total build cost showed EUR 0 and all modification costs showed "No structural changes" for any multilevel layout.
- [x] **Transfer beam point load breakdown** — `[TRANSFER]` line in the what-if output now shows the split between load from the upper-floor column and load from perpendicular framing beams: `P=21.2kN (12.6 col + 8.6 framing)@1.3m`. When no perpendicular framing exists the format stays compact: `P=X.XkN@Y.Ym`. Both components stored in the result dict as `transfer_upper_col_kN` and `transfer_perp_kN`.
