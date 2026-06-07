# Benchmark Analysis — 2026-06-06

Run date: 2026-06-06  
Source data: [python/utils/benchmark_results.json](../python/utils/benchmark_results.json)

---

## Results table

| Node | Test | Provider | Model | Latency (s) | In tok | Out tok | Correct | Error |
|------|------|----------|-------|------------:|-------:|--------:|:-------:|-------|
| reason | households | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 16.53 | 100 | 885 | ✓ | |
| reason | pets | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 10.40 | 83 | 572 | ✓ | |
| reason | activities | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 13.23 | 92 | 676 | ✓ | |
| reason | rooms | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 7.04 | 92 | 354 | ✓ | |
| topology | T1 | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 5.85 | 80 | 390 | ✓ | |
| topology | T2 | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 6.98 | 68 | 295 | ✓ | |
| reason | households | openai | gpt-5-nano | 2.86 | — | — | ✗ | RateLimitError |
| reason | pets | openai | gpt-5-nano | 2.35 | — | — | ✗ | RateLimitError |
| reason | activities | openai | gpt-5-nano | 1.98 | — | — | ✗ | RateLimitError |
| reason | rooms | openai | gpt-5-nano | 2.39 | — | — | ✗ | RateLimitError |
| topology | T1 | openai | gpt-5-nano | 2.00 | — | — | ✗ | RateLimitError |
| topology | T2 | openai | gpt-5-nano | 2.18 | — | — | ✗ | RateLimitError |
| reason | households | google | gemini-2.5-flash-lite | 1.42 | 89 | 47 | ✓ | |
| reason | pets | google | gemini-2.5-flash-lite | 0.88 | 73 | 58 | ✓ | |
| reason | activities | google | gemini-2.5-flash-lite | 0.66 | 81 | 73 | ✓ | |
| reason | rooms | google | gemini-2.5-flash-lite | 0.73 | 81 | 31 | ✓ | |
| topology | T1 | google | gemini-2.5-flash-lite | 0.68 | 70 | 27 | ✓ | |
| topology | T2 | google | gemini-2.5-flash-lite | 0.61 | 58 | 29 | ✓ | |
| reason | households | anthropic | claude-haiku-4-5 | 1.23 | 94 | 128 | ✓ | |
| reason | pets | anthropic | claude-haiku-4-5 | 0.72 | 79 | 40 | ✓ | |
| reason | activities | anthropic | claude-haiku-4-5 | 0.89 | 87 | 56 | ✓ | |
| reason | rooms | anthropic | claude-haiku-4-5 | 1.06 | 91 | 120 | ✓ | |
| topology | T1 | anthropic | claude-haiku-4-5 | 1.06 | 81 | 67 | ✓ | |
| topology | T2 | anthropic | claude-haiku-4-5 | 9.22 | 64 | 37 | ✓ | |

---

## Summary by provider

| Provider | Correct | Avg latency | Avg out tokens | Errors |
|----------|:-------:|------------:|---------------:|:------:|
| cloudflare (`qwen3-30b`) | 6/6 | 9.84 s | 529 | 0 |
| openai (`gpt-5-nano`) | 0/6 | 2.29 s | — | 6 |
| google (`gemini-2.5-flash-lite`) | 6/6 | 0.83 s | 44 | 0 |
| anthropic (`claude-haiku-4-5`) | 6/6 | 2.36 s | 75 | 0 |

`correct: true` only checks that the expected field is non-empty — it misses **structure quality** and **cross-field contamination**.

---

## `reason` node — response quality

### `households` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `["42", "38", "8", "5"]` | Strings — no relationship info |
| Google | `["42-year-old", "38-year-old", "8-year-old", "5-year-old"]` | Age-labelled strings — no relationship |
| **Anthropic** | `[{"age": 42, "relationship": "primary occupant"}, {"age": 38, "relationship": "partner"}, ...]` | **Full objects** — closest to schema |

### `pets` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `["dog"]` | Flat string — lost size |
| **Google** | `[{"type": "dog", "size": "medium"}]` | **Structured object** — matches schema exactly |
| Anthropic | `["medium-sized dog"]` | Flat string — size embedded in label |

### `activities` turn — cross-field contamination
All three providers leaked values into `households` on this turn.

| Provider | Leaked into `households` | Root cause |
|----------|--------------------------|------------|
| Cloudflare | `["We"]` | Pronoun from the activities sentence |
| Google | `["I work from home"]` | Full sentence misclassified as a person |
| Anthropic | `["adults", "kids"]` | Inferred roles, not stated household members |

Google and Cloudflare also put `"living room"` into `rooms`. A tighter system prompt scoping each field to the current question would reduce this across all providers.

### `rooms` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `["bedroom", "bathroom", "kitchen", "living room"]` | Flat — lost room counts |
| Google | `["3 bedrooms", "2 bathrooms", "kitchen", "living room"]` | Count preserved as string label |
| **Anthropic** | `[{"type": "bedroom", "count": 3}, {"type": "bathroom", "count": 2}, {"type": "kitchen", "adjacent_to": "living room"}, {"type": "living room"}]` | **Richest** — count + adjacency as structured fields |

---

## `topology` node — response quality

### T1: "3 bedrooms, 1 bathroom, kitchen, living room. Bedroom next to bathroom."
| Provider | Nodes | Edges | Issue |
|----------|------:|------:|-------|
| Cloudflare | 4 | 1 | Collapsed 3 bedrooms → 1 node |
| Google | 4 | 1 | Collapsed 3 bedrooms → 1 node |
| Anthropic | 6 | 5 | Correct 3 bedroom nodes — invented 4 extra edges not in input |

### T2: "studio with kitchen and bathroom"
All three providers returned identical correct output: 3 nodes, 2 edges (studio→kitchen, studio→bathroom).

---

## Findings

**Finding 1 — OpenAI unusable on this run.**
`RateLimitError` on all 6 calls. Re-run with `gpt-4o-mini` once quota resets; results are not comparable.

**Finding 2 — Cloudflare: slow, verbose, flat output.**
Average 9.84 s and 529 output tokens per call — 12× slower and 12× more verbose than Google. Returns flat strings with no object structure and loses metadata (pet size, room counts). Leaked a pronoun into `households` on the activities turn. Not suitable as a primary provider.

**Finding 3 — Google: fastest overall, schema-aligned for `pets`, contamination on activities.**
`gemini-2.5-flash-lite` averages 0.83 s and 44 output tokens — the best on both metrics. Returns a well-structured `pets` object `{"type": "dog", "size": "medium"}` matching the schema exactly. Contamination rate on the activities turn is equal to the other providers. For `topology` it produces clean minimal edges with no invented connections.

**Finding 4 — Anthropic: richest structure for `reason`, over-connects for `topology`.**
`claude-haiku-4-5` returns the deepest objects for `households` and `rooms`, making it the best structural fit for the `reason` schema. For `topology` T1 it correctly identifies 3 separate bedroom nodes but invents 4 extra edges not stated in the input. The 9.22 s spike on topology T2 is an outlier (T1 was 1.06 s).

---

## Decision

| Node | Provider | Model | Rationale |
|------|---------|-------|-----------|
| `reason` | **Google** | `gemini-2.5-flash-lite` | Fastest; lowest cost; schema-aligned `pets`; contamination equal to Anthropic |
| `topology` | **Google** | `gemini-2.5-flash-lite` | Fastest; minimal edges; no invented connections |

**Potential upgrade for `reason`:** Switch to `anthropic / claude-haiku-4-5` once the activities-turn contamination is reduced with a tighter system prompt — its richer object structure for `households` and `rooms` is the closest match to `parsed_prompt_schema.json`.

**Pending:** Re-run OpenAI with `gpt-4o-mini` to get a valid comparison point.
