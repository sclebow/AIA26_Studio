import json
from pathlib import Path
from typing import Any
import logging
from tools.boundary_embedding_matcher import match_boundaries as boundary_match_boundaries

logger = logging.getLogger(__name__)


def _load_sample_layouts_path(repo_root: Path) -> Path:
    return repo_root / "layout_inputs" / "sample_layouts.json"


def _build_candidate_rows(results: list[tuple[str, float]]) -> list[dict[str, Any]]:
    return [
        {
            "id": lid,
            "score": round(score, 3),
            "description": f"Layout {lid}",
        }
        for lid, score in results
    ]

def build_search_node() -> Any:
    """Search using the input layout boundary only."""
    def search(state: dict) -> dict:
        input_layout_json = state.get("input_layout_json_string") or state.get("layout_json_string")
        iteration = state.get("iteration", 0)

        if not input_layout_json:
            logger.error("❌ No input layout provided for boundary search")
            return {
                "search_results_json_string": json.dumps([]),
                "clarification": "No input layout was provided for boundary search. Please load a layout JSON with an outline.",
                "iteration": iteration + 1,
            }

        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            dataset_path = repo_root / "layout_inputs" / "sample_layouts.json"
            input_layout = json.loads(input_layout_json)
            input_coords = input_layout.get("outline", [])

            if not input_coords:
                logger.error("❌ Input layout does not contain an outline")
                return {
                    "search_results_json_string": json.dumps([]),
                    "clarification": "The input layout does not contain an outline to search with.",
                    "iteration": iteration + 1,
                }

            results = boundary_match_boundaries(
                input_coords=input_coords,
                dataset_path=str(dataset_path),
                top_k=3,
                min_score=0.0,
            ).get("matches", [])

            candidates = _build_candidate_rows(
                [(item.get("layoutId", "unknown"), float(item.get("score", 0.0))) for item in results]
            )

            logger.info(f"🔍 Boundary search results: {candidates}")
            logger.info(f"📌 Candidates: {candidates}")

            if not candidates:
                logger.warning(f"⚠️  No matching layouts found")
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No matching layout found with boundary-only search. How would you like to proceed?",
                    "iteration": iteration + 1,
                }

            logger.info(f"✅ Found {len(candidates)} layouts")

            return {
                "search_result": "success",
                "search_results_json_string": json.dumps(candidates),
                "iteration": iteration + 1,
            }
        except Exception as e:
            logger.error(f"❌ Boundary-only search failed: {str(e)}", exc_info=True)
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": f"Boundary-only search failed: {str(e)}. How would you like to proceed?",
                "iteration": iteration + 1,
            }
        
    return search