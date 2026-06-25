# Making the Presentation Stunning — Graphics Ideas

The deck (`terrapilot-deck.html`) already matches the interface theme exactly
(dark navy `#070b14`, cyan `#28e0d0`, violet `#7c7bff`, holographic grid). Here are
ideas — already built ✅ or easy to add — to make it more attractive.

## ✅ Already in the deck
- **Animated holographic grid** background that slowly drifts (matches the 3D workspace).
- **Light-sweep transition** between slides (the same cyan→violet sweep the interface uses on stage changes).
- **Gradient glass panels** with the cyan-violet accent bar (identical to floating UI panels).
- **Animated score bars** that fill on slide entry (mirrors the Live Design Health dashboard).
- **Pipeline node diagrams** for the 3-layer understanding and the optimization flow.
- **Progress bar** + page counter + glowing brand footer.

## 🎬 The single most powerful upgrade: embed LIVE screen recordings
Static slides are good; a 6–10s clip of the *real* interface doing the thing is unbeatable.
Record these short clips (any screen recorder — Win+G on Windows) and drop them onto the
matching slides as muted, autoplay, looping `<video>`:

| Slide | Clip to record (6–10s each) |
|-------|------------------------------|
| 4 (Context) | Urban context loading + the dashboard scores ticking live |
| 5 (Manipulation) | Type "give it a futuristic appearance" → building twists |
| 5 (Manipulation) | "add 2 floors on right wing" → wing grows |
| 7 (Optimization) | Click optimize → 8 options appear on the site with score cards |
| 8 (Road align) | "align facade to main road" → building rotates to the road |

How to embed (replace the panel/code block on that slide):
```html
<video src="clips/manipulate.mp4" autoplay muted loop playsinline
       style="width:100%;border-radius:14px;border:1px solid rgba(120,160,220,0.16);
              box-shadow:0 10px 40px rgba(0,0,0,0.5)"></video>
```
Put the .mp4 files in `presentation/clips/`. They'll loop silently while you talk.

## ✨ Cheap wins (no new assets)
1. **GIF the 3D building rotating** on the title slide — even a 3-second loop adds life.
2. **Before/After split** on slide 5: left = plain block, right = futuristic twist. A 2-column
   image comparison sells "manipulation" instantly.
3. **A real screenshot** of your interface as a faint, blurred backdrop on the title slide
   (low opacity) — instant context.
4. **Number counters** that count up (e.g. "3768 context elements") — small JS, big effect.
5. **A Pareto scatter plot** on slide 7 — even a simple SVG of dots with the front highlighted
   makes the optimization look rigorous.

## 🎨 Keep it consistent
- Only ever use these colors: bg `#070b14`, text `#c4d2ec`, cyan `#28e0d0` / `#57f2e6`,
  violet `#7c7bff`, amber `#ffb454`, pink `#ff8fa3`, green `#57e08a`.
- One accent per element. Don't rainbow it.
- Lots of negative space — the dark background is your friend; let it breathe.
- Every heading: white→cyan→violet gradient (already styled as `h1`).

## 📤 Need PowerPoint instead of HTML?
The HTML deck is self-contained and looks better, but if the venue requires .pptx:
- Open the HTML, press **F** (fullscreen), screenshot each slide → paste into PowerPoint
  as full-bleed images. You keep the exact look with zero rebuild.
- Or print to PDF from the browser (each slide one page) for a portable handout.

## Want me to add any of these?
Tell me which (live-video embeds, Pareto scatter, before/after, count-up numbers) and
I'll wire it into the deck.
