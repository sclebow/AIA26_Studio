import json
import re
import networkx as nx
from typing import Any, List, Tuple

TOPOLOGY_SYSTEM_PROMPT = (
    "You are an assistant that extracts room nodes and their adjacencies from apartment descriptions. "
    "Return a JSON object with a list of room types (programs) and a list of adjacencies (edges as pairs of room types). "
    "If no adjacencies are specified, leave edges empty. Example output: "
    "{\"programs\": [\"bedroom\", \"kitchen\", \"living\"], \"edges\": [[\"bedroom\", \"kitchen\"]]}"
)

def parse_apartment_description(description: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    room_pattern = r"\b(bedroom|bathroom|kitchen|living|foyer|extra)s?\b"
    programs = re.findall(room_pattern, description, re.IGNORECASE)
    programs = [prog.lower() for prog in programs]

    edge_pattern = r"(\w+)\s+next to\s+(\w+)"
    edges = []
    for a, b in re.findall(edge_pattern, description, re.IGNORECASE):
        a, b = a.lower(), b.lower()
        if a in programs and b in programs:
            edges.append((a, b))

    if programs:
        return programs, edges
    return None, None

def build_graph_from_programs_and_edges(programs: List[str], edges: List[Tuple[str, str]]) -> nx.Graph:
    program_count = {}
    node_ids = []
    G = nx.Graph()
    for prog in programs:
        count = program_count.get(prog, 0) + 1
        program_count[prog] = count
        node_id = f"{prog}_{count}"
        node_ids.append(node_id)
        G.add_node(node_id, program=prog)
    for a, b in edges:
        a_id = next((nid for nid in node_ids if nid.startswith(a)), None)
        b_id = next((nid for nid in node_ids if nid.startswith(b) and nid != a_id), None)
        if a_id and b_id:
            G.add_edge(a_id, b_id)
    return G

def build_topology_node(llm: Any) -> Any:
    def topology(state: dict) -> dict:
        description = state.get("parsed_prompt") or state.get("user_prompt", "")
        iteration = state.get("iteration", 0)

        # 1. Deterministic parsing
        programs, edges = parse_apartment_description(description)
        if programs:
            G = build_graph_from_programs_and_edges(programs, edges)
            graph_json = json.dumps(nx.node_link_data(G))
            return {
                "topology_result": "success",
                "topology_graph_json_string": graph_json,
                "iteration": iteration + 1,
                "parsing_method": "deterministic"
            }

        # 2. Fallback: LLM extraction
        llm_prompt = (
            f"{TOPOLOGY_SYSTEM_PROMPT}\n"
            f"Description: {description}\n"
            "Return JSON: {\"programs\": [...], \"edges\": [[\"room1\", \"room2\"], ...]}"
        )
        try:
            response = llm.invoke(llm_prompt)
            result = json.loads(response.content.strip())
            programs = [prog.lower() for prog in result.get("programs", [])]
            edges = [(a.lower(), b.lower()) for a, b in result.get("edges", [])]
            if programs:
                G = build_graph_from_programs_and_edges(programs, edges)
                graph_json = json.dumps(nx.node_link_data(G))
                return {
                    "topology_result": "success",
                    "topology_graph_json_string": graph_json,
                    "iteration": iteration + 1,
                    "parsing_method": "llm"
                }
        except Exception as e:
            return {
                "topology_result": "failed",
                "error": f"Could not parse apartment description: {e}",
                "iteration": iteration + 1
            }

        # 3. If all fails, ask for clarification
        return {
            "topology_result": "failed",
            "error": "Please provide a list of rooms and any important adjacencies (e.g., 'bedroom next to kitchen').",
            "iteration": iteration + 1
        }

    return topology