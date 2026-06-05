# Week 08 — Image Provider Benchmark: Google vs OpenAI

**Date:** 2026-06-05 · Reproduce: `python -m imaging.benchmark` (from `team_02/python/`)

A head-to-head of the two image backends behind Sensi's per-room renders, on **identical
score-driven prompts**. Goal: pick one provider with evidence. Decision: **Google**.

## Method

- 3 representative rooms, each a different comfort profile (poor / cosy / mixed), prompts built by the
  real `imaging/prompt.py` score→scene mapping (architect persona).
- Same prompt sent to **Google** (`gemini-2.5-flash-image`, "Nano Banana") and **OpenAI**
  (`gpt-image-1` at **medium** quality), 1024².
- Measured wall-clock latency per image; cost from published per-image pricing (June 2026).
- All 6 images saved in [`./benchmark/`](benchmark/).

## Results

| Provider | Case | Latency | Size | Cost/img |
| --- | --- | --- | --- | --- |
| Google | living-room-poor | 6.6 s | 1454 KB | $0.039 |
| Google | bedroom-cosy | 7.2 s | 1732 KB | $0.039 |
| Google | kitchen-mixed | 6.6 s | 1410 KB | $0.039 |
| OpenAI | living-room-poor | 21.5 s | 1386 KB | $0.042 |
| OpenAI | bedroom-cosy | 16.4 s | 1598 KB | $0.042 |
| OpenAI | kitchen-mixed | 18.1 s | 1368 KB | $0.042 |

| Provider | Avg latency | Cost / image | Notes |
| --- | --- | --- | --- |
| **Google** (Nano Banana) | **6.8 s** | **$0.039** | also `Imagen 4 Fast` ≈ $0.02 if editing not needed |
| **OpenAI** (gpt-image-1, medium) | 18.7 s | $0.042 | "high" quality ≈ $0.167/img (~4×) |

**Google is ~2.75× faster and slightly cheaper at matched quality** (and far cheaper vs OpenAI "high").
The gap doubles for Phase 2, which generates two images per before/after.

## Visual character (see `./benchmark/`)

Both correctly express the comfort scores, with different aesthetics:

- **Google** — clean, bright, architectural-daylight realism. Crisp surfaces, honest materials. Reads
  the "poor" living room as a cool, austere, hard-surfaced concrete loft.
- **OpenAI** — darker, moodier, more cinematic. Leans harder into the *emotional* read of discomfort
  (the same room comes out dim and brooding).

For Sensi's purpose — communicating *how a space feels* truthfully and quickly — Google's clean
realism fits, and its multi-turn editing gives better **before/after consistency** (Phase 2).

## Decision

**Committed to Google** (`IMAGE_PROVIDER="google"`): faster, cheaper, more consistent across edits.
OpenAI remains a one-line `.env` swap if a more cinematic look is ever wanted (at ~3× latency and,
at "high", ~4× cost). OpenAI quality is pinned via `OPENAI_IMAGE_QUALITY` (default `medium`).

*Pricing drifts — verify at [Gemini](https://ai.google.dev/gemini-api/docs/pricing) /
[OpenAI](https://openai.com/api/pricing/).*
