from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

import networkx as nx

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.search import build_search_node
from tools.boundary_embedding_matcher import match_boundaries


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dataset_path(repo_root: Path) -> Path:
    return repo_root / "layout_inputs" / "sample_layouts.json"


def _build_topology_graph_json(layout: dict[str, Any]) -> str | None:
    rooms = layout.get("rooms", [])
    if not rooms:
        return None

    graph = nx.Graph()
    room_ids: list[str] = []

    for index, room in enumerate(rooms):
        room_id = room.get("id") or f"room-{index + 1}"
        program = room.get("attributes", {}).get("program") or room.get("name", "")
        graph.add_node(room_id, program=str(program).lower())
        room_ids.append(room_id)

    for door in layout.get("doors", []):
        connected = door.get("attributes", {}).get("connectsRooms", [])
        if len(connected) >= 2:
            left, right = connected[0], connected[1]
            if left in graph and right in graph:
                graph.add_edge(left, right)

    if graph.number_of_edges() == 0 and room_ids:
        hub = next((room_id for room_id in room_ids if graph.nodes[room_id].get("program") == "living"), room_ids[0])
        for room_id in room_ids:
            if room_id != hub:
                graph.add_edge(room_id, hub)

    return json.dumps(nx.node_link_data(graph))


def _top_matches(search_results_json: str, top_k: int = 3) -> list[dict[str, Any]]:
    try:
        results = json.loads(search_results_json)
    except Exception:
        return []
    return results[:top_k]


def _run_search_mode(layout: dict[str, Any], search_mode: str) -> dict[str, Any]:
    search_node = build_search_node()
    topology_graph_json_string = _build_topology_graph_json(layout)

    state: dict[str, Any] = {
        "search_mode": search_mode,
        "input_layout_json_string": json.dumps(layout),
        "layout_json_string": json.dumps(layout),
        "iteration": 0,
    }
    if topology_graph_json_string is not None:
        state["topology_graph_json_string"] = topology_graph_json_string

    if search_mode in {"graph_only", "hybrid"} and topology_graph_json_string is None:
        return {
            "status": "skipped",
            "reason": "layout does not contain rooms, so no topology graph could be built",
            "matches": [],
        }

    if search_mode == "boundary_only":
        boundary_results = match_boundaries(
            input_coords=layout.get("outline", []),
            dataset_path=_dataset_path(Path(__file__).resolve().parent.parent.parent),
            top_k=3,
            min_score=0.0,
        ).get("matches", [])
        return {
            "status": "success" if boundary_results else "empty",
            "matches": boundary_results,
        }

    result_state = search_node(state)
    matches = _top_matches(result_state.get("search_results_json_string", "[]"))
    return {
        "status": result_state.get("search_result", "unknown"),
        "matches": matches,
        "clarification": result_state.get("clarification"),
    }


def _iter_query_files(query_dir: Path) -> list[Path]:
    return sorted(p for p in query_dir.glob("*.json") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch evaluator for boundary, graph, and hybrid search modes.")
    parser.add_argument("--query", type=Path, action="append", help="Query layout JSON file to evaluate. Can be repeated.")
    parser.add_argument("--query-dir", type=Path, help="Directory containing query layout JSON files.")
    parser.add_argument("--modes", nargs="+", default=["boundary_only", "graph_only", "hybrid"], choices=["boundary_only", "graph_only", "hybrid"], help="Search modes to evaluate.")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent.parent.parent / "output", help="Directory where JSON/CSV summaries are written.")
    parser.add_argument("--output-name", type=str, help="Base filename for the generated JSON/CSV summaries.")
    args = parser.parse_args()

    if not args.query and not args.query_dir:
        parser.error("Provide either --query or --query-dir.")

    repo_root = Path(__file__).resolve().parent.parent.parent
    query_files = list(args.query or [])
    if args.query_dir:
        query_files.extend(_iter_query_files(args.query_dir))
    if not query_files:
        raise SystemExit("No query JSON files found.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary: list[dict[str, Any]] = []

    for query_file in query_files:
        layout = _read_json(query_file)
        query_entry: dict[str, Any] = {
            "query_file": str(query_file),
            "layoutId": layout.get("layoutId"),
            "modes": {},
        }

        for mode in args.modes:
            mode_result = _run_search_mode(layout, mode)
            mode_matches = mode_result.get("matches", [])
            query_entry["modes"][mode] = {
                "status": mode_result.get("status"),
                "reason": mode_result.get("reason"),
                "clarification": mode_result.get("clarification"),
                "top_matches": mode_matches,
            }

        summary.append(query_entry)

    output_name = args.output_name
    if not output_name:
        output_name = f"search_evaluation_{query_files[0].stem}" if len(query_files) == 1 else "search_evaluation_summary"

    json_path = args.output_dir / f"{output_name}.json"
    csv_path = args.output_dir / f"{output_name}.csv"

    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_rows = []
    for entry in summary:
        row: dict[str, Any] = {
            "query_file": entry["query_file"],
            "layoutId": entry.get("layoutId"),
        }
        for mode in args.modes:
            mode_info = entry["modes"].get(mode, {})
            matches = mode_info.get("top_matches", [])
            row[f"{mode}_status"] = mode_info.get("status")
            for rank in range(3):
                prefix = f"{mode}_rank{rank + 1}"
                if rank < len(matches):
                    row[f"{prefix}_id"] = matches[rank].get("id") or matches[rank].get("layoutId")
                    row[f"{prefix}_score"] = matches[rank].get("score")
                else:
                    row[f"{prefix}_id"] = ""
                    row[f"{prefix}_score"] = ""
        csv_rows.append(row)

    fieldnames: list[str] = ["query_file", "layoutId"]
    for mode in args.modes:
        fieldnames.append(f"{mode}_status")
        fieldnames.extend([
            f"{mode}_rank1_id",
            f"{mode}_rank1_score",
            f"{mode}_rank2_id",
            f"{mode}_rank2_score",
            f"{mode}_rank3_id",
            f"{mode}_rank3_score",
        ])

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())