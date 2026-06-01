# Design Workflow System - Complete File Summary

## Overview
A complete LangGraph-based site design optimization workflow system implementing the architecture shown in your workflow image. This system orchestrates multiple design operations through a central reasoning loop.

## Complete File List & Purpose

### 🎯 Core Orchestration
1. **`design_workflow_graph.py`** (Main orchestrator)
   - Builds the complete LangGraph workflow
   - Assembles all nodes, edges, and routing logic
   - Runs the workflow end-to-end
   - Prints graph ASCII visualization

2. **`design_main.py`** (Entry point)
   - CLI interface for running the workflow
   - Loads configuration
   - Initializes MCP client
   - Manages I/O and error handling

### 🧠 Central Decision Making
3. **`central_reasoning_node.py`** (The "brain")
   - Central reasoning node that analyzes state
   - Decides which action to take next (suggest/evaluate/optimize/explain/visualize/ask_user/final)
   - Parses LLM JSON responses
   - Handles fallback scenarios

### 🎬 Action Processing Nodes
4. **`design_action_nodes.py`** (Action handlers)
   - `create_suggestion_node()` - Process suggestions
   - `create_evaluation_node()` - Process evaluation scores
   - `create_optimization_node()` - Apply optimizations
   - `create_explanation_node()` - Generate explanations
   - `create_visualization_node()` - Create visualizations
   - `create_constraint_check_node()` - Validate constraints
   - `create_user_feedback_node()` - Collect user input

### 🔧 Tool & State Management
5. **`design_tool_node.py`** (Tool execution)
   - Executes MCP tool calls
   - Validates tool names and arguments
   - Updates state with results
   - Handles tool errors

6. **`design_state.py`** (State definitions)
   - `DesignWorkflowState` TypedDict - Complete workflow state
   - `SceneState` TypedDict - Current design context
   - `build_initial_workflow_state()` - Initialize state
   - `build_initial_scene_state()` - Initialize scene

### 🛣️ Routing Logic
7. **`design_routing.py`** (All routing functions)
   - `create_route_after_central_reasoning()` - Routes to action nodes
   - `create_route_after_action_node()` - Routes to tool execution or constraint check
   - `create_route_after_constraint_check()` - Routes back to reasoning
   - `create_route_after_tool_execution()` - Routes to action processor
   - `create_route_after_user_feedback()` - Routes back to reasoning

### 📋 Configuration & Registry
8. **`design_registry.py`** (Design registry)
   - Central `DESIGN_REGISTRY` mapping actions to tools
   - `AVAILABLE_ACTIONS` tuple
   - `group_tools_by_action()` - Groups tools by design action
   - `build_design_prompt()` - Generates focused prompts

9. **`design_config.py`** (Configuration loader)
   - `DesignSettings` dataclass
   - `load_design_settings()` - Loads from environment
   - Supports: OpenAI, Anthropic, Google, Cloudflare, Local LLM

### 🌐 External Integration
10. **`mcp_client.py`** (MCP communication)
    - JSON-RPC client for MCP servers
    - `initialize()` - Handshake with server
    - `list_tools()` - Discover available tools
    - `call_tool()` - Execute tool and get results

11. **`tool_node.py`** (LLM utilities - shared)
    - `DECISION_SCHEMA` - Base JSON schema for LLM responses
    - `get_llm_response_format()` - Build schema from tools
    - `create_chat_llm()` - Create ChatOpenAI instance

### 📚 Documentation
12. **`README.md`** (Complete documentation)
    - Architecture explanation
    - File structure breakdown
    - How it works (step-by-step)
    - Usage examples
    - Environment variables
    - Extending the system

13. **`.env.example`** (Environment template)
    - LLM provider options
    - API key placeholders
    - Workflow configuration

## File Dependencies & Data Flow

```
design_main.py
├── design_config.py (load settings)
├── mcp_client.py (initialize tools)
└── design_workflow_graph.py (run workflow)
    ├── design_state.py (DesignWorkflowState)
    ├── central_reasoning_node.py (main decision node)
    │   └── tool_node.py (create_chat_llm)
    ├── design_action_nodes.py (5 action processors)
    ├── design_tool_node.py (execute tools)
    ├── design_routing.py (5 routing functions)
    ├── design_registry.py (action registry)
    └── mcp_client.py (tool execution)
```

## Workflow States & Transitions

### State: DesignWorkflowState
```typescript
{
  user_prompt: str
  feedback_history: list[str]
  design_state: dict (suggestions, scores, shapes, etc.)
  constraint_state: dict (violations, compliance)
  pending_action: str (suggest/evaluate/optimize/explain/visualize/ask_user/final)
  pending_tool_calls: list[dict]
  last_tool_result: str
  tool_execution_count: int
  final_response: str | None
  design_iterations: int
}
```

### Execution Flow
1. **Central Reasoning** → Decides action (suggest/evaluate/optimize/explain/visualize)
2. **Action Node** → Processes previous results, prepares for tools
3. **Tool Execution** → Calls MCP tools, updates state
4. **State Aggregation** → Merges tool results into design_state
5. **Constraint Check** → Validates design against constraints
6. **Decision** → Loop back to reasoning OR finish
7. **Final Output** → Return design response

## Key Design Patterns

### 1. Central Reasoning Hub
- Single LLM point of decision
- Analyzes complete state before deciding
- Can trigger any action based on reasoning

### 2. Action Isolation
- Each action has its own node
- Each action gets relevant tools only
- State updates isolated to action

### 3. Conditional Routing
- 5 routers handle different transitions
- Routes based on pending state
- Supports loops and branches

### 4. Tool Grouping
- Tools grouped by design action in registry
- Each action node only sees relevant tools
- Scalable: add new actions by updating registry

### 5. State Merging
- `Annotated` types auto-merge updates
- Domain responses aggregated with `_merge_*` functions
- Parallel-safe state updates

## Configuration Requirements

### Environment Variables (.env)
```
LLM_PROVIDER=openai              # or anthropic, google, cloudflare, local
OPENAI_API_KEY=sk-...           # Your OpenAI API key
OPENAI_MODEL=gpt-4-turbo        # Model to use
DEBUG_GRAPH=true                # Print execution trace
REQUEST_TIMEOUT_SECONDS=30      # HTTP timeout
MAX_ITERATIONS=10               # Max tool calls
MAX_DESIGN_ITERATIONS=5         # Max design loops
```

### MCP Configuration (mcp.json)
```json
{
  "mcpServers": {
    "design-server": {
      "url": "http://localhost:3000"
    }
  }
}
```

## Running the Workflow

```bash
# Setup
pip install langgraph langchain-openai httpx python-dotenv

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python design_main.py "Design a 5-story commercial building on a 100m x 150m site"

# With debug output
DEBUG_GRAPH=true python design_main.py "..."
```

## Extension Points

### Add a New Design Action
1. Add to `DESIGN_REGISTRY` in `design_registry.py`
2. Create action node in `design_action_nodes.py`
3. Register node in `design_workflow_graph.py`
4. Add routing logic in `design_routing.py`

### Customize Reasoning Prompt
Edit `CENTRAL_REASONING_PROMPT` in `central_reasoning_node.py`

### Add New State Fields
Update `DesignWorkflowState` in `design_state.py`

### Implement User Feedback
Modify `create_user_feedback_node()` in `design_action_nodes.py`

## File Statistics

- **Total Files**: 13
- **Core Logic**: 7 files
- **Configuration**: 2 files
- **External Integration**: 2 files
- **Documentation**: 2 files

- **Lines of Code**: ~2,500
- **Largest File**: `design_workflow_graph.py` (~200 lines)
- **Smallest File**: `design_routing.py` (~100 lines)

## Next Steps

1. **Set up MCP server** - Provide design tools (suggest, evaluate, optimize, etc.)
2. **Configure LLM** - Set API keys in .env
3. **Test workflow** - Run with simple design prompt
4. **Add custom actions** - Extend DESIGN_REGISTRY for your needs
5. **Implement visualization** - Make visualization_node actually render

## Key Files to Edit

**For adding actions**: `design_registry.py` + `design_action_nodes.py` + `design_workflow_graph.py`

**For changing behavior**: `central_reasoning_node.py` (modify CENTRAL_REASONING_PROMPT)

**For state changes**: `design_state.py` (DesignWorkflowState TypedDict)

**For new routing**: `design_routing.py` (add new router function)

**For configuration**: `.env` file (not checked in)

## Troubleshooting

**"No MCP tools found"** → Check mcp.json and MCP server is running

**"Invalid JSON from LLM"** → Central reasoning falls back to ask_user

**"Tool not allowed"** → Tool not in design_action_nodes.py allowed_tools

**"Max iterations exceeded"** → workflow has too many tool calls, increase MAX_ITERATIONS

**"State merge error"** → Check _merge_* functions in design_state.py
