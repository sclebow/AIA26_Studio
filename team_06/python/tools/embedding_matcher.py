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
from typing import Any
from functools import lru_cache
import logging

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