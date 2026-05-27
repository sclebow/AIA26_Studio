# Team 04 - Architecture Documentation

## Overview

This is an **AI agent system** that uses LangGraph to implement a **hub-and-spoke workflow** for generating and modifying building layouts through a Grasshopper MCP (Model Context Protocol) server. The agent receives natural language design briefs and a **Central Reason Node (LLM hub)** decides what to do next each cycle, dispatching to 15 specialist worker nodes. Three terminal paths (explain / visualize / accept) end the run.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                              │
│        Natural language design brief (CLI or notebook)          │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                         main.py                                 │
│        • Parses command-line arguments                          │
│        • Bootstraps the system (loads settings, MCP client)     │
│        • Runs the agent graph                                   │
│        • Prints final response                                  │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      bootstrap.py                               │
│        • Loads environment settings (.env)                      │
│        • Connects to MCP server                                 │
│        • Discovers available tools                              │
│        • Builds per-category filtered tool catalogs             │
│        • Creates LLM + reads layout schema JSON                 │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        graph.py                                 │
│              LangGraph Hub-and-Spoke Architecture               │
│                                                                 │
│  START → [central_reason] ─────────────────────────────────┐   │
│            │ suggest       → [suggestion_layer] ────────────┤   │
│            │ generate_shape→ [tool_shape_creation]          │   │
│            │                  → [update_shape_state] ───────┤   │
│            │ evaluate      → [tool_evaluation]              │   │
│            │                  → [update_score_state] ───────┤   │
│            │ ask_user      → [human_feedback] ──────────────┤   │
│            │ check_con...  → [tool_constraint_check]        │   │
│            │                  → [update_constraint_state] ──┤   │
│            │ optimize      → [optimization]                 │   │
│            │               → [tool_manipulation]            │   │
│            │               → [update_modified_shape]        │   │
│            │               → [tool_constraint_check]        │   │
│            │                  → [update_constraint_state] ──┘   │
│            │ explain       → [reason_output] ──────────┐        │
│            │ visualize     → [visualization] ──────────┤        │
│            └ accept        ────────────────────────────┘        │
│                                         ↓                       │
│                                  [final_output]                 │
│                                  [cache_final_state]            │
│                                       END                       │
│                                                                 │
│   • 3 LLM nodes: central_reason, optimization, reason_output   │
│   • 12 AUTO nodes handle tools, state updates, I/O             │
│   • optimize loop re-checks constraints (≤4 cycles)            │
└─────────────────────────────────────────────────────────────────┘
                 │
     ┌───────────┼───────────┬──────────────────┐
     ▼           ▼           ▼                  ▼
┌──────────┐ ┌──────────┐ ┌────────────────┐ ┌────────────────┐
│reason.py │ │ tools.py │ │  Runtime Utils │ │  nodes/        │
│          │ │          │ │                │ │                │
│5 Two-Mode│ │• Executes│ │ • config.py    │ │ • reason.py    │
│LLM nodes │ │  MCP     │ │ • llm.py       │ │ • tools.py     │
│(see §)   │ │  calls   │ │ • mcp_client.py│ │                │
│          │ │• Injects │ │ • bootstrap.py │ └────────────────┘
│          │ │  layout  │ └────────────────┘
│          │ │• Saves   │
│          │ │  results │
└──────────┘ └──────────┘
```

---

## Directory Structure

```
team_04/
├── ARCHITECTURE.md                         # System architecture (this file)
├── PROGRESS.md                             # Implementation progress log
├── QUICK_START.md                          # Week-by-week GH implementation guide
├── README_DELIVERABLES.md                  # Hand-off summary of all deliverables
├── TERRAPILOT_PLAN.md                      # Full 23-tool specification + timeline
├── TOOLS_CHECKLIST.md                      # Interactive per-tool checkbox tracker
├── team_04_edited_layout.json              # Output from latest agent run
│
├── gh/                                     # Grasshopper files
│   ├── team_04_definition_cluster.ghcluster   # INPUT + SHAPE tools cluster
│   ├── team_04_result_cluster.ghcluster       # Remaining tools + MCP output
│   ├── team_04_working.gh                     # Test harness (MCP server entry)
│   └── tool_definitions/                      # Per-tool specification docs
│       ├── README.md                          # GH cluster template (JSON parse/format pattern)
│       ├── 01_site_boundary_reader.md         # Full spec: site_boundary_reader_04
│       └── 05_parametric_shape_generator.md   # Full spec: parametric_shape_generator_04
│
├── test_cases/                             # Test scenario definitions
│   ├── test_01_simple_rectangle.md         # Simple rectangular site
│   └── test_02_pentagon_with_trees.md      # Pentagon site with tree constraints
│
└── python/                                 # Python agent code
    ├── main.py                             # Entry point
    ├── graph.py                            # LangGraph workflow definition
    ├── terrapilot_explore.ipynb            # 19-cell notebook: 5 test cases, mock client, graph viz
    ├── terrapilot_hub_workflow.png         # Generated hub-and-spoke workflow diagram
    │
    ├── _runtime/                           # Core runtime utilities
    │   ├── __init__.py                     # Empty (package marker)
    │   ├── bootstrap.py                    # System initialization
    │   ├── config.py                       # Settings and env loading
    │   ├── llm.py                          # LLM interface & schema
    │   └── mcp_client.py                   # MCP server client
    │
    └── nodes/                              # Graph node implementations
        ├── __init__.py                     # Empty (package marker)
        ├── reason.py                       # 3 LLM nodes: central_reason, optimization, reason_output
        └── tools.py                        # Shared MCP tool executor node
```

---

## File-by-File Breakdown

### 📁 `/` (Team Root)

#### `TERRAPILOT_PLAN.md`
Complete 23-tool specification. Covers all tool input/output schemas, GH implementation notes, and a week-by-week build timeline.

#### `TOOLS_CHECKLIST.md`
Interactive checkbox tracker — one section per tool with sub-tasks and priority levels (CRITICAL / HIGH / MEDIUM / LOW). Update this as you build each GH tool.

#### `QUICK_START.md`
Day-by-day guide for building GH clusters (Week 1 detailed, Weeks 2–4 sketched). Includes Python placeholder templates and testing workflow.

#### `README_DELIVERABLES.md`
Hand-off summary listing everything created in this branch: docs, code, tool specs, test cases.

#### `team_04_edited_layout.json`
Output layout JSON written by the agent during the first successful end-to-end run. Serves as a baseline for regression tests.

---

### 📁 `/gh/tool_definitions/` (GH Tool Specs)

#### `README.md`
Grasshopper cluster template: describes the standard JSON-parse → core logic → JSON-format cluster pattern, with Python component code templates.

#### `01_site_boundary_reader.md`
Full spec for `site_boundary_reader_04`: input schema, output schema, example JSON, GH implementation steps, test cases.

#### `05_parametric_shape_generator.md`
Full spec for `parametric_shape_generator_04`: `geometry_id` generation, shape types (bar/L/U/H/courtyard/cluster), parameter schema.

---

### 📁 `/test_cases/` (Test Scenarios)

#### `test_01_simple_rectangle.md`
Test case for a simple rectangular site. Defines site coordinates, expected tool call sequence, and pass/fail criteria.

#### `test_02_pentagon_with_trees.md`
Test case for an irregular pentagon site with 3 trees. Covers tree constraint checking, setback validation, and geometry manipulation.

> **Note:** Three additional test scenarios (`sloped_site`, `gfa_deficit`, `irregular_boundary`) are fully implemented in notebook cell 17 with mock overrides. Standalone markdown spec files (`test_03`–`test_05`) are still pending.

---

### 📁 `/python/` (Root Python Code)

#### `main.py`
**Purpose:** Application entry point

**What it does:**
- Parses command-line arguments (user's natural language instruction)
- Calls `bootstrap()` to initialize the system
- Calls `run_agent()` to execute the workflow
- Prints the agent's final response
- Cleans up MCP client connection

**Key function:** `main()`

---

#### `graph.py`
**Purpose:** Defines the 16-node hub-and-spoke LangGraph workflow

**Architecture — Central Reason Node as hub:**
The `central_reason` LLM node reads the full conversation history each cycle and picks ONE of 9 actions. Specialist workers execute the action, update state, and return to the hub. Three actions (explain / visualize / accept) terminate the run.

**Node inventory:**
| Node | Type | Role | Tools |
|---|---|---|---|
| `central_reason` | LLM | Hub — decides next action (9 options) | shape + manipulation tools |
| `suggestion_layer` | AUTO | Presents design alternatives | — |
| `tool_shape_creation` | TOOL | Executes site/shape MCP calls | `site_boundary_reader_04`, `context_reader_04`, `legal_constraints_reader_04`, `shape_library_loader_04`, `parametric_shape_generator_04` |
| `update_shape_state` | AUTO | Extracts geometry_id; logs state | — |
| `tool_evaluation` | AUTO | Runs all 3 evaluators | `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04` |
| `update_score_state` | AUTO | Stores evaluation scores | — |
| `human_feedback` | AUTO* | Simulates user feedback | — |
| `tool_constraint_check` | AUTO | Runs all 5 constraint checkers | `site_fit_checker_04`, `setback_checker_04`, `area_requirement_checker_04`, `adjacency_access_checker_04`, `tree_constraint_checker_04` |
| `update_constraint_state` | AUTO | Stores violations | — |
| `optimization` | LLM | Picks ONE manipulation tool to fix top violation | manipulation tools |
| `tool_manipulation` | TOOL | Executes manipulation MCP calls | `scale_shape_tool_04`, `stretch_arm_tool_04`, `width_modifier_tool_04`, `courtyard_modifier_tool_04`, `rotate_mirror_tool_04`, `bend_angle_tool_04`, `terrace_step_tool_04` |
| `update_modified_shape` | AUTO | Updates geometry_id after manipulation | — |
| `reason_output` | LLM | Writes ALIGN/RESIST/FRAME/AVOID narrative | — |
| `visualization` | AUTO | Generates text-based design summary | — |
| `final_output` | AUTO | Consolidates final_response | — |
| `cache_final_state` | AUTO | Saves design JSON to disk | — |

**Decision rules embedded in `central_reason` system prompt:**
1. No `geometry_id` → `generate_shape`
2. `geometry_id` exists, not checked → `check_constraints`
3. Violations + iters < 4 → `optimize`
4. Violations + iters ≥ 4 → `evaluate` (forced)
5. No violations, not evaluated → `evaluate`
6. Evaluation done → `explain`

**`tool_constraint_check` is shared** between the `[check_constraints]` spoke and the end of every `[optimize]` cycle. Both paths flow through the same node sequence: `tool_constraint_check → update_constraint_state → central_reason`.

#### Builder functions in `nodes/reason.py` (hub-and-spoke)

| Function | Role | Prompt variable |
|---|---|---|
| `build_central_reason_node(llm, full_catalog, max_mod_iters)` | Hub — 9-action dispatcher | `CENTRAL_REASON_PROMPT` |
| `build_optimization_node(llm, manipulation_catalog)` | Picks ONE repair tool | `OPTIMIZATION_PROMPT` |
| `build_reason_output_node(llm)` | Final ALIGN/RESIST/FRAME/AVOID report | `REASON_OUTPUT_PROMPT` |

---

### Previous Design — 9-Node Category-Based Pipeline (`graph.py` + `nodes/reason.py`) — 2026-05-10

Replaced by the hub-and-spoke redesign above. The previous design used a linear pipeline: `read_site → plan_form → check_constraints → fix_orientation / fix_form → evaluate → write_report → bake_output`. Each LLM node used a **Two-Mode pattern** (MODE A: plan tool calls; MODE B: summarise results). Superseded because the linear pipeline could not represent the flexible hub-driven decision flow shown in the architectural diagram.

---

### 📁 `/python/_runtime/` (Core Infrastructure)

#### `bootstrap.py`
**Purpose:** System initialization and dependency setup

**What it does:**
- Loads settings from `.env` file and `mcp.json`
- Reads the layout schema JSON from the repository root
- Connects to the Grasshopper MCP server
- Discovers available tools from the MCP server
- Creates the LLM instance with structured output schema
- Returns a `Context` object with all initialized components

**Key class:** `Context` (dataclass holding all runtime dependencies)

**Key function:** `bootstrap()` — returns the fully initialized `Context`

---

#### `config.py`
**Purpose:** Configuration and environment variable management

**What it does:**
- Loads and validates environment variables from `.env`
- Parses `mcp.json` to find the MCP server endpoint
- Supports multiple LLM providers:
  - Local (e.g., Ollama, LM Studio)
  - Cloudflare Workers AI
  - OpenAI
  - Google (Gemini)
  - Anthropic (Claude)
- Validates required configuration and fails fast if anything is missing

**Key class:** `Settings` (frozen dataclass)

**Key function:** `load_settings()` — returns the `Settings` object

---

#### `llm.py`
**Purpose:** LLM interface and response parsing

**What it does:**
- Creates LangChain `ChatOpenAI` instances (works with OpenAI-compatible APIs)
- Defines a reference JSON schema (`LLM_DECISION_SCHEMA`) for documentation purposes
- Parses LLM responses (handles markdown fences, multi-line JSON)
- Normalizes LLM decisions into a consistent format
- Persists tool results to disk (saves edited layouts as JSON)

**Design decision — no `response_format` schema in requests:**  
Earlier versions passed the full `json_schema` / `json_object` `response_format` flag to every API call. This was removed because:
1. Cloudflare Workers AI enforces a 2 000-token output cap when `json_schema` is used, causing `LengthFinishReasonError` on the first reasoning step.
2. The merged argument schema (all 21 tool properties combined) added ~1 000+ tokens to every request, causing HTTP 408 inference timeouts on the 30B model.
3. The system prompt already instructs the model to emit strict JSON, and `_parse_llm_json` / `_normalize_llm_decision` handle any format variance robustly.

As a result, `get_llm_response_format()` now returns `{}` — no API-level schema enforcement.

**`max_tokens=8192` added to `create_chat_llm()`:**  
Cloudflare defaults the output cap to 2 000 tokens. Setting `max_tokens=8192` lifts the limit so the model can emit a complete JSON response for complex prompts.

**Key constants:**
- `LLM_DECISION_SCHEMA` — reference JSON schema; used for documentation, not sent to API

**Key functions:**
- `create_chat_llm()` — factory function; includes `max_tokens=8192`, `temperature=0`
- `get_llm_response_format()` — returns `{}` (no response_format overhead)
- `call_llm()` — invokes the LLM and parses the response
- `write_tool_result()` — saves tool output to file

---

#### `mcp_client.py`
**Purpose:** MCP (Model Context Protocol) client

**What it does:**
- Communicates with the Grasshopper MCP server over HTTP/JSON-RPC 2.0
- Initializes the MCP connection
- Lists available tools from the server
- Calls tools with provided arguments
- Returns tool results as strings (handling both text and JSON responses)

**Key class:** `McpClient`

**Key methods:**
- `initialize()` — handshake with the MCP server
- `list_tools()` — retrieves available tool definitions
- `call_tool(name, arguments)` — executes a tool and returns the result
- `close()` — closes the HTTP client connection

---

### 📁 `/python/nodes/` (Graph Nodes)

#### `reason.py`
**Purpose:** Three LLM nodes for the hub-and-spoke architecture

**Builder functions:**

| Builder | Role | Prompt |
|---|---|---|
| `build_central_reason_node(llm, full_catalog, max_mod_iters)` | Hub — 9-action dispatcher | `CENTRAL_REASON_PROMPT` |
| `build_optimization_node(llm, manipulation_catalog)` | Picks ONE repair tool per cycle | `OPTIMIZATION_PROMPT` |
| `build_reason_output_node(llm)` | Final ALIGN/RESIST/FRAME/AVOID narrative | `REASON_OUTPUT_PROMPT` |

**Shared `_make_node` factory:**  
All three nodes use the same factory which calls `call_llm()` and parses JSON output:
- `action="tool"` → sets `pending_tool_calls` + `next_action`
- `action="final"` → sets `final_response` + `next_action`; appends summary to messages

**Shared output format:**
```json
{ "action": "tool" | "final",
  "next_action": "suggest|generate_shape|check_constraints|optimize|evaluate|ask_user|explain|visualize|accept",
  "tool_calls": [{"name": "<tool>", "arguments": {...}}],
  "final_response": "..." }
```

---

#### `tools.py`
**Purpose:** Tool execution node

**What it does:**
- Iterates over pending tool calls from the reason node
- Validates that requested tools are in the allowed list
- Cleans up null arguments and injects the layout JSON
- Calls tools via the MCP client
- Saves tool results to `team_04_edited_layout.json`
- Updates the agent state with the latest layout
- Appends tool calls and results to the conversation history
- Increments iteration count and enforces max iteration limit

**Key function:** `build_tool_node(mcp_client, allowed_tools, edited_layout_path)` — returns the node function

---

#### `__init__.py`
**Purpose:** Package markers (empty files that make Python treat directories as packages)

---

### 📁 `/gh/` (Grasshopper Files)

#### `team_04_definition_cluster.ghcluster`
**Purpose:** Grasshopper cluster containing the input definition logic

#### `team_04_result_cluster.ghcluster`
**Purpose:** Grasshopper cluster containing the output/result logic

#### `team_04_working.gh`
**Purpose:** Main Grasshopper working file that uses the clusters

---

## Data Flow

1. **User input** → Natural language design brief (CLI or notebook)

2. **Bootstrap phase:**
   - Load settings from `.env` and `mcp.json`
   - Connect to MCP server and discover tools
   - Build per-category filtered tool catalogs (site / form / orient / modify)
   - Create 5 LLM nodes + 3 AUTO nodes + 1 shared tool executor
   - Load building layout JSON

3. **Graph execution — 9-node category pipeline:**

   | Step | Node | Kind | What happens |
   |---|---|---|---|
   | 1 | `read_site` | LLM | Calls up to 3 site tools (Mode A), then writes "SITE READ COMPLETE" summary (Mode B) |
   | 2 | `plan_form` | LLM | Selects typology, calls 1 shape tool (Mode A), writes "FORM GENERATION COMPLETE" summary (Mode B) |
   | 3 | `check_constraints` | AUTO | All 5 checkers run; `violations` list populated; logs "CONSTRAINT CHECK RESULTS (cycle N)" |
   | 4a | `fix_orientation` | LLM | Calls 1 rotation/offset tool (Mode A), writes "ORIENTATION FIX APPLIED" summary (Mode B) |
   | 4b | `fix_form` | LLM | Calls 1 modification tool (Mode A), writes "FORM FIX APPLIED" summary (Mode B) |
   | — | *(loop step 3 → 4a/4b up to 4 times)* | | |
   | 5 | `evaluate` | AUTO | All 3 evaluators run; logs "EVALUATION COMPLETE" message |
   | 6 | `write_report` | LLM | Reads evaluation scores; writes ALIGN/RESIST/FRAME/AVOID narrative (**no tools**) |
   | 7 | `bake_output` | AUTO | Calls `bake_geometry_id_04` to bake geometry to Rhino (**no LLM**) |
   | — | `tool` (shared) | — | Executes any pending MCP tool calls; routes back to current phase node |

4. **Output:**
   - Console: phase-by-phase progress + final narrative
   - `team_04_edited_layout.json` — saved after every tool call
   - Baked geometry in Rhino via `bake_geometry_id_04`

---

## Key Concepts

### AgentState
The data structure that flows through the graph. Contains:
- Conversation history
- Pending tool calls
- Current layout (as JSON string)
- Iteration tracking
- Final response
- Phase tracking (`phase`, `geometry_id`, `violations`, `modification_iters`, `evaluation_done`)

### Two-Mode LLM Pattern
Instead of calling each LLM node repeatedly with no clear separation between planning and
summarising, every node's prompt explicitly defines:
- **Mode A (Plan):** No tool results yet → output `action="tool"` with tool call arguments
- **Mode B (Summarise):** Tool results present → output `action="final"` with a structured phase summary

The Mode B summary is appended to `messages` as an assistant message with a tagged header.
This creates a clear, timestamped log of what each phase accomplished — easily readable by both
humans and the subsequent LLM nodes.

### Category-Based Node Design
21 MCP tools are split across 5 node categories.  Each LLM node sees only the 2–6 tools
relevant to its single task:

| Category | Node | Tools |
|---|---|---|
| Site reading | `read_site` | `site_boundary_reader_04`, `context_reader_04`, `legal_constraints_reader_04` |
| Shape generation | `plan_form` | `shape_library_loader_04`, `parametric_shape_generator_04` |
| Constraint checking (AUTO) | `check_constraints` | `site_fit_checker_04`, `setback_checker_04`, `area_requirement_checker_04`, `adjacency_access_checker_04`, `tree_constraint_checker_04` |
| Orientation fix | `fix_orientation` | `rotate_mirror_tool_04`, `scale_shape_tool_04` |
| Form modification | `fix_form` | `scale_shape_tool_04`, `stretch_arm_tool_04`, `width_modifier_tool_04`, `courtyard_modifier_tool_04`, `bend_angle_tool_04`, `terrace_step_tool_04` |
| Evaluation (AUTO) | `evaluate` | `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04` |
| Report writing | `write_report` | *(no tools)* |
| Output baking (AUTO) | `bake_output` | `bake_geometry_id_04` |

### Separated Report and Bake
Previously the `synthesise_reason` node had to both call `bake_geometry_id_04` **and** compose the
architectural narrative in the same turn — an ambiguous dual role.  Now:
- `write_report` is a pure LLM task: read evaluation scores from messages, write narrative.
- `bake_output` is a pure AUTO task: call the bake tool, log the Rhino GUID.

### Structured Output
The LLM is instructed via the system prompt to return JSON in this exact format:
```json
{
  "action": "final" | "tool",
  "final_response": "...",
  "tool_calls": [
    {
      "name": "<tool-name>",
      "arguments": { ... }
    }
  ]
}
```

No `response_format` flag is passed to the API (see `llm.py` notes above). Parsing is handled by `_parse_llm_json` and `_normalize_llm_decision` in `_runtime/llm.py`.

### LLM Provider — Cloudflare Workers AI

The active provider is Cloudflare Workers AI via an OpenAI-compatible endpoint:
- **Verified working model:** `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (fast FP8-quantised Llama 3.3 70B)
- **Base URL:** `https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1`
- **Credentials:** `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_MODEL` in `.env` at repo root
- **Timeout:** `timeout_seconds=300` for multi-turn agent runs (history grows with each tool call)
- **Max iterations:** `max_iterations=20` — full TerraPilot workflow requires ~10–15 tool calls

**Why `llama-3.3-70b-instruct-fp8-fast` over `qwen3-30b-a3b-fp8`:**  
The Qwen 30B model consistently timed out (HTTP 408) when processing multi-turn conversations with the large TerraPilot system prompt. The Llama 3.3 70B FP8-fast variant handles the same load reliably.

> ⚠️ **Current issue (2026-05-10):** `.env` was changed to `@cf/google/gemini-flash-1.5-8b`, which Cloudflare rejects (`BadRequestError 400: No such model`). Restore `CF_MODEL` to `@cf/meta/llama-3.3-70b-instruct-fp8-fast` to fix.

### MockMcpClient (Notebook)

Used in `terrapilot_explore.ipynb` as a drop-in replacement for the real `McpClient`. Key interface:
- `initialize()` — no-op, prints confirmation
- `list_tools()` — returns `TERRAPILOT_TOOLS` (21 tool definitions)
- `call_tool(name, arguments)` — routes to stubs in `MOCK_TOOL_RESPONSES`; logs to call history
- `call_history()` — returns list of `{"tool": name, "args": {...}}` dicts for test inspection
- `reset_history()` — clears call history between test runs

---

## Usage

From the `team_04/python/` directory:

```bash
python main.py "delete the kitchen"
```

The agent will:
1. Initialize the system
2. Run the reasoning-tool loop
3. Modify the layout via Grasshopper MCP tools
4. Save the result to `team_04_edited_layout.json`
5. Print a confirmation message

---

## Configuration

Settings are loaded from a `.env` file in the repository root. Required variables depend on your LLM provider:

**Common:**
- `LLM_PROVIDER` — "local", "cloudflare", "openai", "google", or "anthropic"
- `REQUEST_TIMEOUT_SECONDS` — Timeout for LLM and MCP requests (default: 30)
- `MAX_ITERATIONS` — Maximum tool-call loops (default: 4)

**Provider-specific:** See `config.py` for details.

The MCP server endpoint is loaded from `mcp.json` in the repository root.

---

## Safety & Limits

- **Max iterations:** Prevents infinite loops (configurable via `MAX_ITERATIONS`; recommended ≥ 20 for full TerraPilot workflows)
- **Output token cap:** `max_tokens=8192` lifts Cloudflare's default 2 000-token cap
- **Tool validation:** Requested tools are checked against the allowed list
- **Timeout protection:** All HTTP requests have configurable timeouts (recommended 300 s for multi-turn runs)
- **Module cache:** Cell 19 in the notebook calls `importlib.reload()` on `_runtime.llm` and `graph` before each run to pick up any on-disk edits without restarting the kernel

---

## Environment Setup

Create a `.env` file at `AIA26_Studio/.env` (repo root):

```dotenv
# Cloudflare Workers AI
CF_ACCOUNT_ID = "<your-account-id>"
CF_API_TOKEN  = "<your-api-token>"
CF_MODEL      = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
```

The notebook loads this file via `load_dotenv(..., override=True)` at cell run time.

---

## Extension Points

To customize the agent:

1. **Change LLM behavior:** Edit `SYSTEM_PROMPT` in `nodes/reason.py`
2. **Add new nodes:** Create new node files in `nodes/` and wire them in `graph.py`
3. **Modify routing logic:** Edit `_route()` in `graph.py`
4. **Add state fields:** Extend `AgentState` in `graph.py`
5. **Support new LLM providers:** Add cases to `load_settings()` in `config.py`

---

## Dependencies

Key Python packages:
- `langgraph` — Graph-based agent framework
- `langchain-openai` — LLM interface (supports OpenAI-compatible APIs)
- `httpx` — Modern HTTP client for MCP communication
- `python-dotenv` — Environment variable loading

See `requirements.txt` in the repository root for the complete list.
