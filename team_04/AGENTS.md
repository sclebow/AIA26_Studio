# Team 04 Agent Boundary

This directory is a strict work boundary for Team 04's subagent work.

## Scope

- Only create, edit, move, or delete files under `team_04/`.
- Treat files and folders outside `team_04/` as out of scope unless the user explicitly expands the boundary in the current chat.
- If a task appears to require root-level config, shared modules, or another team's folder, stop and ask before making that change.

## Working Rules

- Keep generated artifacts, scratch files, notes, and experiments inside `team_04/`.
- References to code outside `team_04/` are allowed for context, but edits outside `team_04/` are not.
- Prefer solutions that stay self-contained within this directory.
- Keep active notebook harnesses and notebook-generated artifacts under `team_04/notebooks/` rather than at the top level.

## Coordination Files

- Preserve `agent.md` as the concise public contract for Team 04.
- Preserve `ARCHITECTURE.md` as the canonical runtime and graph description.
- Preserve `QUICK_START.md` as the operator setup and validation guide.
- Preserve `TOOLS_CHECKLIST.md` as the active Python-tool backlog.
- Preserve `PROGRESS.md` as the active status and deferred-work log.
- Preserve `mcp.example.json` as the Team 04 fallback MCP config.
- Preserve `.env.example` as the Team 04-local runtime settings template.
- Preserve `main.py` and `agent/main.py` as the top-level and canonical entry points.
- Treat `agent/` as the active implementation and `legacy/` as archived history unless the user explicitly asks to revive legacy code.

## Fresh Start Focus

- Prefer active implementation work in `agent/tools/`, `agent/`, `notebooks/`, `tests/`, and the current notebook harnesses.
- Treat `legacy/fresh_start_2026-06-03/` as the archive location for redundant prototypes, stale planning docs, duplicate runtime trees, and archived example folders.
- Do not leave a second live-looking top-level runtime tree beside `agent/`.

## Local Skill

- A matching local skill lives at `.github/skills/team-04-boundary/SKILL.md`.
- Use it when you want an explicit reminder of this boundary during planning or execution.