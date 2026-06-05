# Sensi — Week 07 presentation script (standalone)

Conversational + honest, technical terms intact. **~3:30 total** at a natural pace
(cap 3.5 min). This is a **standalone deck** — the live demo runs *after* slide 12.
Slides 1–7 = the *why*; slides 8–11 = a quick tour of the **new UI + backend features**
in each screenshot; slide 12 = what's next, then hand to the demo.

---

**1 · Title** *(~17s)*
> Hi — this is Sensi. It reads an architectural layout and tells you how it's going to
> *feel*, not just look, across six senses. And it all comes back to one line: the
> number isn't the lesson — the edges are. Let me show you what that means.

**2 · Philosophy** *(~26s)*
> A space is really a conversation between your senses. Soften a wall and the room goes
> quiet; open a window and the air feels fresh — but now it's louder. Every change
> ripples from one sense into another — and *that ripple* is the lesson, far more than
> any single comfort score. So Sensi reads a plan, scores six senses against *your*
> profile, finds the conflicts, and shows you the ripple.

**3 · The maths — it's personal** *(~23s)*
> Under the hood it's real maths, grounded in research — three ideas. First, it's
> personal. A calm introvert and a high-energy extrovert want opposite things from the
> same room. So your onboarding becomes a set of weights, and those weights decide, for
> *you*, how good is good enough before we flag a sense.

**4 · The honest number** *(~23s)*
> Second — and this one matters — we don't average the senses. A room that's perfect in
> five and unbearable in one isn't "eighty-three percent comfortable," it's unbearable.
> So the score leans on the *worst* sense — a one-vote veto. You can't paper over a bad
> sense by being great elsewhere, and that's what keeps it honest.

**5 · The ripple** *(~23s)*
> Third, the ripple itself — the heart of it. When one sense changes, we nudge its
> coupled partners: soft surfaces absorb sound, so a cozier floor literally makes a room
> quieter; a stuffy room feels warmer than it actually is. And every nudge is labelled
> with *why* — research or physics. That's a change to one sense rippling to another.

**6 · Grounded** *(~17s)*
> And honestly, on the rigor — none of this is invented. The couplings come from
> peer-reviewed building science. We ran every claim through an adversarial fact-check,
> kept eighteen of twenty-five, and threw the rest out.

**7 · Architecture** *(~20s)*
> A quick note on the build, because it changed a lot: we moved off the old
> PyQt-and-Grasshopper desktop setup entirely. It's now a FastAPI backend, a React
> frontend, the comfort tools running in-process — no Rhino — and a LangGraph agent.
> Bottom line, it runs anywhere, in a browser.

**8 · The workspace** *(~13s · features)*
> Here's what we built it into. The workspace: chat on the left, the full canvas, a
> layer rail, and a docked sense-couplings key. You pick a layout — or upload your own
> JSON — and the backend now loads and scores it *in-process*: no Rhino, no Grasshopper.

**9 · Scores + the rose** *(~14s · features)*
> Analyze, and every room gets a comfort ring plus a FocusCard — the six-petal "rose,"
> each sense's base-versus-effective with a provenance icon, the conflicts, and one-click
> what-ifs. That's the new in-process comfort engine scoring all six senses for *you*.

**10 · Topology** *(~12s · features)*
> The graph lens turns the same data into a topology — rooms sized by how connected they
> are, arcs showing a sense bleeding between them. That's a new NetworkX pass on the
> backend: degree, bridges, betweenness.

**11 · The relationship galaxy** *(~15s · features)*
> And the relationship galaxy — the whole system in 3D, lazy-loaded so it's free until
> you open it. New here: meaning lenses instead of complexity tiers, click any node to
> expand its sub-world, and a ripple you can actually animate across the network.

**12 · What's next** *(~13s)*
> Where we're headed: make those edges even more legible — more visual ripple, a more
> agentic loop, generative outputs. But that's the core of Sensi — and now, let me show
> you it live.

---

*Pacing: 1–7 is the argument — steady and warm. 8–11 is a quick feature tour — name what's
new (UI + backend) and keep moving. 12 hands off to the live demo.*
