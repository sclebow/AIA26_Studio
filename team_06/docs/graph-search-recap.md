# Branch `feat/edge-lists` — Graph Search: Before vs After

## 1. What Changed at a Glance

| | **Before (main)** | **After (this branch)** |
|---|---|---|
| Search tool | `layout_matcher` (text embeddings) | `layout_graph_search` (topology graphs) |
| Input | Natural-language query string | List of room programs + optional edges |
| Engine | `sentence-transformers` neural model | NetworkX + custom rule-based embedder |
| Dataset | ~6 sample layouts | **100 RPLAN layouts** (pre-built graph index) |
| Result | Top-K by semantic similarity | Exact-count filtered + Jaccard / subgraph / pipeline modes |

---

## 2. How Search Worked Before (main)

```
User query: "cozy 2-bedroom with open kitchen"
         ↓
embedding_matcher.py
  → Load sentence-transformer model (all-MiniLM-L6-v2)  ← first call: ~2-3s
  → Encode query string → 384-dim vector
  → Encode EVERY layout description → 384-dim vector each
  → Cosine similarity(query_vec, desc_vec) for each layout
  → Filter by min_score=0.5, return top_k=3
```

**What the LLM saw in the tool catalog:**
```
layout_matcher(query: str, top_k: int, min_score: float)
```

**Key characteristics:**
- Entirely text-based — matched vibes/descriptions, not structure
- Required pre-written descriptions per layout (`sample_descriptions.json`)
- ML model dependency (22 MB download, external package)
- O(n) per call — no offline phase, re-embeds everything every time
- Could find "cozy apartment" but had no concept of *which rooms connect to which*

---

## 3. How Search Works Now (this branch)

### Three new files introduced:
- `team_06/python/tools/graph_searcher.py` — NetworkX-based search against a pre-built graph index
- `team_06/python/tools/rule_based_embedder.py` — offline feature vectors (no ML model)
- `team_06/python/utils/schema_to_graph.py` — converts layout JSON → NetworkX graph at build time

### Four search modes, one tool:

```
layout_graph_search(programs, connection_type, edges, search_method)
```

#### Mode 1 — `jaccard` (default)
```
programs=['bedroom','bedroom','kitchen']
         ↓
build_topology_graph() → pattern graph (nodes + optional edges)
         ↓
GraphSearcher.search_by_graph_similarity()
  → Hard filter: must have ≥2 bedrooms AND ≥1 kitchen
  → Extract program-level edge sets from each layout
  → Jaccard(pattern_edges ∩ layout_edges) / (pattern_edges ∪ layout_edges)
  → Tiebreak by connectivity density
  → Return ranked list, auto-load best match
```

#### Mode 2 — `subgraph` (exact)
```
edges=[['bedroom:1','bathroom:1'], ['bedroom:2','bathroom:2']]
         ↓
VF2 subgraph isomorphism (NetworkX)
  → Categorical node match on 'program' attribute
  → Finds layouts where the EXACT instance-level structure exists
  → e.g. "each bedroom has its own private bathroom"
  → Falls back to jaccard when no exact match found
```

#### Mode 3 — `embedding` (fast, no-ML)
```
programs=['bedroom','kitchen','living room'], connection_type='connected'
         ↓
RuleBasedEmbedder (offline index, built once at startup)
  → 15-dimensional feature vector per layout:
      [bedroom_count, kitchen_count, ..., bedroom-kitchen edge, density, is_connected]
  → Build query vector from user's programs
  → Exact-count hard filter first
  → Cosine similarity(query_vec, layout_vec)
  → O(index_size) dot products — no graph traversal
```

#### Mode 4 — `pipeline` (best for large datasets)
```
Stage 1: embedding   → pre-filter 100 layouts → top 50 (exact room counts only)
Stage 2: jaccard     → graph traversal on 50 survivors → top 10
Stage 3: subgraph    → VF2 isomorphism on ≤10 candidates (if edges specified)
```

---

## 4. Architecture Diagram

```
                     BEFORE                          AFTER
                  ┌──────────────┐            ┌──────────────────────────┐
User Query ──────►│ text embed   │            │ programs + edges         │
                  │ (neural NLP) │            │                          │
                  └──────┬───────┘            └──────┬───────────────────┘
                         │                           │
                         ▼                           ▼
                  all_descriptions            build_topology_graph()
                  (text vectors)              (NetworkX pattern graph)
                         │                           │
                         ▼                   ┌───────┴──────────────────┐
                  cosine similarity          │  GraphSearcher            │
                  (per description)          │  - jaccard similarity     │
                         │                  │  - subgraph isomorphism   │
                         ▼                  │  - rule-based embedder    │
                  top-K matches             │  - pipeline (3 stages)    │
                  by semantic score         └───────────────────────────┘
                                                       │
                                              ▼ (100 RPLAN layouts)
                                            ranked + auto-load best
```

---

## 5. Dataset Upgrade

| | Before | After |
|---|---|---|
| Source | 6 hand-crafted sample layouts | **100 RPLAN Dataset R-NB** floor plans |
| Graph index | Inline, per-call | Pre-built `graphs.json` (5,752 lines) |
| Node/room data | `name` + `program` | Same schema, with `normalize_program()` aliasing (`bed→bedroom`, `bath→bathroom`) |

---

## 6. Pros and Cons

### Pros

| # | Benefit | Detail |
|---|---|---|
| 1 | **Structural precision** | Can express exact constraints: "2 bedrooms each with its own bathroom" — impossible with text embeddings |
| 2 | **No ML model dependency** | `embedding` and `jaccard` modes need only NetworkX — no `sentence-transformers`, no model download |
| 3 | **Offline indexing** | `RuleBasedEmbedder` builds vectors once at startup; per-search cost is just dot products |
| 4 | **Progressive fallback** | `pipeline` mode degrades gracefully: exact → approximate → ranked list |
| 5 | **10× larger dataset** | 6 → 100 layouts from the RPLAN benchmark dataset |
| 6 | **Explicit edge queries** | LLM can now say `[['bedroom:1','bathroom:1']]` for instance-level connections |
| 7 | **Testable** | `test_graph_searcher.py` (181 lines) covers all modes; old `embedding_matcher` had no tests |

### Cons

| # | Limitation | Detail |
|---|---|---|
| 1 | **No semantic/vibe search** | "cozy studio" or "open-plan feel" queries are not supported — graph search only understands room types and connections |
| 2 | **Closed vocabulary** | `PROGRAMS` list in `rule_based_embedder.py` is fixed to 6 types; unlisted programs (e.g. `balcony`, `utility`) score as 0 |
| 3 | **VF2 scales poorly** | Subgraph isomorphism is NP-complete; at dataset sizes >1,000 the pipeline's pre-filtering becomes critical |
| 4 | **Edges are optional but implicit** | Without `edges`, `jaccard` only checks program-level pairs — two layouts with same rooms but different door positions get identical scores |
| 5 | **`embedding_matcher` orphaned** | The old neural text-search tool is still imported but no longer exposed to the LLM; dual-track capability is not wired together |
| 6 | **Feature vector is brittle** | Adding a new program type to `PROGRAMS` invalidates any cached/serialized vectors (order must never change) |

---

## 7. Key Commits (chronological)

| Commit | What it did |
|---|---|
| `c863b34` | First graph comparison tool added (experimental) |
| `47c19bc` | Simplified to pure graph similarity; removed old embedding-only path |
| `e334182` | **Replaced** `embedding_matcher` with `graph_searcher` as the primary search tool |
| `ad2067c` | Made `edges` parameter optional (allows presence-only queries) |
| `7de2e1e` | Cleaned up `graph_searcher` API |
| `313e456` | Implemented the 3-stage search pipeline |
| `0c16813` | Imported 100 RPLAN graphs into this branch |
| `83361c3` | Finalized pipeline search engine |
| `040bf40` | Fixed layout searcher to exact-match layout IDs |

---

## 8. Summary Statement

> **Before:** the agent found layouts by matching natural-language descriptions using a neural embedding model — good for fuzzy/semantic queries, blind to spatial structure.
>
> **After:** the agent searches by room topology using NetworkX graphs — it can find "2 bedrooms each sharing a door with a private bathroom" across 100 real floor plans, with a 3-stage pipeline that trades precision for speed at scale. The text-semantic path still exists but is no longer exposed to the LLM.
