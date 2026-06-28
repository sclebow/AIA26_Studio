# Sensi / Final Review · spoken script

The arc reads WHAT then WHY then the three acts. WHAT is the cover and the sensory layer. WHY is the research gap, the ripple, and the same plan read through two people. Then the three acts, each opened on its own slide and interleaved with a clip: Act 1 Onboard, then It's Personal and the design levers and the coupling and veto, then Act 2 Shape with the scoring engine, the room graph, and the checkpoint, then Act 3 Report and the rendered output, then the honest close.

The voice is conversational and natural, not a brochure. The slides are clean and carry the detail visually, so the spoken lines stay lean and only the core slides (What is Sensi, the research, the ripple, the design levers, coupling, Act 2, the graph, Report, What we learned) are elaborated.

**Presenters.** Maria 1 to 7 (cover through Act 1) · Charles 9 to 16 (the persona, the how, and Act 2) · Lakzhmy 17 to 21 (Act 3 through the close). **Emilie narrates the 3 demos LIVE over the clips** (the clips are silent screen-captures; she talks over them). Handoffs: Maria to Charles is masked by Clip 1; Charles spans Clip 2; Charles to Lakzhmy is a clean break at Act 3.

No em dashes anywhere. The deck `<aside class="notes">` (press `s` in `deck/index.html`) are the source of truth and match this file.

**Timing (strict 13:00 faculty cap).** Slide narration is about 1,030 words, roughly 7:38 at a calm ~135 wpm. The three clips are fixed: Onboard 1:15, Shape 2:00, Report 0:45 = 4:00. Total about **11:38**, leaving ~1:20 of safety buffer. The demo narration is sized to fit *under* each clip at a relaxed pace, so a fumble never runs past the video.

---

**1 · Cover · Maria · ~5s**

Hi, we're Team 02, and this is Sensi, a comfort copilot.

**2 · What is Sensi · Maria · ~40s**

So, what is Sensi? In building, we already model a plan in layers, structure, cost, energy, and code. The way a space will actually feel was never an accountable layer. Sensi adds the sensory layer. It reads the plan and scores how each room feels across six senses, for the one person who'll live in it. While designing it we kept the following in mind: it's personal, scored for you, it prioritizes the worst sense to carry the weight; and the senses are coupled, they pull on each other.

**3 · The gap in the AEC · Maria · ~28s**

Comfort itself is usually studied one sense at a time, in isolation. The research says otherwise. Spence and colleagues, in 2020, the multisensory mind, you take a room in through all your senses at once. And a 2025 cross-modal review, the senses are coupled, one moderates another. So we leaned on the coupled system, where changing one sense moves the others as a network.

**4 · The ripple · Maria · ~32s**

Let's take the following as an example. A bigger window affects the daylight positively, that's the upgrade you see. But the same glass is a thinner sound barrier, so noise gets in, and it leaks heat, so the room's colder in winter. Those are the costs you don't see. That is what we call the ripple: the noise it let in even dims the daylight you gained, one sense moderating another.

**5 · The same plan, two people · Maria · ~26s**

It all starts with getting to know the user. One plan, read differently for two people. Slide the lens to a child, who minds noise, and the loud living room lights up as the problem. Slide it to a grandmother, who minds the cold, and the cold bedroom does instead. That's why Sensi opens by learning who you are.

**6 · The three acts · Maria · ~32s**

So Sensi is a conversation in three acts. First, Onboard, where it gets to know you, that's the main input. Then Shape, the heart of it, a back-and-forth between you and the agent to edit the plan and watch it respond. And finally Report, which carries the outputs forward, the renders and the edited JSON. You talk, it answers, and the output of each act becomes the input to the next.

**7 · Act 1 / Onboard · Maria · ~39s · then hand to Clip 1**

Let's zoom into the first act. Onboarding is where it learns who you are. You answer a few questions, then you build a moodboard, and behind the scenes Sensi reads both: your words become sense weights, and each image you keep nudges those weights toward the senses you're drawn to. It compiles all of it into your persona, your personal weighting of the six senses, and that carries into act two as the lens for every score. Easier to watch than to describe, so let's see it.

**▶ DEMO 1 / Onboard · Emilie · LIVE over the ~1:15 clip**

Alright, so let's see it in action. This is Sensi, let me walk you through onboarding. I start by typing who I am and what I do, a space I really remember, the senses that matter most to me, my age, who I live with, and the things I won't compromise on. Then I get to the moodboard, where I build my aesthetic. I give it a few keywords, pick from what it shows me, and each picture quietly tells it which sense I'm leaning toward. Once my selection's done, I get my moodboard, and then my profile reveal, where I can see the average I landed on versus someone like me. Then, in the shape phase, I can always refine my persona: say I don't care much for tactile or thermal, and I just got a new dog, and you'll see the petal rose update based on that. And that's onboarding.

**9 · It's personal · Charles · ~9s**

So that's your persona, compiled from your answers, your eye, and your situation. This becomes the lens for everything that follows.

**10 · The design levers · Charles · ~29s**

Comfort comes from a handful of design moves, which way it faces, how much glass, whether it breathes, how big it is, the surfaces, and what's next door. Each lever pulls on one or more senses, and the colour says which way: green helps, red harms, orange is a trade-off. Glazing helps the visual, but hurts the acoustic, and it cuts both ways on thermal.

**11 · Coupling and the veto · Charles · ~16s · the core**

As mentioned before, the ripple is what matters, so we studied the couplings as a matrix, based on researched connections and physics. And the worst sense carries the room, because that's the one you'd actually feel.

**12 · Act 2 / Shape · Charles · ~52s · then hand to Clip 2**

So, act two, Shape, this is where the agentic power lives, and it's the heart of the system. When you ask for something, a fast model first routes your intent, are you asking to score, to edit, or to see it a new way, in one quick step. If it's an edit, the agent plans it, places it soundly so the plan stays valid, applies it, and re-scores. If it's a question, a heavier model reads the whole room, all six scores, their couplings, and your persona, and answers in plain words. It all funnels through one agent, so you can edit materials, furniture, plants, windows and more, and watch the layout and the relationships respond.

**▶ DEMO 2 / Shape · Emilie · LIVE over the ~2:00 clip**

So we're in the design space. Let's pick a layout, that one doesn't really match my grandma and me, so let's go with the city apartment. I run a full analysis, take a look at the capabilities while it works, and then I can read the model's actual answer and find it in the plan itself. It gives me suggestions, so let's try one: I'll add a large window in the kitchen and the living room, and you can see the focus pull land right on those, hover, and you get more detail. We can keep editing to make the space better, adding a rug and curtains, and you'll see the suggestions cross themselves off automatically. Let's commit those changes. Now let's add plans to all the rooms, where the biggest changes show, and we can see them all at a glance. We can also map the topology of the space, and look at the commits so far and how each one moves each sense. In the graph, you can see that ripple we keep talking about, one per sense, hover any one to see how it pulls on the others. We also have the galaxy view, meant for exploration: we see the rooms, the senses, and the design levers behind them. Expand a room to see its senses, they connect to each other too, and on hover you get the ripple, between a lever and the senses, and between the senses themselves.

**14 · Under that score · Charles · ~11s · after Clip 2**

So everything you just saw, every score is built from those levers and their couplings, with fixed rules underneath, deterministic scoring, not LLM reasoning.

**15 · Graph / galaxy · Charles · ~32s**

As we saw in the demo, the relationship graph between the rooms matters too: rooms as nodes, doors as edges, finding the hubs and the bridges, carrying the senses that bleed between rooms, the kitchen's noise and smell reaching the bedroom. So comfort becomes a zoning problem you can see, straight from the autism sensory-design research. And that's the vision we had for the galaxy, the whole project as one living map.

**16 · Every edit, tracked · Charles · ~28s**

Every edit is kept as a checkpoint, so you watch the plan improve honestly, each line is a sense, rising as it gets better. A single-room change nudges a sense or two; a layout-wide change ripples through everything, and that strong weave is the coupling working. And only what you commit carries forward, so the Report shows the plan you actually kept.

**17 · Act 3 / Report · Lakzhmy · ~17s · then hand to Clip 3**

Last act, the Report, is where the loop closes. You get the outputs, the final edited layout, and a vision model that brings your changes to life, so you can compare it back to your moodboard and your needs.

**▶ DEMO 3 / Report · Emilie · LIVE over the ~0:45 clip**

Okay, now we jump into the report. I've got uncommitted changes, so let me commit them first so they show up here. Then we see the moodboard we chose at the start, we can explore the senses coupling, and the before-and-after Sensi generated for the most changed room. We also get a render per room. You can dig into the scores and the prompt behind them, hover any sense to see how it was read into words, and download it as an image, or the plan as JSON. And that's the report.

**19 · Scores to prompt to image · Lakzhmy · ~23s · after Clip 3**

On the left, the room's scores write the prompt, and the honest rule holds: only the extreme senses speak, a clearly good or bad sense writes a phrase in its colour, and the comfortable middle stays quiet. On the right, the same room before and after, same angle, only the change moving.

**20 · What we learned · Lakzhmy · ~38s**

We want to end with what we learned. We got the ripple to become legible, and we benchmarked different nodes to understand where to put the weight and which models perform better. But the real learning is in the questions it raised. Could we ever prove it? What about a sense that doesn't apply, could Sensi lean its weight onto the senses a blind or Deaf person lives by? Which brings us back to: we made the senses legible, what else can we make legible?

**21 · Thanks · Lakzhmy · ~3s**

That's Sensi. Thank you for listening.

---

**Timing recap.** Slides about 1,030 words at a calm ~135 wpm ≈ 7:38: Maria (1 to 7) ≈ 3:40, Charles (9 to 16) ≈ 3:00, Lakzhmy (17 to 21) ≈ 1:50. The three live-narrated clips are fixed at 1:15 + 2:00 + 0:45 = 4:00. Total ≈ **11:38**, comfortably under the strict 13:00 cap. If a run goes long, trim slides 12, 2, or 15 first.
