# Editing, Checkpoints & Interactive Answers

This session reshaped the spine of how a conversation turn becomes an applied edit
becomes a committed milestone — and made the assistant's answers a navigable index into
the canvas. Three connected capabilities, plus the Report repoint they imply.

> Sensi does **not** use MCP — the comfort tools run in-process via `LocalToolClient`.
> The `mcp_client` / `call_tool` names are legacy. Image generation is a separate HTTP API.

---

## 1. Multi-edit (one prompt → several edits → one re-score)

Edits used to be three near-identical graph nodes (`change_material` / `modify_glazing` /
`add_furniture`), each handling one change. They were collapsed into **one path**:

```
action_classifier → "edit"          (single coarse action)
  → edit_planner   [LLM, SMART]      decompose the prompt into an ops list
  → apply_edits    [deterministic]   apply every op via the pure _edits mutators
  → analyze (ONE re-score) → compare_versions → score_interpreter → respond
```

- **`nodes/editing/edit_planner.py`** — LLM segments "add 2 plants and change the glazing"
  into `[{op:add_furniture,...}, {op:modify_glazing,...}]`; keyword fallback if the LLM fails.
  It only *segments* — it never invents canonical values.
- **`nodes/editing/apply_edits.py`** — the **single mutation chokepoint**: loops the ops,
  resolving every value against the real layout via `_edits` helpers (so the LLM can't
  introduce an invalid material or a nonexistent room), accumulates a `layout_diffs` list,
  and snapshots the pre-edit baseline once. One re-score downstream, not one per op.
- Frontend carries `layout_diffs` (array); `MaterialLayer` glows every changed room.

See the flow in [`python/sensi_graph.mermaid`](../../python/sensi_graph.mermaid).

---

## 2. Checkpoints (live working draft → committed milestones)

A git-like model, implemented as an **API layer on top of the session** —
`apply_edits` and the graph are untouched.

- Editing is **live**: edits mutate a working draft (`layout_json_string`) the canvas shows
  in real time. The bottom strip ("Checkpoints", formerly the timeline) shows only milestones
  the user explicitly **commits**.
- A **commit** snapshots the cumulative working state since the last checkpoint
  (before = last checkpoint, after = now). **Checkpoint 0 = the initial loaded layout.**
- **Restore** rolls the working draft back to a checkpoint; **view** (clicking a chip) shows
  that milestone's scores read-only with a "back to current" banner.

**`python/api/checkpoints.py`** owns the state (`checkpoints[]`, `committed_layout_json`,
`committed_scores_json`, `pending_diffs`) with `sync` / `commit` / `restore` / `view` /
`has_uncommitted` / `uncommitted_delta` / `summaries`. Routes: `/api/commit`, `/api/restore`,
`/api/checkpoint` (view). Every `/api/message` calls `checkpoints.sync` after `run_agent`.

Two gotchas that bit us (fixed): compare layouts **canonically** (the on-disk file is
pretty-printed, the working layout is compact — raw-string compares give false positives);
and `run_agent` must start `updated_session` from `{**session, ...}` so the API-layer
checkpoint keys survive the round-trip (otherwise they're dropped every turn).

**The Report/Vision renders the COMMITTED state** — after = latest checkpoint, before =
checkpoint 0. So `/api/report`, `/api/render-room`, `/api/compare-initial` read
`checkpoints.vision_layout/_scores`, not the uncommitted draft. (Details:
[`reference/report-vision-pipeline.md`](../reference/report-vision-pipeline.md).)

---

## 3. Interactive answers (the reply as a guide into the canvas)

Grounded in HCI research (brushing-and-linking, deixis, Strobelt's text-highlighting cue
rules): the chat answer is a **navigable index**, not a dashboard. It *points*, it doesn't
re-chart the data.

- **`web/src/ui/InteractiveMessage.jsx`** deterministically linkifies a CLOSED vocabulary
  (room names + the 6 senses + 0-1 scores) into spans wired to the shared `useSelection`
  bus — no LLM markup contract, no hallucinated UI.
- **Bidirectional**: hover a room/sense word → the orb/lens lights on the plan, and hovering
  the plan back marks the word. (`selection.jsx` gained `hoverRoom`/`focusRoom`; `RoomsLayer`
  uses `focusRoom`.)
- **Three non-interfering cue channels** (no stacking): rooms = underline + halo;
  senses = their spectral glyph in the sense hue; scores = pass/warn/fail tint.

**Prompt side** (what makes the linker reliable): a shared `nodes/_shared/register.py`
(one architect/client/learner voice + truthful CAPABILITIES); `respond` / `detail_respond`
name rooms/senses by their EXACT canonical names and *point, don't dump*; `chitchat` no
longer claims it can't render images (The Vision does) and is the graceful fallback;
`what_next` teaches the new workflow (commit a checkpoint, open The Vision).

---

## 4. Edit-feedback accuracy (post-testing fixes)

After live testing, the edit feedback was made trustworthy:
- `respond` had been **inventing** edit scores (e.g. "olfactory 1.00→1.35", impossible).
  `compare_versions` now emits absolute `before->after` per sense, and `_FORMAT_EDIT` copies
  those exactly — only senses that changed, nothing above 1.0.
- After an edit the panel now focuses the **edited** room (not the worst); changed rings
  briefly **pulse**; checkpoint auto-labels are **≤2 words** ("Plants" / "Glazing" / "3 edits").

The engine always accumulated edits + re-scored correctly — these were display/trust fixes.

---

## Run / preview recipe

Backend (from `team_02/python/`): `uvicorn api.server:app --port 8000` with
`PYTHONIOENCODING=utf-8`. Frontend: `npm run dev` in `team_02/web` (Vite :5173 proxies
`/api` → :8000). A returning-user persona at `team_02/personas/persona.json` boots straight
to chat. **Do not use `uvicorn --reload`** here — the OneDrive path breaks its file-watcher
(it silently runs stale code), so restart manually after backend edits.
