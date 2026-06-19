# Week 09 — Narrative notes

Plain bullets capturing what changed and why it matters to the story. The final
a-to-z deck assembles from these.

## Session 1 — Agentic loop audit & streaming

- **The agent now thinks out loud.** Before, a turn ran the whole LangGraph pipeline
  silently and dumped one block of text after 10-20s — the UI was frozen the entire
  time. We added a streaming endpoint (`/api/message/stream`, SSE) that reports each
  step as it happens ("Scoring the rooms", "Detecting conflicts", "Writing the
  summary") and then streams the final answer in. Time-to-first-feedback dropped from
  "nothing until the turn ends" to **~3s** (first progress label). Why it matters: the
  product finally *feels* like a live collaborator instead of a slow form submit.

- **Edits no longer answer with stale facts.** We found a real correctness bug: after
  you edit the layout, the old conflict/suggestion analysis was silently kept and a
  follow-up question ("why does the Kitchen have conflicts?") answered from data
  computed on the *pre-edit* layout. Now a re-scoring turn properly invalidates the
  derived analysis, and such a follow-up automatically re-detects on the *current*
  layout. Why it matters: the agent's reliability — when it speaks, it's about the
  layout in front of you, not a ghost of an earlier one.

- **Less wasted work per turn.** The LangGraph was being recompiled from scratch on
  every single message (~25 nodes, ~53ms each turn); now it's built once and reused.
  Streaming, cancellation (a Stop button), and graceful error handling were added with
  **zero change to the API contract** — the non-streaming endpoint still returns the
  exact same payload, so nothing downstream regressed.
