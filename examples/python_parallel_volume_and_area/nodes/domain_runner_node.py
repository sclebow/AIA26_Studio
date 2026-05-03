from __future__ import annotations

import json
from typing import Any, Callable, TypedDict

from mcp_client import McpClient
from nodes.domain_registry import AVAILABLE_DOMAINS, build_domain_prompt
from nodes.reason_node import create_reason_node
from nodes.routing import WorkflowState, create_route_after_reason
from nodes.tool_node import create_tool_node, get_llm_response_format, create_chat_llm
from execution_graph_ascii import print_execution_graph_ascii
from langgraph.graph import END, START, StateGraph


class AgentState(TypedDict):
    '''
    Represents the state of the AI agent during its reasoning and tool-calling loop.
    This includes the conversation history, any pending tool calls, the final response 
    if available, the current iteration count, the maximum allowed iterations, and a 
    formatted catalog of available tools.
    '''

    messages: list[dict[str, str]]
    pending_tool_calls: list[dict[str, Any]] | None
    final_response: str | None
    iteration: int
    max_iterations: int
    tool_catalog: str


def _format_tools(tools: list[dict[str, Any]]) -> str:
    '''
    Formats the list of available tools into a human-readable string.
    Each tool is represented with its name, description, and input schema.
    This reflects the definitions in the Swiftlet definition for each tool.
    '''

    lines: list[str] = []
    for tool in tools:
        name = str(tool.get("name", "<unknown>"))
        description = str(tool.get("description", ""))
        input_schema = json.dumps(tool.get("inputSchema", {}))
        lines.append(f"- {name}: {description} | inputSchema={input_schema}")
    return "\n".join(lines)


def build_initial_state(user_prompt: str, tools: list[dict[str, Any]], max_iterations: int) -> AgentState:
    '''
    Builds the initial state for the AI agent, including the user prompt,
    the formatted tool catalog, and the maximum number of iterations allowed.
    '''

    return {
        "messages": [{"role": "user", "content": user_prompt}],
        "pending_tool_calls": None,
        "final_response": None,
        "iteration": 0,
        "max_iterations": max_iterations,
        "tool_catalog": _format_tools(tools),
    }


def run_domain_agent(
    domain_name: str,
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
    '''
    This is the reusable inner agent. We use the exact same logic for both
    volume and area; the only thing that changes is the tool list and the
    small domain-specific instruction added to the user prompt.
    '''

    def dbg(message: str) -> None:
        if debug_graph:
            print(message)

    if not tools:
        raise RuntimeError(f"No {domain_name} tools were found")

    dbg(f"[graph][{domain_name}] Starting domain agent")

    llm = create_chat_llm(
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        timeout_seconds=timeout_seconds,
        model_kwargs=get_llm_response_format(tools),
    ) # This is the LLM used by the domain sub-agent

    reason_node = create_reason_node(llm=llm, dbg=dbg) # This node handles the reasoning step in the domain sub-agent
    tool_node = create_tool_node(mcp_client=mcp_client, allowed_tools=tools, dbg=dbg) # This node handles calling the appropriate tool in the domain sub-agent
    route_after_reason = create_route_after_reason(dbg=dbg) # This function decides the next step after the reasoning node

    graph = StateGraph(AgentState) # This is the state graph for the domain sub-agent
    graph.add_node("reason", reason_node) # Add the reasoning node to the domain sub-agent graph
    graph.add_node("tool", tool_node) # Add the tool node to the domain sub-agent graph
    graph.add_edge(START, "reason") # Connect the start of the graph to the reasoning node
    graph.add_conditional_edges(
        "reason",
        route_after_reason,
        {
            "run_tool": "tool",
            "finish": END,
        },
    ) # Add conditional edges from the reasoning node to either the tool node or the end node based on the route
    graph.add_edge("tool", "reason") # Connect the tool node back to the reasoning node for iterative processing

    app = graph.compile() # Compile the domain sub-agent graph into an executable app
    final_state = app.invoke(
        build_initial_state(
            build_domain_prompt(domain_name, user_prompt),
            tools,
            max_iterations,
        )
    ) # Invoke the domain sub-agent graph with the initial state

    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError(f"{domain_name.title()} agent finished without a final response")

    if debug_graph:
        print(f"\n{domain_name.title()} sub-agent graph (ASCII):")
        app.get_graph().print_ascii() # Print the ASCII representation of the domain sub-agent graph
        print_execution_graph_ascii(final_state["messages"], final_response) # Print the execution trace of the domain sub-agent graph

    dbg(f"[graph][{domain_name}] Completed successfully")
    return final_response


def create_domain_runner_node(
    domain_name: str,
    tools: list[dict[str, Any]],
    mcp_client: McpClient,
    api_key: str,
    base_url: str,
    llm_model: str,
    debug_graph: bool,
    timeout_seconds: float,
    max_iterations: int,
) -> Callable[[WorkflowState], WorkflowState]:
    '''
    Create one parent-graph node that runs a domain sub-agent and stores the
    answer in the outer workflow state.
    '''

    def run_domain(state: WorkflowState) -> WorkflowState:
        if domain_name not in state["selected_domains"]:
            # Fan-out may trigger non-selected domain nodes in a larger registry.
            # Returning no updates keeps this branch a no-op.
            return {}

        response = run_domain_agent(
            domain_name=domain_name,
            user_prompt=state["user_prompt"],
            tools=tools,
            mcp_client=mcp_client,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            debug_graph=debug_graph,
            timeout_seconds=timeout_seconds,
            max_iterations=max_iterations,
        )

        # Important for parallel fan-out: each branch returns only its own
        # domain result so the reducer can merge branch outputs safely.
        return {"domain_responses": {domain_name: response}}

    return run_domain


def build_domain_name_map() -> dict[str, str]:
    """
    Build a reusable map from domain key to graph node name.
    """

    return {domain: f"run_{domain}" for domain in AVAILABLE_DOMAINS}
