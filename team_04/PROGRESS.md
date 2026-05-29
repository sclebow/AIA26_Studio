# Team 04 — TerraPilot Implementation Progress

_Last updated: 2026-05-11_

---

## Status Summary

| Area | Status | Notes |
|---|---|---|
| LangGraph workflow | ✅ Done | **Hub-and-spoke architecture** — Central Reason Node (LLM) dispatches to 15 specialist workers; 3 terminal paths (explain/visualize/accept); `optimize` loop re-checks constraints (≤4 cycles) |
| System prompt | ✅ Done | **3 focused prompts** in `reason.py` — `central_reason` (9-action hub), `optimization` (repair picker), `reason_output` (ALIGN/RESIST/FRAME/AVOID) |
| Tool definitions | ✅ Done | 21 GH tools + 2 LLM-side tools documented |
| Mock MCP client | ✅ Done | All 21 stubs returning realistic JSON |
| Notebook explorer | ✅ Done | 19-cell notebook, all sections running |
| LLM configuration | ✅ Done | Cloudflare Workers AI — `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| Graph visualization | ✅ Done | LangGraph PNG + matplotlib workflow diagram |
| End-to-end agent run | ❌ Broken | Cell 19 fails — `.env` has invalid model `@cf/google/gemini-flash-1.5-8b`; fix: restore `@cf/meta/llama-3.3-70b-instruct-fp8-fast` |
| `.env` setup | ✅ Done | Credentials file created at repo root |
| API schema fix | ✅ Done | Removed `json_schema` response_format; no timeout/token errors |
| Edited layout output | ✅ Done | `team_04_edited_layout.json` generated from first agent run |
| Documentation suite | ✅ Done | TERRAPILOT_PLAN.md, TOOLS_CHECKLIST.md, QUICK_START.md, README_DELIVERABLES.md |
| GH tool specs | ✅ Done | 2 of 23 detailed specs written: tool 1 (`site_boundary_reader`) + tool 5 (`parametric_shape_generator`) |
| GH cluster parameters | ✅ Done | `team_04_definition_cluster.ghcluster` + working.gh parameter-tuned and verified |
| Grasshopper tools (remaining) | 🔄 In progress | 21 tools still need GH implementation; stubs exist for all |
| Test cases | 🔄 In progress | All 5 defined in notebook (with mock overrides); 2/5 markdown files written |

---

## Bugs Fixed (2026-05-04)

Five root-cause issues were diagnosed and resolved to make the full agent run (cell 19) complete successfully end-to-end.

### Bug 1 — 404 NotFoundError (missing `.env`)
**Symptom:** Cloudflare API returned 404; URL was `/accounts//ai/v1` (empty account ID).  
**Root cause:** `.env` file did not exist at the repo root; `CF_ACCOUNT_ID` was never loaded.  
**Fix:** Created `.env` at `AIA26_Studio/.env` with real Cloudflare credentials.

### Bug 2 — Wrong model name format
**Symptom:** API returned 404 for the model endpoint.  
**Root cause:** `.env` had `"openai/gpt-5.5-pro"`, which is not a valid Cloudflare model identifier.  
**Fix:** Changed `CF_MODEL` to `"@cf/qwen/qwen3-30b-a3b-fp8"` (Cloudflare format uses `@cf/...` prefix).

### Bug 3 — `ImportError: grandalf` in `graph.py`
**Symptom:** `run_agent` crashed after the LangGraph run with `ImportError: No module named 'grandalf'`.  
**Root cause:** `app.get_graph().print_ascii()` was called unconditionally; `grandalf` is not installed.  
**Fix:** Wrapped the call in `try/except ImportError` — graph ASCII is printed only when the package is available.

### Bug 4 — `LengthFinishReasonError` (2 000-token output cap)
**Symptom:** Cloudflare returned a truncated response; `openai` SDK raised `LengthFinishReasonError: completion_tokens=2000`.  
**Root cause:** Cloudflare's default output cap is 2 000 tokens. The LLM needed to emit a full JSON object with tool call arguments but was cut off mid-response.  
**Fix:** Added `max_tokens=8192` to `create_chat_llm()` in `_runtime/llm.py`.

### Bug 5 — `json_schema` response_format caused inference timeouts
**Symptom:** Even after the token-cap fix, every API call timed out (HTTP 408 from Cloudflare) on the first reasoning step.  
**Root cause (double):**
1. `get_llm_response_format()` merged ALL 21 tool input-schema properties into a single combined `json_schema` and sent it with every request (~1 000 extra tokens of schema per call).
2. `"strict": True` forces the model to enumerate every property (even null ones) in the output, multiplying response size.
3. The Qwen 30B model is too slow to handle this load within Cloudflare's inference timeout budget.

**Fix (three-part):**
- Changed `get_llm_response_format()` to return `{}` — no `response_format` sent to the API.
- Switched model to `@cf/meta/llama-3.3-70b-instruct-fp8-fast` in `.env` (faster FP8 variant).
- Increased `timeout_seconds` to 300 and `max_iterations` to 20 in cell 19.

### Bug 7 — `BadRequestError` from invalid Cloudflare model name (2026-05-10)
**Symptom:** Cell 19 crashes immediately on the first LLM call: `BadRequestError: Error code: 400 — No such model: @cf/google/gemini-flash-1.5-8b`.  
**Root cause:** The `.env` file was changed to use `@cf/google/gemini-flash-1.5-8b`, which is not a valid Cloudflare Workers AI model identifier.  
**Fix:** Restore `CF_MODEL` in `.env` to `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (the previously verified working model).

---

### Bug 6 — Stale Python module cache in Jupyter kernel
**Symptom:** File edits to `_runtime/llm.py` and `graph.py` did not take effect — Jupyter kernel served the old cached versions from `sys.modules`.  
**Root cause:** Python caches imported modules; edits to `.py` files are invisible to the running kernel until the module is reloaded or the kernel is restarted.  
**Fix:** Added `importlib.reload()` calls at the top of cell 19 for both `_runtime.llm` and `graph`, so every execution picks up the latest disk versions without a kernel restart.

---

## Architecture Redesign (2026-05-11) — Hub-and-Spoke

The LangGraph workflow was redesigned from a **linear 9-node category-based pipeline** to a **hub-and-spoke architecture** to match the intended design diagram.

### Previous design (replaced)
```
START → read_site → plan_form → check_constraints
          ├─[access]──► fix_orientation ──► check_constraints (loop ≤4×)
          ├─[form]───► fix_form ──────────► check_constraints (loop ≤4×)
          └─[clean]──► evaluate → write_report → bake_output → END
```

### New design
```
START → central_reason (LLM hub)
   suggest         → suggestion_layer → central_reason
   generate_shape  → tool_shape_creation → update_shape_state → central_reason
   evaluate        → tool_evaluation → update_score_state → central_reason
   ask_user        → human_feedback → central_reason
   check_constraints→ tool_constraint_check → update_constraint_state → central_reason
   optimize        → optimization → tool_manipulation → update_modified_shape
                   → tool_constraint_check → update_constraint_state → central_reason
   explain         → reason_output → final_output → cache_final_state → END
   visualize       → visualization → final_output → cache_final_state → END
   accept          → final_output → cache_final_state → END
```

### Changes made
| File | Change |
|---|---|
| `python/graph.py` | Full rewrite — 16-node hub-and-spoke graph replacing 9-node linear pipeline |
| `python/nodes/reason.py` | Replaced 5 Two-Mode LLM nodes with 3 new nodes: `central_reason`, `optimization`, `reason_output` |
| `terrapilot_explore.ipynb` | Updated cells 14–15 (graph build + matplotlib diagram) to show new architecture |
| `ARCHITECTURE.md` | Updated Overview, system diagram, graph.py section, reason.py section |
| `PROGRESS.md` | This entry |

---

## Completed Work

### 1. LangGraph Workflow Redesign v2 (`graph.py` + `nodes/reason.py`) — 2026-05-11

Replaced the previous 8-node pipeline with a clearer **9-node category-based pipeline**.

#### Problem with the previous design
In the old pipeline each LLM node was invoked multiple times per phase — once to decide which
tool to call, then again after receiving the tool result to decide what to do next.  This made
the conversation log ambiguous: it was impossible to tell whether a node's latest message was
*planning* the next step or *summarising* the previous one.

#### Solution — Two-Mode LLM Pattern
Each LLM node's system prompt now explicitly describes two modes:

| Mode | Trigger | Output |
|---|---|---|
| **MODE A — Plan** | No tool results in messages yet | `action="tool"` + tool call arguments |
| **MODE B — Summarise** | Tool results already in messages | `action="final"` + structured phase summary |

After MODE B runs, the summary is appended to `state["messages"]` as an assistant message with a
tagged header (e.g. `=== SITE READ COMPLETE ===`).  This creates a clean, timestamped log of what
each phase accomplished.

#### Node → Tool category mapping

```
START → read_site ──(tool loop)──► plan_form ──(tool loop)──► check_constraints
          check_constraints ──[access violation]──► fix_orientation ──(tool loop)──► check_constraints  ┐
          check_constraints ──[form violation]────► fix_form ──(tool loop)──────────► check_constraints  ├ ≤4 cycles
          check_constraints ──[clean / max cycles]─► evaluate ──► write_report ──► bake_output ──► END  ┘
```

| Node | Kind | Role | Tools |
|---|---|---|---|
| `read_site` | LLM | Read site context | `site_boundary_reader_04`, `context_reader_04`, `legal_constraints_reader_04` |
| `plan_form` | LLM | Generate building form | `shape_library_loader_04`, `parametric_shape_generator_04` |
| `check_constraints` | AUTO | Run all 5 constraint checkers | `site_fit_checker_04`, `setback_checker_04`, `area_requirement_checker_04`, `adjacency_access_checker_04`, `tree_constraint_checker_04` |
| `fix_orientation` | LLM | Rotation/offset fix (access violations) | `rotate_mirror_tool_04`, `scale_shape_tool_04` |
| `fix_form` | LLM | Shape modification fix (form violations) | `scale_shape_tool_04`, `stretch_arm_tool_04`, `width_modifier_tool_04`, `courtyard_modifier_tool_04`, `bend_angle_tool_04`, `terrace_step_tool_04` |
| `evaluate` | AUTO | Run all 3 evaluators | `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04` |
| `write_report` | LLM | Final narrative — **no tools** | (LLM only) |
| `bake_output` | AUTO | Bake to Rhino | `bake_geometry_id_04` |
| `tool` | SHARED | Execute any pending tool call | (all phases share this executor) |

**Key improvement:** `write_report` and `bake_output` are now separate nodes.
Previously `synthesise_reason` had to call `bake_geometry_id_04` AND write the narrative in the
same turn — the LLM was expected to both "execute an output step" and "compose a design
summary" simultaneously.  Now baking is automatic (`bake_output` AUTO), and `write_report` is a
pure LLM task with no tool calls.

#### Node name changes (v1 → v2)

| Old node (8-node) | New node (9-node) | Change |
|---|---|---|
| `site_reason` | `read_site` | Renamed for clarity |
| `form_reason` | `plan_form` | Renamed for clarity |
| `check_constraints` | `check_constraints` | Unchanged |
| `orient_reason` | `fix_orientation` | Renamed for clarity |
| `modify_reason` | `fix_form` | Renamed for clarity |
| `auto_evaluate` | `evaluate` | Renamed (dropped `auto_` prefix) |
| `synthesise_reason` | `write_report` | Renamed + role narrowed (no bake) |
| — | `bake_output` | **New** — baking split into its own AUTO node |
| `tool` | `tool` | Unchanged |

#### Updated `AgentState` phase values

| Phase value | Active in node |
|---|---|
| `"site"` | `read_site` |
| `"form"` | `plan_form` |
| `"fix_orient"` | `fix_orientation` |
| `"fix_form"` | `fix_form` |
| `"report"` | `write_report` |

#### Builder functions in `nodes/reason.py` (v2)

| Function | Phase | Prompt variable |
|---|---|---|
| `build_site_reader_node(llm, site_catalog)` | `"site"` | `SITE_READER_PROMPT` |
| `build_form_planner_node(llm, form_catalog)` | `"form"` | `FORM_PLANNER_PROMPT` |
| `build_orientation_fixer_node(llm, orient_catalog)` | `"fix_orient"` | `ORIENTATION_FIXER_PROMPT` |
| `build_form_modifier_node(llm, modify_catalog)` | `"fix_form"` | `FORM_MODIFIER_PROMPT` |
| `build_report_writer_node(llm)` | `"report"` | `REPORT_WRITER_PROMPT` |

---

### Previous Design — 8-Node Phase-Gated Pipeline (`graph.py` + `nodes/reason.py`) — 2026-05-10

Replaced the original single-reason-node ReAct loop with an **8-node phase-gated pipeline**.
Each phase had a dedicated LLM node with a focused system prompt.  Superseded by the 9-node
redesign above.

---

### 2. Tool Catalog (21 MCP tools + 2 LLM-side)

**Site Input (2):** `site_boundary_reader_04`, `context_reader_04`

**Shape Design (3):** `shape_library_loader_04`, `legal_constraints_reader_04`, `parametric_shape_generator_04`

**Constraint Checking (5):** `site_fit_checker_04`, `setback_checker_04`, `area_requirement_checker_04`, `adjacency_access_checker_04`, `tree_constraint_checker_04`

**Manipulation (7):** `scale_shape_tool_04`, `stretch_arm_tool_04`, `width_modifier_tool_04`, `courtyard_modifier_tool_04`, `rotate_mirror_tool_04`, `bend_angle_tool_04`, `terrace_step_tool_04`

**Evaluation — auto-forced (3):** `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04`

**Output (1):** `bake_geometry_id_04`

**LLM-side (2):** `why_operation_selector_04`, `explain_decision_tool_04`

---

### 3. Notebook Explorer (`terrapilot_explore.ipynb`)

19-cell interactive notebook — **all sections functional and fully tested:**

| Cell | Section | Status |
|---|---|---|
| 1–2 | Title + TOC | ✅ |
| 3 | Setup & `sys.path` | ✅ |
| 4–6 | LLM config override (Cloudflare) | ✅ |
| 7–10 | Mock MCP client + 21 tool stubs | ✅ |
| 11–12 | Tool catalog review | ✅ |
| 13–15 | Graph visualization (LangGraph PNG + matplotlib workflow) | ✅ |
| 16–17 | 5 test cases with `ACTIVE_TEST` selector + per-test `mock_overrides` | ✅ |
| 18–19 | **Full agent run** | ❌ Broken — invalid model in `.env` (see Bug 7) |

**Cell 19 specifics — current state:**
- `importlib.reload(_runtime.llm)` and `importlib.reload(graph)` at cell top — always picks up latest file edits
- `LLM_OVERRIDE["max_iterations"] = 20` — enough for a complete TerraPilot workflow
- `LLM_OVERRIDE["timeout_seconds"] = 300` — covers multi-turn conversations where history grows
- `build_llm_from_override()` re-called each run — picks up model/credential changes from `.env`
- Tool call trace now printed after agent response — shows every tool called and its arguments
- **Currently broken**: `.env` contains `@cf/google/gemini-flash-1.5-8b`; restore to `@cf/meta/llama-3.3-70b-instruct-fp8-fast`

**Cell 17 — test case improvements (2026-05-10):**
- All 5 test cases now fully defined with `ACTIVE_TEST` selector — change one variable to switch scenario
- Each test case has `mock_overrides` dict for per-scenario stub overrides (e.g. tree conflicts, failed area checks)
- `MockMcpClient` gained `call_history()` and `reset_history()` methods for test inspection

**Visualization outputs:**
- `terrapilot_workflow.png` — 5-column swimlane diagram of all 21 tools by phase

---

### 5. Documentation Suite (Added 2026-05-04)

Four new top-level documentation files were added to `team_04/`:

| File | Purpose |
|---|---|
| `TERRAPILOT_PLAN.md` | Complete implementation plan — full specs for all 23 tools with input/output schemas, GH notes, and a week-by-week timeline |
| `TOOLS_CHECKLIST.md` | Interactive checkbox list for all 23 tools with per-tool sub-tasks and priority levels |
| `QUICK_START.md` | Week-by-week and day-by-day guide for building GH clusters; includes placeholder templates and testing workflow |
| `README_DELIVERABLES.md` | Summary of all deliverables created — intended as a hand-off reference |

---

### 6. Grasshopper Tool Specifications (`gh/tool_definitions/`)

Detailed markdown specs added for 2 priority tools:

| File | Tool | Status |
|---|---|---|
| `01_site_boundary_reader.md` | `site_boundary_reader_04` | ✅ Full spec — inputs, outputs, example JSON, GH steps |
| `05_parametric_shape_generator.md` | `parametric_shape_generator_04` | ✅ Full spec — geometry_id generation, shape types, parameter schema |
| `README.md` | GH cluster template | ✅ Python component templates for JSON parse/format pattern |

Remaining 21 tools: stubs in mock MCP client; specs not yet written.

---

### 7. Grasshopper Cluster Updates

`team_04_definition_cluster.ghcluster` and `team_04_working.gh` were updated (commit `81f342a`):
- Parameters adjusted to ensure tools are wired correctly
- Binary changes only (no new text-visible changes)
- MCP tool registration in `team_04_result_cluster.ghcluster` also updated

---

### 8. Test Cases

Two detailed markdown test cases added to `test_cases/`:

| File | Scenario | Contents |
|---|---|---|
| `test_01_simple_rectangle.md` | Simple rectangular site | Site coords, expected tool sequence, pass/fail criteria |
| `test_02_pentagon_with_trees.md` | Irregular pentagon + 3 trees | Tree constraint testing, setback validation, geometry manipulation |

All 5 test cases are now defined **in the notebook** (cell 17) with per-scenario `mock_overrides`. The 3 remaining markdown spec files are still pending:
- `test_03_sloped_site.md` — slope adaptation scenario (override: performance evaluator scores)
- `test_04_gfa_deficit.md` — agent must iterate to meet area requirement (override: area checker fails first)
- `test_05_irregular_boundary.md` — hex site with bend constraint (override: setback checker)

---

### 9. Edited Layout Output

`team_04_edited_layout.json` was generated from the first successful end-to-end agent run and committed to the repo. It serves as the baseline for subsequent test runs.

---

### 5. Environment & Dependencies

- **Python env:** Python 3.14.4 kernel
- **Installed packages:** `langgraph`, `langchain_openai`, `matplotlib`, `httpx`, `python-dotenv`  
  Note: `grandalf` is optional — used for `print_ascii()` only; absence is handled gracefully
- **LLM provider:** Cloudflare Workers AI — `@cf/meta/llama-3.3-70b-instruct-fp8-fast`
- **Config file:** `.env` at repo root (`AIA26_Studio/.env`) — must contain `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_MODEL`

---

## In Progress

### Grasshopper Tool Implementation

GH clusters have been started and parameters tuned. Detailed specs exist for tools 1 and 5. Still needed:

| Category | Tools | Count |
|---|---|---|
| Input | `context_reader_04` | 1 |
| Shape | `shape_library_loader_04`, `legal_constraints_reader_04` | 2 |
| Constraint | `site_fit_checker_04`, `setback_checker_04`, `area_requirement_checker_04`, `adjacency_access_checker_04`, `tree_constraint_checker_04` | 5 |
| Manipulation | `scale_shape_tool_04`, `stretch_arm_tool_04`, `width_modifier_tool_04`, `courtyard_modifier_tool_04`, `rotate_mirror_tool_04`, `bend_angle_tool_04`, `terrace_step_tool_04` | 7 |
| Evaluation | `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04` | 3 |
| Output | `bake_geometry_id_04` | 1 |
| **Total** | | **19** |

Each tool still needs: GH cluster wiring, real output JSON, and mock stub updated to match real schema.

### Test Cases

All 5 scenarios now run in notebook (cell 17). Still needed — markdown spec files:
- `test_03_sloped_site.md`
- `test_04_gfa_deficit.md`
- `test_05_irregular_boundary.md`

---

## Next Steps

### Priority 1 — Grasshopper tool implementation (19 tools remaining)
Build GH components for all remaining tools. Each tool needs:
1. GH cluster wiring (input/output wires, Python JSON parser/formatter)
2. MCP registration verified in `team_04_working.gh`
3. Mock stub in the notebook updated to match real output schema
4. Checkbox ticked in `TOOLS_CHECKLIST.md`

Use `gh/tool_definitions/README.md` as the template. Follow the `01_site_boundary_reader.md` spec as a reference pattern.

### Priority 2 — Complete remaining tool specs
Write `gh/tool_definitions/` specs for the remaining 21 tools (prioritise constraint checkers and manipulation tools first).

### Priority 3 — Write remaining 3 test cases
`test_03_sloped_site.md`, `test_04_gfa_deficit.md`, `test_05_irregular_boundary.md`.

### Priority 4 — Test case validation with live GH
Run all 5 test cases against the live MCP server once GH tools are complete.

### Priority 5 — Tune system prompt for live tools
Mock stubs always return `success: true`; real GH tools may return errors or different field names. Adjust `reason.py` prompt guidance and `tools.py` parsing accordingly.

---

## Known Issues

| Issue | Severity | Status |
|---|---|---|
| 19 GH tools not yet implemented | High | In progress — see Priority 1 above |
| GH tool specs written for only 2 of 23 tools | Medium | In progress — write specs before implementing |
| 3 of 5 test cases not yet written | Low | Planned |
| `grandalf` not installed — `print_ascii` silently skipped | Low | Resolved via `try/except` — no action needed |
| Cloudflare rate limits under heavy testing | Medium | Monitor — stagger test runs if hitting 429 errors |
