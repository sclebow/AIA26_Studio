#!/usr/bin/env python
"""
Generate and visualize the Team 04 State Graph
(Minimal bootstrap version - doesn't require valid .env)
"""
import sys
sys.path.insert(0, '.')

from graph import build_graph, AgentState, run_agent
from langgraph.graph import StateGraph

print("=" * 70)
print("TEAM 04 - STATE GRAPH GENERATION")
print("=" * 70)

try:
    print("\n[1/2] Creating minimal context for graph visualization...")
    
    # Create a minimal context object for graph building
    class MinimalContext:
        def __init__(self):
            self.llm = None
            self.mcp_client = None
            self.tools = []
            self.layout_data = {"rooms": [], "constraints": []}
            self.max_iterations = 3
            self.edited_layout_path = None
    
    ctx = MinimalContext()
    print("✓ Minimal context created")
    
    print("\n[2/2] Building state graph...")
    graph = build_graph(ctx)
    print("✓ State graph compiled successfully")
    
    print("\n" + "=" * 70)
    print("WORKFLOW STATE MACHINE DIAGRAM")
    print("=" * 70 + "\n")
    
    try:
        graph.get_graph().print_ascii()
    except Exception as viz_error:
        print(f"(ASCII visualization not available: {viz_error})")
        print("\nGraph nodes and edges:")
        print(f"Nodes: {list(graph.get_graph().nodes)}")
        print(f"Edges: {list(graph.get_graph().edges)}")
    
    print("\n" + "=" * 70)
    print("✓ STATE GRAPH GENERATION COMPLETE!")
    print("=" * 70)
    
    # Print node information
    print("\n" + "=" * 70)
    print("NODES IN WORKFLOW")
    print("=" * 70)
    nodes = list(graph.get_graph().nodes)
    for i, node in enumerate(nodes, 1):
        print(f"{i:2d}. {node}")
    
    # Print edge information
    print("\n" + "=" * 80)
    print("CONNECTIONS (Edges)")
    print("=" * 80)
    edges = list(graph.get_graph().edges)
    for i, edge in enumerate(edges, 1):
        src = edge.source
        tgt = edge.target
        cond = " [conditional]" if edge.conditional else ""
        print(f"{i:2d}. {src:20s} → {tgt:20s}{cond}")
    
    print("\n" + "=" * 80)
    print("STATE SCHEMA (AgentState Variables)")
    print("=" * 80)
    print("\nAll state variables available in the workflow:\n")
    import inspect
    from typing import get_type_hints, get_args
    
    try:
        annotations = AgentState.__annotations__
        categories = {
            "INPUT & CONTEXT": [],
            "GENERATION ANALYSIS": [],
            "DECISION & OUTPUT": [],
            "RUNTIME METADATA": []
        }
        
        # Categorize variables
        for key in sorted(annotations.keys()):
            if key in ["user_prompt", "user_input", "layout_json_string", "layout_data", "cached_scene_state", "messages"]:
                categories["INPUT & CONTEXT"].append(key)
            elif key in ["suggestions", "current_suggestion_index", "proposed_shapes", "shape_creation_report",
                         "passes_constraints", "constraint_violations", "constraint_report",
                         "performance_metrics", "evaluation_report", "optimization_needed",
                         "optimization_suggestions", "optimization_report"]:
                categories["GENERATION ANALYSIS"].append(key)
            elif key in ["reasoning", "why_reasoning", "visualization_data", "human_feedback", "feedback_received",
                         "user_decision", "decision_reason", "final_shapes", "final_response", "final_scene_state"]:
                categories["DECISION & OUTPUT"].append(key)
            else:
                categories["RUNTIME METADATA"].append(key)
        
        for category, vars in categories.items():
            if vars:
                print(f"\n{category}:")
                for var in sorted(vars):
                    print(f"  • {var}")
    except Exception as e:
        print(f"  (Could not extract full type hints: {e})")
    
    print("\n" + "=" * 80)
    print("WORKFLOW EXECUTION PATH")
    print("=" * 80)
    print("""
Step 1: __start__ 
   ↓
Step 2: input_setup (Initialize state)
   ↓
Step 3: suggestion_layer (Generate suggestions)
   ↓
Step 4: shape_creation (Create geometry)
   ↓
Step 5: constraint_check (Validate design)
   ├→ PASS → Step 6: evaluation (Calculate metrics)
   └→ FAIL → Step 7: optimization (Fix issues)
              ↓
              Step 6: evaluation (or re-evaluate)
   ↓
Step 8: reasoning (Generate explanations)
   ↓
Step 9: visualization (Prepare GH output)
   ↓
Step 10: output (Final result)
   ↓
Step 11: __end__
    """)
    
    print("=" * 80)
    print("\n✓ STATE GRAPH SUCCESSFULLY GENERATED!")
    print("✓ Total Nodes: {} (including START and END)".format(len(nodes)))
    print("✓ Total Edges: {} (including conditional routing)".format(len(edges)))
    print("\n" + "=" * 80)
    
except Exception as e:
    print(f"\n✗ ERROR: {type(e).__name__}")
    print(f"  Message: {str(e)}")
    import traceback
    traceback.print_exc()
