from typing import Annotated, Any, Callable, TypedDict

from langgraph.types import Send

from nodes.domain_registry import AVAILABLE_DOMAINS


def _merge_domain_responses(
    existing: dict[str, str] | None,
    incoming: dict[str, str] | None,
) -> dict[str, str]:
    """
    Merge partial domain response dictionaries produced by parallel branches.
    """

    merged: dict[str, str] = {}
    if isinstance(existing, dict):
        merged.update(existing)
    if isinstance(incoming, dict):
        merged.update(incoming)
    return merged


class WorkflowState(TypedDict):
    '''
    The outer workflow state decides which domain-specific sub-agent should run.

    Think of this as the "project manager" state. It does not store the inner
    tool-calling conversation history. Instead, it stores the user's prompt,
    the chosen route, and the finished result from each domain sub-agent.
    '''

    user_prompt: str
    selected_domains: list[str]
    domain_responses: Annotated[dict[str, str], _merge_domain_responses]
    final_response: str | None
    api_key: str
    base_url: str
    llm_model: str
    timeout_seconds: float
    debug_graph: bool


def create_route_after_reason(dbg: Callable[[str], None]) -> Callable[[dict[str, Any]], str]:
    '''
    Decide whether to finish the workflow or run the tool node next.
    '''

    def route_after_reason(state: dict[str, Any]) -> str:
        if state["final_response"] is not None:
            dbg("[graph][route] reason -> finish")
            return "finish"
        dbg("[graph][route] reason -> run_tool")
        return "run_tool"

    return route_after_reason


def create_route_after_classifier(dbg: Callable[[str], None]) -> Callable[[WorkflowState], str | list[Send]]:
    '''
    Dispatch all domain runner nodes in one step using Send packets.

    Selected domains will do real work, and non-selected domains will no-op.
    This gives us one consistent barrier pattern for both single-domain and
    multi-domain requests.
    '''

    def route_after_classifier(state: WorkflowState) -> list[Send]:
        selected_domains = state["selected_domains"]
        if not selected_domains:
            raise RuntimeError("Workflow classifier returned no selected domains")

        unique_domains = list(dict.fromkeys(selected_domains))
        dbg("[graph][route] classify -> direct multi-send (all domains)")
        return [
            Send(
                f"run_{domain}",
                {
                    "user_prompt": state["user_prompt"],
                    "selected_domains": unique_domains,
                    "domain_responses": state.get("domain_responses", {}),
                    "final_response": state.get("final_response"),
                },
            )
            for domain in AVAILABLE_DOMAINS
        ]

    return route_after_classifier


