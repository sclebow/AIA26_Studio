# Team 04 Python Tool Checklist

This checklist tracks the active Python-first work for Team 04.

Older Grasshopper-first planning checklists were archived under `legacy/fresh_start_2026-06-03/docs/`.

## Active Local Tools

### `generate_building_boundary`
- [x] Supports `I`, `L`, `T`, `Y`, `H`, `X`, and `O` footprints.
- [x] Returns closed boundary coordinates and summary metrics.
- [x] Accepts orientation, rotation, mirroring, and translation inputs.
- [ ] Tighten invalid-input validation and error messages.
- [ ] Add more regression cases for extreme aspect ratios and tiny footprints.

### `modify_building_boundary`
- [x] Supports centroid move and relative translation.
- [x] Supports orientation, rotation, and mirroring.
- [x] Reports whether the transformed boundary still fits inside the site.
- [ ] Add more edge-case tests for concave sites and boundary-touching cases.
- [ ] Decide whether site-fit classification should become stricter for edge contact.

### `direction_to_site_centroid`
- [x] Computes orientation guidance from a requested point toward the site centroid.
- [ ] Add direct tests for degenerate or already-centered requests.

### Multi-Building Local Mocks
- [x] `import_building_boundary` mock is registered locally.
- [x] `remaining_buildable_positions` mock is registered locally.
- [x] `requested_position_checker` mock is registered locally.
- [ ] Clarify the boundary between mock behavior and production-ready Python behavior.
- [ ] Decide which mock flows should become real local tools before MCP parity work continues.

## Runtime Integration

- [x] Local tool definitions are exported from `agent/tools/__init__.py`.
- [x] Local tool handlers are registered in `agent/mcp_client.py`.
- [x] Canonical runtime entry stays at `main.py` -> `agent/main.py`.
- [ ] Keep `QUICK_START.md` aligned whenever the active local tool surface changes.
- [ ] Add one test that asserts the full default local tool registry matches the intended Python-tool surface.

## Python-First Next Steps

- [ ] Add schema or payload normalization helpers shared across local tools.
- [ ] Add a dedicated test module for malformed tool inputs.
- [ ] Decide whether to split geometry utilities out of the tool modules for reuse.
- [ ] Add one notebook or CLI example per active local tool so each tool has a minimal demo path.

## Deferred Bridge Work

- [ ] Replace the local placement-analysis mocks with either production Python tools or live Swiftlet equivalents.
- [ ] Finish `import_building_boundary_04` on the Grasshopper side.
- [ ] Finish `remaining_buildable_positions_04` on the Grasshopper side.
- [ ] Finish `requested_position_checker_04` on the Grasshopper side.
- [ ] Finish `modify_building_boundary_04` on the Grasshopper side.