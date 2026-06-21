# Week 08 — CLI for the Orchestrator (faculty notes)

**Status:** implemented & verified · **File changed:** `team_02/python/main.py` (only) · **Date:** 2026-06-05

This documents Team 02's implementation of the **CLI Requirements** (orchestrator subprocess
interface). It is written for faculty review — it covers what we built, how to call it, and the
**one place where we deliberately deviated from the spec** because of our architecture.

---

## What was required

The agent must be callable by the orchestrator as a subprocess: accept user instructions and an
optional layout JSON string, run the agent, and print the response plus the edited layout JSON in a
stable, machine-readable format.

## How to call it

```bash
# From team_02/python/  (Windows: set PYTHONIOENCODING=utf-8 first)
python main.py --prompt "add a window to the south wall of the living room" --layout_json '{ ...layout... }'
```

- `--prompt` (required to enter CLI mode) — the user instruction.
- `--layout_json` (optional) — a layout as a JSON string.
- **No flags → the existing interactive REPL** runs unchanged.

### Output contract (stdout)

```
Final Response:
<agent response>

Edited Layout JSON:
<edited layout JSON, or "No layout changes">
```

stdout carries **only** this block — all diagnostic logging is redirected to stderr so an
orchestrator can parse stdout directly. Invalid `--layout_json` prints a clear error to stderr and
exits with a non-zero code.

---

## ⚠️ Deviation from the spec (please note)

The provided instructions say to *"set `ctx.layout_data` to the parsed dict before calling
`run_agent(...)`"*. **This does not work for our architecture.** Our graph does **not** read
`ctx.layout_data`; layout flows through the `load_layout` node and is carried in the agent session
as `session["layout_json_string"]`.

**What we did instead:** we inject the orchestrator-provided layout into the **session**, and the
`load_layout` node's existing "skip if already loaded" guard honors it instead of reading a file
from `randomized_layouts/`. Result: the CLI uses the orchestrator's layout exactly as intended, and
**no changes to the graph or any node were needed.** (Verified: passing `Layout-101`, which does not
exist on disk, is used correctly — proving the injected layout wins.)

---

## Design decisions (team choices)

- **Interactive back-and-forth:** after the first `--prompt` turn, the process stays alive and reads
  follow-up lines from stdin, so the orchestrator (or a user) can answer clarifying questions and
  continue the conversation. `EOF` / `exit` ends the process. This satisfies the spec's
  "prompt the user for input… back-and-forth conversation" requirement.
- **Onboarding skipped in CLI mode:** a subprocess can't run greet/quiz/inspire. We load
  `personas/persona.json` if present (so scoring uses real comfort weights); otherwise neutral.
- **No disk pollution:** in CLI mode the analysis writer is redirected to a temp directory, so a
  throwaway orchestrator layout (e.g. `Layout-101`) never writes into `resulting_layout/`.
- **Windows note:** run with `PYTHONIOENCODING=utf-8` (terminal must be UTF-8, or the agent 500s on
  non-ASCII output).

## Verification performed

| Check | Result |
| --- | --- |
| PDF "add a window" sample (Layout-101) | edited layout returned |
| Injected layout honored (not disk fallback) | confirmed |
| stdout is a clean, parseable block | confirmed (diagnostics on stderr) |
| Analyze-only prompt | prints `No layout changes` |
| Invalid `--layout_json` | clear error + non-zero exit |
| No-flags REPL | unchanged, no regression |
| Ran end-to-end on Google Gemini provider | confirmed |
