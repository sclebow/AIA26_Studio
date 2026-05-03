# =============================================================================
# agent_graph.py — The "brain" of the AI agent
# =============================================================================

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from mcp_client import McpClient
from nodes.classifier_node import CLASSIFIER_RESPONSE_FORMAT, create_classifier_node
from nodes.combine_node import combine_results_node
from nodes.domain_registry import AVAILABLE_DOMAINS, group_tools_by_domain
from nodes.domain_runner_node import build_domain_name_map, create_domain_runner_node
from nodes.parallel_join_node import wait_for_parallel_join_node
from nodes.tool_node import create_chat_llm
from nodes.routing import (
    WorkflowState,
    create_route_after_classifier,
)


def _build_workflow_initial_state(
    user_prompt: str,
    api_key: str,
    base_url: str,
    llm_model: str,
    timeout_seconds: float,
    debug_graph: bool,
) -> WorkflowState:
    '''
    The parent graph starts with just the user prompt. The classifier fills in
    selected_domains, and the runner nodes fill in domain-specific answers.
    '''

    return {
        "user_prompt": user_prompt,
        "selected_domains": [],
        "domain_responses": {},
        "debug_graph": debug_graph,
        "final_response": None,
        "api_key": api_key,
        "base_url": base_url,
        "llm_model": llm_model,
        "timeout_seconds": timeout_seconds,
    }


def run_agent(
    user_prompt: str,
    tools: list[dict[str, Any]],
    mcp_client: McpClient,
    api_key: str,
    base_url: str,
    llm_model: str,
    debug_graph: bool,
    timeout_seconds: float,
    max_iterations: int,
    llm_provider: str,
) -> str:
    '''
    Run a two-level LangGraph workflow.

    Level 1 is a small router graph that decides whether the question is about
    volume, area, or both.

    Level 2 is a reusable domain sub-agent. We run the same inner graph for the
    volume and area branches, but each branch receives only its own tool list.
    That means each tool node has a deliberately small and explicit tool surface.
    '''

    def dbg(message: str) -> None:
        '''
        Prints a debug message if debug_graph is True.
        '''

        if debug_graph:
            print(message)

    dbg("[graph] Initializing agent graph")
    dbg(f"[graph] Model: {llm_model}")
    dbg(f"[graph] Max iterations: {max_iterations}")

    grouped_tools = group_tools_by_domain(tools)

    classifier_llm = create_chat_llm(
        api_key=api_key,
        base_url=base_url,
        llm_model=llm_model,
        timeout_seconds=timeout_seconds,
        model_kwargs=CLASSIFIER_RESPONSE_FORMAT,
    )

    classifier_node = create_classifier_node(llm=classifier_llm, dbg=dbg)
    domain_node_names = build_domain_name_map()
    run_domain_nodes: dict[str, Callable[[WorkflowState], WorkflowState]] = {}
    for domain in AVAILABLE_DOMAINS:
        run_domain_nodes[domain] = create_domain_runner_node(
            domain_name=domain,
            tools=grouped_tools[domain],
            mcp_client=mcp_client,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            debug_graph=debug_graph,
            timeout_seconds=timeout_seconds,
            max_iterations=max_iterations,
        )

    route_after_classifier = create_route_after_classifier(dbg=dbg)

    # This outer graph does only orchestration. The actual reasoning and tool
    # calls happen inside the reusable domain sub-agents created above.
    graph = StateGraph(WorkflowState)
    graph.add_node("classify", classifier_node)
    graph.add_node("wait_for_parallel_join", wait_for_parallel_join_node)
    for domain in AVAILABLE_DOMAINS:
        graph.add_node(domain_node_names[domain], run_domain_nodes[domain])
    graph.add_node("combine", combine_results_node)
    graph.add_edge(START, "classify")

    classify_targets: dict[str, str] = {}
    for domain in AVAILABLE_DOMAINS:
        node_name = domain_node_names[domain]
        classify_targets[node_name] = node_name

    graph.add_conditional_edges(
        "classify",
        route_after_classifier,
        classify_targets,
    )

    # Every domain runner completes first, then we synchronize once at the
    # join node. This works for both single-domain and multi-domain requests
    # because non-selected domains no-op quickly.
    graph.add_edge([domain_node_names[domain] for domain in AVAILABLE_DOMAINS], "wait_for_parallel_join")
    graph.add_edge("wait_for_parallel_join", "combine")

    graph.add_edge("combine", END)

    app = graph.compile()
    dbg("[graph] Graph compiled")

    final_state = app.invoke(
        _build_workflow_initial_state(
            user_prompt=user_prompt,
            api_key=api_key,
            base_url=base_url,
            llm_model=llm_model,
            timeout_seconds=timeout_seconds,
            debug_graph=debug_graph,
        )
    )
    dbg("[graph] Final state received")
    final_response = final_state.get("final_response")
    if not isinstance(final_response, str):
        raise RuntimeError("Agent finished without a final response")

    print("\nWorkflow graph (ASCII):")
    app.get_graph().print_ascii()

    # # Save the graph visualization to a file for debugging
    # with open("graph_visualization.mmd", "w") as f:
    #     f.write(app.get_graph().draw_mermaid())

    dbg("[graph] Completed successfully")

    return final_response
