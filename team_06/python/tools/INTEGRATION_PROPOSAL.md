# Integration Proposal: RuleBasedEmbedder + GraphSearcher

**Date:** 2026-05-17  
**Author:** Symon Kipkemei  
**Files touched:** `tools/rule_based_embedder.py`, `tools/graph_searcher.py`, `nodes/local_tools.py`

---

## 1. Current State

The `layout_graph_search` tool (wired in `local_tools.py`) supports two search modes:

| `search_method` | Class/function | How it works |
|---|---|---|
| `"jaccard"` (default) | `GraphSearcher.search_by_graph_similarity()` | O(n) scan — re-extracts program counts + edge sets from every layout on each call |
| `"subgraph"` | `GraphSearcher.search_hybrid()` → VF2 isomorphism | Exact structural match; O(n × VF2 complexity); falls back to Jaccard |

Both methods **re-traverse every layout graph on every search call** — no caching of graph structure.

At 6 layouts this is fine. At 1,000 layouts with a specific query, `subgraph` in particular becomes expensive because VF2 isomorphism runs against every layout regardless of whether it's a plausible match.

---

## 2. What the RuleBasedEmbedder Adds

`RuleBasedEmbedder` builds a **numeric index once at startup** and replaces graph traversal with dot products at search time.

```
Offline (once):  layout graph → extract_features() → 15-dim float vector → stored in self.index
Online  (each):  user programs → build_query_vector() → cosine_similarity() against index
```

The 15-dim feature vector encodes:
- **[0–5]** room counts for 6 program types (bedroom, kitchen, living room, bathroom, dining room, study)
- **[6–12]** binary presence of 7 program-pair edges (e.g. bedroom↔kitchen)
- **[13]** graph density
- **[14]** is_connected flag

---

## 3. The Problem at Scale: Why a Pipeline Is Needed

With a **specific query** against **1,000 layouts**, running all three methods independently is wasteful:

| Method | Per-call work at 1,000 layouts |
|---|---|
| `embedding` | 1,000 dot products — microseconds |
| `jaccard` | 1,000 full graph traversals — milliseconds |
| `subgraph` | 1,000 VF2 checks — seconds (VF2 is exponential worst-case) |

The right answer is a **coarse-to-fine pipeline**: use the cheapest method to eliminate obvious mismatches first, then apply the expensive methods only to the survivors.

```
1,000 layouts
      │
      ▼  Stage 1 — embedding  (~1 ms)
   top-50 candidates          ← dot products only, no graph traversal
      │
      ▼  Stage 2 — jaccard    (~5 ms on 50, not 1,000)
   top-10 candidates
      │
      ▼  Stage 3 — subgraph   (VF2 on 10, not 1,000)
   exact matches
```

Each stage narrows the pool so the next stage only does expensive work on plausible candidates.

---

## 4. Integration Plan

### 4.1 Change `graph_searcher.py` — add `candidate_ids` filter

Both search methods currently iterate `self.layout_graphs` unconditionally. Add an optional `candidate_ids` parameter to restrict the search pool:

```python
def search_by_graph_similarity(
    self,
    topology_graph: nx.Graph,
    method: str = "jaccard",
    candidate_ids: set | None = None,   # ← new
) -> list:
    pool = (
        {k: v for k, v in self.layout_graphs.items() if k in candidate_ids}
        if candidate_ids else self.layout_graphs
    )
    for layout_id, G in pool.items():   # ← was self.layout_graphs.items()
        ...
```

Apply the same change to `search_by_subgraph_isomorphism`:

```python
def search_by_subgraph_isomorphism(
    self,
    pattern_graph: nx.Graph,
    candidate_ids: set | None = None,   # ← new
) -> list:
    pool = (
        {k: v for k, v in self.layout_graphs.items() if k in candidate_ids}
        if candidate_ids else self.layout_graphs
    )
    for layout_id, G in pool.items():   # ← was self.layout_graphs.items()
        ...
```

> `search_hybrid` calls both methods internally — update it to accept and pass through `candidate_ids` as well.

---

### 4.2 Add a cached embedder initialiser in `local_tools.py`

Next to the existing `_get_graph_searcher()`:

```python
import networkx as nx
from tools.rule_based_embedder import RuleBasedEmbedder

@lru_cache(maxsize=1)
def _get_rule_based_embedder() -> RuleBasedEmbedder:
    """Build and cache the rule-based embedding index (runs once at startup)."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    graphs_path = repo_root / "layout_inputs" / "sample_graphs.json"
    graphs_data = json.loads(graphs_path.read_text(encoding="utf-8"))
    layout_graphs = {lid: nx.node_link_graph(data) for lid, data in graphs_data.items()}
    return RuleBasedEmbedder(layout_graphs)
```

---

### 4.3 Extend the tool schema — four `search_method` options

```python
"search_method": {
    "type": "string",
    "enum": ["jaccard", "subgraph", "embedding", "pipeline"],
    "description": (
        "'jaccard' = program-level Jaccard ranking, always returns results. "
        "'subgraph' = exact structural match via graph isomorphism — use with "
        "instance-level edges for symmetric patterns ('each bedroom has its own bathroom'). "
        "'embedding' = pre-built cosine similarity index; fast count + connectivity queries. "
        "'pipeline' = embedding → jaccard → subgraph in sequence; best for specific queries "
        "against large layout sets — embedding pre-filters before the expensive steps run."
    )
}
```

---

### 4.4 Add execution branches in `local_tool_node`

**Branch A — `"embedding"` (standalone):**

```python
elif search_method == "embedding":
    if edges is not None:
        print("[local_tool] WARNING: 'embedding' ignores explicit edges — falling back to jaccard")
        search_method = "jaccard"
        # fall through to jaccard branch
    else:
        embedder = _get_rule_based_embedder()
        want_connected = (connection_type == "connected")
        results = embedder.search(programs, connected=want_connected, top_k=len(embedder.index))
        candidates = [{"layoutId": lid, "score": round(s, 3)} for lid, s in results]
        if results:
            best_layout_id, best_score = results[0]
            load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
            tool_output = {
                "pattern": pattern_desc,
                "search_method": "embedding",
                "best_match": best_layout_id,
                "best_score": round(best_score, 3),
                "all_candidates": candidates,
                "total": len(candidates),
                "message": f"Embedding search ranked {len(candidates)} layouts. Auto-loaded best: {best_layout_id}.",
            }
```

**Branch B — `"pipeline"` (coarse-to-fine):**

```python
elif search_method == "pipeline":
    embedder  = _get_rule_based_embedder()
    searcher  = _get_graph_searcher()
    want_connected = (connection_type == "connected")

    # Stage 1: embedding pre-filter — cheap, eliminates obvious mismatches
    STAGE1_K = 50
    stage1 = embedder.search(programs, connected=want_connected, top_k=STAGE1_K)
    stage1_ids = {lid for lid, _ in stage1}
    print(f"[pipeline] Stage 1 (embedding): {len(stage1_ids)} candidates from {len(embedder.index)} layouts")

    # Stage 2: jaccard on the survivors — graph traversal on 50, not all layouts
    STAGE2_K = 10
    stage2 = searcher.search_by_graph_similarity(topology_graph, method="jaccard", candidate_ids=stage1_ids)
    stage2_ids = {lid for lid, _ in stage2[:STAGE2_K]}
    print(f"[pipeline] Stage 2 (jaccard): {len(stage2_ids)} candidates")

    # Stage 3: subgraph isomorphism on top survivors — VF2 on ≤10, not all layouts
    if edges is not None:
        hybrid = searcher.search_hybrid(topology_graph, candidate_ids=stage2_ids)
        exact      = hybrid["exact"]
        approximate = hybrid["approximate"]
        best_list  = exact if exact else approximate
        all_candidates = (
            [{"layoutId": lid, "score": 1.0,          "match_type": "exact"}       for lid, _ in exact] +
            [{"layoutId": lid, "score": round(s, 2),  "match_type": "approximate"} for lid, s in approximate]
        )
    else:
        # No explicit edges — jaccard ranking is the final answer
        best_list = stage2[:STAGE2_K]
        all_candidates = [{"layoutId": lid, "score": round(s, 2)} for lid, s in best_list]

    if best_list:
        best_layout_id, best_score = best_list[0]
        load_result = _load_layout_to_state(state, reference_layout_path, best_layout_id)
        tool_output = {
            "pattern": pattern_desc,
            "search_method": "pipeline",
            "pipeline_stages": {
                "embedding_candidates": len(stage1_ids),
                "jaccard_candidates":   len(stage2_ids),
                "final_candidates":     len(all_candidates),
            },
            "best_match": best_layout_id,
            "best_score": round(best_score, 2),
            "all_candidates": all_candidates,
            "message": (
                f"Pipeline: embedding → {len(stage1_ids)} → jaccard → {len(stage2_ids)} → "
                f"subgraph → {len(all_candidates)} final. Auto-loaded {best_layout_id}."
            ),
        }
        print(f"[pipeline] Best: {best_layout_id} (score={round(best_score, 2)})")
```

---

## 5. When the LLM Should Prefer Each Method

| Query type | Recommended method |
|---|---|
| Simple room presence ("a layout with a kitchen and 2 bedrooms") | `jaccard` |
| Exact paired structure ("each bedroom has its own private bathroom") | `subgraph` |
| Count + connectivity queries at any scale | `embedding` |
| **Specific query, large layout set (100+)** | **`pipeline`** |

Add to the tool description:
> Use `"pipeline"` whenever the layout set is large and the query is specific — embedding pre-filters cheap, so jaccard and subgraph only run on plausible candidates.

---

## 6. Full Diff Summary

| File | Change |
|---|---|
| `tools/graph_searcher.py` | Add `candidate_ids: set \| None = None` to `search_by_graph_similarity`, `search_by_subgraph_isomorphism`, and `search_hybrid`; filter the iteration pool when provided |
| `nodes/local_tools.py` | Add `import networkx as nx`; add `_get_rule_based_embedder()`; extend `search_method` enum to 4 values; add `"embedding"` and `"pipeline"` branches + edge-fallback guard |
| `tools/rule_based_embedder.py` | **No changes** — already integration-ready |

Approximate new lines: ~20 in `graph_searcher.py`, ~60 in `local_tools.py`.

---

## 7. Testing Checklist

- [ ] `_get_rule_based_embedder()` called once; second call hits `lru_cache`
- [ ] `search_method="embedding"` with `connection_type="connected"` returns sensible rankings
- [ ] `search_method="embedding"` with `edges=[...]` logs warning and falls back to jaccard without error
- [ ] `search_method="pipeline"` with no `edges` stops at jaccard (Stage 2), skips VF2
- [ ] `search_method="pipeline"` with `edges` runs all three stages
- [ ] `candidate_ids=set()` (empty) returns no results without crashing
- [ ] Existing `jaccard` and `subgraph` paths called without `candidate_ids` are unaffected
- [ ] Pipeline `STAGE1_K` and `STAGE2_K` constants are easy to tune without code changes

---

## 8. Tuning the Pipeline

The two stage-size constants (`STAGE1_K=50`, `STAGE2_K=10`) are starting points. At 1,000 layouts:

| Layouts | Stage 1 K | Stage 2 K | Notes |
|---|---|---|---|
| < 100 | skip pipeline — use jaccard directly | | overhead not worth it |
| 100–500 | 30 | 10 | |
| 500–2,000 | 50 | 15 | default above |
| 2,000+ | 100 | 20 | widen net to avoid missing edge cases |

These can be exposed as optional tool parameters later if needed.

---

## 9. Future Extension

Once the index is in place, `extract_features()` can be extended (e.g. adding `"office"` to `PROGRAMS`) without touching `GraphSearcher` or `local_tools.py`. The only constraint is that the vector schema must stay consistent — any change to `PROGRAMS` or `PROGRAM_PAIRS` invalidates cached vectors and requires rebuilding the index (which happens automatically on next startup since the index is built from the raw graphs).
