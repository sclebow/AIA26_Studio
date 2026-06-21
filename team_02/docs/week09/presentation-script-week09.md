# Sensi / Final review · presentation script

18 numbered slides + 3 full-bleed, live-narrated demo clips, interleaved by act.
**Target ~10-12 min slides + ~3:30 of clips.** The authoritative copy is embedded in the deck
as reveal speaker notes (press `s` in `deck/index.html`); this file mirrors them.
Heroes: Clip 2, Clip 3, slide 10 (the veto → 0.34), slide 16 (the close). Jargon translated at
handoffs ("worst sense wins, no averaging"). No em dashes; use `→` `/` `[ ]`.

---

**1 · Cover** *(~12s)* — This is Sensi, end to end. It reads an architectural plan and tells you how it will feel, across six senses, for a specific person.

**2 · The question** *(~25s)* — We measure everything except how a room will feel. And we never measure the ripple between the senses, where every move has a hidden second cost. Sensi makes that axis, and its trade-offs, measurable.

**3 · The thesis** *(~20s)* — The line the project comes back to: the number isn't the lesson, the edges are. Three ideas, personal / honest / coupled, each proved where it shows.

**4 · How it's built** *(~28s)* — One classifier routes each turn into the right chain: analysis, the edit ripple, or an insight branch, always ending respond → evaluate. In-process comfort engine, no Rhino. It streams its thinking and runs in a browser.

**5 · The models** *(~22s)* — Two reasoning tiers: FAST for routing, SMART for the reasoning you read, plus a native image model. Current Gemini 3.x, verified live before trust. Small models route the turn; the reasoning tier runs only where quality compounds.

**6 · Act 1 / Onboard** *(~10s)* — You tell Sensi who you are. **▶ PLAY CLIP 1 (~50s):** quiz → moodboard → the earned persona reveal.

**7 · It's personal · math [1/3]** *(~25s)* — Your answers raise per-sense weights, which set each sense's alert threshold: `t = clamp(0.35 + 0.40·w, 0.35, 0.75)`. Care more about a sense, flagged sooner. It travels too: a grandmother or a cat shifts the scores.

**8 · Act 2 / Shape** *(~10s)* — Read the plan, see the conflicts you can't. **▶ PLAY CLIP 2 (~90s):** CAD plan → scores → conflict → edit → Focus Pull → re-score → ripple graph → galaxy.

**9 · How a room is scored · math [2/3]** *(~28s)* — Each sense starts at a room-type baseline, then real geometry moves it: orientation, glazing, Sabine reverberation, ventilation, materials. In the Kitchen, acoustic falls to 0.39 and olfactory to 0.20.

**10 · The ripple, then the veto · HERO** *(~30s)* — Then the senses pull on each other: a failing sense drags its partners, every nudge labelled with why. And the worst sense vetoes, no averaging: half the weighted mean, half the single worst. The Kitchen lands at 0.34. A great room with one unbearable sense is still unbearable.

**11 · The reasoning, measured** *(~22s)* — FAST stays sub-second and near-free. SMART is where time and cost live, score_interpreter the biggest lever at 24 seconds. The whole session is under a nickel. And judged blind, the new reasoning won four of five nodes: no regression.

**12 · Act 3 / Report** *(~10s)* — How will each room feel? **▶ PLAY CLIP 3 (~70s):** persona + moodboard return → renders → before/after.

**13 · Scores → prompt → image · math [3/3]** *(~25s)* — A room's scores assemble deterministically into a prompt: only the extreme senses speak, below 0.45 or above 0.70. The "after" is the room's canonical render; the "before" is that same image edited by a "what changed" clause, so the scene holds and only the change moves. The aesthetic you curated comes back here.

**14 · The renders, judged blind · HERO** *(~22s)* — Are the renders trustworthy? Two image engines on one prompt: Google is faster and cleaner than OpenAI, so we stay on Google. And the new image model beats the old one three of three, judged blind: sharper, more photorealistic.

**15 · Grounded** *(~22s)* — None of this is invented. The couplings come from peer-reviewed building science and standard room physics, run through an adversarial fact-check, eighteen of twenty-five kept. Where evidence is thin we encode the direction, not false precision.

**16 · The close · HERO** *(~18s · slow)* — The score was never the point. The ripple was. Sensi makes the coupling between senses designable at the plan stage: a feedback loop before the building exists. [beat of silence] We measure everything except how it feels. Now we can argue about it.

**17 · What this raises** *(~25s)* — The questions worth arguing about: legible or optimal, whose comfort when a household disagrees, how far the agent should go, and whether a felt-experience score is accountable or just persuasive.

**18 · Thanks** *(~8s)* — Thank you. Now let the senses talk.

---

## Pacing
1-5 frame (the why + the machine + its models), steady. 6-14 the three-act spine, each frame →
clip → math, with the act's benchmark folded in (performance in Shape, the renders in Report).
15 grounds the model; let slide 10 (0.34) breathe. **16 is the stance** that sets up 17's
questions: say the line, hold the frame, beat of silence into Q&A. 18 hands off.
