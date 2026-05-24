from typing import Any

# Central registry for domain-specific sub-agents.
#
# To add a new domain later, add one entry here (for example "mass").
# The rest of the workflow reads from this registry instead of hard-coding
# separate lists in multiple files.
DOMAIN_REGISTRY: dict[str, dict[str, object]] = {
    "volume": {
        "tool_name_contains": ["volume"],
        "label": "Volume",
    },
    "area": {
        "tool_name_contains": ["area"],
        "label": "Area",
    },
}

AVAILABLE_DOMAINS: tuple[str, ...] = tuple(DOMAIN_REGISTRY.keys())


def group_tools_by_domain(tools: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    '''
    Split the MCP tools into the small domain-specific collections used by the
    child agents. Right now the tool names are the simplest source of truth:
    tools containing "volume" go to the volume agent, and tools containing
    "area" go to the area agent.
    '''

    grouped_tools: dict[str, list[dict[str, Any]]] = {
        domain: [] for domain in AVAILABLE_DOMAINS
    }

    for tool in tools:
        tool_name = str(tool.get("name", "")).lower()
        for domain_name in AVAILABLE_DOMAINS:
            domain_config = DOMAIN_REGISTRY[domain_name]
            match_tokens = domain_config.get("tool_name_contains", [])
            if not isinstance(match_tokens, list):
                continue
            if any(str(token).lower() in tool_name for token in match_tokens):
                grouped_tools[domain_name].append(tool)
                break

    return grouped_tools


def build_domain_prompt(domain_name: str, user_prompt: str) -> str:
    '''
    When a sub-agent runs, we remind it to solve only its own slice of the job.
    That keeps the volume agent from trying to answer area questions, and vice
    versa, even when the original user prompt asks for both.
    '''

    return (
        f"You are the {domain_name} specialist inside a larger workflow. "
        f"Only solve the parts of the request related to {domain_name}.\n\n"
        f"Original user request:\n{user_prompt}"
    )