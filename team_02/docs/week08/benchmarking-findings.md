# Week 08 — Benchmarking: per-node model tiers (faculty notes)

**Status:** implemented & verified · **Date:** 2026-06-05
**Files changed:** `_runtime/bootstrap.py`, `_runtime/llm.py`, `graph.py`, `.env`

Implements the faculty **Benchmarking** ask (root `README.md` → `## Benchmarking`): let each node
use a different model so we can run **small/cheap models for simple tasks** and **larger models for
complex ones**, and compare.

## Provider choice

Team 02 standardized on a **single provider, Google Gemini**, and mixes *models within it*. Rationale
(pricing + capability review, June 2026): Gemini is the only provider that covers all three of our
needs under one API key — cheap text (Flash / Flash-Lite), strong vision (for the `inspire`
moodboard analysis), and native, *consistent* image generation (Nano Banana / Imagen 4) for the
upcoming image-output work. Consistency across iterative edits ("add a window → change material")
was the deciding factor for the image side.

## Two tiers (set in `.env`)

| Tier | Model | env var | Used for |
| --- | --- | --- | --- |
| 🟢 FAST | `gemini-2.5-flash-lite` | `GOOGLE_MODEL_FAST` | routing, classification, short internal text |
| 🔵 SMART | `gemini-2.5-flash` | `GOOGLE_MODEL_SMART` | user-facing prose & nuanced persona reasoning |

Both fall back to `GOOGLE_MODEL` if the tier var is unset. The resolver is provider-generic
(`{PROVIDER}_MODEL_FAST/_SMART`), so switching providers later needs no code change.

## Node → tier assignment

Only the **13 LLM nodes** take a model. The scoring/edit/insight nodes call MCP tools or pure Python
and take none.

| Node | Tier | Why |
| --- | --- | --- |
| `action_classifier` | 🟢 FAST | Pure classification into 13 actions; runs every turn. |
| `chitchat` | 🟢 FAST | Light small-talk. |
| `greet` | 🟢 FAST | Near-canned greeting. |
| `quiz` | 🟢 FAST | Emits the next quiz question. |
| `what_next` | 🟢 FAST | Short "next step" offer. |
| `evaluator` | 🟢 FAST | Internal APPROVED/REVISE judge (not user-facing). |
| `respond` | 🔵 SMART | The main natural-language report the user reads. |
| `score_interpreter` | 🔵 SMART | Turns raw scores into persona-specific meaning. |
| `conflict_reasoner` | 🔵 SMART | Explains *why* sensory conflicts occur. |
| `suggestion_critic` | 🔵 SMART | Critiques/improves generated suggestions. |
| `detail_respond` | 🔵 SMART | Answers follow-up questions — user-facing. |
| `inspire` | 🔵 SMART | Moodboard/vision synthesis — multimodal nuance. |
| `persona_compiler` | 🔵 SMART | Builds the persona that drives all downstream scoring. |

**6 FAST / 7 SMART.** The expensive model runs only where the user sees output or where reasoning
quality compounds downstream.

## How it's wired

- `bootstrap.py` builds `ctx.llm_fast` and `ctx.llm_smart` once (alongside the legacy `ctx.llm_simple`
  default/fallback).
- `graph.py` passes the right tier to each node's builder.
- `llm.py`'s `call_llm_simple()` also gained optional `provider` / `model` args (the faculty example's
  pattern) for **ad-hoc A/B experiments** without rewiring the graph.

## Ad-hoc comparison (escape hatch)

```python
from _runtime.llm import call_llm_simple
# force a one-off call onto a different model/provider:
out = call_llm_simple(ctx.llm_simple, system_prompt, user_msg, provider="google", model="gemini-2.5-flash")
```

## Verification

- Live run on the `full` analysis path: FAST handled routing/eval, SMART handled
  interpret/suggest/respond; grounded, quality output. Startup logs
  `Benchmarking tiers -> FAST: gemini-2.5-flash-lite | SMART: gemini-2.5-flash`.
- Falls back safely to `GOOGLE_MODEL` when tier vars are absent.

## Measured per-node latency & cost — second batch (2026-06-07)

Captured with a new harness, **`bench_nodes.py`**, which wraps every graph node with a
wall-clock timer + an LLM token snapshot (gated on `BENCH_NODES=1`; zero overhead when off).
It runs one scripted layout-mode session (analyze → full detect/conflict/suggest → edit →
follow-up → chitchat) so every runtime LLM node fires at least once.

Reproduce: `BENCH_NODES=1 python bench_nodes.py` (from `team_02/python/`, UTF-8) →
writes `docs/week08/benchmark/node-bench.json`. Token cost uses approx Google pricing
(USD/1M tok): FAST $0.10 in / $0.40 out · SMART $0.30 in / $2.50 out — update if pricing moves.

| Node | Tier | calls | avg s | in tok | out tok | $ (session) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `suggestion_critic` | 🔵 SMART | 1 | 16.1 | 924 | 838 | 0.0024 |
| `score_interpreter` | 🔵 SMART | 2 | 14.3 | 1696 | 1024 | 0.0031 |
| `conflict_reasoner` | 🔵 SMART | 1 | 9.3 | 1062 | 320 | 0.0011 |
| `respond` | 🔵 SMART | 3 | 7.4 | 4820 | 243 | 0.0021 |
| `detail_respond` | 🔵 SMART | 1 | 2.1 | 8017 | 42 | 0.0025 |
| `edit_planner` | 🔵 SMART | 1 | 1.5 | 474 | 105 | 0.0004 |
| `chitchat` | 🟢 FAST | 1 | 0.85 | 469 | 63 | 0.0001 |
| `what_next` | 🟢 FAST | 5 | 0.79 | 2564 | 182 | 0.0003 |
| `action_classifier` | 🟢 FAST | 5 | 0.74 | 4105 | 175 | 0.0005 |
| `greet` | 🟢 FAST | 1 | 0.54 | 124 | 12 | 0.0000 |
| `evaluator` | 🟢 FAST | 3 | 0.47 | 1272 | 3 | 0.0001 |
| no-LLM (`analyze` MCP, `detect`, `suggest`, `apply_edits`, `compare_versions`, `load_layout`) | — | — | ~0.00 | 0 | 0 | 0.0000 |

**Tier summary:** FAST avg **0.68 s** / **$0.0010** · SMART avg **8.48 s** / **$0.0115** →
SMART is ~12× slower and ~11× costlier per call. Total scripted session: **$0.0126**.

**Takeaway:** the tiering pays off — routing/eval/small-talk/next-step (FAST) are sub-second and
near-free; the spend and latency live in the deep reasoners (`suggestion_critic`,
`score_interpreter`, `conflict_reasoner`), exactly where quality compounds. The biggest lever for
*latency* is `score_interpreter` (runs on every analysis); a candidate for prompt-trimming or a
streaming response.

*Coverage:* the onboarding LLM nodes (`inspire`, `persona_compiler`, `quiz`) aren't in this batch —
they run once per user, are multi-step/multimodal, and don't affect steady-state cost. `greet` is
included as the onboarding probe.

## Open question / next

- `evaluator` is on FAST (0.47 s, ~free) and currently rubber-stamps (it APPROVED every turn this
  run). If the revise-loop never fires, either tighten its rubric or promote to SMART (one-line in
  `graph.py`) — measure with `bench_nodes.py` after.
- `score_interpreter` / `suggestion_critic` dominate latency (14–16 s); trim their prompts or stream
  to cut perceived wait.
