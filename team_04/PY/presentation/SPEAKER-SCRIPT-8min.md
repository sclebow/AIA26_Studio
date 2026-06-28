# TerraPilot — 8-Minute Speaker Script

Open `terrapilot-deck.html` in a browser (Chrome). Press **F** for fullscreen.
Navigate: **→ / Space** forward, **←** back, click right-half = next.

**Timing target: 8:00.** Slide numbers match the deck. Keep moving — don't over-explain.

---

### Slide 1 — Title  ·  ⏱ 0:00–0:30  ·  *David*
> "This is **TerraPilot** — an AI co-pilot for early-stage architectural design.
> You describe a building in a simple prompt, and it generates, places, and optimizes
> it on a *real* site. We're a team of four, and we'll walk you through it end to end."

---

### Slide 2 — The Idea  ·  ⏱ 0:30–1:10  ·  *David*
> "Early design is slow — one massing study can take days. TerraPilot collapses that
> into minutes. Three things make it different: **you talk to it** — no menus, just
> design intent. It works on a **real site** — real roads, sun, wind, neighbours.
> And it **explains itself** — every change has a reason, and it tells you what's real
> versus estimated."

---

### Slide 3 — The Workflow  ·  ⏱ 1:10–1:50  ·  *David → hand to Daniel*
> "It's one guided workflow: Site, Boundary, Context, Shape, Optimize, Compare, Export.
> Each stage builds on the last — so by the end the design responds to its environment.
> Daniel will start with the site."

---

### Slide 4 — Site & Urban Context  ·  ⏱ 1:50–3:00  ·  *Daniel*
> "First we define the site — setbacks are applied automatically. Then we build a
> **digital twin** of the surroundings: real OpenStreetMap data in a 2-km radius —
> roads, transit, parks, amenities, neighbouring buildings.
>
> On the right is our **Live Design Health dashboard**. It scores the design across
> seven factors and updates live as the design changes — and it never alters the
> building, it's a pure health check. The key detail: each score shows a **geometry
> estimate AND a real value** from NASA and OpenStreetMap. We never fake numbers.
> It's draggable and minimizable too."
>
> *(Hand to Nihan.)*

---

### Slide 5 — Shape Generation & Manipulation  ·  ⏱ 3:00–4:10  ·  *Nihan*
> "I just describe what I want — '8-floor building' — and TerraPilot generates a
> **Shape Library** of typologies scaled to the site. I pick one.
>
> Then the magic: I give **design intent, not commands**. 'Give it a futuristic
> appearance' twists the massing. 'Add 2 floors on the right wing' edits a single
> wing — because every building is a **stack of floor plates**, we can edit per-floor
> and per-wing, not just the whole block. 'Add a courtyard' carves a real void.
>
> Every version can be **saved** to browse, preview and optimize later.
> Now Sush will explain the intelligence behind all this."
>
> *(Hand to Sush.)*

---

### Slide 6 — Prompt Understanding  ·  ⏱ 4:10–5:10  ·  *Sush*
> "Everything Nihan typed went through a **3-layer understanding pipeline**.
> **Layer 1** parses direct commands literally. **Layer 2** uses an LLM, Gemini, to
> classify vague intent like 'more daylight'. **Layer 3** is a Reason Node that gives
> every change an intent, a confidence, and a WHY.
>
> Two things we're proud of: a **two-tier fallback** — Gemini, then Cloudflare, then
> keyword matching — so it never dies on an API limit. And a **hallucination guard** —
> if a prompt matches no real operation, we *reject* it instead of faking a change."

---

### Slide 7 — Optimization Engine  ·  ⏱ 5:10–6:20  ·  *Sush*
> "Optimization isn't one answer — it's a **trade-off across many goals**.
> We generate a large pool of candidates — different placements, rotations, massings —
> **score every one** across all objectives, build a **true Pareto front**, and pick
> **8 named strategies**: Highest Solar, Best View, Lowest Noise, Open Space, Density,
> Wind, Balanced, Landmark.
>
> And the scores use **real data** — NASA climate, OpenStreetMap. It's a scoring engine
> grounded in the actual site, not a fabricated simulation. If data isn't available,
> we show N/A — we never invent it."

---

### Slide 8 — Hard Problems Solved  ·  ⏱ 6:20–7:10  ·  *Sush*
> "Three problems we went deep on. **One** — when you optimize a manipulated building,
> we preserve the twist and the added floors instead of reverting to a plain block;
> we carry the full floor-plate geometry through every step. **Two** — a saved-shapes
> explorer: browse, preview in 3D, optimize the exact one you pick. **Three** —
> 'align facade to main road' rotates the building parallel to the *real* road
> geometry from OpenStreetMap.
>
> And all six environmental scorers run in **dual mode** — estimate and real value —
> with a badge so you always know which is which."

---

### Slide 9 — Backend  ·  ⏱ 7:10–7:40  ·  *Sush*
> "Under the hood it's a **FastAPI** runtime — the notebooks and the UI share one
> engine, so routes are thin wrappers. The intelligence lives in two packages:
> **nodes** for the 3-layer understanding, and **optimization** for the 16 scorers and
> Pareto selector. Data comes from **NASA POWER** for climate and **OpenStreetMap**
> for the urban context — fetched once and cached."

---

### Slide 10 — Close  ·  ⏱ 7:40–8:00  ·  *Sush*
> "So: **plain prompts in, site-aware architecture out**. TerraPilot understands
> intent, generates and edits geometry, optimizes across real environmental goals,
> and explains every decision. It's honest — it tells you what's real, what's
> estimated, and why. **Thank you — happy to take questions.**"

---

## Timing cheat-sheet
| # | Slide | Speaker | End by |
|---|-------|---------|--------|
| 1 | Title | David | 0:30 |
| 2 | The Idea | David | 1:10 |
| 3 | Workflow | David | 1:50 |
| 4 | Site & Context | Daniel | 3:00 |
| 5 | Shape & Manipulation | Nihan | 4:10 |
| 6 | Prompt Understanding | Sush | 5:10 |
| 7 | Optimization | Sush | 6:20 |
| 8 | Hard Problems | Sush | 7:10 |
| 9 | Backend | Sush | 7:40 |
| 10 | Close | Sush | 8:00 |

## If you're running long
Cut Slide 9 (Backend) — fold one line into Slide 7. Saves ~30s.

## Q&A redirect
Any technical "how does it actually work" → **Sush**. Others: "That's Sush's area."
