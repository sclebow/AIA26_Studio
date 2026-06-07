# TerraPilot Agent

## Description

TerraPilot is Team 04's site-planning and building-massing agent for early architectural workflows. The active implementation is a Python-first LangGraph runtime under `team_04/agent/` that generates graph-backed building footprints, can optimize placement inside a site boundary, and keeps Grasshopper or MCP integration as a downstream handoff rather than the primary development surface.

## Example Prompts

1. `python main.py "Place a U-shaped building of 900 square meters inside the site boundary"`
   - Generates a wing-indexed footprint, runs placement optimization when site geometry is available, and reports fit status.
2. `python main.py "Create an H-shaped building with a fixed area and keep it near the site centroid"`
   - Produces a graph-backed shape payload with stable wing indices for later edits.
3. `python main.py "Move the current building east, rotate it 90 degrees, and check whether it still fits"`
   - Uses Team 04 boundary-manipulation tools to transform the footprint and report fit or violation status.

## Coordination Contract

These files are the Team 04 coordination surface and should stay aligned:

- `agent.md`: concise public contract for people and agents comparing teams.
- `AGENTS.md`: folder-scoped coding-agent rules and boundary constraints.
- `ARCHITECTURE.md`: canonical design and graph structure for the active runtime.
- `QUICK_START.md`: setup, run, and validation workflow.
- `PROGRESS.md`: completed work, validation, and deferred tasks.
- `mcp.example.json`: Team 04 fallback MCP configuration.
- `.env.example`: Team 04-local runtime settings template.
- `main.py` and `agent/main.py`: top-level and canonical entry points.

## Runtime Settings

- The canonical runtime loads repository root `.env` first and falls back to `team_04/.env`.
- The canonical runtime loads repository root `mcp.json` first and falls back to `team_04/mcp.example.json`.
- Required provider settings depend on `LLM_PROVIDER`.
- Optional Team 04 benchmarking overrides are:
  - `TEAM04_DECISION_LLM_PROVIDER`
  - `TEAM04_DECISION_LLM_MODEL`
  - `TEAM04_REPORT_LLM_PROVIDER`
  - `TEAM04_REPORT_LLM_MODEL`

## Current Focus

- Active development now centers on the local Python tool surface in `agent/tools/`.
- `generate_building_boundary` now produces graph-backed wings plus TopologicPy-compatible geometry and fit summaries.
- Site-aware placement uses `pymoo` when `site_boundary` data is available.
- Active notebook harnesses now live under `notebooks/`.
- Old parallel runtime trees, prototype notebooks, and stale planning docs were archived under `legacy/fresh_start_2026-06-03/`.
- Grasshopper and MCP remain integration targets, but they are secondary to keeping the Python tool path clean and well tested.

## Active Implementation Layout

- `agent/`: canonical runtime.
- `agent/tools/`: current Python-tool implementation focus.
- `notebooks/`: active notebook harnesses and notebook-generated artifacts.
- `tests/`: focused automated tests for the canonical runtime and geometry helpers.
- `gh/`: Grasshopper definitions and tool specifications.
- `legacy/`: archived pre-rewrite implementations.

## Primary Output

- `team_04_placement_result.json`: latest emitted Team 04 result payload, including final response, shape context, placement summaries, and tool history.