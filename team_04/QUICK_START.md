# Team 04 Quick Start

Team 04 now treats `agent/` as the only active runtime and `agent/tools/` as the main development surface.

Active notebook harnesses now live under `notebooks/`, and redundant example folders were archived under `legacy/fresh_start_2026-06-03/reference_examples/` so the top level stays focused on the current LangGraph agent and its local Python tools.

Use `test_notebooks/` for the new split between deterministic tool-development notebooks and live-LLM end-to-end notebook runs.

## Active Paths

- `agent/`: canonical LangGraph runtime.
- `agent/tools/`: active local Python tool surface.
- `notebooks/`: active notebook harnesses and notebook-generated artifacts.
- `test_notebooks/`: purpose-built notebook entry points for dev-mode tool checks and end-to-end API-driven agent runs.
- `tests/`: focused automated coverage for the active runtime and tool helpers.
- `gh/`: secondary integration surface for MCP and Grasshopper handoff, not the primary development path.

## 1. Environment Setup

1. From the repository root, install Python dependencies:
   ```bash
  python -m pip install -r team_04/requirements.txt
   ```
2. If the repository root does not already have a `.env`, copy `team_04/.env.example` to `team_04/.env` and fill in the provider you want to use.
3. If you are using live MCP integration, review `team_04/mcp.example.json`. The runtime loads repo-root `mcp.json` first and falls back to this file.

## 2. Run The Canonical Agent

From the `team_04/` folder:

```bash
python main.py "Place a U-shaped building of 900 square meters inside the site boundary"
```

The runtime writes its current result payload to `team_04_placement_result.json`.

Optional benchmarking overrides:

```bash
python main.py "Generate a compact residential boundary near the site centroid" \
  --decision-provider cloudflare \
  --decision-model @cf/meta/llama-3.1-8b-instruct \
  --report-provider openai \
  --report-model gpt-4.1-mini
```

## 3. Work On Local Python Tools

When you add or change a local Python tool:

1. Edit or add the implementation under `agent/tools/`.
2. Export the tool definition and handler from `agent/tools/__init__.py`.
3. Register the tool in `build_default_local_tool_client()` in `agent/mcp_client.py`.
4. Add or update tests under `tests/`.
5. Add or refresh a notebook harness under `notebooks/` when the tool benefits from an end-to-end demo.

## 4. Current Local Tool Surface

- `generate_building_boundary`: create graph-backed `I`, `L`, `T`, `U`, `Y`, `H`, `X`, and `O` footprints with stable wing indices, TopologicPy geometry payloads, and optional GA placement inside a supplied `site_boundary`.
- `modify_building_boundary`: transform an existing footprint and classify whether it still fits inside the site.
- `direction_to_site_centroid`: derive an orientation hint from a requested building point toward the site centroid.
- `import_building_boundary`: local mock for placement import while the live Grasshopper tool is incomplete.
- `remaining_buildable_positions`: local mock for multi-building remaining-site analysis.
- `requested_position_checker`: local mock for requested-point feasibility checks.

## 5. Notebook Harnesses

- `notebooks/agent_graph_visualization.ipynb`
- `notebooks/test_generate_building_boundary.ipynb`
- `notebooks/test_two_building_workflow.ipynb`
- `notebooks/test_multi_building_shape_transformations.ipynb`
- `test_notebooks/tool_dev_mode.ipynb`: deterministic local tool-development notebook for graph-backed generation, placement, and transform checks.
- `test_notebooks/end_to_end_api_agent.ipynb`: planner plus supervisor plus live-LLM notebook using notebook-local site and evaluation tools instead of a live MCP server.
- `tests/test_context_reader_live.ipynb` for live MCP and provider checks

Keep notebook-generated artifacts beside the notebooks in `notebooks/`, not at the Team 04 top level.

## 6. Focused Validation

Run the active Team 04 Python-tool slice from the repository root:

```bash
python -m unittest team_04.tests.test_boundary_tools team_04.tests.test_agent_graph team_04.tests.test_benchmark_logger
```

If the current interpreter is missing `langgraph`, `langchain-openai`, or `pymoo`, install `team_04/requirements.txt` into that interpreter first.

## 7. What Stays Archived

- Live Swiftlet and Grasshopper bridge completion remains important, but it is no longer the primary top-level workflow.
- Keep MCP or Grasshopper bridge work in `gh/`, `test_gh/`, and the active docs only when it directly supports the canonical `agent/` runtime.
- Keep archived examples like `JSON_Tools_Example/` and `llm_call/` under `legacy/fresh_start_2026-06-03/reference_examples/` instead of restoring them to the top level unless there is a concrete need.
