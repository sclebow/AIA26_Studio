# Team 04 - Architectural Design Generation Workflow

## Latest Update

- The latest notebook run path uses the LLM-driven LangGraph workflow again, so Grasshopper/MCP is reached through the tool node instead of a direct notebook call.
- Human feedback is only requested when the model generates multiple viable options; single-option runs continue automatically.
- MCP tool calls now use a higher default timeout and fail gracefully when Grasshopper responds too slowly.

## Overview

This workflow implements a complete **design generation and iterative optimization loop** for architectural layouts. The system processes user input, generates design suggestions, validates them against constraints, evaluates performance metrics, and provides optimization recommendations—all in a structured state machine architecture.

---

## Workflow Architecture

The workflow is divided into **three major phases**:

### 1. **INPUT & CONTEXT SETUP**
**Purpose**: Initialize the design session and prepare context.

- **Input Processing**: Receive user prompt and initial instructions
- **Scene State Loading**: Load cached scene state if available
- **Context Preparation**: Initialize layout JSON, constraints, and metadata
- **State Initialization**: Set up runtime parameters and iteration counters

**Key Variables Initialized:**
- `user_prompt`: The design instruction from the user
- `layout_json_string`: Current layout in JSON format
- `cached_scene_state`: Previously saved design states
- `iteration`, `loop_count`: Tracking workflow execution

---

### 2. **GENERATION ANALYSIS LOOP**
**Purpose**: Generate, analyze, and optimize design proposals iteratively.

#### Stage 1: Suggestion Layer
- **Input**: Current layout context and user requirements
- **Process**: LLM analyzes context and generates design suggestions
- **Output**: List of proposed design modifications with confidence scores
- **State Variables**: `suggestions`, `current_suggestion_index`

#### Stage 2: Shape Creation
- **Input**: Design suggestions from analysis
- **Process**: Convert suggestions into geometric proposals
- **Output**: 3D/2D shape definitions with metadata
- **State Variables**: `proposed_shapes`, `shape_creation_report`

#### Stage 3: Constraint Check
- **Input**: Proposed shapes and design constraints
- **Process**: Validate shapes against:
  - Geometric constraints
  - Spatial relationships
  - Building codes
  - User-defined restrictions
- **Output**: Validation report and constraint violation list
- **State Variables**: `passes_constraints`, `constraint_violations`, `constraint_report`
- **Routing**: 
  - ✅ **PASS** → Continue to Evaluation
  - ❌ **FAIL** → Route to Optimization for correction

#### Stage 4: Evaluation & Performance Analysis
- **Input**: Validated shapes
- **Process**: Calculate performance metrics:
  - Area efficiency (%)
  - Constraint satisfaction score
  - Geometry quality score
  - Optimization potential
- **Output**: Performance report and optimization flag
- **State Variables**: `performance_metrics`, `evaluation_report`, `optimization_needed`

#### Stage 5: Optimization Suggestions
- **Input**: Performance metrics and evaluation results
- **Process**: Generate optimization recommendations if:
  - Average performance score < 85%
  - Constraint violations exist
  - Efficiency can be improved
- **Output**: Prioritized list of optimization strategies
- **State Variables**: `optimization_suggestions`, `optimization_report`
- **Routing**: 
  - If optimizations available → Re-evaluate with suggestions
  - If no improvements needed → Continue to decision/reasoning

---

### 3. **DECISION OUTPUT & FEEDBACK**
**Purpose**: Generate reasoning, collect feedback, and finalize output.

#### Stage 6: Reasoning & Justification
- **Input**: All previous analysis results
- **Process**: Generate comprehensive design reasoning:
  - Why this design was selected
  - How constraints are satisfied
  - Performance justification
  - Optimization opportunities addressed
  - Ask for human feedback only when multiple viable options are generated
- **Output**: Detailed text explanations and JSON reasoning data
- **State Variables**: `reasoning`, `why_reasoning`, `decision_reason`

#### Stage 7: Visualization
- **Input**: Proposed shapes, metrics, and evaluation results
- **Process**: Prepare data for Grasshopper visualization:
  - Shape geometry in GH-compatible format
  - Performance metric charts
  - Constraint satisfaction visualization
- **Output**: Visualization data structure
- **State Variables**: `visualization_data`

#### Stage 8: Final Output & Caching
- **Input**: All processed design data
- **Process**: 
  - Compile final shapes and recommendations
  - Save scene state for future reference
  - Generate comprehensive response
- **Output**: Final response string and cached state
- **State Variables**: `final_shapes`, `final_scene_state`, `final_response`

---

## State Machine Graph

```
INPUT SETUP
    ↓
SUGGESTION LAYER (Generate suggestions)
    ↓
SHAPE CREATION (Create geometry)
    ↓
CONSTRAINT CHECK (Validate)
    ├─→ PASS → EVALUATION (Calculate metrics)
    └─→ FAIL → OPTIMIZATION (Fix issues)
         ↓
EVALUATION (Performance analysis)
    ├─→ Optimization Needed → OPTIMIZATION
    └─→ Optimal → REASONING
         ↓
REASONING (Generate explanations)
    ↓
VISUALIZATION (Prepare for GH)
    ↓
OUTPUT (Final result)
    ↓
END
```

---

## AgentState: Complete Data Schema

### Input & Context
```python
user_prompt: str                          # User's design instruction
layout_json_string: str                   # Current layout JSON
layout_data: dict[str, Any]               # Parsed layout data
cached_scene_state: dict[str, Any] | None # Previously saved state
```

### Generation Analysis Loop
```python
# Suggestions
suggestions: list[dict[str, Any]]         # Generated design suggestions
current_suggestion_index: int             # Current suggestion being processed

# Shape Creation
proposed_shapes: list[dict[str, Any]]     # Generated geometric proposals
shape_creation_report: str                # Creation process log

# Constraint Validation
constraint_violations: list[str]          # List of constraint failures
passes_constraints: bool                  # Overall validation result
constraint_report: str                    # Validation details

# Performance Evaluation
performance_metrics: dict[str, float]     # Metric values (area_efficiency, etc.)
evaluation_report: str                    # Evaluation results
optimization_needed: bool                 # Flag for optimization requirement

# Optimization
optimization_suggestions: list[dict]      # Suggested improvements
optimization_report: str                  # Optimization analysis
```

### Decision & Feedback
```python
user_decision: Literal["accept", "modify", "reject", "optimize"]
decision_reason: str                      # Rationale for decision
human_feedback: str                       # User feedback if provided
feedback_received: bool                   # Flag for feedback presence

reasoning: str                            # Design reasoning explanation
why_reasoning: str                        # Justification narrative
visualization_data: dict[str, Any]        # GH visualization format
```

### Final Output
```python
final_shapes: list[dict[str, Any]]        # Final design shapes
final_response: str                       # Response to user
final_scene_state: dict[str, Any]         # Saved state for caching
```

### Runtime Metadata
```python
iteration: int                            # Current iteration count
max_iterations: int                       # Maximum allowed iterations
loop_count: int                           # Loop-back counter
tool_catalog: str                         # Available MCP tools
pending_tool_calls: list | None           # Queued tool calls
error_state: str | None                   # Error flag if any
messages: list[dict[str, Any]]            # Message history
```

---

## Routing Decisions

### After Constraint Check
- **PASS**: Forward to Evaluation
- **FAIL**: Route to Optimization for correction

### After Evaluation
- **Optimization Needed**: Route to Optimization
- **Already Optimal**: Continue to Reasoning

### After Optimization Cycle
- **Improvements Made**: Re-evaluate new design
- **No Improvements Possible**: Continue to Reasoning
- **Max Iterations Reached**: Force progress to Reasoning

---

## Key Features

### 1. **Iterative Optimization**
- Multi-stage validation pipeline
- Automatic constraint-violation detection and correction
- Performance-driven optimization suggestions

### 2. **Comprehensive Analysis**
- Constraint satisfaction scoring
- Multi-metric performance evaluation
- Optimization potential assessment

### 3. **Design Justification**
- Detailed reasoning generation
- Explanations for all design decisions
- Transparency into why shapes were selected

### 4. **Visualization Integration**
- Grasshopper-compatible output format
- Performance metric visualization data
- Constraint satisfaction visualization

### 5. **State Persistence**
- Scene state caching for continuity
- Full workflow execution history
- Metadata tracking for audit trails

---

## Integration Points

### MCP Tools Integration
- Shape generation tools via MCP
- Constraint checking services
- Geometry validation utilities
- Performance analysis tools
- Tool execution runs through the LangGraph tool node and now returns a clean workflow response when a tool call times out

### LLM Integration
- Suggestion generation at Suggestion Layer
- Reasoning and explanation generation
- Decision-making support
- Option filtering for human feedback routing

### Grasshopper Integration
- Direct shape output format
- Visualization data export
- Scene state import/export
- Input is supplied indirectly by the workflow through MCP tool calls, not by the notebook calling Grasshopper directly

---

## Extension Points

### Custom Nodes
Extend the workflow by adding nodes in `graph.py`:
```python
graph.add_node("custom_stage", custom_function)
```

### Custom Routing
Modify decision logic in routing functions:
```python
def _route_custom(state: AgentState) -> str:
    # Custom logic here
    return next_node_name
```

### Performance Metrics
Add new metrics in `_evaluation_node`:
```python
state["performance_metrics"]["custom_metric"] = calculate_metric()
```

---

## Files Generated

- **graph.py**: Complete state machine implementation
- **WORKFLOW_SUMMARY.md**: This documentation
- **langgraph_test.ipynb**: Current validation notebook for the latest workflow state
- **workflow_structure.ipynb**: Interactive workflow visualization
- **STATE_DEFINITIONS.md**: Detailed state schema reference

---

## Usage

### Basic Execution
```bash
python main.py "Your design instruction here"
```

### Workflow Execution Flow
1. Initialize context via `bootstrap()`
2. Build state graph via `build_graph(ctx)`
3. Invoke with initial state
4. Workflow executes through all stages
5. Return final response to user

### Accessing Intermediate Results
All intermediate states are available in the `final_state` dictionary:
```python
final_state["proposed_shapes"]      # Generated shapes
final_state["performance_metrics"]  # Performance scores
final_state["optimization_suggestions"]  # Suggestions
final_state["reasoning"]            # Explanation
```

---

## Performance Considerations

- **Iteration Limit**: Default max_iterations prevents infinite loops
- **State Size**: Complete state is maintained in memory
- **Tool Calls**: MCP calls run through the workflow tool node with a configurable timeout
- **Caching**: Scene states are cached to avoid recomputation

---

## Future Enhancements

- [ ] Parallel shape generation for multiple suggestions
- [ ] Machine learning-based constraint violation prediction
- [ ] Advanced visualization with real-time rendering
- [ ] Multi-objective optimization (Pareto frontier)
- [ ] Collaborative feedback loop with multiple users
- [ ] Historical design pattern learning

---

*Generated for AIA26 Studio - Team 04*
*Workflow Version: 1.0*
*Last Updated: 2026*
