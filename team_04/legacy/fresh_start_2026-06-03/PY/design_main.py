import argparse
import json
from pathlib import Path
import re

from design_workflow_graph import run_design_workflow
from design_config import load_design_settings
from design_state import load_prompt_memory_state, build_prompt_memory_state, build_shape_generation_state
from mcp_client import McpClient
import plan_agent as pa
from plan_agent import (
    format_plan_agent_response,
    generate_plan_agent_payload,
    should_request_clarification,
)
from tool_node import create_chat_llm


def _parse_move_request(prompt: str) -> tuple[float, str] | None:
    """Extract a move distance and canonical direction from a free-form prompt."""
    text = (prompt or "").lower()
    if not any(keyword in text for keyword in ("move", "shift", "translate", "reposition", "relocate", "offset")):
        return None

    distance_match = re.search(r"(-?[0-9]+(?:\.[0-9]+)?)\s*(?:m|meter|meters|metre|metres)\b", text)
    distance = float(distance_match.group(1)) if distance_match else 1.0

    direction_patterns = [
        (r"\b(left|west)\b", "move_left"),
        (r"\b(right|east)\b", "move_right"),
        (r"\b(front|forward|north)\b", "move_front"),
        (r"\b(back|backward|backwards|south|down)\b", "move_back"),
        (r"\b(up|top|above)\b", "move_front"),
    ]

    for pattern, arg_key in direction_patterns:
        if re.search(pattern, text):
            return distance, arg_key

    return distance, "move_back"


def _parse_rotate_request(prompt: str) -> tuple[float, str] | None:
    """Extract rotation angle and direction from a free-form prompt."""
    text = (prompt or "").lower()
    if not any(keyword in text for keyword in ("rotate", "rotation", "turn", "spin")):
        return None

    angle_match = re.search(r"(-?[0-9]+(?:\.[0-9]+)?)\s*(?:degrees?|deg)\b", text)
    angle = float(angle_match.group(1)) if angle_match else 15.0

    direction = "clockwise"
    if any(keyword in text for keyword in ("anticlockwise", "counterclockwise", "counter-clockwise", "ccw")):
        direction = "anticlockwise"

    return angle, direction


def _parse_scale_request(prompt: str) -> tuple[float, str] | None:
    """Extract scale factor and scale type from a free-form prompt."""
    text = (prompt or "").lower()
    if not any(keyword in text for keyword in ("scale", "resize", "enlarge", "shrink", "expand", "contract", "bigger", "smaller")):
        return None

    percentage_match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    multiplier_match = re.search(r"(\d+(?:\.\d+)?)\s*times?", text)
    
    scale_factor = 1.0
    
    if percentage_match:
        percentage_value = float(percentage_match.group(1)) / 100.0
        if any(keyword in text for keyword in ("shrink", "smaller", "reduce", "decrease", "contract")):
            scale_factor = max(0.1, 1.0 - percentage_value)
        else:
            scale_factor = 1.0 + percentage_value
    elif multiplier_match:
        multiplier_value = float(multiplier_match.group(1))
        if any(keyword in text for keyword in ("shrink", "smaller", "reduce", "decrease", "contract")):
            scale_factor = max(0.1, 1.0 / multiplier_value)
        else:
            scale_factor = multiplier_value
    else:
        if any(keyword in text for keyword in ("enlarge", "bigger", "expand", "increase", "wider", "larger")):
            scale_factor = 1.1
        elif any(keyword in text for keyword in ("shrink", "smaller", "reduce", "decrease", "contract")):
            scale_factor = 0.9

    return scale_factor, "scale"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Site design optimization workflow using LangGraph + MCP"
    )
    parser.add_argument("prompt", help="User prompt for the design task")
    parser.add_argument(
        "--feedback",
        help="Optional feedback to refine the design",
        default="",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = load_design_settings()

    layout_schema_path = Path(__file__).with_name("layout_schema.json")
    try:
        layout_schema = json.loads(layout_schema_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        layout_schema = {}

    print("=" * 60)
    print("SITE DESIGN OPTIMIZATION WORKFLOW")
    print("=" * 60)
    print(f"Provider: {settings.llm_provider}")
    print(f"Model: {settings.llm_model}")
    print(f"Base URL: {settings.base_url}")
    print(f"DEBUG_GRAPH: {settings.debug_graph}")
    print(f"MCP Config Path: {settings.mcp_config_path}")
    print(f"MCP Server Key: {settings.mcp_server_key}")
    print(f"MCP Endpoint: {settings.mcp_endpoint}")
    print(f"Max Iterations: {settings.max_iterations}")
    print(f"Max Design Iterations: {settings.max_design_iterations}")
    print("=" * 60)

    prompt_memory_state = load_prompt_memory_state()
    # Initialize MCP client
    mcp_client = McpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
    mcp_client.initialize()
    tools = mcp_client.list_tools()
    print(f"\nDiscovered {len(tools)} MCP tools")
    for tool in tools:
        print(f"  - {tool.get('name', 'unknown')}")
    print()

    # Fast path: simple move command -> first create building, then apply move.
    # This avoids unnecessary multi-step LLM workflow and interactive prompts
    # for a straightforward deterministic operation.
    available_tool_names = {str(t.get("name", "")) for t in tools if t.get("name")}
    move_request = _parse_move_request(args.prompt) if isinstance(args.prompt, str) else None
    if move_request and "manipulation_tools" in available_tool_names and "parametric_shape_generator" in available_tool_names:
        distance, arg_key = move_request
        
        print("\n" + "=" * 60)
        print("DIRECT MOVE MODE")
        print("=" * 60)
        current_memory = build_prompt_memory_state(
            args.prompt,
            existing_memory=prompt_memory_state,
            shape_hint=build_shape_generation_state(args.prompt),
        )
        print("Prompt Memory")
        print(f"Latest user prompt: {current_memory.get('latest_user_prompt', '')}")
        print(f"Latest manipulation prompt: {current_memory.get('latest_manipulation_prompt', '')}")
        print(f"Merged MCP prompt: {current_memory.get('merged_mcp_prompt', '')}")
        
        # Initialize defaults
        shape_hint = "rectangle"
        tree_count = 0
        gene_defaults = {}
        
        # Step 1: Create the building using the original shape prompt
        original_shape_prompt = current_memory.get('original_shape_prompt', '')
        if original_shape_prompt:
            shape_state = build_shape_generation_state(original_shape_prompt)
            shape_hint = shape_state.get('locked_shape_type', 'rectangle')
            tree_count = shape_state.get('tree_count', 0)
            gene_defaults = shape_state.get('gene_defaults', {})
            
            # Build shape generation payload
            shape_payload = {
                "shape_type": shape_hint,
                "locked_shape_type": shape_hint,
                "tree_count": tree_count,
                "number_of_trees": tree_count,
            }
            # Merge gene defaults (area-based parameters)
            shape_payload.update(gene_defaults)
            
            print(f"\nStep 1: Creating {shape_hint} building...")
            print(f"  Tree count: {tree_count}")
            print(f"  Parameters: {gene_defaults}")
            try:
                create_response = mcp_client.call_tool("parametric_shape_generator", shape_payload)
                print(f"  Result: Shape created successfully")
            except Exception as e:
                print(f"  Error creating shape: {e}")
                mcp_client.close()
                return
        
        # Step 2: Apply the movement (include full shape context for MCP to apply manipulation)
        tree_policy = {
            "tree_count": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "inferred_tree_points": [],
            "inferred_tree_sizes": [],
            "tree_count_source": "default",
            "tree_positions_provided": False,
            "preferred_edge": "",
            "placement_mode": "",
            "notes": ""
        }
        
        move_args = {
            "move_left": 0.0,
            "move_right": 0.0,
            "move_front": 0.0,
            "move_back": 0.0,
            arg_key: distance,
            # Include shape context so manipulation_tools knows what it's manipulating
            "shape_type": shape_hint,
            "locked_shape_type": shape_hint,
            "tree_count": tree_count,
            "number_of_trees": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "tree_locations": [],
            "tree_policy": tree_policy,
            "tree_policy_json": json.dumps(tree_policy),
        }
        
        print(f"\nStep 2: Applying movement...")
        print(f"Tool: manipulation_tools | {arg_key}={distance}")
        response = mcp_client.call_tool("manipulation_tools", move_args)
        print("\n" + "=" * 60)
        print("DESIGN WORKFLOW RESULT")
        print("=" * 60)
        print(response)
        print("=" * 60)
        mcp_client.close()
        return

    # Fast path: simple rotate command -> first create building, then apply rotation
    rotate_request = _parse_rotate_request(args.prompt) if isinstance(args.prompt, str) else None
    if rotate_request and "manipulation_tools" in available_tool_names and "parametric_shape_generator" in available_tool_names:
        angle, direction = rotate_request
        
        print("\n" + "=" * 60)
        print("DIRECT ROTATE MODE")
        print("=" * 60)
        current_memory = build_prompt_memory_state(
            args.prompt,
            existing_memory=prompt_memory_state,
            shape_hint=build_shape_generation_state(args.prompt),
        )
        print("Prompt Memory")
        print(f"Latest user prompt: {current_memory.get('latest_user_prompt', '')}")
        print(f"Latest manipulation prompt: {current_memory.get('latest_manipulation_prompt', '')}")
        print(f"Merged MCP prompt: {current_memory.get('merged_mcp_prompt', '')}")
        
        # Initialize defaults
        shape_hint = "rectangle"
        tree_count = 0
        gene_defaults = {}
        
        # Step 1: Create the building using the original shape prompt
        original_shape_prompt = current_memory.get('original_shape_prompt', '')
        if original_shape_prompt:
            shape_state = build_shape_generation_state(original_shape_prompt)
            shape_hint = shape_state.get('locked_shape_type', 'rectangle')
            tree_count = shape_state.get('tree_count', 0)
            gene_defaults = shape_state.get('gene_defaults', {})
            
            # Build shape generation payload
            shape_payload = {
                "shape_type": shape_hint,
                "locked_shape_type": shape_hint,
                "tree_count": tree_count,
                "number_of_trees": tree_count,
            }
            # Merge gene defaults (area-based parameters)
            shape_payload.update(gene_defaults)
            
            print(f"\nStep 1: Creating {shape_hint} building...")
            print(f"  Tree count: {tree_count}")
            print(f"  Parameters: {gene_defaults}")
            try:
                create_response = mcp_client.call_tool("parametric_shape_generator", shape_payload)
                print(f"  Result: Shape created successfully")
            except Exception as e:
                print(f"  Error creating shape: {e}")
                mcp_client.close()
                return
        
        # Step 2: Apply the rotation (include full shape context)
        tree_policy = {
            "tree_count": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "inferred_tree_points": [],
            "inferred_tree_sizes": [],
            "tree_count_source": "default",
            "tree_positions_provided": False,
            "preferred_edge": "",
            "placement_mode": "",
            "notes": ""
        }
        
        rotate_args = {
            "rotation_degrees": angle,
            "rotation_direction": direction,
            "apply_rotation": True,
            # Include shape context for manipulation_tools
            "shape_type": shape_hint,
            "locked_shape_type": shape_hint,
            "tree_count": tree_count,
            "number_of_trees": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "tree_locations": [],
            "tree_policy": tree_policy,
            "tree_policy_json": json.dumps(tree_policy),
        }
        
        print(f"\nStep 2: Applying rotation...")
        print(f"Tool: manipulation_tools | rotation_degrees={angle} {direction}")
        response = mcp_client.call_tool("manipulation_tools", rotate_args)
        print("\n" + "=" * 60)
        print("DESIGN WORKFLOW RESULT")
        print("=" * 60)
        print(response)
        print("=" * 60)
        mcp_client.close()
        return

    # Fast path: simple scale command -> first create building, then apply scaling
    scale_request = _parse_scale_request(args.prompt) if isinstance(args.prompt, str) else None
    if scale_request and "manipulation_tools" in available_tool_names and "parametric_shape_generator" in available_tool_names:
        scale_factor, _ = scale_request
        
        print("\n" + "=" * 60)
        print("DIRECT SCALE MODE")
        print("=" * 60)
        current_memory = build_prompt_memory_state(
            args.prompt,
            existing_memory=prompt_memory_state,
            shape_hint=build_shape_generation_state(args.prompt),
        )
        print("Prompt Memory")
        print(f"Latest user prompt: {current_memory.get('latest_user_prompt', '')}")
        print(f"Latest manipulation prompt: {current_memory.get('latest_manipulation_prompt', '')}")
        print(f"Merged MCP prompt: {current_memory.get('merged_mcp_prompt', '')}")
        
        # Initialize defaults
        shape_hint = "rectangle"
        tree_count = 0
        gene_defaults = {}
        
        # Step 1: Create the building using the original shape prompt
        original_shape_prompt = current_memory.get('original_shape_prompt', '')
        if original_shape_prompt:
            shape_state = build_shape_generation_state(original_shape_prompt)
            shape_hint = shape_state.get('locked_shape_type', 'rectangle')
            tree_count = shape_state.get('tree_count', 0)
            gene_defaults = shape_state.get('gene_defaults', {})
            
            # Build shape generation payload
            shape_payload = {
                "shape_type": shape_hint,
                "locked_shape_type": shape_hint,
                "tree_count": tree_count,
                "number_of_trees": tree_count,
            }
            # Merge gene defaults (area-based parameters)
            shape_payload.update(gene_defaults)
            
            print(f"\nStep 1: Creating {shape_hint} building...")
            print(f"  Tree count: {tree_count}")
            print(f"  Parameters: {gene_defaults}")
            try:
                create_response = mcp_client.call_tool("parametric_shape_generator", shape_payload)
                print(f"  Result: Shape created successfully")
            except Exception as e:
                print(f"  Error creating shape: {e}")
                mcp_client.close()
                return
        
        # Step 2: Apply the scaling
        tree_policy = {
            "tree_count": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "inferred_tree_points": [],
            "inferred_tree_sizes": [],
            "tree_count_source": "default",
            "tree_positions_provided": False,
            "preferred_edge": "",
            "placement_mode": "",
            "notes": ""
        }
        
        scale_args = {
            "scale_factor": scale_factor,
            "apply_scale": True,
            # Include shape context for manipulation_tools
            "shape_type": shape_hint,
            "locked_shape_type": shape_hint,
            "tree_count": tree_count,
            "number_of_trees": tree_count,
            "tree_points": [],
            "tree_sizes": [],
            "tree_locations": [],
            "tree_policy": tree_policy,
            "tree_policy_json": json.dumps(tree_policy),
        }
        
        print(f"\nStep 2: Applying scaling...")
        print(f"Tool: manipulation_tools | scale_factor={scale_factor}")
        response = mcp_client.call_tool("manipulation_tools", scale_args)
        print("\n" + "=" * 60)
        print("DESIGN WORKFLOW RESULT")
        print("=" * 60)
        print(response)
        print("=" * 60)
        mcp_client.close()
        return

    # Plan Agent: prepare the strategy before the existing workflow starts
    # Use a shorter timeout for the planning LLM call so the script fails fast
    planning_timeout = min(settings.request_timeout_seconds, 15.0)
    planning_llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=planning_timeout,
    )

    try:
        planning_context = generate_plan_agent_payload(
            llm=planning_llm,
            user_prompt=args.prompt,
            tools=tools,
            layout_schema=layout_schema,
                memory_state=prompt_memory_state,
            dbg=lambda message: print(message) if settings.debug_graph else None,
        )
    except Exception as e:
        print(f"[warning] Plan agent LLM failed or timed out: {e}")
        print("Falling back to deterministic planning logic.")
        planning_context = pa._fallback_plan(
            args.prompt,
            pa.build_shape_generation_state(args.prompt),
            prompt_memory_state=prompt_memory_state,
        )

    # Auto-detect simple move commands in the user's prompt (e.g. "move the building by 2m down")
    try:
        if move_request:
            distance, arg_key = move_request
            # Prefer an available manipulation tool if present so the initial_tool_call
            # uses a tool name the MCP will accept (e.g. 'manipulation_tools').
            move_tool_name = "move"
            try:
                # look for a tool name that likely handles manipulations
                for t in tools:
                    tname = str(t.get("name", "") or "").lower()
                    if "manipul" in tname or "manipulation" in tname or "move" in tname:
                        move_tool_name = t.get("name")
                        break
            except Exception:
                move_tool_name = "move"

            move_call = {"name": move_tool_name, "arguments": {arg_key: distance}}
            planning_context = planning_context or {}
            planning_context.setdefault("initial_tool_calls", [])
            planning_context["initial_tool_calls"].insert(0, move_call)
    except Exception:
        # Non-fatal: if parsing fails, proceed without auto-injection
        pass

    print("\n" + "=" * 60)
    print("PLAN AGENT")
    print("=" * 60)
    print(format_plan_agent_response(planning_context))
    print("=" * 60)

    if should_request_clarification(planning_context):
        clarification = str(planning_context.get("clarification_question", "")).strip()
        if clarification:
            print(f"\nClarification needed: {clarification}")
        mcp_client.close()
        return

    # Run the workflow
    response = run_design_workflow(
        user_prompt=args.prompt,
        tools=tools,
        mcp_client=mcp_client,
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        debug_graph=settings.debug_graph,
        timeout_seconds=settings.request_timeout_seconds,
        max_iterations=settings.max_iterations,
        planning_context=planning_context,
        prompt_memory_state=prompt_memory_state,
    )

    print("\n" + "=" * 60)
    print("DESIGN WORKFLOW RESULT")
    print("=" * 60)
    print(response)
    print("=" * 60)

    mcp_client.close()


if __name__ == "__main__":
    main()
