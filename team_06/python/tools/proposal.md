# Refactor Proposal: Layered Search Pipeline in `GraphSearcher`

## Current State

`GraphSearcher` (`graph_searcher.py`) exposes three independent search methods:

| Method | Algorithm | Complexity | Returns |
|---|---|---|---|
| `search_by_graph_similarity` | Jaccard / overlap on program-pair edge sets | O(n · E) per query | ranked `(id, score)` list |
| `search_by_subgraph_isomorphism` | VF2 exact subgraph matching | O(n · V! ) worst case | matched `[id]` list |
| `search_hybrid` | isomorphism first → Jaccard fallback | combined above | `{exact, approximate}` dict |

`RuleBasedEmbedder` (`rule_based_embedder.py`) is a **separate class** that:

- Builds a fixed-length feature vector per layout **once** at startup (offline phase).
- Answers queries with pure dot-product cosine similarity (online phase) — no graph traversal.
- Already accepts `programs` and `connected` flags; returns `(id, score)` list.

The two classes share `layout_graphs` as their primary input but are currently unaware of each other. `search_hybrid` uses the `candidate_ids` parameter to chain isomorphism and Jaccard, but the faster embedding pre-filter is never applied.

---

## Goal

1. **Absorb `RuleBasedEmbedder` into `GraphSearcher`** as a first-class method.
2. **Morph `search_hybrid` into `search_layered`** — a three-stage pipeline where each stage narrows the candidate pool passed to the next.

```
Stage 1 — Rule-based embedding   (fast cosine pre-filter)
     ↓  candidate_ids
Stage 2 — Graph similarity       (Jaccard ranking on candidates)
     ↓  top_k candidate_ids
Stage 3 — Subgraph isomorphism   (exact VF2 on finalists)
     ↓
Final result: exact matches + ranked approximate fallback
```

---

## Proposed Changes

### 1. Constructor — build embedding index alongside graph index

```python
class GraphSearcher:
    def __init__(self, graphs_path: str):
        self.graphs_path = graphs_path
        self.layout_graphs = self._load_graphs()
        # Build rule-based embedding index once at startup.
        # Replaces constructing a separate RuleBasedEmbedder instance externally.
        self._embedder = RuleBasedEmbedder(self.layout_graphs)
```

**Why:** the embedder index is cheap to build (one pass over the graphs) and eliminates
the need for callers to manage two separate objects with the same `layout_graphs` input.

---

### 2. New method — `search_by_embedding`

```python
def search_by_embedding(
    self,
    programs: list[str],
    connected: bool = False,
    top_k: int | None = None,
    candidate_ids: set | None = None,
) -> list[tuple[str, float]]:
    """Pre-filter layouts by rule-based cosine similarity.

    Fast O(n) scan using pre-built feature vectors — no graph traversal.
    Returns (layout_id, score) sorted best-first.

    Args:
        programs:      room types the user wants (duplicates = multiple instances).
        connected:     whether all programs must be directly connected by doors.
        top_k:         keep only the top-k results; None = keep all that pass.
        candidate_ids: restrict search to this subset (for chaining).
    """
```

Internally delegates to `self._embedder.search(...)`, but respects `candidate_ids`
and `top_k=None` (return all, not just 3) so it can serve as a soft pre-filter
rather than a terminal result.

---

### 3. Refactored method — `search_layered` (replaces `search_hybrid`)

```python
def search_layered(
    self,
    pattern_graph: nx.Graph,
    programs: list[str],
    connected: bool = False,
    embedding_top_k: int = 50,
    similarity_top_k: int = 10,
) -> dict:
    """Three-stage layered search.

    Stage 1 — Embedding pre-filter (fast, approximate):
        Cosine similarity on fixed feature vectors.
        Returns up to `embedding_top_k` candidates.

    Stage 2 — Graph similarity (medium, structural):
        Jaccard ranking applied only to the Stage-1 candidates.
        Returns up to `similarity_top_k` candidates.

    Stage 3 — Subgraph isomorphism (slow, exact):
        VF2 exact matching applied only to the Stage-2 candidates.

    Returns:
        {
          "exact":       [(layout_id, 1.0), ...],   # passed all 3 stages
          "approximate": [(layout_id, score), ...],  # passed Stage 1+2 but not exact
        }
    """
```

**Pipeline logic:**

```python
# Stage 1
embedding_results = self.search_by_embedding(
    programs, connected=connected, top_k=embedding_top_k
)
stage1_ids = {lid for lid, _ in embedding_results}

# Stage 2
similarity_results = self.search_by_graph_similarity(
    pattern_graph, candidate_ids=stage1_ids
)
stage2_ids = {lid for lid, _ in similarity_results[:similarity_top_k]}

# Stage 3
exact_ids = set(self.search_by_subgraph_isomorphism(
    pattern_graph, candidate_ids=stage2_ids
))

exact = [(lid, 1.0) for lid in exact_ids]
approximate = [
    (lid, score)
    for lid, score in similarity_results
    if lid not in exact_ids
]
return {"exact": exact, "approximate": approximate}
```

---

### 4. Backward-compatibility shim — keep `search_hybrid` as a thin wrapper

```python
def search_hybrid(self, pattern_graph, candidate_ids=None):
    """Deprecated: use search_layered instead.
    Preserved for call-sites that have not migrated yet.
    """
    exact_ids = set(self.search_by_subgraph_isomorphism(
        pattern_graph, candidate_ids=candidate_ids
    ))
    jaccard_all = self.search_by_graph_similarity(
        pattern_graph, candidate_ids=candidate_ids
    )
    exact = [(lid, 1.0) for lid in exact_ids]
    approximate = [(lid, s) for lid, s in jaccard_all if lid not in exact_ids]
    return {"exact": exact, "approximate": approximate}
```

This keeps existing call-sites working without changes while the migration happens.

---

## File Changes Summary

| File | Change |
|---|---|
| `graph_searcher.py` | Import `RuleBasedEmbedder`; update `__init__`; add `search_by_embedding`; add `search_layered`; keep `search_hybrid` as shim |
| `rule_based_embedder.py` | No changes required |
| Callers of `search_hybrid` | Migrate to `search_layered` when ready; shim keeps old interface working |

---

## Parameter Design Rationale

| Parameter | Default | Reasoning |
|---|---|---|
| `embedding_top_k` | 50 | Generous pre-filter; at dataset scale (~6 layouts) this is effectively "all". At 6 000 layouts it prunes ~99 % before graph work. |
| `similarity_top_k` | 10 | Jaccard is fast but VF2 scales poorly; limit exact-match candidates to a manageable set. |
| `connected` on `search_by_embedding` | same as caller passes | Mirrors the `build_query_vector` flag so the embedding stage aligns with the structural intent. |

---

## What Does NOT Change

- `build_topology_graph` (standalone helper) — unchanged; callers still build `pattern_graph` externally.
- `search_by_graph_similarity` signature — unchanged; `candidate_ids` parameter already supports chaining.
- `search_by_subgraph_isomorphism` signature — unchanged.
- `get_layout_info` / `get_graph_stats` — unchanged.
- `rule_based_embedder.py` — no modifications; `RuleBasedEmbedder` is imported, not rewritten.

---

## Open Questions Before Implementation

1. **`programs` duplication** — `search_layered` needs both `pattern_graph` (for Stages 2 and 3) and `programs` (for Stage 1 embedding). Should `programs` be derived from `pattern_graph` automatically, or should the caller always provide both?  
   _Suggestion: derive from `pattern_graph.nodes` so the caller only passes one thing._

2. **`embedding_top_k` at small dataset sizes** — with 6 layouts, `top_k=50` is a no-op pre-filter. Should Stage 1 be skipped automatically when `len(layout_graphs) <= embedding_top_k`?  
   _Suggestion: yes, skip Stage 1 and pass `candidate_ids=None` to Stage 2._

3. **Score normalisation** — Stage 1 and Stage 2 produce scores on different scales (cosine 0–1 vs Jaccard 0–1). For the `approximate` bucket, which score is surfaced to the caller?  
   _Suggestion: surface Stage 2 (Jaccard) scores as they are more structurally interpretable._
