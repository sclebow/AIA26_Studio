# Week 08 — Image Generation: research findings

Distilled from a deep-research pass (22 sources, 23 verified / 2 refuted claims), 2026-06-05.
Feeds the image-output feature design. Full question covered consistency, score-conditioning, and
2D edit legibility.

## TL;DR decision points

1. **Gemini "Nano Banana" has NO reliable seed.** On a pure-Gemini stack, "same room, one change"
   is achieved by **multi-turn conversational editing + reference-image anchoring + explicit
   "keep everything else the same"** — giving ~80–90% perceptual consistency, *not* 100%.
2. **True reproducibility needs Imagen-on-Vertex** (deterministic seed, requires `addWatermark=false`)
   or an SD/ControlNet depth path (strongest geometry lock) — neither is Nano Banana.
3. **For a sensory "feeling" render, ~80–90% is acceptable** — we convey vibe, not CAD precision. Use
   Nano Banana; keep Imagen/hybrid as an escape hatch if before/after consistency proves too loose.

## (1) Consistency — what works on Gemini

| Technique | Verdict | Note |
| --- | --- | --- |
| Multi-turn conversational editing | ✅ Google's *recommended* way to iterate | First-party docs |
| Reference-image anchoring (feed prior render back; up to 14 refs on Gemini 3) | ✅ primary consistency lever | ~80–90% (vendor estimate) |
| "Keep everything else the same" semantic masking in the prompt | ✅ recommended | text-based mask |
| Gemini seed determinism | ❌ unreliable / not exposed for image models | confirmed |
| Imagen-on-Vertex seed | ✅ truly deterministic | needs `addWatermark=false` |
| SD + depth ControlNet | ✅ strongest geometry lock | not Gemini; hybrid only |

**Failure modes:** large prompt changes break consistency; Gemini "character consistency is not
always perfect"; depth conditioning preserves *coarse* structure, not exact fine geometry.

## (2) Score-conditioned generation — bake scores into the prompt

Map each 0–1 comfort score to concrete, documented prompt modifiers (lighting, camera/lens,
color-grading, color-temperature — all verbatim-supported by Google's Nano Banana guide):

| Sense / signal | Low score → prompt fragment | High score → prompt fragment |
| --- | --- | --- |
| Thermal | cool blue palette, flat light | warm golden hues, cosy light |
| Visual | dim, high-contrast, cluttered | bright, balanced, airy, uncluttered |
| Acoustic | hard reflective surfaces (glass, concrete) | soft textiles, rugs, drapes, acoustic panels |
| Spatial | cramped, low ceiling, tight framing | open, wide-angle, generous volume |
| Olfactory | stuffy, closed | fresh, plants, open airflow |
| Tactile | cold hard materials | soft natural textures (wood, wool) |

- Persona drives style register (e.g. architect = restrained/material-honest).
- Research-grade alternative ("condition on a separate quantitative signal") exists but is **not** a
  Gemini API capability — prompt-baking is the implementable path now.
- **Open question (test empirically):** does a mid-range score (0.3 vs 0.7) actually move the render
  monotonically, or saturate? Needs a quick calibration sweep.

## (3) Edit legibility in the 2D plan (no AI) — use CAD diff conventions

Established patterns to emulate (don't use pure side-by-side):

- **Overlay + color highlight** (Procore): **red = removed, blue = added.**
- **Change clouds / callouts** (Bluebeam *Compare*): orange revision clouds mark each diff.
- **Color-coded version stacking** (Bluebeam *Overlay*): each version auto-assigned a distinct color.

**Differentiation opportunity (no tool does this well):** combine material swatches + a change badge
+ a *score-driven* "why" callout on top of the red/blue diff. This is exactly the floating-bubble
idea — annotate *what* changed AND *which sense it affects*, e.g. "Oak → Polished Concrete · acoustic ↓".

## Sources (primary)
- Gemini image API docs — https://ai.google.dev/gemini-api/docs/image-generation
- Nano Banana prompting guide — https://cloud.google.com/blog/products/ai-machine-learning/ultimate-prompting-guide-for-nano-banana
- Imagen deterministic seed (Vertex) — https://docs.cloud.google.com/vertex-ai/generative-ai/docs/image/generate-deterministic-images
- Prompt-modifier taxonomy (peer-reviewed) — https://www.tandfonline.com/doi/full/10.1080/0144929X.2023.2286532
- Affect-conditioned generation (IEEE TAC) — https://arxiv.org/pdf/2302.09742
- Procore drawing compare — https://support.procore.com/products/online/user-guide/project-level/drawings/tutorials/compare-drawing-revisions
- Bluebeam Compare vs Overlay — https://support.bluebeam.com/revu/features/compare-documents-vs-overlay-pages.html
