# Sensi — Week 9 demo runbook (record the 3 clips + the shot-list)

The deck is **`team_02/docs/week09/deck/index.html`** (reveal.js, self-contained). It carries
the talk; **three pre-recorded, full-bleed, live-narrated clips** carry the app. This is the
exact record path, the de-risking, the stills to drop in, and how to present/export.

---

## 0 · Pre-flight (once, before recording)

**Launch the app (Windows):**
- Backend: from `team_02/`, set `PYTHONIOENCODING=utf-8`, then `uvicorn api.server:app --port 8000`
  (the backend 500s every turn on Windows if stdout isn't UTF-8). Wait for bootstrap.
- Frontend: from `team_02/web/`, `npm run dev` → `http://localhost:5173`.
- If `/api/init` 500s on first load, it's a harmless startup race — **just reload.**

**De-risk before you hit record:**
- 🔑 **API key off-screen** — `.env` holds a plaintext `GOOGLE_API_KEY`. No terminals/DevTools/`.env` in frame.
- ⏱ **Pre-warm the Report renders** (~11s/room) before recording Clip 3, so the take isn't spinners.
- 🧩 **Verify the layout** — load example **201**; confirm the CAD plan draws.
- 🚫 **Don't restore a checkpoint mid-stream.** Record at **1080p**, browser zoom 100%, chrome hidden.

---

## 1 · ▶ Clip 1 — Onboard (~50s, shortest) → `deck/assets/clips/onboard.mp4`
Brisk — don't read every answer.
1. Greet screen → quiz: name → role → space story → toggle senses → life-stage + living → non-negotiable → energy.
2. Inspire: type an aesthetic, then the **3 rounds** of picking images.
3. Moodboard → "this is it" → end on the **persona reveal**.

## 2 · ▶ Clip 2 — Shape (~90s, the hero) → `deck/assets/clips/shape.mp4`
The ripple, live.
1. Enter layout mode → pick **201**; let the **CAD linework** draw.
2. **Analyze** → scores + the six-petal rose.
3. Point at a **conflict** (a flagged sense).
4. **Open the capabilities menu** (organized per sense) → show the agent's full vocabulary: 9 edit tools (add window · change wall · curtains · ventilation · relocate · remove · furniture · glazing · material) plus the insight passes (topology · biophilic · persona-compare · galaxy). This is where the breadth lands; the deck only names it in one line.
5. Edit, e.g. **"change the kitchen walls to cork"** or **"add a window to the master bedroom."**
6. **Focus Pull**: the plan dims, the change lights in place; hover for `before → after` + score impact.
7. Show the **re-score delta** (the suggestion crosses off).
8. Open the **ripple checkpoint graph** (sense-strands weaving).
9. A quick **glance at the galaxy + Narrator** (hover a thread → plain-words read-out).

## 3 · ▶ Clip 3 — Report (~70s, the payoff) → `deck/assets/clips/report.mp4`
The loop closing.
1. Open the **Report** → land on the **persona header + moodboard band**.
2. Expand a room → **progressive reveal** → the **rendered room** (pre-warmed).
3. Trigger a **before/after** wipe on an edited room.

---

## 4 · Still screenshots the deck needs → `deck/assets/shots/`
Exact filenames (the deck auto-loads them; the "[ drop … ]" box disappears once present):

| File | Slide | Capture |
|---|---|---|
| `report-before.png` | 11 · Made real | a Report room render BEFORE an edit |
| `report-after.png` | 11 · Made real | the SAME room AFTER the edit (the glow-up) |

Slide 16 (the renders, judged) already uses the real Google-vs-OpenAI A/B in the repo
(`deck/assets/bench-google-living.png` / `bench-openai-living.png`); slide 13's before/after uses
the generated `shots/report-before.png` / `report-after.png`. Nothing else to drop.

---

## 5 · Present & export
- **Open** `deck/index.html` — double-click (file://) works, or serve any parent folder. The
  deck is self-contained (all assets under `deck/assets/`).
- **Navigate:** arrow keys / space · `f` fullscreen · `o` overview · **`s` opens speaker notes**
  (the full spoken script is embedded per slide — see `presentation-script-week09.md`). On-screen
  nav arrows are intentionally off; drive it from the keyboard or a clicker.
- **Clips** autoplay (muted, looped) when their file is present; they're full-bleed and show
  `▶ DEMO` instead of a slide number. Content slides number `1…18`.
- **Static PDF** (handout) is already built at `team_02/docs/week09/Sensi-FinalReview-week09.pdf`
  (21 pages, one per section). To regenerate after edits, run
  `python team_02/docs/week09/deck/make-pdf.py` — it screenshots each slide headlessly (Edge) and
  assembles the PDF with PyMuPDF (reveal's own `?print-pdf` is unreliable headless). Clip pages
  export as their `▶ DEMO` placeholder, since a PDF can't play video.

*The deck authors its own 3-zone architecture diagram, so no mermaid render is needed. The
earlier reportlab deck (`build_deck_week09.py` + `Sensi-Presentation-week09.pdf`) has been
removed — the HTML deck and its exported `Sensi-FinalReview-week09.pdf` are now the only
presentation artifacts.*
