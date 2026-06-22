# Sensi / Final review · spoken script

**Maria** = Speaker 1 (slides 1-6) · **Charles** = Speaker 2 (slides 8-14) · **Lakzhmy** = Speaker 3 (slides 16-21). **Emilie** records the 3 demo voiceovers (slides 7, 10, 15), in `demo-scripts-week09.md`.

---

**1 · Cover · Maria**

Hi, we're Team 02. This is Sensi. It reads a floor plan and tells you how it will feel, across six senses, for one specific person.

**2 · The question · Maria**

We start from a gap. In the AEC we measure almost everything. Energy, cost, code, structure. The one thing we never measure is how a room will actually feel to be in, for the person who lives there. And there's a second blind spot. The senses aren't independent. Add a big window, and yes, the daylight improves. But the same window makes the room louder. Every design move has a hidden second cost. We call it the ripple. Sensi makes that invisible axis, visible at the plan stage.

**3 · The thesis · Maria**

A space is a conversation between your senses, and the single overall score is the least interesting part of it. Three ideas carry the work, and we prove each one where it shows up. Personal: your senses, your weights. Honest: no averaging. And coupled: the senses ripple on each other.

**4 · How it's built · Maria**

One quick look under the hood. Everything you type is one turn. A small, fast model reads that turn and routes it, to the right kind of work. There are three: understanding a plan, editing a plan, which is where the agent and the ripple live, and seeing a plan a new way. In this loop, the system answers, then grades its own answer once to make sure of accurate results.

**5 · The models · Maria**

What powers it is three Gemini models, and the whole choice was cost against reasoning. A cheap, fast model does the routing, the quick decisions. A smarter, pricier model does the reasoning you actually read, where quality is worth paying for. And a native image model paints the rooms at the end.

**6 · Act 1 / Onboard · Maria**

Act one. Onboarding. This is where you tell Sensi who you are, and it builds a sensory persona from your answers. Rather than describe it, let's watch.

**7 · DEMO 1 / Onboard · Emilie (recorded)**

[ clip plays · see `demo-scripts-week09.md` ]

**8 · It's personal · Charles**

The quiz and the moodboard, all of it becomes numbers. Every answer nudges a weight, one per sense, and weights only ever go up. Say plants are non-negotiable, your smell weight climbs. Say noise really gets to you, acoustic jumps. Each weight then sets that sense's alert threshold, the bar where Sensi flags a problem. The rule is intuitive: the more you care about a sense, the higher its bar, so Sensi flags it sooner for you than for someone who doesn't care.

**9 · Act 2 / Shape · Charles**

Act two is the heart of the tool. Shape. We read a real CAD plan, score all six senses on it, and surface the conflicts you'd never catch by eye. Then we edit, and watch it ripple.

**10 · DEMO 2 / Shape · Emilie (recorded)**

[ clip plays · see `demo-scripts-week09.md` ]

**11 · How a room is scored · Charles**

Let us take an example to look at the math. Every sense runs zero to one, where one is ideal comfort. Each starts at a baseline for the room type, a kitchen starts middling on sound, low on smell, that's just what kitchens are. Then the real geometry moves each number. Which way the room faces, how much glass, whether there's ventilation, what the surfaces are. Every one of those moves is grounded research and physics.

**12 · The ripple, then the veto · Charles**

This is the core of the whole project. First, the ripple. A failing sense doesn't stay in its lane. That weak sound score reaches over and drags down its neighbors, a little off thermal, a little off visual, because a loud room genuinely feels worse in other ways too. And every one of those nudges is labelled with its reason, building science or physics. Then the honest part. To combine six senses into one number, we do not average them. Instead the worst sense gets a veto. The overall is half the weighted average, and half the single worst sense. A great room with one unbearable sense is still an unbearable room.

**13 · The reasoning, measured · Charles**

Because reasoning models can be slow and pricey. We measured every node in one full session. The fast routing models stay under a second and basically free. All the time and cost live in the smart tier, the reasoning you read.

**14 · Act 3 / Report · Charles**

Act three. The Report. This is where the loop closes, where the output finally answers the input you gave at the very start.

**15 · DEMO 3 / Report · Emilie (recorded)**

[ clip plays · see `demo-scripts-week09.md` ]

**16 · Scores → prompt → image · Lakzhmy**

A room's six scores become a text prompt by a fixed rule, no model improvising. And the rule is: only the extreme senses get to speak. Clearly bad, below 0.45, or clearly good, above 0.70, writes a phrase. This kitchen's prompt says stuffy, closed air, hard reflective surfaces, a cool bluish light, and a generous open volume. Those are its real scores, in words. And the before-and-after is the same trick in reverse. The after is the room's true render. The before is that exact image, edited by one short what-changed clause, so the scene holds still and only the change moves.

**17 · The renders, judged blind · Lakzhmy**

We tested, same prompts, Google against OpenAI, head to head. Google came back about three times faster, a touch cheaper, and cleaner, more like real architectural daylight, so that's the engine we ship. The renders are the scores, made visible.

**18 · Grounded · Lakzhmy**

The obvious challenge is: did you just invent these couplings? Every coupling comes from peer-reviewed building science or standard room physics. Where the evidence is real but thin, we encode only the direction, a plus or a minus, never a fake-precise number. We can look at the matrix, to understand better. Each row is a sense. Read across the row and you see what that sense does to the others. Plus helps a neighbor, minus harms one, plus-or-minus means it depends. Solid cells are research-verified, dashed cells are standard physics. Another detail lies in Acoustic and visual. Noise harms visual focus, that's a minus. But the mirror cell is just a dot, empty, because light does nothing to how loud a room feels. That coupling runs one way only. One honest limit: we ground these rules in research, we haven't validated them against a comfort dataset.

**19 · The close · Lakzhmy**

The score was never the point. The ripple was. Sensi makes the coupling between the senses something you can design with, at the plan stage. A feedback loop for how a building will feel, before the building exists.

**20 · What this raises · Lakzhmy**

We also want to bring forward some questions. When a household disagrees, whose senses win, and who gets to set the weights? And how far should the agent go, surface the trade-off, or make the call for you? But the one underneath all of them is this: a felt-experience score, is it actually accountable, or is it just persuasive? We don't think that's settled. We think it's the interesting part.

**21 · Thanks · Lakzhmy**

That's Sensi. Thank you.
