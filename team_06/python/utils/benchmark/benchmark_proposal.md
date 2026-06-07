# Benchmark update proposal — round 2

## Context

The agent now has two LLM nodes: `reason` (already benchmarked) and `evaluate` (new).
The `search` node is not an LLM call but its results depend entirely on what `reason` produces —
so testing `reason` prompt variants directly measures search quality downstream.

---

## Changes required

### 1. Add `evaluate` node benchmark

`evaluate` takes a layout JSON + the brief (graph + description) and returns a scored assessment.

**What to test:**

| id | scenario | check |
|----|----------|-------|
| `E1` | brief has 2 bedrooms, layout has 2 bedrooms — good match | `fit_score >= 60` |
| `E2` | brief has 3 bedrooms, layout has 1 bedroom — clear mismatch | `fit_score < 60` and `concerns` non-empty |
| `E3` | brief has adjacency requirement that layout satisfies | `strengths` non-empty |
| `E4` | layout JSON is empty / malformed | node returns fallback without crashing |

Each test needs two fixtures: a **brief** (`topology_graph_json_string`) and a **layout** (`layout_json_string`).
These can be small hand-written JSON objects — they don't need to come from the real dataset.

Add `run_evaluate(llm, model)` following the same pattern as `run_reason()`.
Record `system_prompt` from `nodes/evaluate.py` in each result row.

---

### 2. Prompt ablation for `reason`

Instead of one fixed system prompt, define two or three variants and run the same
`REASON_TURNS` against each. Compare scores across variants to find which phrasing
produces more reliable structured output.

Suggested variants to test:

| id | description |
|----|-------------|
| `P_current` | Current prompt from `nodes/reason.py` (imported as-is) |
| `P_strict` | Same rules but opens with "Return ONLY raw JSON. No prose." to push models that add markdown fences |
| `P_examples` | Current prompt + one concrete few-shot example of input → output |

Add a `PROMPT_VARIANTS` list and an outer loop in `run_reason()` over variants.
Each result row gets a `prompt_variant` field (`"current"`, `"strict"`, `"examples"`) so
results are filterable in the JSON.

---

### 3. Search strategy comparison

The `search` node combines two retrieval methods via RRF:
- **Graph search** — matches on room programs and adjacency pairs
- **Description search** — matches on the free-text household/lifestyle description

Test the same query three ways by controlling what `reason` puts in the payload:

| strategy | graph | description |
|----------|-------|-------------|
| `graph_only` | populated | `""` |
| `description_only` | empty | populated |
| `both` | populated | populated |

For each strategy, record the top-4 returned layout IDs and their scores.
No ground truth is needed — the output shows side by side which layouts each strategy
surfaces and whether they diverge.

Add `run_search_strategies(repo_root)` that builds the three payloads directly
(no LLM call needed — the search node is deterministic) and calls `build_search_node()`
directly with each. Use one fixed test query that has both graph and description content:

> `"2 bedrooms, kitchen next to living. Family with a dog, both partners work from home."`

---

## Updated summary of file-level changes

| Location | Change |
|----------|--------|
| Import `SYSTEM_PROMPT` from `nodes/evaluate.py` | New import |
| `EVALUATE_FIXTURES` | New — 4 hand-written brief + layout pairs |
| `run_evaluate(llm, model)` | New runner for evaluate node |
| `PROMPT_VARIANTS` | New — list of 3 reason prompt variants |
| `run_reason()` | Add outer loop over `PROMPT_VARIANTS`; add `prompt_variant` to each row |
| `run_search_strategies(repo_root)` | New — deterministic, no LLM; compares 3 search modes |
| `__main__` loop | Add `run_evaluate`, `run_search_strategies` calls |
| `print_table()` | Handle `prompt_variant` column for reason rows |
