# TerraPilot — Presentation

Everything for the 8-minute TerraPilot presentation, themed to match the interface.

## Files
| File | What it is |
|------|-----------|
| **terrapilot-deck.html** | The slide deck. **Open in Chrome, press F for fullscreen.** Self-contained — no internet needed. |
| **SPEAKER-SCRIPT-8min.md** | Word-for-word script with timing + who speaks each slide (David → Daniel → Nihan → Sush). |
| **GRAPHICS-IDEAS.md** | Ideas to make it more stunning (live-video embeds, before/after, Pareto plot…). |

## How to present
1. Double-click `terrapilot-deck.html` → opens in your browser.
2. Press **F** for fullscreen.
3. Navigate: **→ / Space** = next, **←** = back, **Home/End** = first/last.
   Clicking the right side of the screen also advances.
4. Follow `SPEAKER-SCRIPT-8min.md` for timing and lines.

## The 10 slides (8 min)
1. Title — what TerraPilot is *(David)*
2. The Idea — why it matters *(David)*
3. The Workflow — 7 stages *(David)*
4. Site & Urban Context + live dashboard *(Daniel)*
5. Shape Generation & Manipulation *(Nihan)*
6. Prompt Understanding — 3-layer pipeline *(Sush)*
7. Optimization — multi-objective Pareto *(Sush)*
8. Hard Problems Solved *(Sush)*
9. Backend architecture *(Sush)*
9b. **Agent state graph** — animated, drawn from `agent/graph.py` *(Sush)*
10. Close *(Sush)*

> The **state-graph slide** is the live animated version of `state-graph.html`,
> embedded directly in the deck (data flows along every edge; the `central_reason`
> hub pulses). It also stands alone as `../state-graph.html` if you want to show it
> full-screen on its own.

## Theme
Matched to the interface: dark navy `#070b14`, cyan `#28e0d0` / `#57f2e6`,
violet `#7c7bff`, holographic grid, light-sweep slide transitions, animated score bars.

## Best upgrade before the day
Record 6–10s screen clips of the real interface (manipulation, optimization, road-align)
and embed them — see GRAPHICS-IDEAS.md. A live clip beats any static slide.
