from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from langgraph.graph import END, START, StateGraph

import json

from mcp_client import McpClient
from design_state import DesignWorkflowState, build_initial_workflow_state
from central_reasoning_node import create_central_reasoning_node
from design_action_nodes import (
    create_suggestion_node,
    create_evaluation_node,
    create_optimization_node,
    create_explanation_node,
    create_visualization_node,
    create_constraint_check_node,
    create_user_feedback_node,
)
from design_tool_node import create_design_tool_node
from design_routing import (
    create_route_after_central_reasoning,
    create_route_after_action_node,
    create_route_after_constraint_check,
    create_route_after_tool_execution,
    create_route_after_user_feedback,
)
from design_registry import group_tools_by_action
from tool_node import create_chat_llm


def run_design_workflow(
    user_prompt: str,
    tools: list[dict[str, Any]],
    mcp_client: McpClient,
    api_key: str,
    base_url: str,
    llm_model: str,
    debug_graph: bool,
    timeout_seconds: float,
    max_iterations: int,
) -> str:
    """
    Run the complete site design optimization workflow.
    
    This is a complex iterative loop where:
    1. Central reasoning node decides what action to take
    2. Action-specific nodes process results
    3. Tools are executed as needed
    4. Constraints are checked
    5. Loop continues until design is complete
    """

    def dbg(message: str) -> None:
        if debug_graph:
            print(message)

    dbg("[workflow] Initializing design workflow")
    dbg(f"[workflow] Model: {llm_model}")
    dbg(f"[workflow] Max iterations: {max_iterations}")

    # Group tools by design action
    grouped_tools = group_tools_by_action(tools)

    # Create LLM for central reasoning
    llm = create_chat_llm(
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        timeout_seconds=timeout_seconds,
    )

    tool_catalog_text = "\n".join(
        f"- {tool.get('name', '<unknown>')}: {tool.get('description', '')} | inputSchema={json.dumps(tool.get('inputSchema', {}))}"
        for tool in tools
        if tool.get("name")
    )

    # Create all nodes
    try:
        central_reasoning = create_central_reasoning_node(
            llm=llm,
            dbg=dbg,
            tool_names=tool_catalog_text,
        )
    except TypeError:
        central_reasoning = create_central_reasoning_node(
            llm=llm,
            dbg=dbg,
        )
    suggestion_node = create_suggestion_node(dbg=dbg)
    evaluation_node = create_evaluation_node(dbg=dbg)
    optimization_node = create_optimization_node(dbg=dbg)
    explanation_node = create_explanation_node(dbg=dbg)
    visualization_node = create_visualization_node(dbg=dbg)
    constraint_check = create_constraint_check_node(dbg=dbg)
    user_feedback_node = create_user_feedback_node(dbg=dbg)
    
    # Tool node for all actions (use all discovered tools)
    tool_node_available = bool(tools)
    design_tool_node = None
    if tool_node_available:
        design_tool_node = create_design_tool_node(
            mcp_client=mcp_client,
            allowed_tools=tools,
            dbg=dbg,
        )

    # Create all routers
    route_after_reasoning = create_route_after_central_reasoning(dbg=dbg)
    route_after_action = create_route_after_action_node(dbg=dbg)
    route_after_constraint = create_route_after_constraint_check(dbg=dbg)
    route_after_tool = create_route_after_tool_execution(dbg=dbg)
    route_after_feedback = create_route_after_user_feedback(dbg=dbg)

    # Build the graph
    graph = StateGraph(DesignWorkflowState)

    # Add all nodes
    graph.add_node("central_reason", central_reasoning)
    graph.add_node("suggestion", suggestion_node)
    graph.add_node("evaluation", evaluation_node)
    graph.add_node("optimization", optimization_node)
    graph.add_node("explanation", explanation_node)
    graph.add_node("visualization", visualization_node)
    graph.add_node("constraint_check", constraint_check)
    graph.add_node("user_feedback", user_feedback_node)
    
    # Add design tool node only if available
    if tool_node_available and design_tool_node is not None:
        graph.add_node("design_tool", design_tool_node)
    
    graph.add_node("finish", lambda state: state)

    # Build edges
    graph.add_edge(START, "central_reason")

    # Central reasoning routes to action nodes
    graph.add_conditional_edges(
        "central_reason",
        route_after_reasoning,
        {
            "suggestion": "suggestion",
            "evaluation": "evaluation",
            "optimize": "optimization",
            "optimization": "optimization",
            "explanation": "explanation",
            "explain": "explanation",
            "visualization": "visualization",
            "visualize": "visualization",
            "design_tool": "design_tool",
            "user_feedback": "user_feedback",
            "finish": "finish",
        },
    )

    # Action nodes route to tool execution or constraint check
    for action_name in ["suggestion", "evaluation", "optimization", "explanation", "visualization"]:
        action_routes: dict[Hashable, str] = {
            "constraint_check": "constraint_check",
            "central_reason": "central_reason",
        }
        if tool_node_available:
            action_routes["design_tool"] = "design_tool"
        
        graph.add_conditional_edges(
            action_name,
            route_after_action,
            action_routes,
        )

    # Tool execution routes back to action processor (only if tool node exists)
    if tool_node_available:
        graph.add_conditional_edges(
            "design_tool",
            route_after_tool,
            {
                "suggestion": "suggestion",
                "evaluation": "evaluation",
                "optimization": "optimization",
                "explanation": "explanation",
                "visualization": "visualization",
                "central_reason": "central_reason",
                "finish": "finish",
            },
        )

    # Constraint check routes back to reasoning
    graph.add_conditional_edges(
        "constraint_check",
        route_after_constraint,
        {
            "central_reason": "central_reason",
            "finish": "finish",
        },
    )

    # User feedback loops back to reasoning
    graph.add_edge("user_feedback", "central_reason")

    # Finish ends the workflow
    graph.add_edge("finish", END)

    # Compile and run
    app = graph.compile()
    dbg("[workflow] Graph compiled")

    initial_state = build_initial_workflow_state(
        user_prompt=user_prompt,
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        timeout_seconds=timeout_seconds,
        debug_graph=debug_graph,
        max_iterations=max_iterations,
    )

    final_state = app.invoke(initial_state)
    dbg("[workflow] Workflow complete")

    final_response = final_state.get("final_response")
    if not isinstance(final_response, str) or not final_response.strip():
        tool_results = final_state.get("tool_results", [])
        if isinstance(tool_results, list) and tool_results:
            last_tool_result = tool_results[-1]
            if isinstance(last_tool_result, str) and last_tool_result.strip():
                final_response = last_tool_result
            else:
                final_response = "Design workflow completed successfully."
        else:
            last_tool_result = final_state.get("last_tool_result")
            if isinstance(last_tool_result, str) and last_tool_result.strip():
                final_response = last_tool_result
            else:
                final_response = "Design workflow completed successfully."

    if debug_graph:
        print("\nDesign workflow graph (ASCII):")
        app.get_graph().print_ascii()

    return final_response
