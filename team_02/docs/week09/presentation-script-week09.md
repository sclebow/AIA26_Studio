# Sensi / Final review · spoken script

21 pages in one continuous count: 18 talk slides + 3 pre-recorded, narrated demo clips, interleaved
by act (each clip also keeps a ▶ DEMO n / 3 title). **Target ~9:00-9:30 of live talk + ~3:30 of
clips (~13 min total, under a 15-min cap).** The authoritative copy is embedded in the deck as
reveal speaker notes (press `s` in `deck/index.html`); this file mirrors them.

**Four presenters.** Three live speakers split the 18 talk slides into roughly equal time; a fourth
records the three demo voiceovers. Both live handoffs are masked by a demo clip, so no awkward live
baton-pass. The script narrates the WHY, never reads a slide, and says every formula in plain
English. No em dashes; use `→` `/` `[ ]` and commas.

Heroes: Clip 2, Clip 3, page 12 (the veto → 0.34), page 19 (the close). Handoff cues (one word,
spoken into the clip): **S1→S2 = "watch."  S2→S3 = "look."**

---

## Speaker split + time tally

| Speaker | Owns (pages) | Arc | Tally |
|---|---|---|---|
| **Speaker 1** | 1, 2, 3, 4, 5, 6 → **CLIP 1** | Why + the machine + Onboard intro | **~2:43** |
| **Speaker 2** | 8, 9 → **CLIP 2** → 11, 12, 13, 14 → **CLIP 3** | The math + all of Shape (the climax) | **~3:14** |
| **Speaker 3** | 16, 17, 18, 19, 20, 21 | Report + grounding + the close | **~2:57** |
| **Speaker 4** | CLIP 1 / 2 / 3 voiceovers | Pre-recorded demo narration | ~3:30 (clips) |

Speaker 2 runs ~20-30s long by design (owns both heroes + the Clip-2 re-entry). If you need it
tighter, shave page 12 or 13 by ~10s each.

## Delivery / rehearsal notes
1. **Presenter 4 = real clip operator.** Don't trust autoplay across the room's browser/projector.
   P4 owns the laptop and manually triggers each clip; test on the actual machine + HDMI + audio out.
2. **Mute live mics during every clip** so breathing/whispers don't bleed over the recorded VO.
3. **Pass the clicker during the clip,** not after, the receiving speaker takes it mid-clip.
4. **Choreograph the page-19 silence:** Speaker 3 holds still + eye contact on each `[beat]` so it
   reads as intent, not a stall.
5. **Speaker 2 rehearses the Clip-2 re-entry cold,** the first word after a clip is where people freeze.

---

## ▸ SPEAKER 1 · Why + the machine (pages 1-6, ~2:43)

**1 · Cover** *(~16s)* · Hi, we're Team 02. This is Sensi. It reads a floor plan and tells you how it
will feel, across six senses, for one specific person. Not the average occupant. The actual person
who'll live there. Here's the whole instrument, end to end.

**2 · The question** *(~42s)* · We start from a gap. In architecture we measure almost everything.
Energy, cost, code, structure. The one thing we never measure is how a room will actually feel to be
in, for the person who lives there. And there's a second blind spot. The senses aren't independent.
Add a big window, and yes, the daylight improves. But the same window makes the room louder, and
colder in winter. You fixed one sense and quietly hurt two others. Every design move has a hidden
second cost. We call it the ripple, and right now nobody sees it until the building is built and
someone's living in it. Sensi makes that invisible axis, and its trade-offs, visible at the plan stage.

**3 · The thesis** *(~30s)* · This is the line the whole project comes back to. The number isn't the
lesson. The edges are. A space is a conversation between your senses, and the single overall score is
the least interesting part of it. Three ideas carry the work, and we prove each one where it shows
up. Personal: your senses, your weights, not an average body. Honest: no averaging, the worst sense
gets a veto. And coupled: the senses pull on each other. That pull is the ripple. The rest of the
talk is us earning those three words.

**4 · How it's built** *(~34s)* · One quick look under the hood, then we show it. Everything you type
is one turn. A small, fast model reads that turn and routes it, in a single call, to the right kind
of work. There are three: understanding a plan, editing a plan, which is where the agent and the
ripple live, and seeing a plan a new way. Whatever the path, it always ends the same way, the system
answers, then grades its own answer once. It all runs in your browser, the comfort engine
in-process, no Rhino, no plugin, and it streams its thinking as it goes. About three seconds to first
feedback.

**5 · The models** *(~26s)* · What powers it is three Gemini models, and the whole choice was cost
against reasoning. A cheap, fast model does the routing, the quick decisions. A smarter, pricier
model does the reasoning you actually read, where quality is worth paying for. And a native image
model paints the rooms at the end. These are current Gemini 3.x, and because model names go stale
fast, we verified every one live against Google's docs before trusting it. Small models route, the
expensive tier only runs where it earns its cost.

**6 · Act 1 / Onboard** *(~15s · cue "watch" → CLIP 1 → hand to Speaker 2)* · Act one. Onboarding.
This is where you tell Sensi who you are, and it builds a sensory persona from your answers. Rather
than describe it, let's **watch.**

> **▶ CLIP 1 plays (Speaker 4 VO, ~50s). Speaker 2 takes the clicker during the clip.**

## ▸ SPEAKER 2 · The math + Shape (pages 8-14, ~3:14) · opens after Clip 1

**8 · It's personal · math [1/3]** *(~40s)* · What you just watched, the quiz and the moodboard, all
of it becomes numbers. Here's how, in plain terms. Every answer nudges a weight, one per sense, and
weights only ever go up. Say plants are non-negotiable, your smell weight climbs. Say noise really
gets to you, acoustic jumps. Each weight then sets that sense's alert threshold, the bar where Sensi
flags a problem. The rule is intuitive: the more you care about a sense, the higher its bar, so Sensi
flags it sooner for you than for someone who doesn't care. And we deliberately tune to one person,
not a household average, because comfort isn't an average. It's whoever suffers most. Add a
grandmother or a cat, and the scores shift again.

**9 · Act 2 / Shape** *(~15s → CLIP 2)* · Act two is the heart of the tool. Shape. We read a real CAD
plan, score all six senses on it, and surface the conflicts you'd never catch by eye. Then we edit,
and watch it ripple. To the plan.

> **▶ CLIP 2 plays (Speaker 4 VO, ~90s). Speaker 2 resumes after, rehearse this re-entry cold.**

**11 · How a room is scored · math [2/3]** *(~40s)* · You just watched it score a kitchen. Let me open
up one of those scores, because it isn't a black box. Every sense runs zero to one, where one is
ideal comfort. Each starts at a baseline for the room type, a kitchen starts middling on sound, low
on smell, that's just what kitchens are. Then the real geometry moves each number. Which way the room
faces, how much glass, how sound bounces off hard tile, whether there's ventilation, what the
surfaces are. In this kitchen, two senses fall hard. Sound drops, it's a hard, boxy room. And smell
drops further, weak ventilation, and it sits right next to a wet zone. Every one of those moves is
grounded physics, not a vibe. Now watch what happens when the senses start talking to each other.

**12 · The ripple, then the veto · HERO** *(~52s · shave ~10s here if tightening)* · This is the core
of the whole project, so let me slow down. First, the ripple. A failing sense doesn't stay in its
lane. That weak sound score reaches over and drags down its neighbors, a little off thermal, a little
off visual, because a loud room genuinely feels worse in other ways too. And every one of those
nudges is labelled with its reason, building science or physics. Nothing moves in secret. Then the
honest part. To combine six senses into one number, we do not average them. Averaging is a lie, it
lets a great kitchen hide one unbearable problem behind five good scores. Instead the worst sense
gets a veto. The overall is half the weighted average, and half the single worst sense. So this
kitchen, where most senses are actually fine, lands at 0.34 out of one. Floored by smell. [beat] A
great room with one unbearable sense is still an unbearable room. That's the number finally telling
the truth.

**13 · The reasoning, measured** *(~30s · trim-first if you run long)* · A quick word on whether this
is actually practical, because reasoning models can be slow and pricey. We measured every node in one
full session. The fast routing models stay under a second and basically free. All the time and cost
live in the smart tier, the reasoning you read. The whole session, start to finish, costs under a
nickel. And when we moved up a model generation, we checked we hadn't gotten worse, judged blind, the
new reasoning won four of five nodes. We pay a little latency and a few cents, and the reasoning gets
better. That's the trade we'll take.

**14 · Act 3 / Report** *(~17s · cue "look" → CLIP 3 → hand to Speaker 3)* · Act three. The Report.
This is where the loop closes, where the output finally answers the input you gave at the very start.
Your persona comes back, the look you curated comes back, and every room becomes an image of how it
feels. Take a **look.**

> **▶ CLIP 3 plays (Speaker 4 VO, ~70s). Speaker 3 takes the clicker during the clip.**

## ▸ SPEAKER 3 · Report + the close (pages 16-21, ~2:57) · opens after Clip 3

**16 · Scores → prompt → image · math [3/3]** *(~38s)* · What you just saw is generated, not stock
photos, and the way we generate it is built to stay honest. A room's six scores become a text prompt
by a fixed rule, no model improvising. And the rule is: only the extreme senses get to speak. Clearly
bad, below 0.45, or clearly good, above 0.70, writes a phrase. Everything in the comfortable middle
stays silent, so the picture only shows what's genuinely notable. This kitchen's prompt says stuffy,
closed air, hard reflective surfaces, a cool bluish light, and a generous open volume. Those are its
real scores, in words. And the before-and-after is the same trick in reverse. The after is the room's
true render. The before is that exact image, edited by one short what-changed clause, so the scene
holds still and only the change moves. The aesthetic you picked at minute one, it comes back here.
The circle closes.

**17 · The renders, judged blind** *(~24s)* · Fair question: can you trust an AI render? So we tested
it instead of asserting it. First, the engine. Same prompts, Google against OpenAI, head to head.
Google came back about three times faster, a touch cheaper, and cleaner, more like real architectural
daylight, so that's the engine we ship. Then the generation. The new Google model against the old
one, judged blind, the new won all three rooms, sharper and more photoreal. The renders aren't
decoration. They're the scores, made believable.

**18 · Grounded** *(~52s)* · This is the slide I most want to defend, because the obvious challenge
is: did you just invent these couplings? No. Every coupling comes from peer-reviewed building science
or standard room physics. The research-based ones went through an adversarial fact-check, three
independent votes each. Twenty-five claims went in, eighteen survived, the other seven we cut. Where
the evidence is real but thin, we encode only the direction, a plus or a minus, never a fake-precise
number. Now the matrix, because it rewards reading. Each row is a sense. Read across the row and you
see what that sense does to the others. Plus helps a neighbor, minus harms one, plus-or-minus means
it depends. Solid cells are research-verified, dashed cells are standard physics. And here's the
detail I love. Acoustic and visual. Noise harms visual focus, that's a minus. But the mirror cell is
just a dot, empty, because light does nothing to how loud a room feels. That coupling runs one way
only, and the model says so instead of pretending the world is symmetric. One honest limit: we ground
these rules in research, we haven't validated them against a comfort dataset, because one doesn't
really exist. Which is exactly why we built a tool that makes comfort legible, not one that claims to
be right.

**19 · The close · HERO** *(~24s · slow, hold the beats)* · [beat] The score was never the point. The
ripple was. What we're claiming is small, but we think it's real. Sensi makes the coupling between
the senses something you can design with, at the plan stage, before a single wall goes up. A feedback
loop for how a building will feel, before the building exists. [beat] We measure everything except
how it feels. Now we can argue about it.

**20 · What this raises** *(~28s)* · And we'd rather end on the arguments than a victory lap. Two we
keep circling. When a household disagrees, whose senses win, and who gets to set the weights? And how
far should the agent go, surface the trade-off, or make the call for you? There are two more on the
slide. But the one underneath all of them is this: a felt-experience score, is it actually
accountable, or is it just persuasive? We don't think that's settled. We think it's the interesting
part.

**21 · Thanks** *(~11s)* · That's Sensi. Thank you. Now, let the senses talk. We'd love your questions.

---

## Demo voiceovers (Speaker 4, pre-recorded · paced to 150-160 wpm)

**▶ CLIP 1 / Onboard · ~50s** *(quiz → inspire → moodboard → persona reveal)* · Sensi starts by
getting to know you. A few quick questions, your name, your role, the story of the space you're
shaping. You toggle the senses that matter most to you. You say who lives here, and the one thing you
won't compromise on. Then it learns your eye. You type an aesthetic in your own words, and Sensi
gives you rounds of images, you keep what feels right and skip what doesn't. Three passes, and a
moodboard takes shape. And here's the point of all of it. Sensi compiles your answers and your
choices into a single sensory persona. Your weights, your priorities, in its words. That persona
becomes the lens for everything that follows.

**▶ CLIP 2 / Shape · ~90s** *(load 201 → analyze → conflict → capabilities → edit → Focus Pull →
re-score → graph → galaxy)* · Now the real work. We load an actual floor plan, layout 201, and Sensi
draws it as clean CAD linework, walls, doors, windows, furniture. We hit analyze. In a few seconds
every room is scored across all six senses, shown as a six-petal rose, the bigger the petal, the
better that sense. And right away a conflict surfaces, a sense Sensi has flagged below your personal
bar. Before we fix it, look at what the agent can actually do. This menu is its full vocabulary,
organized by sense. Nine real edit tools, add a window, change a wall, hang curtains, add
ventilation, swap a material, and more, plus four ways to see the plan differently. So we just tell
it, in plain language, change the kitchen walls to cork. It plans the edit, applies it, and then
Focus Pull takes over. The whole plan dims, and only what changed lights up, right where it is. Hover,
and you see the before, the after, and exactly which scores moved. The room re-scores, and the
suggestion that flagged it crosses itself off. Open the checkpoint graph, and every sense is a strand
you can watch weave as you edit. And the galaxy gives you the whole project as one living map, hover
any thread, and the Narrator explains it in plain words.

**▶ CLIP 3 / Report · ~70s** *(persona + moodboard → expand room → progressive reveal → render →
before/after)* · This is the Report, and notice what greets you first. Your persona, right at the
top, and the moodboard you built at the very start. The output opens by remembering your input. We
expand a room. It reveals in stages, the scores, then the reasoning, and then the room itself,
rendered. A first-person image of how that space actually feels to be in. Not a generic 3D model,
this room, with its real comfort scores turned into light, material, and air. And for a room we
edited, we can wipe between before and after. Same room, same angle, only the change moves, so you
can see the improvement, not just read it. That's the whole loop, closed. You told Sensi who you are.
It read your plan, scored how it feels, and showed you the trade-offs. And every room you walk
through in this report, you've already shaped, without lifting a pencil.

---

## Pacing
1-6 frame the why + the machine + onboarding, steady; page 2 plants both the person and a concrete
ripple so "the ripple" is tangible the first time it's named. 8-14 are the math and all of Shape, the
conceptual climax: page 11 states the 0→1 scale, page 12 (the veto → 0.34) is the hero, let it
breathe. 16-18 close the loop and ground the model; page 18 walks the matrix and ends on one honest
limitation. **19 is the stance**, delivered slow with two held beats, that sets up 20's questions.
21 hands off to Q&A.
