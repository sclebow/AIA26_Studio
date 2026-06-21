# Sensi / Final review · deck spine (source of truth)

> The whole a-to-z story of Sensi, told once, as the FINAL review. **18 numbered slides
> (~10-12 min) + 3 full-bleed, un-numbered, live-narrated demo clips (~3:30)**, interleaved
> by act. Hybrid Pecha-Kucha cadence: one idea per slide, rich + varied visuals, calm slides
> / motion only in the clips. The math and any technical content stay visible on-slide.
>
> **Primary deliverable:** the HTML deck **`deck/index.html`** (reveal.js, self-contained
> under `deck/assets/`, Tabler icons). Present from the browser; `s` = embedded speaker notes;
> export a static PDF via `?print-pdf`. Script: `presentation-script-week09.md` (mirrors the
> embedded notes). Record path + shot-list: `demo-runbook-week09.md`. The reportlab
> `Sensi-Presentation-week09.pdf` remains a static fallback.

## Thesis
The number isn't the lesson, the edges are. Three pillars, proved where each shows:
**personal** (Onboard) · **honest** (Shape) · **coupled / the ripple** (Shape) → **made real**
(Report), all **grounded** in research. The ripple is the visual through-line.

## Cold open (the AEC question)
We measure everything except how it feels, and never the ripple between the senses. Sensi
makes that invisible axis, and its trade-offs, measurable.

## The 18 beats (+ 3 clips)

> Benchmarks are distributed to the act each one belongs to (not a block at the end).

**FRAME** — 1 Cover (FINAL REVIEW, static galaxy, ring logo) · 2 The question (louder ripple
motif) · 3 The thesis (3 pillars) · 4 How it's built (the **fuller layered diagram B**, real
complexity, icons) · 5 **The models** (3 Gemini 3.x tiers, IDs/pricing/context; pairs with the engine).

**ACT 1 · ONBOARD** — 6 Frame (diagram **A**, Onboard lit) → **▶ Clip 1** → 7 It's personal,
**math [1/3]**: signals → weights → `threshold = clamp(0.35 + 0.40·w, 0.35, 0.75)` + curve.

**ACT 2 · SHAPE** — 8 Frame (A, Shape lit) → **▶ Clip 2** → 9 How a room is scored, **math
[2/3]**: the Kitchen table, baseline → design levers → effective (acoustic 0.39, olfactory 0.20)
→ 10 The ripple, then the veto: coupling drags partners (−0.06), then `overall = (1−v)·mean_w +
v·worst, v=0.5` → 0.49 mean + 0.20 worst = **0.34** → 11 **The reasoning, measured** (FAST vs
SMART node-tier bars, $0.048/session, no-regression) — the benchmark for Shape's reasoning.

**ACT 3 · REPORT** — 12 Frame (A, Report lit) → **▶ Clip 3** → 13 Made real, **math [3/3]**:
the voiced-senses band (only `<0.45` / `>0.70` speak) → prompt fragments → **before/after** pair
(+ how-it-holds note) · 14 The renders, judged: Google vs OpenAI real A/B → stay on Google; new image 3/3.

**GROUNDED + CLOSE** — 15 Grounded (the coupling matrix: research-verified solid / physics dashed,
18/25 fact-check) · 16 **The close** (the stance: *"the score was never the point — the ripple
was"* + contribution claim "coupling between senses, made designable" + the coupling/ripple visual
+ slide-2 bookend + team credit) · 17 What this raises (open questions) · 18 Thanks.

Heroes: Clip 2, Clip 3, slide 10 (the veto → 0.34), slide 16 (the close stance).

## Style rules (locked)
- Use the full canvas; whitespace with intent. Rich, varied visuals, no repetition.
- Calm slides, motion only in the clips. Ripple is the recurring motif (and the close).
- Technical content (formulas, numbers) stays visible on-slide.
- **No em dashes.** Use `→`, `/`, `[ ]`, `{ }`, `·`.
- Tabler outline icons for visual cues. App brand: `#0D0D0D`, sense hues, Inter / JetBrains Mono.
- Placeholders are designed SVG with a keep-or-replace note; only the slide-11 before/after
  (`report-before.png` + `report-after.png`) expects real shots.
