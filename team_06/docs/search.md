# Search — how it works

## Overview

Search combines two independent signals and fuses them into a single score.

```
user brief
    │
    ▼
[reason node — LLM]
    │
    ├─── graph payload  ─────────────────────────────────────────────┐
    │    programs, access_pairs, adjacency_pairs,                    │
    │    not_adjacency_pairs, centrality, windows,                   │
    │    shape, area, aspect_ratio, compactness                      │
    │                                                                │
    └─── description  ───────────────────────────────────────────┐  │
         natural language summary of the layout                  │  │
                                                                 ▼  ▼
                                                           [search node]
                                                                 │
                                                          fused score
                                                    0.65 × desc + 0.35 × graph
                                                                 │
                                                           top-4 results
```

---

## Graph search (structural)

**Built offline (at startup):** every layout in the dataset is converted to a fixed-size numeric vector:
- room counts per program type (bedroom ×2, bathroom ×1, …)
- adjacency / access edge presence between room pairs
- window counts per program
- graph metrics (density, compactness, aspect ratio)

**At query time:** the user's programs are converted to the same vector format → cosine similarity is computed against the pre-built index.

**Hard filter:** layouts with fewer rooms than required (e.g. 3 bedrooms when 2 are requested) are excluded. All remaining layouts get a graph score.

---

## Description search (semantic)

**Built offline (at startup):** each layout has a text description. All descriptions are encoded with `all-MiniLM-L6-v2` (SentenceTransformer, 384-dim, runs locally) and stored as normalised vectors.

**At query time:** the description string from the reason node is encoded → cosine similarity against the pre-built matrix.

Only layouts that passed the graph filter are considered.

---

## Score fusion

```python
final_score = 0.65 * description_score + 0.35 * graph_score
```

- Description is the primary signal (semantic intent).
- Graph adds a structural tiebreaker and filters out impossible layouts.
- If there is no description query, layouts are ranked by graph score alone.
- If there are no graph constraints, description score is used directly.

---

## Embedding map (visualisation)

The 2D map is built **once at startup** from the dataset and never changes between queries.

**Offline (startup):**
```
for each layout:
    desc_vec  = SentenceTransformer(description)  → 384-dim, L2-normalised
    graph_vec = RuleBasedEmbedder(graph)           → N-dim,   L2-normalised
    combined  = concat(0.65 × desc_vec, 0.35 × graph_vec)

PCA(n=2).fit(all combined vectors) → fixed 2D coordinate per layout
```

> *L2-normalised* means each vector is divided by its own length so it has magnitude 1. This makes dot product equal to cosine similarity, and puts all vectors on the same scale before concatenating.

The PCA uses the same fusion weights (65/35) as the search scores, so dot proximity in the map reflects how similar two layouts would score against each other.

**Per query (online):**
```
desc_vec  = SentenceTransformer(description_query)  → encoded
graph_vec = build_query_vector(programs, pairs, …)  → same N-dim format
combined  = concat(0.65 × desc_vec, 0.35 × graph_vec)

query_coord = PCA.transform(combined)   ← projects INTO the fixed space
```

The layout cloud is fixed. Only the query dot (✦) moves per search.

**Result:** layouts close to the query dot are both semantically and structurally similar to the brief.

### Dot legend

| Dot style         | Meaning                        |
|-------------------|-------------------------------|
| Large orange      | Top result (auto-selected)    |
| Medium blue       | Other top-k results           |
| Small grey        | All other layouts in dataset  |
| ✦ crosshair       | Query position                |
| Orange ring + №   | Pinned (for "find in between")|

### User interactions

| Action              | Effect                                        |
|---------------------|-----------------------------------------------|
| Hover               | Show layout miniature + description tooltip   |
| Click               | Sticky popup with Select / Pin buttons        |
| Select              | Run pipeline with that layout                 |
| Pin two layouts     | Enable "Find in between" → new search         |
