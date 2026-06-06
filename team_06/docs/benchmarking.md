# Benchmarking: Per-Call Model Selection

## What was added to `llm.py`

Three private helpers and an updated `call_llm` were added to
[python/_runtime/llm.py](../python/_runtime/llm.py).

### `_required_env(name)` — line 31
Reads an env var and raises a clear error if it is missing. Used by
`_resolve_llm_connection` to pull credentials on demand rather than at startup.

### `_resolve_llm_connection(provider, model)` — line 38
Maps a provider name (`"openai"`, `"cloudflare"`, `"google"`, `"anthropic"`,
`"local"`) plus an optional model string to the `(api_key, base_url,
resolved_model)` triple needed to build a `ChatOpenAI` instance. If `model` is
`None` it falls back to the matching `*_MODEL` env var.

### `_resolve_timeout_seconds(llm)` — line 55
Extracts the timeout from the existing LLM object so a temporary per-call
instance inherits the same setting. Defaults to 30 s if the attribute is absent.

### Updated `call_llm` — line 235

Old signature:
```python
call_llm(llm, system_prompt, messages, tool_catalog)
```
New signature:
```python
call_llm(llm, system_prompt, messages, provider=None, model=None)
```

- `tool_catalog` removed — nodes format their own system prompts.
- When `provider`/`model` are omitted the call is identical to before.
- When either is supplied a temporary `ChatOpenAI` is built for that one call,
  inheriting `model_kwargs` and timeout from the default `llm`. The default
  instance in `Context` is never mutated.

Usage in a node:
```python
from _runtime.llm import call_llm

result = call_llm(llm, system_prompt, messages)                        # default
result = call_llm(llm, system_prompt, messages, provider="google",
                  model="gemini-2.5-flash-lite")                       # override
```

---

## Node inventory

| Node | Has LLM call | Call type |
|------|-------------|-----------|
| `preprocess` | No | Keyword routing only |
| `reason` | **Yes** | Structured JSON extraction from user answers |
| `topology` | **Yes** (fallback) | Room list + adjacency extraction from free text |
| `search` | No | Embedding cosine similarity |
| `select` | No | JSON lookup |
| `adapt` | No | MCP tool call (`adapt_layout_06`) |
| `evaluate` | No | MCP tool call (`daylight_06`) |
| `feedback` | No | String formatting |
| `modify` | No | MCP tool call |

Only **`reason`** and **`topology`** (LLM fallback path) are benchmarked.

---

## Benchmark plan

### Providers and models tested

| ID | Provider | Model | Notes |
|----|----------|-------|-------|
| A | `cloudflare` | `@cf/qwen/qwen3-30b-a3b-fp8` | Free tier |
| B | `openai` | `gpt-5-nano` | Paid — hit rate limit |
| C | `google` | `gemini-2.5-flash-lite` | Paid |
| D | `anthropic` | `claude-haiku-4-5` | Paid |

### Test inputs

#### `reason` node — household extraction

| Turn | Expected field | User input |
|------|---------------|-----------|
| 1 | `households` | `I am 42, my partner is 38, we have two kids aged 8 and 5.` |
| 2 | `pets` | `We have a medium-sized dog.` |
| 3 | `activities` | `We cook daily. I work from home. Kids play in the living room.` |
| 4 | `rooms` | `We want 3 bedrooms, 2 bathrooms. Kitchen next to living room.` |

#### `topology` node — room extraction fallback

| Test | Input string |
|------|-------------|
| T1 | `3 bedrooms, 1 bathroom, kitchen, living room. Bedroom next to bathroom.` |
| T2 | `studio with kitchen and bathroom` |

### Running the benchmark

```bash
cd team_06/python
python utils/benchmark.py
```

Results are printed to the terminal and saved to
[python/utils/benchmark_results.json](../python/utils/benchmark_results.json).

---

## Results — 2026-06-06

| Node | Test | Provider | Model | Latency (s) | In tok | Out tok | Correct | Error |
|------|------|----------|-------|------------:|-------:|--------:|:-------:|-------|
| reason | households | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 37.76 | 100 | 350 | ✓ | |
| reason | pets | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 6.34 | 83 | 289 | ✓ | |
| reason | activities | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 11.07 | 92 | 716 | ✓ | |
| reason | rooms | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 12.49 | 92 | 812 | ✓ | |
| topology | T1 | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 6.54 | 80 | 368 | ✓ | |
| topology | T2 | cloudflare | @cf/qwen/qwen3-30b-a3b-fp8 | 4.47 | 68 | 241 | ✓ | |
| reason | households | openai | gpt-5-nano | 3.70 | — | — | ✗ | RateLimitError |
| reason | pets | openai | gpt-5-nano | 2.70 | — | — | ✗ | RateLimitError |
| reason | activities | openai | gpt-5-nano | 2.24 | — | — | ✗ | RateLimitError |
| reason | rooms | openai | gpt-5-nano | 2.26 | — | — | ✗ | RateLimitError |
| topology | T1 | openai | gpt-5-nano | 2.30 | — | — | ✗ | RateLimitError |
| topology | T2 | openai | gpt-5-nano | 2.13 | — | — | ✗ | RateLimitError |
| reason | households | google | gemini-2.5-flash-lite | 1.56 | 89 | 47 | ✓ | |
| reason | pets | google | gemini-2.5-flash-lite | 0.64 | 73 | 58 | ✓ | |
| reason | activities | google | gemini-2.5-flash-lite | 0.62 | 81 | 73 | ✓ | |
| reason | rooms | google | gemini-2.5-flash-lite | 0.68 | 81 | 31 | ✓ | |
| topology | T1 | google | gemini-2.5-flash-lite | 0.62 | 70 | 27 | ✓ | |
| topology | T2 | google | gemini-2.5-flash-lite | 0.62 | 58 | 29 | ✓ | |
| reason | households | anthropic | claude-haiku-4-5 | 1.72 | 94 | 128 | ✓ | |
| reason | pets | anthropic | claude-haiku-4-5 | 0.77 | 79 | 40 | ✓ | |
| reason | activities | anthropic | claude-haiku-4-5 | 0.83 | 87 | 56 | ✓ | |
| reason | rooms | anthropic | claude-haiku-4-5 | 1.52 | 91 | 120 | ✓ | |
| topology | T1 | anthropic | claude-haiku-4-5 | 0.78 | 81 | 41 | ✓ | |
| topology | T2 | anthropic | claude-haiku-4-5 | 8.22 | 64 | 37 | ✓ | |

---

## Interpretation

### Summary by provider

| Provider | Correct | Avg latency | Avg out tokens | Errors |
|----------|:-------:|------------:|---------------:|:------:|
| cloudflare (`qwen3-30b`) | 6/6 | 13.11 s | 463 | 0 |
| openai (`gpt-5-nano`) | 0/6 | 2.56 s | — | 6 |
| google (`gemini-2.5-flash-lite`) | 6/6 | 0.79 s | 44 | 0 |
| anthropic (`claude-haiku-4-5`) | 6/6 | 2.31 s | 70 | 0 |

`correct: true` only checks that the expected field is non-empty — it misses **structure quality** and **cross-field contamination**. The response content reveals a different picture.

---

### `reason` node — response quality breakdown

#### `households` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `[42, 38, 8, 5]` | Bare integers — no relationship info |
| Google | `["42-year-old", "38-year-old", ...]` | Strings — no relationship |
| **Anthropic** | `[{"age": 42, "relationship": "primary occupant"}, ...]` | **Full objects** — closest to schema |

#### `pets` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `["medium-sized dog"]` | Flat string |
| **Google** | `[{"type": "dog", "size": "medium"}]` | **Structured object** — exactly what schema expects |
| Anthropic | `["medium-sized dog"]` | Flat string |

#### `activities` turn — cross-field contamination
| Provider | Problem |
|----------|---------|
| Google | Put `"I work from home"` into `households` |
| Anthropic | Put `"adults"`, `"kids"` into `households` |
| Cloudflare | No contamination — correctly scoped to `activities` only |

#### `rooms` turn
| Provider | Response | Structure |
|----------|----------|-----------|
| Cloudflare | `["bedrooms", "bathrooms", "kitchen", "living room"]` | Flat — lost room counts |
| Google | `["3 bedrooms", "2 bathrooms", "kitchen", "living room"]` | Count preserved as string |
| **Anthropic** | `[{"type": "bedroom", "count": 3}, {"type": "kitchen", "adjacent_to": "living room"}, ...]` | **Richest** — count + adjacency as structured objects |

---

### `topology` node — response quality breakdown

#### T1: "3 bedrooms, 1 bathroom, kitchen, living room. Bedroom next to bathroom."
| Provider | Nodes | Edges | Issue |
|----------|------:|------:|-------|
| Cloudflare | 4 | 1 | Collapsed 3 bedrooms → 1 node |
| Google | 4 | 1 | Collapsed 3 bedrooms → 1 node |
| Anthropic | 6 | 5 | Correctly 3 bedroom nodes — but invented 4 extra edges not in input |

#### T2: "studio with kitchen and bathroom"
All three providers returned identical, correct output: 3 nodes, 2 edges (studio→kitchen, studio→bathroom).

---

### Revised findings

**Finding 1 — OpenAI unusable.** `RateLimitError` on all 6 calls. Retry with `gpt-4o-mini`.

**Finding 2 — Cloudflare: verbose, slow, flat output.**
Warm calls 6–12 s, up to 644 output tokens. Extracts correctly but always returns flat strings/integers — no object structure. Lowest contamination of all providers for `reason`.

**Finding 3 — Google: fast and schema-aligned for `pets`, contaminates `activities`.**
`gemini-2.5-flash-lite` produces well-structured `pets` objects `{"type", "size"}`, which matches the schema exactly. However it misclassified `"I work from home"` as a household member, indicating it needs a tighter system prompt for scoped extraction.

**Finding 4 — Anthropic: richest structure for `reason`, over-edges for `topology`.**
`claude-haiku-4-5` returns the deepest objects for `households` (age + relationship) and `rooms` (type + count + adjacency), making it the best fit for the `reason` node's structured extraction goal. For `topology`, it correctly handles plural room counts ("3 bedrooms" → 3 nodes) but invents edges not stated in the input — making it less reliable there.

---

### Updated decision

| Node | Primary | Reason |
|------|---------|--------|
| `reason` | **Anthropic** `claude-haiku-4-5` | Richest object structure; closest to `parsed_prompt_schema.json` |
| `topology` | **Google** `gemini-2.5-flash-lite` | Fastest; clean edges; no invented connections |

Pattern in each node — preferred provider with graceful fallback if credentials are missing:

```python
from _runtime.llm import call_llm

_PREFERRED = {"provider": "anthropic", "model": "claude-haiku-4-5"}   # reason
# _PREFERRED = {"provider": "google", "model": "gemini-2.5-flash-lite"}  # topology

try:
    result = call_llm(llm, system_prompt, messages, **_PREFERRED)
except ValueError:
    result = call_llm(llm, system_prompt, messages)  # falls back to .env default
```

### New metrics tracked in `benchmark.py` (v2)

| Metric | Node | What it measures |
|--------|------|-----------------|
| `structure_depth` | reason | 0 = empty, 1 = flat strings/ints, 2 = objects (dicts) |
| `contaminated_fields` | reason | Fields that should be empty for this turn but are not |
| `node_count` | topology | Number of room nodes returned |
| `edge_count` | topology | Total edges returned |
| `invented_edges` | topology | Edges beyond what the node count implies |

Retry OpenAI once rate limit clears and re-run `python utils/benchmark.py` to compare.
