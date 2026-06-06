# Benchmarking: Per-Call Model Selection

## What was added to `llm.py`

Three private helpers, an updated `call_llm`, and a new `llm_invoke` were added to
[python/_runtime/llm.py](../python/_runtime/llm.py).

### `_required_env(name)` — line 31
Reads an env var and raises a clear `ValueError` if it is missing. Used by
`_resolve_llm_connection` to pull credentials on demand rather than at startup.

### `_resolve_llm_connection(provider, model)` — line 38
Maps a provider name (`"openai"`, `"cloudflare"`, `"google"`, `"anthropic"`,
`"local"`) plus an optional model string to the `(api_key, base_url,
resolved_model)` triple needed to build a `ChatOpenAI` instance. If `model` is
`None` it falls back to the matching `*_MODEL` env var.

### `_resolve_timeout_seconds(llm)` — line 55
Extracts the timeout from the existing LLM object so a temporary per-call
instance inherits the same setting. Defaults to 30 s if the attribute is absent.

### `llm_invoke(llm, messages, provider, model)` — line 235
Drop-in replacement for `llm.invoke()` that accepts optional `provider`/`model`
overrides. Builds a temporary `ChatOpenAI` instance for that one call only,
inheriting `model_kwargs` and timeout from the default LLM. Returns the raw
LangChain response object so callers can do `response.content` directly.

`reason` and `topology` use this function — not `call_llm` — because they parse
`response.content` directly as JSON. `call_llm` runs `_normalize_llm_decision`
which returns a decision dict, incompatible with that pattern.

### Updated `call_llm` — line 269
`tool_catalog` removed from the signature; `provider` and `model` optional kwargs
added. Used by nodes that need a normalized `{"action": ..., "tool_calls": ...}`
dict rather than a raw response object.

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
| B | `openai` | `gpt-5-nano` | Paid |
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

### Metrics recorded per call

| Metric | Description |
|--------|-------------|
| `latency` | Wall-clock seconds from `llm.invoke()` start to response |
| `tokens_in` | Input tokens reported in `usage_metadata` |
| `tokens_out` | Output tokens reported in `usage_metadata` |
| `correct` | `true` if the expected field is non-empty in the parsed response |
| `error` | Exception class name if the call failed, `null` otherwise |
| `response` | Full parsed JSON returned by the model |

### Running the benchmark

```bash
cd team_06/python
python utils/benchmark.py
```

Results are printed to the terminal and saved to
[python/utils/benchmark_results.json](../python/utils/benchmark_results.json).
Full analysis is in [benchmark-analysis.md](./benchmark-analysis.md).

---

## Wiring pattern

Each node declares a `_PREFERRED` dict at module level and wraps the LLM call in
a try/except. If the preferred provider's credentials are absent from `.env`, the
`ValueError` raised by `_resolve_llm_connection` is caught and the default `.env`
model is used instead — no crash, no config change required.

```python
from _runtime.llm import llm_invoke

_PREFERRED = {"provider": "google", "model": "gemini-2.5-flash-lite"}

try:
    response = llm_invoke(llm, messages, **_PREFERRED)
except ValueError:
    response = llm.invoke(messages)   # falls back to .env default

result = json.loads(response.content.strip())
```

### `.env` keys required per provider

| Provider | Required keys |
|----------|--------------|
| `cloudflare` | `CF_ACCOUNT_ID`, `CF_API_TOKEN`, `CF_MODEL` |
| `openai` | `OPENAI_API_KEY`, `OPENAI_MODEL` |
| `google` | `GOOGLE_API_KEY`, `GOOGLE_MODEL` |
| `anthropic` | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |
| `local` | `LOCAL_LLM_ENDPOINT` |

If any key for the preferred provider is missing, the fallback triggers silently.
