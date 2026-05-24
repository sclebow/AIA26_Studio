import json
import re
import networkx as nx
from typing import Any, List, Tuple
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.search.rule_based_embedder import normalize_program

TOPOLOGY_SYSTEM_PROMPT = (
    "You are an assistant that extracts room nodes and their adjacencies from apartment descriptions. "
    "Return a JSON object with a list of room types (programs) and a list of adjacencies (edges as pairs of room types). "
    "If no adjacencies are specified, leave edges empty. Example output: "
    "{\"programs\": [\"bedroom\", \"kitchen\", \"living\"], \"edges\": [[\"bedroom\", \"kitchen\"]]}"
)

_ROOM_TYPES = ["bedroom", "bathroom", "kitchen", "living", "foyer", "extra", "dining", "study"]
_WORD_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def parse_apartment_description(description: str) -> Tuple[List[str], List[Tuple[str, str]]]:
    desc = description.lower()
    programs: List[str] = []
    counted: set = set()

    # Step 1: "N room_type(s)" — explicit count wins.
    count_pat = r"\b(\d+|one|two|three|four|five)\s+(bedroom|bathroom|kitchen|living|foyer|extra|dining|study)s?\b"
    for m in re.finditer(count_pat, desc):
        num_str, room = m.group(1), m.group(2)
        n = int(num_str) if num_str.isdigit() else _WORD_TO_NUM.get(num_str, 1)
        programs.extend([room] * n)
        counted.add(room)

    # Step 2: any room type not already handled by a count → add once.
    for room in _ROOM_TYPES:
        if room not in counted and re.search(rf"\b{room}s?\b", desc):
            programs.append(room)

    # Step 3: adjacency edges — "X connected to Y", "X next to Y", "X adjacent to Y".
    edge_pat = r"\b(bedroom|bathroom|kitchen|living|foyer|extra|dining|study)\b\s+(?:is\s+)?(?:connected\s+to|next\s+to|adjacent\s+to)\s+(?:the\s+)?\b(bedroom|bathroom|kitchen|living|foyer|extra|dining|study)\b"
    edges: List[Tuple[str, str]] = [
        (m.group(1), m.group(2))
        for m in re.finditer(edge_pat, desc)
    ]

    if programs:
        return programs, edges
    return None, None

def build_graph_from_programs_and_edges(programs: List[str], edges: List[Tuple[str, str]]) -> nx.Graph:
    program_count = {}
    node_ids = []
    G = nx.Graph()
    for prog in programs:
        prog = normalize_program(prog)
        count = program_count.get(prog, 0) + 1
        program_count[prog] = count
        node_id = f"{prog}_{count}"
        node_ids.append(node_id)
        G.add_node(node_id, program=prog)
    for a, b in edges:
        a = normalize_program(a)
        b = normalize_program(b)
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