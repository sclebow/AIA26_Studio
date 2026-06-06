import json
from pathlib import Path
from typing import Any
import logging
from tools.boundary_embedding_matcher import match_boundaries
from tools.boundary_analyzer import (
    compute_boundary_stats,
    calculate_area_score,
    calculate_iou_with_rotation,
    calculate_topology_score,
    calculate_composite_score,
)

logger = logging.getLogger(__name__)

# Stage 1: cosine similarity (turning function) weight
# Stage 2: geometric composite (IoU + area + topology) weight
COSINE_WEIGHT = 0.4
GEO_WEIGHT = 0.6

# How many cosine candidates to feed into the geometric re-ranker
SCREEN_MULTIPLIER = 5
MAX_SCREEN_CANDIDATES = 20


def _extract_outline_from_state(state: dict) -> list[list[float]] | None:
    layout_json = state.get("layout_json_string")
    if layout_json:
        try:
            layout = json.loads(layout_json)
            outline = layout.get("outline")
            if outline and isinstance(outline, list):
                return outline
        except json.JSONDecodeError:
            pass

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
    descriptions: dict[str, str] = {}

    pf_jsons_dir = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons"
    if pf_jsons_dir.exists():
        for layout_file in pf_jsons_dir.glob("*.json"):
            try:
                layout = json.loads(layout_file.read_text(encoding="utf-8"))
                layout_id = layout.get("layoutId", layout_file.stem)
                description = layout.get("apartment", {}).get("attributes", {}).get("description")
                if layout_id and description:
                    descriptions[layout_id] = description
            except Exception:
                continue

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

    return descriptions


def _rerank_with_geometry(
    cosine_matches: list[dict],
    input_outline: list[list[float]],
) -> list[dict]:
    """Re-rank cosine-screened candidates by blending with IoU + area + topology score."""
    input_stats = compute_boundary_stats(input_outline)
    scored = []
    for match in cosine_matches:
        coords = match["boundary_graph"]["coordinates"]
        cosine_score = match["score"]

        candidate_stats = compute_boundary_stats(coords)
        area_score = calculate_area_score(input_stats["area"], candidate_stats["area"])
        iou_score = calculate_iou_with_rotation(input_outline, coords)
        topo_score = calculate_topology_score(input_stats, candidate_stats)
        geo_score = calculate_composite_score(area_score, iou_score, topo_score)

        final_score = COSINE_WEIGHT * cosine_score + GEO_WEIGHT * geo_score
        scored.append({
            "layoutId": match["layoutId"],
            "score": round(float(final_score), 3),
            "cosine_score": round(float(cosine_score), 3),
            "geo_score": round(float(geo_score), 3),
            "iou_score": round(float(iou_score), 3),
            "area_score": round(float(area_score), 3),
            "name": match.get("name"),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def build_search_boundary_node() -> Any:
    """Search layouts by boundary shape: cosine screen → geometric re-rank."""
    def search_boundary(state: dict) -> dict:
        iteration = state.get("iteration", 0)
        top_k = state.get("boundary_top_k") or state.get("graph_top_k") or 4
        min_score = state.get("boundary_min_score", 0.5)

        outline = _extract_outline_from_state(state)
        circulation = _extract_circulation_from_state(state)

        if not outline:
            logger.error("❌ No outline found in state for boundary search")
            return {
                "search_result": "failed",
                "search_results_json_string": json.dumps([]),
                "clarification": "No boundary outline found. Please provide a layout with an outline to search by boundary shape.",
                "iteration": iteration + 1,
            }

        try:
            repo_root = Path(__file__).resolve().parent.parent.parent
            input_layout = {"outline": outline, "circulation": circulation or []}
            descriptions = _load_layout_descriptions(repo_root)

            # ----------------------------------------------------------------
            # Stage 1 — fast cosine screen
            # Fetch more candidates than needed so the geometric re-ranker has
            # enough material to re-order meaningfully.
            # ----------------------------------------------------------------
            screen_k = min(top_k * SCREEN_MULTIPLIER, MAX_SCREEN_CANDIDATES)
            cosine_pool: list[dict] = []

            sample_layouts_path = repo_root / "layout_inputs" / "sample_layouts.json"
            if sample_layouts_path.exists():
                logger.info("🔍 Stage 1 — cosine screen: sample_layouts.json")
                res = match_boundaries(
                    input_graph=input_layout,
                    dataset_path=str(sample_layouts_path),
                    top_k=screen_k,
                    min_score=0.0,
                )
                cosine_pool.extend(res.get("matches", []))

            pf_jsons_path = repo_root / "layout_inputs" / "Planfinder_Dataset" / "pf_jsons"
            if pf_jsons_path.exists():
                logger.info("🔍 Stage 1 — cosine screen: pf_jsons (precomputed vectors)")
                res = match_boundaries(
                    input_graph=input_layout,
                    dataset_path=str(pf_jsons_path),
                    top_k=screen_k,
                    min_score=0.0,
                )
                cosine_pool.extend(res.get("matches", []))

            # Deduplicate by layoutId, keeping the higher cosine score
            seen: dict[str, dict] = {}
            for m in cosine_pool:
                lid = m["layoutId"]
                if lid not in seen or m["score"] > seen[lid]["score"]:
                    seen[lid] = m
            cosine_pool = sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:screen_k]

            if not cosine_pool:
                logger.warning("⚠️  Cosine screen returned no candidates")
                return {
                    "search_result": "failed",
                    "search_results_json_string": json.dumps([]),
                    "clarification": "No layouts with similar boundary shapes found. How would you like to proceed? (Type 'end' to exit or write a new request)",
                    "iteration": iteration + 1,
                }

            # ----------------------------------------------------------------
            # Stage 2 — geometric re-ranking (IoU + area + topology)
            # Only runs on the small cosine-screened pool, not all 546 layouts.
            # ----------------------------------------------------------------
            logger.info(f"📐 Stage 2 — geometric re-ranking {len(cosine_pool)} candidates...")
            reranked = _rerank_with_geometry(cosine_pool, outline)

            # Apply min_score filter on the blended final score
            reranked = [r for r in reranked if r["score"] >= min_score][:top_k]

            candidates = [
                {
                    "id": r["layoutId"],
                    "score": r["score"],
                    "cosine_score": r["cosine_score"],
                    "geo_score": r["geo_score"],
                    "iou_score": r["iou_score"],
                    "area_score": r["area_score"],
                    "description": descriptions.get(r["layoutId"], f"Layout {r['layoutId']} (boundary match)"),
                }
                for r in reranked
            ]

            logger.info(f"📌 Boundary search candidates: {candidates}")

            if not candidates:
                logger.warning("⚠️  No candidates survived the min_score filter")
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
