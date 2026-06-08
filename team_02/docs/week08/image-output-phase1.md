# Week 08 — Image Output Phase 1: generative per-room render

**Status:** implemented & verified (browser, Gemini) · **Date:** 2026-06-05

Phase 1 of the image-output feature: click a room → a first-person "how it feels to be there"
interior render whose atmosphere is driven by that room's 6 comfort scores + persona. Shown in the
`FocusCard` that already opens on room-click. On-demand (button), cached.

## How it works

1. **Prompt from scores** (`python/imaging/prompt.py`): each 0-1 sense score maps to concrete scene
   qualities (thermal→palette, acoustic→hard/soft surfaces, visual→brightness/clutter, spatial→volume,
   olfactory→air/plants, tactile→materials). Only clearly-low (<0.45) or clearly-high (>0.70) senses
   are voiced, so a room's *weak* senses set the mood (discomfort becomes visible). Persona role sets
   the photographic register.
2. **Provider-abstracted generation** (`python/imaging/client.py`): `generate_image(prompt)` →
   base64 PNG. `IMAGE_PROVIDER` picks the backend — **google** (Nano Banana `gemini-2.5-flash-image`,
   via REST `generateContent`, no extra SDK) or **openai** (`gpt-image-1` via the `openai` SDK). Flip
   one `.env` var to A/B. A `reference_b64` param is wired for Phase 2 (consistency anchoring).
3. **Endpoint** `POST /api/render-room` (`api/server.py`): pulls the session's layout + latest scores
   + persona, builds the prompt, generates, returns `{ image_base64, prompt, provider }`. **Cached**
   per (provider, layout, room, material, scores, role) — repeat clicks are instant/free; `force`
   bypasses the cache (re-render).
4. **Frontend** (`web/src/components/FocusCard.jsx` + `api/client.js`): a **"✦ render this space"**
   button → loading → image in a "how it feels" section, with **↻ re-render**. Resets per room.

## `.env`

```
IMAGE_PROVIDER     = "google"
GOOGLE_IMAGE_MODEL = "gemini-2.5-flash-image"
OPENAI_IMAGE_MODEL = "gpt-image-1"
```

## Verified (live, Gemini)

- Direct client test: valid 1024² PNG in ~8s; prompt is score-driven.
- UI: analysed layout 201 → Kitchen FocusCard → "render this space" → a cool, hard-surfaced kitchen
  render appears, matching the Kitchen's low thermal/acoustic/tactile scores. No new console errors.

## Notes / next

- Cost ~$0.02–0.04/image (Gemini), on-demand + cached.
- To A/B OpenAI: set `IMAGE_PROVIDER="openai"` (needs the org-verified OpenAI key); same prompts.
- `gpt-image-1` org-verification is required or OpenAI returns 403.
- Phase 2 (before/after + deltas) will reuse `reference_b64` for ~85% consistency across edits.
