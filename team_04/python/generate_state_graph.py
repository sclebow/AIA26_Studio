#!/usr/bin/env python
"""
Generate and visualize the Team 04 State Graph
"""
import sys
sys.path.insert(0, '.')

from _runtime.bootstrap import bootstrap
from graph import build_graph

print("=" * 70)
print("TEAM 04 - STATE GRAPH GENERATION")
print("=" * 70)

try:
    print("\n[1/3] Bootstrapping context...")
    ctx = bootstrap()
    print("✓ Context initialized successfully")
    
    print("\n[2/3] Building state graph...")
    graph = build_graph(ctx)
    print("✓ State graph compiled successfully")
    
    print("\n[3/3] Generating ASCII visualization...")
    print("\n" + "=" * 70)
    print("WORKFLOW STATE MACHINE DIAGRAM")
    print("=" * 70)
    graph.get_graph().print_ascii()
    
    print("\n" + "=" * 70)
    print("✓ STATE GRAPH GENERATION COMPLETE!")
    print("=" * 70)
    
    # Save the graph structure to file
    import json
    graph_dict = {
        "nodes": list(graph.get_graph().nodes),
        "edges": [{"source": src, "target": tgt} for src, tgt in graph.get_graph().edges]
    }
    
    with open("state_graph_structure.json", "w") as f:
        json.dump(graph_dict, f, indent=2)
    print("\n✓ Graph structure saved to: state_graph_structure.json")
    
except Exception as e:
    print(f"\n✗ ERROR: {type(e).__name__}")
    print(f"  Message: {str(e)}")
    import traceback
    traceback.print_exc()
