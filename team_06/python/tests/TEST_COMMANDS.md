# Test Commands

This directory contains all unit and integration tests for the team_06 agent workflow.

## Setup

All tests should be run from the `/tests/` directory:
```bash
cd team_06/python/tests
```

## Available Tests

### 1. GraphSearcher Tests
Comprehensive validation of graph search functionality across 4 test categories.

```bash
python test_graph_searcher.py
```

**What it tests:**
- Presence queries (rooms exist anywhere)
- Connectivity queries (rooms connected via doors)
- Similarity metrics (Jaccard vs Overlap)
- Real-world query examples

---

### 2. Agent Workflow Tests
Full agent workflow test without real LLM - uses MockLLM to simulate reasoning while executing real tools.

**Run custom prompt:**
```bash
python test_workflow.py "filter layout-3 and delete kitchen"
```

**Run predefined test suite (4 tests):**
```bash
python test_workflow.py --test all
```

**Supported natural language patterns:**
- Search layouts: `"find layouts with 1 bedroom and 2 bathrooms"`
- Filter layout: `"filter layout-2"`
- Chained commands: `"filter layout-3 and delete kitchen"`
- Delete room: `"delete kitchen"`
- Add window: `"add window 1.0 m width to the living"`
- Graph search: `"find layout with bedroom and kitchen connected"`

**Output:**
- Session state: `test_results/test_session_state.json` (persists layout_id across runs)
- Execution log: `test_results/test_execution_log.jsonl`
- Edited layout: `test_results/team_06_edited_layout.json` (if MCP server available)

**Features:**
- State persistence across multiple invocations (loads/saves session file)
- Real tool execution (layout_filter, graph search)
- MCP server integration (delete_room_06, add_window_06) with 5-second timeout
- Graceful fallback if MCP server unavailable

---

### 3. Embedding Matcher Tests
Validation of embedding-based layout matching.

```bash
python test_embedding_matcher.py
```

---

## Integration with MCP Server

To test MCP tool execution (delete_room_06, add_window_06):

1. **Start MCP server** (if available):
   ```bash
   # Start server at http://localhost:3001/mcp/
   python -m server  # or your MCP server start command
   ```

2. **Run workflow tests** - they will auto-detect and use the server

**Without MCP server:**
- Tests run gracefully with "would do X" fallback messages
- Session state and local tools still work
- MCP tools timeout after 5 seconds with graceful messages

---

## Test Results Location

After running `test_workflow.py`, results are saved to:
```
tests/
└── test_results/
    ├── test_session_state.json        # Session persistence (layout_id)
    ├── test_execution_log.jsonl       # Detailed execution log (JSONL format)
    └── team_06_edited_layout.json     # Edited layout snapshot (if MCP executed)
```

---

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python test_graph_searcher.py` | Validate graph search across all scenarios |
| `python test_workflow.py --test all` | Run 4 predefined workflow tests |
| `python test_workflow.py "your prompt"` | Test custom natural language prompt |
| `python test_embedding_matcher.py` | Test embedding-based matching |

