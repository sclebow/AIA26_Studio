import json


def _format_node_label(node_id: int, node_type: str, detail: str) -> str:
    '''
    Formats a node label for the ASCII execution graph.
    '''

    if detail:
        return f"[{node_id:02d}] {node_type}: {detail}"
    return f"[{node_id:02d}] {node_type}"


def _extract_tool_sequence(messages: list[dict[str, str]]) -> list[str]:
    '''
    Extracts the sequence of tool names from the assistant messages.
    '''
    tool_names: list[str] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")

        if role == "assistant":
            parsed = json.loads(content)
            tool_call = parsed.get("tool_call")
            if isinstance(tool_call, dict):
                tool_name = tool_call["name"]
                tool_names.append(tool_name)

    return tool_names


def print_execution_graph_ascii(messages: list[dict[str, str]], final_response: str) -> None:
    '''
    Prints the execution graph in ASCII format based on the sequence of tool calls
    extracted from the assistant messages, followed by the final response.
    This helps visualize the sequence of tool calls and the flow of execution.
    '''
    print("\nExecution graph (ASCII):")

    nodes: list[str] = []
    node_id = 1
    nodes.append(_format_node_label(node_id, "start", "user_prompt"))

    for tool_name in _extract_tool_sequence(messages):
        node_id += 1
        nodes.append(_format_node_label(node_id, "tool", tool_name))

    node_id += 1
    nodes.append(_format_node_label(node_id, "final", "response"))

    print(nodes[0])
    for node in nodes[1:]:
        print("  |")
        print("  v")
        print(node)

    print("\nFinal response summary:")
    print(final_response)
