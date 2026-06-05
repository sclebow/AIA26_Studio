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

## Open question / next

- `evaluator` is on FAST. If the revise-loop starts rubber-stamping weak responses, promote it to
  SMART (one-line change in `graph.py`).
- Cost/latency numbers per tier to be captured during the week-8 demo runs.
