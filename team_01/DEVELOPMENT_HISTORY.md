# PermanenceOS-UI — Development History

> Auto-generated on 2026-06-08 from Claude Code session logs.
> Covers all Claude-assisted sessions from project setup through UI overhaul.

---

## Project Overview

**PermanenceOS-UI** is the AIA 2026 Studio project for **team_01**.
A conversational structural design agent for early architectural decision-making.
The architect types plain-language instructions; the agent reasons about structural
consequences, runs first-principles calculations, modifies the layout if needed,
and returns a written response with a full evaluation table.

| Tech stack | Python 3.10+, LangGraph, LangChain, Streamlit 1.57.0 |
| LLM backends | Cloudflare (default/free), OpenAI, Google, Anthropic, LM Studio |
| Optional GH | Grasshopper + Swiftlet MCP server (Python fallback for all tools) |

---

## Project File Structure

```
PermanenceOS-UI/
├── .env / .env.example             # LLM provider config
├── requirements.txt                # langgraph, langchain-anthropic, httpx, etc.
├── layout_input/layout_schema.json # shared input floor plan (14×10m "Family Rectangle")
├── team_01_edited_layout.json      # agent output (written after each run)
├── layout_viewer.html              # browser viewer for layout JSON
├── mcp.example.json                # template MCP config (gitignored actual)
├── examples/                       # reference parallel agent example
└── team_01/
    ├── AGENT_SUMMARY.md            # detailed design doc
    ├── gh/                         # Grasshopper files + other layout variants
    └── python/                     # the agent
        ├── app.py                  # Streamlit UI (~3200+ lines) — main work target
        ├── main.py                 # CLI entry point
        ├── graph.py                # LangGraph StateGraph
        ├── nodes/
        │   ├── reason.py           # LLM reasoning node
        │   ├── tools.py            # local action executor
        │   ├── evaluate.py         # first-principles structural calculations (~1111 lines)
        │   ├── modify.py           # thin wrapper delegating to tools.py
        │   ├── comparison.py       # layout diff + LLM summary
        │   ├── tag_and_audit.py    # generate_structure() — produces column/beam grids
        │   └── structural_grid.py  # local grid generation (RCC/Steel/Timber)
        ├── _runtime/
        │   ├── bootstrap.py        # builds Context (llm, tools, paths)
        │   ├── config.py           # loads .env and mcp.json
        │   ├── llm.py              # OpenAI-compatible chat wrapper
        │   └── mcp_client.py       # HTTP MCP client (legacy remote path)
        └── example_layouts/        # sample complex layouts used as agent context
```

> **Note:** Teams 02–06 folders were deleted locally (no commit). Team_01 has zero dependencies on them.

---

## Agent Graph (LangGraph StateGraph)

```
START → reason → modify → evaluate → comparison → reason (max 2 cycles) → END
              ↓                  ↓
           evaluate           reason (if no modify)
              ↓
             END
```

### Routing Rules

| From | To | Condition |
|------|----|-----------|
| reason | modify | `pending_tool_calls` set and `cycle < 2` |
| reason | evaluate | default (no tool call, eval not yet run) |
| reason | END | `cycle >= 2` or `evaluation_result` already set |
| evaluate | comparison | `came_from == "modify"` |
| evaluate | END | `came_from == "tag_and_audit"` (fast exit) |
| evaluate | reason | otherwise |
| comparison | reason | always |

### AgentState Keys
`messages`, `pending_tool_calls`, `final_response`, `iteration`, `max_iterations`,
`tool_catalog`, `layout_json_string`, `evaluation_result`, `comparison_result`,
`came_from`, `original_layout_json_string`, `cycle`, `material_override`

---

## CLI Modes

```bash
python main.py "add a structural grid"       # default: fully local LangGraph
python main.py "..." --remote                # old MCP/LLM path via Grasshopper
python main.py "..." --llm-only              # direct LLM, no tools
python main.py "..." --simple-grid           # local grid only, no LLM
python main.py "..." --material STEEL        # force material for simple-grid
```

---

## Structural Engine (evaluate.py)

**Materials:** RCC (EC2), Steel (EC3 S235), Timber (EN338 C16)

**Beam checks (4):**
- Bending stress
- Shear stress
- LL deflection (L/360)
- TL deflection (L/250)

**Column checks (2):**
- Compressive stress
- Euler buckling (SF ≥ 3.0)

**Section tiers (10):**
RCC / RCC_M / RCC_L, STEEL / STEEL_M / STEEL_L (IPE160/200/240),
TIMBER / TIMBER_M / TIMBER_L / TIMBER_XL

**Human-in-the-loop prompts:**
1. Material picker (first evaluate pass)
2. Global section upgrade prompt (on FAIL)
3. Alternatives menu: auto-upgrade failing beams / per-element upgrade / midspan column insertion / global material switch

---

## Session History — Bugs Fixed & Features Built

### Session 1 — Initial Setup & Agent Pipeline

**Context:** Project scaffolded with LangGraph pipeline. Grasshopper/MCP integration optional.

**Work done:**
- Established `reason → modify → evaluate → comparison` graph
- Wrote `reason.py` system prompt with strict rules (never invent element IDs, only call `tag_and_audit` on explicit user request, evaluation handled by evaluate node)
- Established `nodes/tools.py` as local action executor with 6 tool schemas
- Design principle: LLM handles language only — all math in Python

---

### Session 2 — Streamlit UI Construction (app.py)

**Context:** Built the main Streamlit UI in `team_01/python/app.py`.

**Key features built:**
- Dark/light theme toggle
- Left sidebar: layout selector, material picker, session controls
- Main area: Plotly floor plan viewer + version history
- Right panel: Design Details tab (Analysis + structural elements list)
- Agent chat history panel
- Version snapshot system (`_push_version()` — increments `currentVersion`, saves versioned JSON, updates `currentLayout`, calls `_sync_viewers()`)
- Compare Work Place tab for side-by-side layout diffing
- JS bridge: `postMessage` → query param → rerun pattern for Plotly events and tab navigation

**Color tokens established:**
```python
_ACC   # accent (teal)
_CARD  # card background
_BORD  # border
_TEXT  # primary text
_MUT   # muted text
_F     # font family
```

---

### Session 3 — Generate Grid Fix

**Bug:** "Generate Grid produces no options"

**Root cause:**
`_run_grid_options()` called `build_structural_grid_with_options` from `nodes/tools.py` —
this function never existed anywhere in the codebase.

**Fix — rewrote `_run_grid_options()`** to call `generate_structure()` directly:
```python
def _run_grid_options(layout: dict, material: str) -> list[dict]:
    if not layout.get("rooms") or not layout.get("outline"):
        st.error("Generate Grid failed: layout missing required keys.")
        return []
    try:
        from nodes.tag_and_audit import generate_structure
        raw = generate_structure(layout)
        if not isinstance(raw, list) or len(raw) == 0:
            st.warning(f"generate_structure returned {type(raw).__name__} ...")
            return []
        opts = []
        for lay in raw:
            lay_copy = dict(lay)
            if "meta" not in lay_copy or not isinstance(lay_copy.get("meta"), dict):
                lay_copy["meta"] = {}
            lay_copy["meta"]["material"] = material
            opts.append({"layout": lay_copy, "evaluation": None})
        return opts
    except Exception as e:
        st.error(f"Generate Grid error: **{e}**")
        return []
```

**Result:** `generate_structure()` confirmed to return 3 options (22 cols, 29 beams).

**Context:** `generate_structure()` in `tag_and_audit.py` returns a **list** of layout dicts
on success, or the original layout dict unchanged on failure.
It does NOT go through `build_structural_grid_with_options`.

---

### Session 4 — Agent Import Crash Fix

**Bug:**
```
Agent error: cannot import name 'get_action_tools' from 'nodes.tools'
(C:\...\team_01\python\nodes\tools.py)
```

**Root cause:**
`get_action_tools()` was deleted from `nodes/tools.py` at some point but was still
imported in both `_runtime/bootstrap.py` and `app.py`.

**Fix — added `get_action_tools()` back to `nodes/tools.py`:**
```python
def get_action_tools() -> list[dict[str, Any]]:
    """Return the list of tool schemas the agent LLM can call."""
    return [
        {"name": "tag_and_audit",          "description": "...", "inputSchema": {...}},
        {"name": "modify_structure",        ...},
        {"name": "remove_element",          ...},
        {"name": "add_midspan_column",      ...},
        {"name": "upgrade_element_section", ...},
        {"name": "evaluate_structure",      ...},
    ]
```

Returns 6 tool schemas for the LLM.

---

### Session 5 — Plotly Viewer Overhaul

**Bug:** "The Plotly is completely non-functional: does not update, does not let select element, shows removed elements wrong — it is a disaster."

**Four separate bugs fixed:**

#### 5a — Element selection broken
- **Root cause:** `dragmode="select"` requires the user to drag a selection box, not single-click.
- **Fix:** Changed `dragmode="select"` → `dragmode="zoom"` so single-click fires selection events.

#### 5b — Hover text showing `?` for everything
- **Root cause:** Code read `beam.get('section_mm', '?')` and `beam.get('material', '?')` — data lives one level deeper in the `attributes` sub-dict.
- **Fix:**
  ```python
  attrs = beam.get("attributes", {})
  section = attrs.get("section", "?")
  material = attrs.get("material", "?")
  ```

#### 5c — Chart not updating after layout changes
- **Root cause:** `uirevision=f"plan-{len(structure)}"` — doesn't change if element count stays the same, so Plotly thinks the chart is the same and keeps old state.
- **Fix:** `uirevision=f"plan-v{revision}"` using `currentVersion` from session state so it increments on every `_push_version()` call.

#### 5d — Diff view showing uniform ghost instead of color-coded changes
- **Root cause:** Was inserting all before-layout elements as faint ACCENT-colored dotted traces with no actual diff computation.
- **Fix:** Proper diff computation:
  ```python
  _diff_removed  # elements in before but not after  → red dashed
  _diff_added    # elements in after but not before   → green
  _diff_changed  # same ID but different geometry     → amber
  ```

**`_render_floor_plan_plotly()` signature updated** to accept `revision: int = 0` parameter.

**Selection handler updated** to handle both dict and attribute access:
```python
if _sel_ev and _sel_ev.selection and _sel_ev.selection.points:
    try:
        _pt0 = _sel_ev.selection.points[0]
        _cd = (
            _pt0.get("customdata") if isinstance(_pt0, dict)
            else getattr(_pt0, "customdata", None)
        )
        if _cd:
            _new_sel = str(_cd[0]) if isinstance(_cd, (list, tuple)) else str(_cd)
            if _new_sel != st.session_state.selected_el:
                st.session_state.selected_el = _new_sel
                st.rerun()
    except Exception:
        pass
```

---

### Session 6 — Layout Proportions & Button Alignment

**User request:** "Left sidebar must be wider, right side bar must be thinner, and the tabs Save Snap and Run Analysis must be aligned with the right sidebar."

**Changes:**

1. **Column ratios:** `st.columns([1.65, 0.75])` → `st.columns([2.1, 0.55])`

2. **Step bar + button row restructured:**
   ```python
   _sb_col, _btn_area = st.columns([2.1, 0.55], gap="small")
   with _sb_col:
       st.markdown(_sbar_html, unsafe_allow_html=True)
   with _btn_area:
       _run_col, _snap_col = st.columns([1, 1], gap="small")
       with _run_col:
           _run_clicked = st.button("▶  Run Analysis", type="primary", ...)
       with _snap_col:
           _snap_clicked = st.button(f"Snapshot #{_sn_n}", ...)
   ```

---

### Session 7 — Sidebar Width Fix

**User request:** "Remove the drag option please because it is not working just make a simple sidebar that is wider than it currently is."

**Background:**
Streamlit's sidebar uses a `react-resizable` component that sets `style="width:244px"` as an
inline style on the inner div, and stores the width in `localStorage.sidebarWidth`.
Multiple approaches attempted:

| Attempt | Result |
|---------|--------|
| `width: 300px` on `stSidebarContent` | No effect — flex container ignores `width` alone |
| `components.html` JS injection (`window.parent.document.head`, MutationObserver, inline style setter) | Failed silently — iframe isolation blocks parent DOM access |
| `flex: 0 0 300px !important` on `section[data-testid="stSidebar"]` | **Worked** — confirmed by user screenshot showing wider sidebar |
| Added `max-width: 300px` to inner `stSidebarContent` and `stSidebarUserContent` divs | Caused content clipping / hiding (bug) |

**Final CSS (working state):**
```css
section[data-testid="stSidebar"] {
  background: {_SB} !important;
  border-right: 1px solid {_BORD} !important;
  width: 300px !important;
  min-width: 300px !important;
  flex: 0 0 300px !important;
}
section[data-testid="stSidebar"] > div:first-child {
  padding: 14px 14px 10px !important;
}
.react-resizable-handle {
  display: none !important;
  pointer-events: none !important;
}
```

**Key learnings:**
- `flex: 0 0 300px` is what controls the flex row allocation — `width` alone does not override flex-basis
- CSS `!important` overrides React's inline styles
- `max-width` on inner content divs causes `overflow: hidden` clipping — must NOT be set
- `components.html` iframe cannot reach `window.parent` DOM — all JS injection approaches for Streamlit layout control fail silently
- The resize handle is hidden with `display:none` to prevent confusion

---

## Planned Work (In Progress)

### Global Slide-out Agent Panel

**Goal:** Persistent agent chat panel accessible from all tabs (Modify + Compare).
A `◀` arrow tab sits on the right edge at all times. Clicking it slides out a 280px panel.

**Approach:** `position: fixed` div injected via `components.html` at module level.
Communicates back via existing JS bridge (`postMessage` → query param `_aq` → rerun).

**Status:** Plan written, not yet implemented.

---

## Design Principles

- LLM handles **language only** — all structural math runs in Python
- Never invent element IDs — `reason.py` system prompt enforces this strictly
- GH fallback: if Grasshopper returns empty, Python generates the column grid
- `_runtime/` is read-only infrastructure — all intelligence lives in the 5 node files
- `tag_and_audit` fast exit: skips evaluate/comparison/reason after grid generation
- Version history: every `_push_version()` call increments counter, saves JSON, updates viewers

---

## Key File Reference

| File | Purpose |
|------|---------|
| `app.py` | All Streamlit UI logic (~3200+ lines) |
| `nodes/reason.py` | LLM system prompt + reasoning node |
| `nodes/tools.py` | Tool schemas + tool execution node |
| `nodes/evaluate.py` | First-principles structural engine (~1111 lines) |
| `nodes/tag_and_audit.py` | `generate_structure()` — produces column/beam grid options |
| `nodes/comparison.py` | Layout diff + LLM summary |
| `_runtime/bootstrap.py` | Builds agent context (imports `get_action_tools`) |
| `_runtime/llm.py` | OpenAI-compatible chat wrapper |
| `team_01_edited_layout.json` | Live agent output, updated after each tool run |

---

*End of development history — 2026-06-08*
