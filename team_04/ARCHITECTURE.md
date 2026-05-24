# Team 04 - Architecture Documentation

## Overview

This is an **AI agent system** that uses LangGraph to build a reasoning-tool loop for modifying building layouts through a Grasshopper MCP (Model Context Protocol) server. The agent receives natural language instructions, reasons about them using an LLM, executes Grasshopper tools to modify the layout, and iterates until the task is complete.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         User Input                              │
│        Natural language design request (CLI or notebook)        │
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
│        • Creates LLM with structured output                     │
│        • Reads layout schema JSON                               │
└────────────────┬────────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                        graph.py                                 │
│                  LangGraph Workflow Engine                      │
│                                                                 │
│  ┌─────────┐   ┌──────────────────────────────────────────┐   │
│  │  START  │──▶│              reason node                 │   │
│  └─────────┘   │  (LLM: plan, call tools, or respond)     │   │
│                └──────┬────────────┬───────────────────────┘   │
│          tool calls   │            │ final_response set         │
│                       │            │                            │
│                ┌──────▼──────┐     ├── geometry + !evaluated   │
│                │  tool node  │     │      ┌─────────────────┐  │
│                │  (MCP exec) │     └─────▶│  auto_evaluate  │  │
│                └──────┬──────┘            │  (3 evaluators) │  │
│                       │                   └────────┬────────┘  │
│                       │◀───────────────────────────┘           │
│                       │                                        │
│                       │  final_response + evaluated            │
│                       ▼                                        │
│                  ┌────────┐                                    │
│                  │  END   │                                    │
│                  └────────┘                                    │
│                                                                 │
│   • Defines AgentState (messages, tools, phase tracking)       │
│   • Routes between reason, tool, and auto_evaluate nodes       │
│   • Forces evaluation before final response if geometry exists │
│   • Manages iteration count and safety limits                  │
└─────────────────────────────────────────────────────────────────┘
                 │
                 ├──────────────────┬──────────────────┐
                 ▼                  ▼                  ▼
        ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
        │  reason.py     │ │   tools.py     │ │  Runtime Utils │
        │                │ │                │ │                │
        │ • System prompt│ │ • Executes MCP │ │ • config.py    │
        │ • Calls LLM    │ │   tool calls   │ │ • llm.py       │
        │ • Decides next │ │ • Validates    │ │ • mcp_client.py│
        │   action       │ │   arguments    │ └────────────────┘
        │                │ │ • Updates state│
        │                │ │ • Saves results│
        └────────────────┘ └────────────────┘
```

---

## Directory Structure

```
team_04/
├── gh/                                 # Grasshopper files
│   ├── team_04_definition_cluster.ghcluster   # Input definition
│   ├── team_04_result_cluster.ghcluster       # Output results
│   └── team_04_working.gh                     # Working file
│
└── python/                             # Python agent code
    ├── main.py                         # Entry point
    ├── graph.py                        # LangGraph workflow definition
    │
    ├── _runtime/                       # Core runtime utilities
    │   ├── __init__.py                 # Empty (package marker)
    │   ├── bootstrap.py                # System initialization
    │   ├── config.py                   # Settings and env loading
    │   ├── llm.py                      # LLM interface & schema
    │   └── mcp_client.py               # MCP server client
    │
    └── nodes/                          # Graph node implementations
        ├── __init__.py                 # Empty (package marker)
        ├── reason.py                   # Reasoning node (LLM)
        └── tools.py                    # Tool execution node
```

---

## File-by-File Breakdown

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
**Purpose:** Defines the agent workflow using LangGraph

**What it does:**
- Defines `AgentState` (TypedDict) — the data structure that flows through the graph:
  - `messages`: conversation history
  - `pending_tool_calls`: tool calls queued by the LLM
  - `final_response`: set when the agent is ready to respond
  - `iteration`: current tool-call count
  - `max_iterations`: safety limit
  - `tool_catalog`: formatted list of available MCP tools
  - `layout_json_string`: current building layout as JSON
  - `phase`: workflow phase — `"design"` | `"evaluate"` | `"done"`
  - `geometry_id`: active parametric geometry ID (auto-extracted)
  - `evaluation_done`: `True` after `auto_evaluate` has run — prevents double-evaluation
- Builds the LangGraph workflow with **three nodes**: `reason`, `tool`, `auto_evaluate`
- Routes conditionally: tool calls → `tool`; unvalidated geometry → `auto_evaluate`; done → `END`
- `auto_evaluate` calls all 3 evaluators (spatial, performance, integrity) then clears `final_response` so the LLM synthesises a qualified response
- `_build_tracked_tool_node` wraps the inner tool node to extract `geometry_id` from `parametric_shape_generator_04` responses automatically
- `print_ascii()` call in `run_agent` is wrapped in `try/except ImportError` — prints graph structure only when `grandalf` is installed; silently skipped otherwise

**Key functions:**
- `build_graph(ctx)` — assembles the 3-node workflow and compiles it
- `run_agent(prompt, ctx)` — executes the graph and returns the final response
- `_route(state)` — 3-way routing: `run_tool` | `evaluate` | `finish`
- `_build_initial_state(prompt, ctx)` — prepares state including `phase`, `geometry_id`, `evaluation_done`
- `_build_auto_evaluate_node(mcp_client)` — builds the evaluation gate node
- `_build_tracked_tool_node(ctx)` — wraps tool node with `geometry_id` extraction
- `_format_tool_catalog(tools)` — formats tool descriptions for the LLM

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
**Purpose:** LLM reasoning node

**What it does:**
- Defines the system prompt that instructs the LLM how to behave
- Calls the LLM with conversation history and tool catalog
- Updates the agent state based on the LLM's decision:
  - If action is `"final"`: sets `final_response` (agent done)
  - If action is `"tool"`: sets `pending_tool_calls` (execute tools)

**Key constant:** `SYSTEM_PROMPT` — the instruction given to the LLM

**Key function:** `build_reason_node(llm)` — returns the node function

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

1. **User input** → Command-line argument (e.g., `"delete the kitchen"`)

2. **Bootstrap phase:**
   - Load settings and environment variables
   - Connect to MCP server and discover tools
   - Create LLM with structured output schema
   - Load building layout from JSON

3. **Graph execution — 5 phases:**
   - **START** → Initial state: `phase="design"`, `geometry_id=None`, `evaluation_done=False`
   - **reason node:** LLM analyses the request and decides:
     - Call tools (site reading, shape generation, constraint checking, manipulation) → `tool` node
     - Signal completion (`final_response` set) → routing check
   - **tool node:** Executes MCP tool calls; automatically extracts `geometry_id` from `parametric_shape_generator_04`; saves layout; loops back to `reason`
   - **auto_evaluate gate** (triggered when `final_response` set + `geometry_id` present + `evaluation_done=False`):
     - Calls `spatial_intention_evaluator_04`, `performance_evaluator_04`, `shape_integrity_evaluator_04`
     - Injects results as a new user message; clears `final_response`; sets `evaluation_done=True`
     - Returns to `reason` for synthesis
   - **END:** Reached only after evaluation is complete (or if no geometry was created)

4. **Output:**
   - Console output with agent's response (includes evaluation scores)
   - `team_04_edited_layout.json` with the modified layout
   - `geometry_id` in state for downstream baking via `bake_geometry_id_04`

---

## Key Concepts

### AgentState
The data structure that flows through the graph. Contains:
- Conversation history
- Pending tool calls
- Current layout (as JSON string)
- Iteration tracking
- Final response

### Reasoning Loop
1. LLM receives conversation history and tool catalog
2. LLM decides: call a tool OR respond to user
3. If tool: execute tool, update state, go back to step 1
4. If respond: set final response and terminate

### MCP Tools
Tools exposed by the Grasshopper MCP server. Examples might include:
- `modify_layout` — edit the building layout
- `analyze_layout` — get information about the layout
- `validate_layout` — check if the layout is valid

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
- **Model:** `@cf/meta/llama-3.3-70b-instruct-fp8-fast` (fast FP8-quantised Llama 3.3 70B)
- **Base URL:** `https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/v1`
- **Credentials:** `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_MODEL` in `.env` at repo root
- **Timeout:** `timeout_seconds=300` for multi-turn agent runs (history grows with each tool call)
- **Max iterations:** `max_iterations=20` — full TerraPilot workflow requires ~10–15 tool calls

**Why `llama-3.3-70b-instruct-fp8-fast` over `qwen3-30b-a3b-fp8`:**  
The Qwen 30B model consistently timed out (HTTP 408) when processing multi-turn conversations with the large TerraPilot system prompt. The Llama 3.3 70B FP8-fast variant handles the same load reliably.

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
