# Team 04 - Workflow Architecture Documentation

This directory contains the complete state graph implementation for the architectural design generation workflow.

## Latest Update

- The active notebook [langgraph_test.ipynb](./langgraph_test.ipynb) is back on the LLM-driven workflow path.
- Grasshopper/MCP tool calls now return a clean workflow response when a tool exceeds the configured timeout instead of crashing the notebook.
- The default request timeout is now higher so slower GH computations have more time to finish.
- Human feedback is only prompted when the workflow produces multiple generated options.

## 📋 Files Generated

### 1. **graph.py** (Core Implementation)
The main workflow state machine implementation featuring:
- Complete `AgentState` TypedDict with all state variables
- 9 workflow nodes: Input Setup, Suggestion Layer, Shape Creation, Constraint Check, Evaluation, Optimization, Reasoning, Visualization, Output
- Intelligent routing logic for conditional execution paths
- Full state initialization and helper functions

**Key Functions:**
- `build_graph(ctx)` - Builds and compiles the state machine
- `run_agent(prompt, ctx)` - Entry point from main.py
- `_input_setup_node()` - Phase 1 initialization
- `_suggestion_layer_node()` - Generate design suggestions
- `_shape_creation_node()` - Convert suggestions to geometry
- `_constraint_check_node()` - Validate against rules
- `_evaluation_node()` - Calculate performance metrics
- `_optimization_node()` - Generate improvement suggestions
- `_reasoning_node()` - Create design justifications
- `_visualization_node()` - Prepare GH output
- `_output_node()` - Finalize results

### 2. **WORKFLOW_SUMMARY.md** (Complete Guide)
Comprehensive documentation covering:
- Workflow overview and key characteristics
- Three major phases with detailed explanations
- Complete state machine architecture
- All 9 nodes with purposes and outputs
- Routing decisions and conditional logic
- Key features (iterative optimization, analysis, justification, visualization, persistence)
- Integration points (MCP, LLM, Grasshopper)
- Extension points for customization
- Performance considerations

### 3. **STATE_DEFINITIONS.md** (State Reference)
Detailed specification of all state variables:
- **Input & Context Setup**: user_prompt, layout_json_string, cached_scene_state
- **Generation Analysis Loop**: suggestions, proposed_shapes, performance_metrics, optimization_suggestions
- **Decision Output & Feedback**: reasoning, visualization_data, final_shapes, final_response
- **Runtime Metadata**: iteration, loop_count, error_state
- State transitions by node
- Validation rules
- Extension guide

**Contains:** ~1500 lines of detailed variable documentation with examples

### 4. **workflow_structure.ipynb** (Interactive Notebook)
Jupyter notebook with:
- Workflow overview and architecture
- Visual state machine diagram
- Three-phase breakdown
- Detailed node documentation
- Execution timeline visualization
- Performance metrics analysis
- Integration points
- Extension guide with code examples

### 5. **langgraph_test.ipynb** (Current Validation Notebook)
Jupyter notebook used to validate the latest Team 04 workflow changes:
- LLM-driven prompt routing through LangGraph
- MCP/Grasshopper execution through the tool node
- Graceful handling for slow tool responses
- Notebook-level validation of the current integration path

**Features:**
- ASCII workflow diagrams
- Matplotlib visualizations
- Execution timing analysis
- Performance metric charts
- Runnable code cells for testing

### 6. **README.md** (This File)
Quick reference guide to all generated documentation

---

## 🔄 Workflow Phases

### Phase 1: INPUT & CONTEXT SETUP
```
INPUT SETUP
    ↓
Initialize context, load layout, prepare runtime parameters
```
**Duration:** < 1 second

### Phase 2: GENERATION ANALYSIS LOOP
```
SUGGESTION LAYER → SHAPE CREATION → CONSTRAINT CHECK
                                      ├→ PASS → EVALUATION
                                      └→ FAIL → OPTIMIZATION
                                           ↓
                                      Re-evaluate (loop)
```
**Duration:** 1-5 seconds per iteration
**Max Iterations:** 3 (configurable)

### Phase 3: DECISION OUTPUT & FEEDBACK
```
REASONING → VISUALIZATION → OUTPUT
                              ↓
                          Final Result & Caching
```
**Duration:** < 2 seconds

---

## 🎯 Key State Variables

### Phase 1: Input & Context
| Variable | Type | Purpose |
|----------|------|---------|
| `user_prompt` | str | User's design instruction |
| `layout_json_string` | str | Layout in JSON format |
| `layout_data` | dict | Parsed layout structure |
| `iteration` | int | Current iteration count |

### Phase 2: Analysis Loop
| Variable | Type | Purpose |
|----------|------|---------|
| `suggestions` | list | Design suggestions with confidence |
| `proposed_shapes` | list | Generated geometric shapes |
| `passes_constraints` | bool | Constraint validation result |
| `performance_metrics` | dict | Scored performance indicators |
| `optimization_needed` | bool | Flag for optimization requirement |
| `optimization_suggestions` | list | Improvement recommendations |

### Phase 3: Output & Feedback
| Variable | Type | Purpose |
|----------|------|---------|
| `reasoning` | str | Design justification text |
| `visualization_data` | dict | Grasshopper-compatible output |
| `final_shapes` | list | Final approved shapes |
| `final_response` | str | Complete response to user |
| `final_scene_state` | dict | Cached state for continuity |

---

## 🔧 Node Descriptions

| Node | Purpose | Input | Output | Routing |
|------|---------|-------|--------|---------|
| **Input Setup** | Initialize context | User prompt, layout | Initial state | → Suggestion Layer |
| **Suggestion Layer** | Generate ideas | Layout context | Suggestions | → Shape Creation |
| **Shape Creation** | Convert to geometry | Suggestions | Proposed shapes | → Constraint Check |
| **Constraint Check** | Validate design | Shapes, constraints | Pass/Fail | PASS→Evaluation, FAIL→Optimization |
| **Evaluation** | Calculate metrics | Validated shapes | Performance scores | Scores < 85%→Optimization, else→Reasoning |
| **Optimization** | Generate improvements | Metrics, shapes | Optimization suggestions | → Re-evaluate or → Reasoning |
| **Reasoning** | Create justifications | All analysis results | Design reasoning | → Visualization |
| **Visualization** | Prepare GH output | Shapes, metrics | Visualization data | → Output |
| **Output** | Finalize results | All workflow data | Final response, cached state | → END |

---

## 📊 Performance Metrics

Standard metrics calculated during evaluation:
- **Area Efficiency** (0-1): Usable area / total area
- **Constraint Satisfaction** (0-1): Constraints met ratio
- **Geometry Quality** (0-1): Shape quality score
- **Optimization Potential** (0-1): Room for improvement
- **Workflow Efficiency** (0-1): User movement optimization
- **Accessibility Score** (0-1): ADA compliance
- **Cost Efficiency** (0-1): Material/labor efficiency

**Optimization Trigger:** Average score < 85%

---

## 🔌 Integration Points

### MCP Tools
- `create_shape` - Generate shapes
- `validate_constraints` - Check compliance
- `calculate_metrics` - Compute scores
- `generate_suggestions` - Create ideas
- `export_to_grasshopper` - Format output

### LLM Integration
- Suggestion generation
- Design reasoning
- Optimization ideas
- Explanations and narratives

### Grasshopper Integration
- **Input:** Layout JSON from GH file
- **Output:** Visualization data, geometry, coordinates
- **Format:** GH-compatible structures

### Data Persistence
- Scene state caching in `final_scene_state`
- JSON serializable format
- Enables resuming/comparing designs

---

## 🚀 Usage

### Basic Execution
```bash
python main.py "Your design instruction"
```

### Example Instructions
- "Optimize the kitchen layout for better workflow"
- "Create an island in the center with prep area"
- "Improve accessibility for the dining room"

### Access Results
```python
# In main.py or after run_agent() call
final_state = app.invoke(initial_state)

# Access intermediate results
shapes = final_state["proposed_shapes"]
metrics = final_state["performance_metrics"]
reasoning = final_state["reasoning"]
visualizations = final_state["visualization_data"]
```

---

## 📈 Extension Examples

### Add Custom Node
```python
def _custom_node(state: AgentState) -> AgentState:
    result = custom_processing(state["proposed_shapes"])
    state["custom_metric"] = result
    return state

# In build_graph():
graph.add_node("custom_node", _custom_node)
graph.add_edge("evaluation", "custom_node")
```

### Add Custom Metric
```python
state["performance_metrics"]["custom_score"] = calculate_score()
```

### Add Custom Routing
```python
def _custom_route(state) -> str:
    if condition(state):
        return "optimization"
    return "reasoning"
```

---

## 📚 Related Files

- **graph.py** - Implementation
- **main.py** - Entry point
- **nodes/reason.py** - Reason node implementation
- **nodes/tools.py** - Tool integration
- **_runtime/config.py** - Configuration
- **_runtime/llm.py** - LLM setup
- **_runtime/mcp_client.py** - MCP connection

---

## ✅ Generated Files Summary

| File | Type | Lines | Purpose |
|------|------|-------|---------|
| graph.py | Python | 400+ | Complete state machine |
| WORKFLOW_SUMMARY.md | Markdown | 500+ | Comprehensive guide |
| STATE_DEFINITIONS.md | Markdown | 1500+ | Variable reference |
| workflow_structure.ipynb | Jupyter | 400+ | Interactive notebook |
| README.md | Markdown | This file | Quick reference |

---

## 🎓 Learning Path

1. **Start:** Read `WORKFLOW_SUMMARY.md` for overview
2. **Understand:** Review state machine diagram in notebook
3. **Detail:** Consult `STATE_DEFINITIONS.md` for variable specs
4. **Implement:** Review `graph.py` source code
5. **Extend:** Follow extension examples in `workflow_structure.ipynb`

---

## 🔗 Quick Links

- **Source Code:** [graph.py](./python/graph.py)
- **Main Guide:** [WORKFLOW_SUMMARY.md](./WORKFLOW_SUMMARY.md)
- **Variable Reference:** [STATE_DEFINITIONS.md](./STATE_DEFINITIONS.md)
- **Interactive Guide:** [workflow_structure.ipynb](./workflow_structure.ipynb)

---

## 📝 Notes

- All nodes are connected in a directed acyclic graph (DAG)
- Conditional routing allows flexible execution paths
- State is passed through complete pipeline
- All intermediate results are accessible
- Supports caching and resumption
- Extensible for custom nodes and metrics

---

**Generated for:** AIA26 Studio - Team 04
**Version:** 1.0
**Date:** 2026
