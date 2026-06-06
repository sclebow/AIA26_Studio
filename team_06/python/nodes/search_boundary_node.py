import json
from pathlib import Path
from typing import Any
import logging
from tools.boundary_embedding_matcher import match_boundaries

logger = logging.getLogger(__name__)


def _extract_outline_from_state(state: dict) -> list[list[float]] | None:
    """Extract outline coordinates from the state's layout data."""
    # Try to get outline from the current layout
    layout_json = state.get("layout_json_string")
    if layout_json:
        try:
            layout = json.loads(layout_json)
            outline = layout.get("outline")
            if outline and isinstance(outline, list):
                return outline
        except json.JSONDecodeError:
            pass
    
    # Try to get from topology_graph_json_string
    topology_json = state.get("topology_graph_json_string")
    if topology_json:
        try:
            topology = json.loads(topology_json)
            outline = topology.get("outline")
            if outline and isinstance(outline, list):
                return outline
        except json.JSONDecodeError:
            pass
    
    return None


def _extract_circulation_from_state(state: dict) -> list[dict] | None:
    """Extract circulation data from the state's layout data."""
    layout_json = state.get("layout_json_string")
    if layout_json:
        try:
            layout = json.loads(layout_json)
            circulation = layout.get("circulation")
            if circulation and isinstance(circulation, list):
                return circulation
        except json.JSONDecodeError:
            pass
    
    topology_json = state.get("topology_graph_json_string")
    if topology_json:
        try:
            topology = json.loads(topology_json)
            circulation = topology.get("circulation")
            if circulation and isinstance(circulation, list):
                return circulation
        except json.JSONDecodeError:
            pass
    
    return None


def _load_layout_descriptions(repo_root: Path) -> dict[str, str]:
    """Load layout descriptions from sample_layouts.json and Planfinder_Dataset."""
    descriptions: dict[str, str] = {}

    # Load from sample_layouts.json
    layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
    if layouts_path.exists():
        try:
            layouts = json.loads(layouts_path.read_text(encoding="utf-8"))
            for layout in layouts:
                layout_id = layout.get("layoutId")
                description = layout.get("apartment", {}).get("attributes", {}).get("description")
                if layout_id and description:
                    descriptions[layout_id] = description
        except Exception as e:
            logger.warning(f"Failed to load descriptions from sample_layouts.json: {e}")

    # Load from Planfinder_Dataset
    planfinder_dir = repo_root / "layout_inputs" / "Planfinder_Dataset"
    if planfinder_dir.exists():
        for layout_file in planfinder_dir.glob("*.json"):
            try:
                layout = json.loads(layout_file.read_text(encoding="utf-8"))
                layout_id = layout.get("layoutId", layout_file.stem)
                description = layout.get("apartment", {}).get("attributes", {}).get("description")
                if layout_id and description:
                    descriptions[layout_id] = description
            except Exception:
                continue

    return descriptions


def build_search_boundary_node() -> Any:
    """Search layouts by boundary shape using turning function similarity."""
    def search_boundary(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("boundary_top_k") or state.get("graph_top_k") or 4
        min_score = state.get("boundary_min_score", 0.5)
        
        # Extract outline and circulation from state
        outline = _extract_outline_from_state(state)
        circulation = _extract_circulation_from_state(state)
        
        if not outline:
            logger.error("❌ No outline found in state for boundary search")
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": "No boundary outline found. Please provide a layout with an outline to search by boundary shape.",
                "iteration": iteration + 1
            }

        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            
            # Prepare input layout with outline and circulation
            input_layout = {
                "outline": outline,
                "circulation": circulation or []
            }
            
            # Load layout descriptions
            descriptions = _load_layout_descriptions(repo_root)
            
            # Search in sample_layouts.json
            sample_layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
            results = []
            
            if sample_layouts_path.exists():
                logger.info(f"🔍 Searching sample_layouts.json by boundary shape...")
                sample_results = match_boundaries(
                    input_graph=input_layout,
                    dataset_path=str(sample_layouts_path),
                    top_k=top_k,
                    min_score=min_score
                )
                
                if sample_results.get("matches"):
                    for match in sample_results["matches"]:
                        results.append((match["layoutId"], match["score"]))
                    logger.info(f"✅ Found {len(sample_results['matches'])} matches in sample_layouts")
            
            # Search in Planfinder_Dataset if available
            planfinder_path = repo_root / "layout_inputs" / "Planfinder_Dataset"
            planfinder_json = None
            
            # Look for a consolidated planfinder JSON or search individual files
            for possible_name in ["planfinder_layouts.json", "Planfinder_Dataset.json"]:
                candidate = repo_root / "layout_inputs" / possible_name
                if candidate.exists():
                    planfinder_json = candidate
                    break
            
            if planfinder_json and planfinder_json.exists():
                logger.info(f"🔍 Searching Planfinder dataset by boundary shape...")
                pf_results = match_boundaries(
                    input_graph=input_layout,
                    dataset_path=str(planfinder_json),
                    top_k=top_k,
                    min_score=min_score
                )
                
                if pf_results.get("matches"):
                    for match in pf_results["matches"]:
                        results.append((match["layoutId"], match["score"]))
                    logger.info(f"✅ Found {len(pf_results['matches'])} matches in Planfinder")
            
            # Sort by score and deduplicate
            results = sorted(results, key=lambda x: x[1], reverse=True)
            
            deduped_results: list[tuple[str, float]] = []
            seen_layout_ids: set[str] = set()
            for layout_id, score in results:
                if layout_id in seen_layout_ids:
                    continue
                seen_layout_ids.add(layout_id)
                deduped_results.append((layout_id, score))
            
            # Build candidate list
            candidates = [
                {
                    "id": layout_id,
                    "score": round(score, 2),
                    "description": descriptions.get(layout_id, f"Layout {layout_id} (boundary match)"),
                }
                for layout_id, score in deduped_results[:top_k]
            ]
            
            logger.info(f"📌 Boundary search candidates: {candidates}")
            
            if not candidates:
                logger.warning("⚠️  No matching boundaries found")
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No layouts with similar boundary shapes found. How would you like to proceed? (Type 'end' to exit or write a new request)",
                    "iteration": iteration + 1,
                }
            
            logger.info(f"✅ Found {len(candidates)} layouts with similar boundaries")
            
            return {
                "search_result": "select",
                "search_results_json_string": json.dumps(candidates),
                "layout_id": candidates[0]["id"],
                "iteration": iteration + 1,
            }
            
        except Exception as e:
            logger.error(f"❌ Boundary search failed: {str(e)}", exc_info=True)
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": f"Boundary search failed: {str(e)}. How would you like to proceed?",
                "iteration": iteration + 1,
            }
    
    return search_boundary
