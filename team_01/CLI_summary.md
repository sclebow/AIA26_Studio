# Structural Agent — CLI & Team Handoff Summary

*Team 01 · AIA26 Studio · June 7 2026*

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

All 9 `input()` calls replaced with `_safe_input()`. When stdin is not a
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

## How we work with the other teams

| Direction | Team | What flows | Where it lives |
|-----------|------|-----------|----------------|
| Input | Use / Inhabit | The floor plan (rooms, outline, doors, etc.) | We receive it via `--layout_json` |
| Output | Everyone | The final floor plan **with our structure added** | The JSON we print back |

**Our minimum requirement on Use/Inhabit:** their floor plan must include
`outline` (so we can build the grid) and `rooms` (so we can name things).
We only add/edit the `structure` array — we don't touch rooms or doors.

## What's still to do

- [ ] Inject `analysis.structure_cost` into the returned JSON so cost data
      travels with the layout (currently only in the evaluation report).
- [ ] Pin versions in `app_requirements.txt` (`langgraph`, `langchain-openai`).
- [ ] Confirm layout schema with Use/Inhabit team (`outline` + `rooms` required).
- [ ] Later: let heritage status and floor level come from the orchestrator
      instead of only our local settings file.
