#!/usr/bin/env python
"""
Simplified workflow test with file-based state persistence and REAL tool execution.

Features:
- File-based state persistence (test_results/test_reference_layout.json, etc.)
- Same file structure as production code (team_06_reference_layout.json, etc.)
- Mock LLM that parses natural language into tool calls
- Executes local tools: layout_filter, layout_graph_search (real)
- Executes MCP tools: delete_room_06, add_window_06, adapt_layout_06 (real, 15s timeout)
- Auto-loading search results into state
- File-based state persistence across tests

Usage:
    python test_workflow.py "your prompt here"
    python test_workflow.py --show-state
    python test_workflow.py --clear
    
Example prompts:
    python test_workflow.py "select layout-1 and adapt to input layout"
    python test_workflow.py "search layout with 2 bedrooms and bathroom"
    python test_workflow.py "delete kitchen"

Requirements:
    - MCP server must be running (set endpoint in mcp.json)
    - All tools execute for real and save results to state files
"""

import sys
import json
import argparse
import re
from pathlib import Path
from typing import Any
import threading
from functools import lru_cache
from _runtime.bootstrap import bootstrap
from tools.layout_filter import select_layout
from tools.graph_searcher import GraphSearcher, build_topology_graph


# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ============================================================================
# State Management — File-based persistence (same structure as production)
# ============================================================================

# Test file paths (mirrors team_06 structure)
TEST_RESULTS_DIR = Path(__file__).parent / "test_results"
TEST_REFERENCE_LAYOUT = TEST_RESULTS_DIR / "test_reference_layout.json"
TEST_EDITED_LAYOUT = TEST_RESULTS_DIR / "test_edited_layout.json"
TEST_INPUT_LAYOUT = TEST_RESULTS_DIR / "test_input_layout.json"
TEST_HISTORY = TEST_RESULTS_DIR / "test_history.json"


def init_test_dirs():
    """Create test results directory."""
    TEST_RESULTS_DIR.mkdir(exist_ok=True)


def load_current_layout() -> dict:
    """Load current layout with priority: edited > reference > None."""
    if TEST_EDITED_LAYOUT.exists():
        return json.loads(TEST_EDITED_LAYOUT.read_text(encoding="utf-8"))
    elif TEST_REFERENCE_LAYOUT.exists():
        return json.loads(TEST_REFERENCE_LAYOUT.read_text(encoding="utf-8"))
    else:
        return None


def load_input_layout() -> dict:
    """Load input layout if exists."""
    if TEST_INPUT_LAYOUT.exists():
        return json.loads(TEST_INPUT_LAYOUT.read_text(encoding="utf-8"))
    else:
        return None


def save_reference_layout(layout: dict):
    """Save layout to reference file."""
    TEST_REFERENCE_LAYOUT.write_text(json.dumps(layout, indent=2), encoding="utf-8")


def save_edited_layout(layout: dict):
    """Save layout to edited file."""
    TEST_EDITED_LAYOUT.write_text(json.dumps(layout, indent=2), encoding="utf-8")


def save_input_layout(layout: dict):
    """Save input layout."""
    TEST_INPUT_LAYOUT.write_text(json.dumps(layout, indent=2), encoding="utf-8")


def add_history(event: str, tool: str = None, result: Any = None):
    """Add event to history file."""
    history = []
    if TEST_HISTORY.exists():
        history = json.loads(TEST_HISTORY.read_text(encoding="utf-8"))
    
    history.append({
        "event": event,
        "tool": tool,
        "result": result
    })
    TEST_HISTORY.write_text(json.dumps(history, indent=2), encoding="utf-8")


def clear_test_state():
    """Delete all test state files."""
    for path in [TEST_REFERENCE_LAYOUT, TEST_EDITED_LAYOUT, TEST_INPUT_LAYOUT, TEST_HISTORY]:
        if path.exists():
            path.unlink()


def call_mcp_tool_safe(ctx: Any, tool_name: str, args: dict, timeout_sec: float = 30.0) -> tuple[bool, str]:
    """
    Safely call an MCP tool with timeout.
    Returns (success: bool, result_or_error: str)
    """
    result = {"success": False, "output": None, "error": None}
    
    def _call():
        try:
            result["output"] = ctx.mcp_client.call_tool(tool_name, args)
            result["success"] = True
        except Exception as e:
            result["error"] = str(e)
    
    thread = threading.Thread(target=_call, daemon=True)
    thread.start()
    thread.join(timeout=timeout_sec)
    
    if thread.is_alive():
        return (False, f"MCP timeout after {timeout_sec}s (server not responding?)")
    
    if result["success"]:
        return (True, result["output"])
    else:
        return (False, result["error"] or "Unknown error")

# ============================================================================
# Local tool helpers (replaces local_tools.py imports)
# ============================================================================

@lru_cache(maxsize=1)
def _load_all_layouts() -> list[dict[str, Any]]:
    """Load all layouts from sample_layouts.json."""
    repo_root = Path(__file__).resolve().parent.parent.parent  # team_06/
    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    return json.loads(layouts_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _get_graph_searcher():
    """Initialize and cache GraphSearcher instance."""
    repo_root = Path(__file__).resolve().parent.parent.parent  # team_06/
    graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    return GraphSearcher(str(graphs_path))

# ============================================================================
# Mock LLM — Parse natural language to tool calls
# ============================================================================

class MockLLM:
    """Simple mock LLM using pattern matching."""
    
    def parse(self, prompt: str) -> dict[str, Any]:
        """Parse prompt into tool calls. Supports chained commands."""
        text = prompt.lower()
        tool_calls = []
        
        # Check for layout selection (do first)
        layout_match = re.search(r'layout-(\d+)', text)
        if layout_match:
            layout_result = self._parse_layout_command(text, layout_match.group(1))
            tool_calls.extend(layout_result["tool_calls"])
        
        # Check for search (independent)
        if any(w in text for w in ["search", "find", "show", "get", "any layouts"]):
            search_result = self._parse_search(text)
            tool_calls.extend(search_result["tool_calls"])
        
        # Check for delete (chained after layout/search)
        if "delete" in text:
            delete_result = self._parse_delete(text)
            tool_calls.extend(delete_result["tool_calls"])
        
        # Check for adapt/adjust (chained)
        if any(w in text for w in ["adapt", "adjust", "match", "align"]):
            adapt_result = self._parse_adapt(text)
            tool_calls.extend(adapt_result["tool_calls"])
        
        # Check for add window (chained)
        if "add window" in text or "add a window" in text:
            window_result = self._parse_add_window(text)
            tool_calls.extend(window_result["tool_calls"])
        
        # Check for daylight analysis
        if "daylight" in text or "daylight analysis" in text:
            daylight_result = self._parse_daylight(text)
            tool_calls.extend(daylight_result["tool_calls"])
        
        # If we have tool calls, return them
        if tool_calls:
            return {
                "action": "tool",
                "final_response": "",
                "tool_calls": tool_calls
            }
        
        # Default: final response
        return {
            "action": "final",
            "final_response": f"I don't understand: '{prompt}'",
            "tool_calls": []
        }
    
    def _parse_layout_command(self, text: str, layout_num: str) -> dict[str, Any]:
        """Handle 'layout-X' commands - returns just the filter."""
        layout_id = f"layout-{layout_num}"
        tool_calls = [
            {"name": "layout_filter", "arguments": {"layoutId": layout_id}}
        ]
        
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": tool_calls
        }
    
    def _parse_search(self, text: str) -> dict[str, Any]:
        """Parse search/find commands."""
        programs = []
        
        # Count bedrooms
        bed_match = re.search(r'(\d+)\s*[-\s]?bedroom', text)
        if bed_match:
            programs.extend(['bedroom'] * int(bed_match.group(1)))
        
        # Count bathrooms
        bath_match = re.search(r'(\d+)\s*[-\s]?bathroom?', text)
        if bath_match:
            programs.extend(['bathroom'] * int(bath_match.group(1)))
        
        # Keywords
        if 'kitchen' in text:
            programs.append('kitchen')
        if 'living' in text:
            programs.append('living')
        
        if not programs:
            programs = ['bedroom', 'kitchen']
        
        connection = "connected" if "accessible" in text or "connected" in text else "any"
        
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": [{
                "name": "layout_graph_search",
                "arguments": {
                    "programs": programs,
                    "connection_type": connection
                }
            }]
        }
    
    def _parse_delete(self, text: str) -> dict[str, Any]:
        """Parse delete commands."""
        room = None
        for r in ['kitchen', 'living', 'bedroom', 'bathroom', 'foyer']:
            if r in text:
                room = r.capitalize()
                break
        
        if not room:
            room = "Kitchen"
        
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": [{
                "name": "delete_room_06",
                "arguments": {"room_name": room}
            }]
        }
    
    def _parse_adapt(self, text: str) -> dict[str, Any]:
        """Parse adapt/adjust commands."""
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": [{
                "name": "adapt_layout_06",
                "arguments": {"input_layout": "placeholder"}  # Will be injected
            }]
        }
    
    def _parse_add_window(self, text: str) -> dict[str, Any]:
        """Parse add window commands."""
        width_match = re.search(r'(\d+(?:\.\d+)?)\s*m', text)
        width = float(width_match.group(1)) if width_match else 1.0
        
        room = "Living"
        for r in ['kitchen', 'living', 'bedroom', 'bathroom']:
            if r in text:
                room = r.capitalize()
                break
        
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": [{
                "name": "add_window_06",
                "arguments": {"room_name": room, "width": width}
            }]
        }
    
    def _parse_daylight(self, text: str) -> dict[str, Any]:
        """Parse daylight analysis commands."""
        # Extract window-wall-ratio if provided
        ratio_match = re.search(r'window[-\s]?wall[-\s]?ratio\s+of\s+(\d+(?:\.\d+)?)', text)
        window_wall_ratio = float(ratio_match.group(1)) if ratio_match else 0.4
        
        return {
            "action": "tool",
            "final_response": "",
            "tool_calls": [{
                "name": "daylight_06",
                "arguments": {"window_wall_ratio": window_wall_ratio}
            }]
        }

# ============================================================================
# Tool Execution
# ============================================================================

def execute_tool(tool_name: str, args: dict, ctx: Any) -> Any:
    """Execute a tool and update state."""
    print(f"  → Executing: {tool_name}")
    
    try:
        if tool_name == "layout_filter":
            # Load layout by ID
            layout_id = args.get("layoutId")
            all_layouts = _load_all_layouts()
            layout = select_layout(all_layouts, layout_id)
            
            # Save to reference layout (mirrors local_tools.py behavior)
            save_reference_layout(layout)
            add_history(f"Loaded {layout_id}", tool_name, {"layoutId": layout_id})
            print(f"    ✓ Loaded {layout_id}")
            return layout
        
        elif tool_name == "layout_graph_search":
            # Search layouts
            programs = args.get("programs", [])
            connection = args.get("connection_type", "any")
            
            graph_searcher = _get_graph_searcher()
            topology_graph = build_topology_graph(programs, connection)
            results = graph_searcher.search_by_graph_similarity(topology_graph, method="jaccard")
            
            # Auto-load best match (mirrors local_tools.py behavior)
            if results:
                best_id, score = results[0]
                all_layouts = _load_all_layouts()
                best_layout = select_layout(all_layouts, best_id)
                
                # Save to reference layout
                save_reference_layout(best_layout)
                add_history(f"Searched {programs}, found {len(results)}", tool_name, 
                           {"programs": programs, "best": best_id, "score": score})
                print(f"    ✓ Found {len(results)} layouts, auto-loaded {best_id}")
                return {"best": best_id, "candidates": len(results)}
            else:
                add_history(f"Searched {programs}, no results", tool_name)
                print(f"    ✓ No layouts found")
                return {"candidates": 0}
        
        elif tool_name == "delete_room_06":
            # Delete room (MCP tool)
            room = args.get("room_name", "?")
            current_layout = load_current_layout()
            layout_id = current_layout.get("layoutId", "?") if current_layout else "?"
            
            print(f"    → Calling MCP: delete_room_06 (timeout: 15s)")
            
            # Inject layout_json (mirrors tools.py behavior)
            args_to_send = args.copy()
            if "layout_json" not in args_to_send and current_layout:
                args_to_send["layout_json"] = current_layout
            
            success, output = call_mcp_tool_safe(ctx, tool_name, args_to_send, timeout_sec=15.0)
            
            if success:
                print(f"    ✓ MCP returned: {output[:80]}...")
                try:
                    result = json.loads(output) if output.startswith("{") else json.loads(output)
                    # Save edited layout (mirrors tools.py behavior)
                    if isinstance(result, dict):
                        save_edited_layout(result)
                        add_history(f"Deleted {room}", tool_name, {"room": room, "layout": layout_id})
                    return result
                except json.JSONDecodeError:
                    add_history(f"Deleted {room} (non-JSON response)", tool_name, {"room": room})
                    return {"status": "deleted", "room": room}
            else:
                print(f"    ⚠ MCP error: {output}")
                add_history(f"MCP error: {output}", tool_name, {"error": output})
                return {"error": output}
        
        elif tool_name == "add_window_06":
            # Add window (MCP tool)
            room = args.get("room_name", "?")
            width = args.get("width", "?")
            current_layout = load_current_layout()
            layout_id = current_layout.get("layoutId", "?") if current_layout else "?"
            
            print(f"    → Calling MCP: add_window_06 (timeout: 15s)")
            
            # Inject layout_json (mirrors tools.py behavior)
            args_to_send = args.copy()
            if "layout_json" not in args_to_send and current_layout:
                args_to_send["layout_json"] = current_layout
            
            success, output = call_mcp_tool_safe(ctx, tool_name, args_to_send, timeout_sec=15.0)
            
            if success:
                print(f"    ✓ MCP returned: {output[:80]}...")
                try:
                    result = json.loads(output) if output.startswith("{") else json.loads(output)
                    # Save edited layout (mirrors tools.py behavior)
                    if isinstance(result, dict):
                        save_edited_layout(result)
                        add_history(f"Added window", tool_name, {"width": width, "room": room})
                    return result
                except json.JSONDecodeError:
                    add_history(f"Added window (non-JSON response)", tool_name, {"width": width, "room": room})
                    return {"status": "added_window", "width": width, "room": room}
            else:
                print(f"    ⚠ MCP error: {output}")
                add_history(f"MCP error: {output}", tool_name, {"error": output})
                return {"error": output}
            
        elif tool_name == "adapt_layout_06":
            # Adapt layout (MCP tool)
            current_layout = load_current_layout()
            layout_id = current_layout.get("layoutId", "?") if current_layout else "?"
            
            print(f"    → Calling MCP: adapt_layout_06 (timeout: 15s)")
            
            # Inject current layout_json if not already included
            args_to_send = args.copy()
            if "layout_json" not in args_to_send and current_layout:
                args_to_send["layout_json"] = current_layout
            
            # Inject input_layout from file if exists, else use current layout as template
            if "input_layout" in args_to_send:
                input_layout = load_input_layout()
                if input_layout:
                    args_to_send["input_layout"] = input_layout
                elif current_layout:
                    # If no separate input_layout file, use current layout as the template
                    args_to_send["input_layout"] = current_layout
            
            success, output = call_mcp_tool_safe(ctx, tool_name, args_to_send, timeout_sec=15.0)
            
            if success:
                print(f"    ✓ MCP returned: {output[:80]}...")
                try:
                    result = json.loads(output) if output.startswith("{") else json.loads(output)
                    # Save edited layout (mirrors tools.py behavior)
                    if isinstance(result, dict):
                        save_edited_layout(result)
                        add_history(f"Adapted {layout_id}", tool_name, {"layout": layout_id})
                    return result
                except json.JSONDecodeError:
                    add_history(f"Adapted {layout_id} (non-JSON response)", tool_name, {"layout": layout_id})
                    return {"status": "adapted", "layout": layout_id}
            else:
                print(f"    ⚠ MCP error: {output}")
                add_history(f"MCP error: {output}", tool_name, {"error": output})
                return {"error": output}
        
        elif tool_name == "daylight_06":
            # Daylight analysis (MCP tool)
            window_wall_ratio = args.get("window_wall_ratio", 0.4)
            current_layout = load_current_layout()
            layout_id = current_layout.get("layoutId", "?") if current_layout else "?"
            
            print(f"    → Calling MCP: daylight_06 (window_wall_ratio={window_wall_ratio}, layout_json={current_layout}, timeout: 60s)")
            
            # Inject layout_json_str (mirrors tools.py behavior)
            args_to_send = args.copy()
            if "layout_json" not in args_to_send and current_layout:
                args_to_send["layout_json"] = current_layout
            
            success, output = call_mcp_tool_safe(ctx, tool_name, args_to_send, timeout_sec=60.0)
            
            if success:
                print(f"    ✓ MCP returned: {output[:80]}...")
                try:
                    result = json.loads(output) if output.startswith("{") else json.loads(output)
                    # Save edited layout (mirrors tools.py behavior)
                    if isinstance(result, dict):
                        save_edited_layout(result)
                    add_history(f"Ran daylight analysis (wwr={window_wall_ratio})", tool_name, 
                               {"layout": layout_id, "window_wall_ratio": window_wall_ratio})
                    return result
                except json.JSONDecodeError:
                    add_history(f"Daylight analysis completed (non-JSON response)", tool_name, 
                               {"layout": layout_id})
                    return {"status": "analysis_complete", "window_wall_ratio": window_wall_ratio}
            else:
                print(f"    ⚠ MCP error: {output}")
                add_history(f"MCP error: {output}", tool_name, {"error": output})
                return {"error": output}
        
        else:
            return {"error": f"Unknown tool: {tool_name}"}
    
    except Exception as e:
        print(f"    ✗ Error: {e}")
        add_history(f"Error in {tool_name}", tool_name, {"error": str(e)})
        return {"error": str(e)}


# ============================================================================
# Main Test
# ============================================================================

def run_test(prompt: str, reset: bool = False):
    """Execute a single test."""
    print(f"\n{'='*70}")
    print(f"Test: {prompt}")
    print(f"{'='*70}")
    
    # Initialize
    init_test_dirs()
    if reset:
        clear_test_state()
    
    current_layout = load_current_layout()
    layout_id = current_layout.get("layoutId") if current_layout else None
    history = json.loads(TEST_HISTORY.read_text()) if TEST_HISTORY.exists() else []
    print(f"State: layout={layout_id}, history_events={len(history)}")
    
    # Bootstrap
    try:
        ctx = bootstrap()
        print(f"✓ Bootstrapped context")
    except Exception as e:
        print(f"✗ Bootstrap failed: {e}")
        return
    
    # Parse with mock LLM
    mock_llm = MockLLM()
    decision = mock_llm.parse(prompt)
    
    print(f"Parsed: action={decision['action']}, tools={len(decision.get('tool_calls', []))}")
    
    # Execute tools
    if decision["action"] == "final":
        print(f"Final response: {decision['final_response']}")
        add_history("Final response", result=decision["final_response"])
    
    elif decision["action"] == "tool":
        for call in decision["tool_calls"]:
            tool_name = call["name"]
            args = call["arguments"]
            
            # Inject current layout_json if needed (mirrors graph.py behavior)
            if "layout_json" in args:
                current_layout = load_current_layout()
                if current_layout:
                    args["layout_json"] = current_layout
            
            # Inject input_layout if needed
            if "input_layout" in args:
                input_layout = load_input_layout()
                if input_layout:
                    args["input_layout"] = input_layout
            
            result = execute_tool(tool_name, args, ctx)
    
    print(f"\n✓ Test complete\n")


def main():
    parser = argparse.ArgumentParser(description="Test workflow with mock LLM")
    parser.add_argument("prompt", nargs="?", help="Test prompt")
    parser.add_argument("--reset", action="store_true", help="Reset state before test")
    parser.add_argument("--show-state", action="store_true", help="Show current state files")
    parser.add_argument("--clear", action="store_true", help="Clear state")
    parser.add_argument("--test", choices=["all"], help="Run predefined test suite")
    
    args = parser.parse_args()
    init_test_dirs()
    
    if args.clear:
        clear_test_state()
        print("✓ State cleared")
        return
    
    if args.show_state:
        print("\n" + "="*70)
        print("Test State Files")
        print("="*70)
        
        if TEST_REFERENCE_LAYOUT.exists():
            print(f"\n📄 {TEST_REFERENCE_LAYOUT.name}:")
            data = json.loads(TEST_REFERENCE_LAYOUT.read_text())
            print(f"   layoutId: {data.get('layoutId')}")
            print(f"   size: {len(json.dumps(data))} bytes")
        
        if TEST_EDITED_LAYOUT.exists():
            print(f"\n📝 {TEST_EDITED_LAYOUT.name}:")
            data = json.loads(TEST_EDITED_LAYOUT.read_text())
            print(f"   layoutId: {data.get('layoutId')}")
            print(f"   size: {len(json.dumps(data))} bytes")
        
        if TEST_INPUT_LAYOUT.exists():
            print(f"\n📥 {TEST_INPUT_LAYOUT.name}:")
            data = json.loads(TEST_INPUT_LAYOUT.read_text())
            print(f"   layoutId: {data.get('layoutId')}")
            print(f"   size: {len(json.dumps(data))} bytes")
        
        if TEST_HISTORY.exists():
            history = json.loads(TEST_HISTORY.read_text())
            print(f"\n📋 {TEST_HISTORY.name}: {len(history)} events")
            for i, event in enumerate(history[-5:], start=max(1, len(history)-4)):
                print(f"   {i}. {event.get('event')} [{event.get('tool', '-')}]")
        
        print("\n" + "="*70 + "\n")
        return
    
    if args.test == "all":
        # Run predefined test suite
        print("Running predefined test suite (6 tests)...\n")
        
        clear_test_state()
        run_test("select layout-1 and adapt to input layout", reset=True)
        run_test("search layout with 2 bedrooms and bathroom")
        run_test("adapt reference layout to input layout")
        run_test("delete kitchen")
        run_test("add window 1.0 m width to living room")
        run_test("run daylight analysis with window-wall-ratio of 0.8")
        return
    
    if args.prompt:
        run_test(args.prompt, reset=args.reset)
    else:
        # Run default test cases (3 tests)
        print("No prompt provided. Running example tests...\n")
        
        clear_test_state()
        run_test("select layout-1 and adapt to input layout", reset=True)
        run_test("search layout with 2 bedrooms and bathroom")
        run_test("delete kitchen")


if __name__ == "__main__":
    main()
