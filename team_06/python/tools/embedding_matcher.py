# ============================================================================
# embedding_matcher.py — Search layouts using semantic embeddings.
#
# This tool finds the best matching layouts based on a user's natural language
# query. It embeds the query and layout descriptions, then ranks them by
# cosine similarity.
#
# Data flow:
# 1. Receive user query + descriptions from state
# 2. Load/cache embedding model (one-time initialization)
# 3. Embed user query into a vector
# 4. Embed each layout description into vectors
# 5. Calculate cosine similarity between query and each description
# 6. Rank by similarity score, return top K
# ============================================================================

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from functools import lru_cache
import logging

import numpy as np
from sklearn.decomposition import PCA

logger = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer, util
except ImportError:
    raise ImportError(
        "sentence-transformers not installed. Run: pip install sentence-transformers"
    )


# ============================================================================
# STEP 1: Load and cache the embedding model
# ============================================================================
#
# The embedding model converts text into vectors (embeddings).
# These vectors capture semantic meaning — similar texts have similar vectors.
#
# Why @lru_cache?
# - First call: loads model from disk/internet (~2-3 seconds)
# - Subsequent calls: returns cached model instantly
# - Without this, every search would reload the model (very slow!)
#
# Model: "all-MiniLM-L6-v2"
# - Fast: ~100ms per text
# - Lightweight: 22MB
# - Good for semantic search of apartment descriptions
# - Works locally (no API calls, no latency)
# ============================================================================

@lru_cache(maxsize=1)
def get_embedding_model():
    """
    Load and cache the sentence embedding model.
    
    Returns:
        SentenceTransformer: Cached model for embedding text
    """
    return SentenceTransformer("all-MiniLM-L6-v2")


# ============================================================================
# STEP 2: Core matching function
# ============================================================================
#
# This is what gets called by the LLM agent via the local_tool node.
# It receives:
# - query: User's natural language request (e.g., "cozy studio for one")
# - all_descriptions: List of layout descriptions from state
# - top_k: How many results to return
# - min_score: Minimum similarity threshold (0-1) to include results
#
# Returns:
# - Dictionary with matches, query, and count for LLM to read
# ============================================================================

def match_layouts(
    query: str,
    all_descriptions: list[dict[str, Any]],
    top_k: int = 3,
    min_score: float = 0.5
) -> dict[str, Any]:
    
    # Load model and validate input
    try:
        model = get_embedding_model()
    except Exception as e:
        logger.error(f"[embedding_matcher] Error loading model: {e}")
        raise
    
    # Early return if query is empty
    if not query or not query.strip():
        return {
            "error": "Query cannot be empty",
            "matches": [],
            "count": 0
        }
    
    # Convert the query text into a vector and compare it against all
    # descriptions in one batch to avoid repeated progress logging.
    query_embedding = model.encode(query, convert_to_tensor=True, show_progress_bar=False)

    descriptions = [item["description"] for item in all_descriptions]
    description_embeddings = model.encode(descriptions, convert_to_tensor=True, show_progress_bar=False)

    similarities = util.pytorch_cos_sim(query_embedding, description_embeddings)[0]
    results = []

    for desc_item, similarity_tensor in zip(all_descriptions, similarities):
        similarity = float(similarity_tensor.item())
        if similarity >= min_score:
            results.append({
                "layoutId": desc_item["layoutId"],
                "description": desc_item["description"],
                "score": round(similarity, 3),
                "area": desc_item.get("area"),
                "roomTypes": desc_item.get("roomTypes", [])
            })
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Limit to top_k results
    results = results[:top_k]
    logger.info(f"[embedding_matcher] Checked {len(all_descriptions)} descriptions and returned {len(results)} matches")
    
    return {
        "matches": results,
        "query": query,
        "count": len(results)
    }


# ============================================================================
# DescriptionIndex — pre-encoded description embeddings with 2D PCA projection.
#
# Build once at startup, reuse across all queries:
#   - All layout descriptions encoded to 384-dim vectors (normalised)
#   - PCA fitted to those vectors, giving a stable 2D coordinate per layout
#   - search(): cosine similarity against the pre-built matrix (fast)
#   - project(): map a new query string into the same 2D PCA space
# ============================================================================

class DescriptionIndex:

    def __init__(self, descriptions_dir: Path):
        ids: list[str] = []
        texts: list[str] = []

        for desc_file in sorted(descriptions_dir.glob("*.json")):
            try:
                payload = json.loads(desc_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            lid = payload.get("layoutId", desc_file.stem)
            desc = payload.get("description")
            if lid and desc:
                ids.append(lid)
                texts.append(desc)

        if not ids:
            raise ValueError(f"No descriptions found in {descriptions_dir}")

        logger.info(f"[DescriptionIndex] Encoding {len(ids)} descriptions…")
        model = get_embedding_model()
        matrix = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)

        # L2-normalise so dot product == cosine similarity
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms

        pca = PCA(n_components=2)
        coords_2d = pca.fit_transform(matrix)

        self._ids: list[str] = ids
        self._matrix: np.ndarray = matrix          # shape (N, 384), normalised
        self._pca: PCA = pca
        self._coords: dict[str, dict[str, float]] = {
            lid: {"x": float(x), "y": float(y)}
            for lid, (x, y) in zip(ids, coords_2d)
        }
        logger.info("[DescriptionIndex] Ready.")

    # ------------------------------------------------------------------
    @property
    def coords(self) -> dict[str, dict[str, float]]:
        """2D PCA coordinates for every layout in the index."""
        return self._coords

    # ------------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int | None = None,
        candidate_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Return (layout_id, cosine_score) pairs, best first.

        candidate_ids: if given, only rank those layouts (room-count pre-filter).
        """
        model = get_embedding_model()
        q_vec = model.encode(query, convert_to_numpy=True, show_progress_bar=False)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm

        scores = self._matrix @ q_vec  # cosine similarities, shape (N,)
        results = [
            (self._ids[i], float(scores[i]))
            for i in range(len(self._ids))
            if candidate_ids is None or self._ids[i] in candidate_ids
        ]
        results.sort(key=lambda x: x[1], reverse=True)
        if top_k is not None:
            results = results[:top_k]
        return results

    # ------------------------------------------------------------------
    def project(self, query: str) -> dict[str, float]:
        """Project a query string into the same 2D PCA space as the index."""
        model = get_embedding_model()
        q_vec = model.encode(query, convert_to_numpy=True, show_progress_bar=False)
        q_norm = np.linalg.norm(q_vec)
        if q_norm > 0:
            q_vec = q_vec / q_norm
        xy = self._pca.transform(q_vec.reshape(1, -1))[0]
        return {"x": float(xy[0]), "y": float(xy[1])}