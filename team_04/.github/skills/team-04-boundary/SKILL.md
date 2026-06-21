---
name: team-04-boundary
description: "Use when working in team_04, Team 04 TerraPilot, or tasks that must stay inside this folder. Keeps edits inside team_04, preserves Team 04 coordination files and runtime settings, and requires asking the user before touching anything else."
user-invocable: true
---

# Team 04 Boundary And Contract

Use this skill to keep Team 04 work contained inside this folder and preserve the files that let Team 04 coordinate with the rest of the multi-agent workspace.

## Rules

1. Only create, edit, move, or delete files under `team_04/`.
2. Treat every path outside `team_04/` as out of scope unless the user explicitly overrides that rule.
3. If a requested fix appears to require another folder, a shared module, or a workspace-level config change, stop and ask first.
4. Keep temporary notes, generated artifacts, and prototypes inside `team_04/`.

## Coordination Contract

Keep these top-level files consistent because they serve different coordination roles:

1. `agent.md` is the concise public description of what Team 04 does, how to invoke it, and which outputs it owns.
2. `AGENTS.md` is the coding-agent boundary and local working policy file.
3. `ARCHITECTURE.md` is the canonical design and graph description for the active runtime.
4. `QUICK_START.md` is the setup, run, and validation guide for operators.
5. `TOOLS_CHECKLIST.md` is the active Python-tool backlog and should reflect the current local tool surface.
6. `PROGRESS.md` is the active status log, completed work record, validation history, and deferred-work list.
7. `mcp.example.json` is the Team 04 fallback MCP configuration when no repo-level `mcp.json` exists.
8. `.env.example` documents the Team 04-local runtime settings that can be copied to `.env` when a repo-level `.env` is absent.
9. `main.py` and `agent/main.py` remain the top-level and canonical runtime entry points.

## Runtime Settings

1. The canonical runtime loads the repository root `.env` first and falls back to `team_04/.env`.
2. The canonical runtime loads repository root `mcp.json` first and falls back to `team_04/mcp.example.json`.
3. Provider-specific environment variables must match the provider selected by `LLM_PROVIDER`.
4. Team 04-specific benchmarking overrides use `TEAM04_DECISION_LLM_PROVIDER`, `TEAM04_DECISION_LLM_MODEL`, `TEAM04_REPORT_LLM_PROVIDER`, and `TEAM04_REPORT_LLM_MODEL`.
5. Local reorganizations should preserve `agent/` as the active implementation and keep `legacy/` archived rather than mixing active code across both trees.

## Fresh Start Organization

1. The active implementation focus is the local Python tool surface in `agent/tools/`.
2. Active notebook harnesses and notebook-generated artifacts should live in `notebooks/`.
3. Current Python-tool guidance should live in `QUICK_START.md` and `TOOLS_CHECKLIST.md`, not in archived planning docs.
4. Redundant prototypes, stale plans, duplicate runtime trees, and archived examples belong in `legacy/fresh_start_2026-06-03/` or a later dated archive folder.
5. Avoid recreating a second active top-level runtime tree beside `agent/`.

## Start-Of-Task Checklist

1. Confirm the target file or requested output is under `team_04/`.
2. Confirm whether the task touches one of the coordination files or runtime settings listed above.
3. Restate the boundary if the user request is broad or ambiguous.
4. If the requested work conflicts with this boundary, ask for approval before continuing.

## Examples

- Safe: edit `team_04/agent/graph.py`
- Safe: edit `team_04/agent/tools/generate_building_boundary.py`
- Safe: move active Team 04 notebooks into `team_04/notebooks/`
- Safe: add a new test under `team_04/tests/`
- Safe: update `team_04/agent.md` when the public Team 04 contract changes
- Safe: update `team_04/.env.example` when the canonical runtime gains a new required setting
- Safe: archive stale Team 04 planning files into `team_04/legacy/fresh_start_2026-06-03/`
- Stop and ask: edit the workspace `README.md`
- Stop and ask: modify another team's folder

This skill is local to the Team 04 folder in this checkout. It does not change behavior for the rest of the workspace.