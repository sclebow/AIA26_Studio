# Week 09 — Current Gemini models + refreshed benchmarks (faculty notes)

**Status:** implemented & verified · **Date:** 2026-06-20
**Files changed:** `.env`, `.env.example`, `bench_nodes.py`, `imaging/benchmark.py`, `bench_quality.py` (new),
`_runtime/llm.py`, `graph.py`
**Artifacts:** `docs/week09/benchmark/` — `node-bench.json`, `results.json`, `quality-pairs.json`,
`quality-reveal.json`, render PNGs.

Sensi runs every LLM node on a two-tier Gemini setup (FAST = routing/classification, SMART = user-facing
reasoning) plus a separate native image model. Those IDs were chosen in week 08 (`gemini-2.5-flash-lite` /
`gemini-2.5-flash` / `gemini-2.5-flash-image`). This session moves the app onto the **current Gemini
generation** and re-captures the benchmarks as a new baseline that also reflects the sessions 1–9 graph.

> **The whole point of this session was real model identity.** Training knowledge of model IDs is stale, so
> every ID below was researched **live** against official Google sources (a fan-out research pass with
> adversarial per-ID verification) and then **confirmed to actually load via a live smoke call** before it
> was trusted. A wrong/hallucinated/deprecated ID was the failure mode to avoid.

## What changed (the one-token swap)

| Tier | Was (week 08) | **Now** | env var |
| --- | --- | --- | --- |
| 🟢 FAST | `gemini-2.5-flash-lite` | **`gemini-3.1-flash-lite`** | `GOOGLE_MODEL_FAST` |
| 🔵 SMART | `gemini-2.5-flash` | **`gemini-3.5-flash`** | `GOOGLE_MODEL_SMART` |
| 🖼️ IMAGE | `gemini-2.5-flash-image` | **`gemini-3.1-flash-image`** (Nano Banana 2) | `GOOGLE_IMAGE_MODEL` |

The two-tier strategy and every node→tier assignment are **unchanged** — only the IDs moved a generation.
The resolver is still provider-generic (`{PROVIDER}_MODEL_FAST/_SMART`, `bootstrap.py`), so this stayed a
pure `.env` edit with **no app-code change** on the model path. Startup logs confirm it:
`Benchmarking tiers -> FAST: gemini-3.1-flash-lite | SMART: gemini-3.5-flash`.

## Models table (verified on official Google sources, checked 2026-06-20)

As of 2026-06-20 the current generation is **Gemini 3.x** (3, 3.1, 3.5). The **Gemini 2.0 family was retired**
(shut down 2026-06-01); the **Gemini 2.5 family is still GA** but is now the *legacy-stable* tier. So this was
a deliberate generation upgrade, not a forced migration — our old models still worked.

**Chosen models** (full technical detail):

| Model | API model ID | Tier | Status | Context (in / out) | $ / 1M in · out | Per-image | Modalities | Cutoff | Source (ai.google.dev/gemini-api/docs/…) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Gemini 3.1 Flash-Lite | `gemini-3.1-flash-lite` | FAST | GA | 1,048,576 / 65,536 | $0.25 · $1.50 (audio in $0.50) | — | text·image·video·audio·PDF → text | Jan 2025 | `models/gemini-3.1-flash-lite` |
| Gemini 3.5 Flash | `gemini-3.5-flash` | SMART | GA | 1,048,576 / 65,536 | $1.50 · $9.00 | — | text·image·video·audio·PDF → text | Jan 2025 | `models/gemini-3.5-flash` |
| Gemini 3.1 Flash Image (Nano Banana 2) | `gemini-3.1-flash-image` | IMAGE | GA | 131,072 / 32,768 | $0.50 · $3.00 | ~$0.045@0.5K · $0.067@1K · $0.101@2K · $0.151@4K | text·image → image·text | Jan 2025 | `models/gemini-3.1-flash-image` |

All paid-tier prices per 1M tokens unless noted; pricing page: `ai.google.dev/gemini-api/docs/pricing`.

**Considered but not chosen** (kept on the two-tier strategy):

| Model | API model ID | Status | $ / 1M in·out (or img) | Why not (this session) |
| --- | --- | --- | --- | --- |
| Gemini 2.5 Flash-Lite | `gemini-2.5-flash-lite` | GA | $0.10 · $0.40 | Previous FAST; cheaper but a generation behind. |
| Gemini 2.5 Flash | `gemini-2.5-flash` | GA | $0.30 · $2.50 | Previous SMART; still valid, lower quality than 3.5. |
| Gemini 2.5 Flash Image | `gemini-2.5-flash-image` | GA | $0.039 / img | Previous IMAGE (original Nano Banana); lower fidelity. |
| Gemini 3 Flash | `gemini-3-flash-preview` | **preview** | $0.50 · $3.00 | Cheaper newer-gen SMART, but preview (no production SLA), superseded by 3.5 Flash. |
| Gemini 3.1 Pro | `gemini-3.1-pro-preview` | **preview** | $2.00 · $12.00 (≤200k) | Top-reasoning step-up; preview + ~8× cost. Noted as a future per-node lever, not adopted. |
| Nano Banana Pro | `gemini-3-pro-image` | GA | $0.134 (1–2K) / $0.24 (4K) | Studio-quality 4K + text rendering; ~2–3.5× image cost. Noted as the option for hero Report renders. |

**Avoid — verified deprecated/retired** (do NOT use; from `…/docs/deprecations`):
`gemini-2.0-flash`, `gemini-2.0-flash-lite` (retired 2026-06-01) · `gemini-2.5-pro` (shutdown 2026-10-16) ·
`gemini-3-pro-preview` (shutdown 2026-03-09) · `imagen-4.0-*` (shutdown 2026-08-17).

## Performance benchmark — NEW baseline (2026-06-20)

Reproduce: `BENCH_NODES=1 python bench_nodes.py` (from `team_02/python/`, UTF-8) → `node-bench.json`.
One scripted layout session (analyze → full detect/conflict/suggest → edit → follow-up → chitchat + a greet
probe) so every runtime LLM node fires ≥ once. Token cost from the in-script `PRICE` dict
(FAST $0.25 in / $1.50 out · SMART $1.50 in / $9.00 out per 1M — checked 2026-06-20).

| Node | Tier | calls | avg s | in tok | out tok | $ (session) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `score_interpreter` | 🔵 SMART | 2 | 24.07 | 1782 | 1004 | 0.0117 |
| `suggestion_critic` | 🔵 SMART | 1 | 16.46 | 1051 | 765 | 0.0085 |
| `conflict_reasoner` | 🔵 SMART | 1 | 10.11 | 1020 | 357 | 0.0047 |
| `respond` | 🔵 SMART | 3 | 8.07 | 5070 | 278 | 0.0101 |
| `detail_respond` | 🔵 SMART | 1 | 5.66 | 4506 | 142 | 0.0080 |
| `edit_planner` | 🔵 SMART | 1 | 3.21 | 855 | 100 | 0.0022 |
| `chitchat` | 🟢 FAST | 1 | 1.48 | 632 | 144 | 0.0004 |
| `what_next` | 🟢 FAST | 5 | 0.77 | 2549 | 249 | 0.0010 |
| `action_classifier` | 🟢 FAST | 5 | 0.76 | 4105 | 183 | 0.0013 |
| `greet` | 🟢 FAST | 1 | 0.60 | 124 | 12 | 0.0001 |
| `evaluator` | 🟢 FAST | 3 | 0.56 | 1307 | 3 | 0.0003 |
| no-LLM (`analyze`/`detect`/`suggest`/`apply_edits`/`compare_versions`/`load_layout`) | — | — | ~0.00 | 0 | 0 | 0.0000 |

**Tier summary (new):** FAST avg **0.83 s** / **$0.0031** · SMART avg **11.26 s** / **$0.0452**. Total scripted
session: **$0.0483**.

**Image (new):** `python -m imaging.benchmark` (Gemini-only) → `results.json`. Nano Banana 2 rendered the 3 room
cases at avg **11.4 s**, **$0.067/img**, ~800 KB each.

**Old → new contrast** (week08 baseline in *italics*):

| | FAST avg | SMART avg | Session total | Image |
| --- | --- | --- | --- | --- |
| *Old (2.5 tier)* | *0.68 s / $0.0010* | *8.48 s / $0.0115* | *$0.0126* | *6.7 s / $0.039 img* |
| **New (3.x tier)** | **0.83 s / $0.0031** | **11.26 s / $0.0452** | **$0.0483** | **11.4 s / $0.067 img** |

The upgrade trades **latency and cost for capability**: SMART is ~1.3× slower and the session is ~3.8× costlier
(driven by 3.5 Flash's higher token price + its thinking budget — `score_interpreter` rose 14 s → 24 s). In
absolute terms it is still **under a nickel per full session** and FAST stays sub-second / near-free. The
biggest latency lever remains `score_interpreter` (runs every analysis) — a candidate for prompt-trimming or a
"minimal thinking" setting on the new models.

## Quality comparison — OLD → new (no-regression check)

**Method (stated):** `bench_quality.py` ran one scripted session with `BENCH_QUALITY=1` to **capture the real
(system, user) prompt each SMART node actually sent**, then **replayed each identical prompt** through the OLD
(`gemini-2.5-flash`) and NEW (`gemini-3.5-flash`) model so the model is the only variable. Outputs were written
as **blind A/B pairs** (`quality-pairs.json`) with the old/new mapping held separately
(`quality-reveal.json`). The judge (Claude) scored each pair **blind** on a 5-point rubric —
**groundedness · persona fidelity · clarity · no-hallucination · usefulness** — then the mapping was revealed.
Same method for images: the 3 room cases rendered on the OLD vs NEW image model, judged blind.

**Text verdicts (5 user-facing SMART nodes):**

| Node | Blind winner | Rationale |
| --- | --- | --- |
| `score_interpreter` | **NEW** | Richer, varied, persona-specific prose; OLD repeated "very open and comfortable to move through" verbatim 3×. |
| `conflict_reasoner` | **NEW** | More cohesive architect-voice; equally grounded in the orientation/glazing facts; OLD more repetitive. |
| `suggestion_critic` | **NEW** | Sharper feasibility calls (kitchen rugs = fire/grease hazard, bathroom wood = mold), cross-modal warnings, and it caught a *missed* thermal fix for the cold Master Bedroom. |
| `detail_respond` | **NEW** | Fuller grounded causal breakdown (base 0.28 + the two named adjustments → final 0.19). |
| `respond` | OLD (marginal) | Both grounded and correct; OLD's 2-sentence summary phrasing read slightly cleaner. Within noise. |

**Image verdicts (3 cases):** NEW (`gemini-3.1-flash-image`) won **3/3** — markedly higher-resolution,
photorealistic renders; the OLD model produced lower-res, flatter CG. (See `old_*.png` vs `google_*.png` /
the `qimg_*_A/B.png` blind pairs.)

**Conclusion: NEW wins 7 of 8 blind comparisons; the single OLD edge is a marginal phrasing call on a terse
summary — no reasoning regression.** The upgrade buys deeper critique (catches real-world constraints + a
coverage gap the old model missed) and substantially more realistic renders, at the latency/cost noted above.

## Open questions / next

- **Latency:** `score_interpreter` / `suggestion_critic` dominate (16–24 s) on 3.5 Flash's thinking. Trim their
  prompts or cap thinking; measure with `bench_nodes.py`.
- **Optional tier lever (not done):** a single user-facing node (`suggestion_critic` or `respond`) could be
  promoted to `gemini-3.1-pro-preview` for top reasoning — preview + ~8× cost; revisit if quality demands it.
- **Optional image lever (not done):** hero Report renders could use `gemini-3-pro-image` (Nano Banana Pro,
  4K + text rendering) at ~2–3.5× the per-image cost; Nano Banana 2 is the balanced default.
