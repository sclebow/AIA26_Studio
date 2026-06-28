# Sensi — Flow audit (Onboard → Shape → Report)

**Session 6 deliverable.** Maps the whole journey end-to-end as **INPUT** (what we ask
of the user) vs **OUTPUT** (what we hand back), names the friction, and scopes the
fixes — split into *this session* and *session E (report + moodboard)*. Code
references are `file:line` into `team_02/`.

> Method note: this was traced from the running app **and** the code (onboarding nodes
> `python/nodes/onboarding/*`, the comfort engine `python/comfort/*`, the layout-mode
> nodes `python/nodes/{scoring,conversation,quality,insights,editing}/*`, and the
> frontend screens `web/src/screens/*` + `web/src/App.jsx`).

---

## 1. The journey at a glance

| Act | Screen / node | INPUT (user effort) | OUTPUT (what they get back) |
|---|---|---|---|
| **1 Onboard** | `App.init` → `greet.py` | — | "Hi, I'm Sensi — who are you?" |
| | `QuizScreen` step 0 / `quiz.py` | type name | "Nice to meet you, {name}!" + Q1 |
| | step 1 | pick role (3 pills) | role ACK + Q2 |
| | step 2 | free-text space story | **LLM** warm ACK + Q3 |
| | step 3 | toggle senses (≥1) + done | sense ACK + Q4 |
| | step 4 | life stage **and** living (2 pickers) + continue | life ACK + Q5 |
| | step 5 | free-text non-negotiable | anchor ACK + Q6 |
| | step 6 | pick energy (3 pills) | "let's build your sensory world" |
| | `InspireScreen` "question" / `inspire.py` | free-text aesthetic + optional ≤5 images | image grid |
| | "grid" | **3 mandatory rounds** × (pick ≥1 + continue) | next grid → moodboard |
| | "moodboard" | "this is it" (or "keep picking") | persona compiles (**~2–3s LLM**) |
| | `PersonaScreen` | scroll ~2000px; "this is me" / "tweak it" | full persona dump |
| | `ProfileChatScreen` *(optional)* | ask Qs; "profile looks good" | read-only Q&A — **changes nothing** |
| **2 Shape** | `LayoutModeScreen` | chat + canvas | comfort scores, conflicts, edits, report CTA |
| **3 Report** | `ReportScreen` | open; expand rooms; export | per-room renders + narrative |

**~15 discrete interactions** stand between launch and the persona, the heaviest being
the 3-round image loop. The persona is compiled in `persona_compiler.py` (one SMART
LLM call + deterministic patches), persisted to `personas/persona.json`, and returned
on every turn — so it is **fully re-fetchable**; the frontend simply doesn't resurface
it after the reveal.

---

## 2. Gap 1 — Math honesty (the reveal lies about how comfort is scored)

The persona reveal teaches the user a formula (`PersonaScreen.jsx:95–143`):

```
w(s)           = derive(quiz, inspire)
score(room, s) = w(s) × raw(room, s)
C(room)        = Σ score(room, s)
flag(s)        = |w(s) − baseline(s)| > 0.25
```

**The real engine does none of this** (`comfort/sense_model.py`,
`comfort/compute_comfort_scores.py`):

| Claimed in reveal | What the code actually does | Where |
|---|---|---|
| `score(room,s) = w(s) × raw` | Per-sense score is **objective**: `baseline(roomType) ± design levers ± cross-modal ± personality`, clamped [0,1]. Weights never multiply a per-sense score. | `compute_comfort_scores.py:124–238`; comment at `:228` |
| `C(room) = Σ score` | **Non-additive veto blend:** `C = (1−V)·(Σ w·eff / Σ w) + V·min(eff)`, `V = VETO_WEIGHT = 0.5`. A sum would exceed 1.0; the UI shows 0–1. | `sense_model.py:79, 215–230` |
| `w(s)` as a multiplier | Weights are **aggregation coefficients only**, applied once at the end. | `compute_comfort_scores.py:239`; `sense_model.py:226–228` |
| (no cross-modal shown) | `apply_cross_modal` nudges coupled senses (failing senses drag partners down; strong senses lift "+" partners, capped). | `sense_model.py:108–149` |
| (no personality shown) | `apply_personality` (K=0.15) shifts acoustic/visual/spatial by the introvert↔extrovert axis. | `sense_model.py:163–187` |
| `flag = |w−baseline| > 0.25` | The 0.25 rule is an **onboarding-display** concept (`preference_vs_baseline`). Layout-mode conflict detection uses a **dynamic** `threshold_from_weight()` instead. | `persona_compiler.py:675–693`; `sense_model.py:190–204` |

**Why it matters:** the reveal is the one place we *teach the user the model*. Teaching
a fictional model — and one inconsistent with what they then watch happen in layout
mode — erodes trust in every score that follows. **Fix (this session):** rewrite the
reveal's math to the real model, sourced from the engine constants so they can't drift.

---

## 3. Gap 2 — Data fidelity (stated context doesn't reach layout mode)

The user's litmus test: *"if I mention a grandma or a pet, it should register and be
taken into account in layout mode."* Today it largely doesn't.

### Capture (onboarding → persona)
- **"grandma"** → `age_group = "elderly"`, `household_type = "dual"` via keyword
  patches (`persona_compiler.py` `_AGE_GROUP_KEYWORDS` / `_HOUSEHOLD_KEYWORDS`). ✅
- **"a dog / a cat / a pet"** → matches **no keyword**, no field, no note. ❌ Lost.
- `aesthetic_preferences`, `lifestyle`, `notes`, `preference_vs_baseline` are populated
  but, as shown below, consumed nowhere in layout mode.

### Propagation (persona → layout mode) — fragmented & lossy
Every layout-mode node hand-rolls its **own** `_format_persona` with a **different**
subset, and the scoring engine sees almost none of it:

| Consumer | Persona fields it actually uses | Drops |
|---|---|---|
| Scoring MCP (`analyze`/`detect`/`suggest`/`preview`) | `comfort_weights`, `personality` (name/role only as a *display label*, never a scoring input — `utils.py:47–56`) | age, household, pets, sensitivities, key-reqs, notes |
| `score_interpreter.py:67–92` | name, role, desc, age_group, household_type, priorities, sensitivities, key-reqs | weights(text), aesthetic, lifestyle, notes |
| `quality/respond.py` | name, role, desc, priorities, sensitivities, weights | age, household, key-reqs, aesthetic, lifestyle, notes |
| `conversation/detail_respond.py` | name, role, desc, priorities, sensitivities | age, household, key-reqs, … |
| `conversation/what_next.py` | name, role, desc | everything else |
| `suggestion_critic.py` | priorities, sensitivities, weights | name, role, age, household, key-reqs |
| `routing/action_classifier.py`, `conversation/chitchat.py` | **none** | all |

**Field-fate summary** — captured but **dropped before layout mode**:
`aesthetic_preferences`, `lifestyle`, `preference_vs_baseline`, `notes` (never used);
`age_group` / `household_type` (reach only `score_interpreter`, *after* scoring, never
the engine); **pets** (never captured at all).

**Why it matters:** the persona is the product's reason to exist, yet the richest human
facts evaporate between onboarding and the work. **Fix (this session, full depth):**
(a) capture pets/household members; (b) one **single source of truth** persona→prompt
formatter wired into every responder; (c) a labelled **context-modifier layer** in the
scoring engine so age/household/pets nudge the actual numbers — visible, capped,
re-validated against the demo layouts.

---

## 4. Gap 3 — Persona comparison is silently inert

`insights/persona_comparison.py` selects the contrast archetype from a
`persona_type` field (e.g. "Elderly 65+", "Young Active") that the **current**
`persona_compiler` never produces, so it always falls back to **"Neutral"**
(`persona_comparison.py:45–48`). The five archetypes are hardcoded labels handed to
the scoring tool, not stored personas. The "compare personas" action therefore never
reflects the real user. **Fix (this session):** re-derive the archetype from
`age_group`/`household_type`/`sensory_sensitivities`/`comfort_weights`.

---

## 5. Gap 4 — Reveal & recall friction

- **The reveal is a data dump.** `PersonaScreen` stacks identity + 3 priority cards +
  6 spectrum bars + gap cards + moodboard + a deep formula block (nested collapsible +
  a monospace weight/baseline/delta table) in one ~2000px scroll. Meaning competes
  with math; nothing is clearly the headline.
- **"tweak it" is a mislabeled dead-end.** It routes to `ProfileChatScreen`
  (`App.jsx:295`), a *second* reveal that only **explains** (read-only chat), can't
  actually tweak anything, and needs a second "profile looks good" to escape
  (`ProfileChatScreen.jsx:61`). The same Q&A already works in layout-mode chat.
- **The reveal vanishes on entering layout.** In `LayoutModeScreen`, the only persona
  surface is a tiny avatar-initial (`:202–204`) opening a cramped `ProfilePanel`
  (top-3 + 6 bars) whose **"full view" button is a no-op**
  (`onFullView={() => setProfileOpen(false)}`, `:314`). Moodboard, description, gaps,
  and the (now-honest) math are all unreachable while shaping.

**Fix (this session):** a shared `PersonaCard` used by both the reveal and an enriched
avatar→drawer; retire the ProfileChat loop; fix the no-op; make the avatar
discoverable.

---

## 6. Output-side gaps → scope for session E (report + moodboard)

Documented here so they scope the next session; **not fixed now**:

1. **No persona recap in the Report.** `ReportScreen` is rooms-first; it never says
   "here's why these rooms scored this way *for you*." The persona is used only for
   role-aware copy inside `RoomReportCard`.
2. **The moodboard/aesthetic signature is dropped after onboarding** — it never returns
   in Shape or Report. The aesthetic the user curated has no afterlife.
3. **No persona throughline across acts** — the persona is a gate at the front, not a
   companion that frames Shape and Report.
4. **Moodboard could be richer** — more images per round, and/or a single
   Gemini-generated final board (overlaps the report's image-gen).
5. **Image-gen latency (10–30s) has weak affordance** in the Report.

---

## 7. Prioritized fixes

**This session**
1. Rewrite the reveal's math to be true to `sense_model.py` (Gap 1).
2. Data fidelity, full depth — capture pets/household, single-source persona→prompt
   formatter, and a labelled context-modifier scoring layer + re-validation (Gap 2).
3. Fix persona comparison (Gap 3).
4. Clean, earned `PersonaCard` reveal, reachable via an enriched avatar drawer; retire
   the ProfileChat dead-end (Gap 4).

**Session E (report + moodboard)** — items in §6: persona recap + moodboard in the
Report, a persona throughline across acts, richer/generated moodboard, image-gen
affordance.

---

*Companion artifact: the build plan for this session lives in the session plan file;
narrative beats land in `docs/week09/narrative-notes.md`.*
