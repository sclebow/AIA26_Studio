### ✅ COMPLETED

1. **Preprocessing command detection** - Detects: "end", "layout-X", "change boundary", "change rooms"
2. **Preprocessing keyword-based routing** - Routes to evaluate/parse based on layout + prompt keywords
3. **Choice node layout loading** - Loads layout when user provides "layout-ID"
4. **Feedback → END flow** - After evaluate, feedback asks "Satisfied?", preprocessing routes responses

---

### ⏳ IN PROGRESS / TODO

### 1. "change rooms" should trigger brief, not search
**File**: `python/nodes/preprocess.py`
**Issue**: User says "change rooms" after feedback → preprocessing routes directly to search, but search uses old topology from initial brief
**Fix**: In preprocessing, change "change rooms" routing from `"research"` to `"brief"`, not `"research"`/`"search"`

### 2. Loop handling & iteration limits
**File**: `python/graph.py`, `python/nodes/*.py`
**Issue**: No safeguard against infinite loops; need iteration counter & max_iterations enforcement
**Required**:
- Track `iteration` counter incrementing in each node
- Check `iteration < max_iterations` before proceeding
- Return error response if max iterations exceeded

### 3. Smart brief for simple requests (no LLM)
**File**: `python/nodes/brief.py`
**Issue**: All requests go through LLM; some simple cases (single room, standard programs) don't need LLM
**Required**:
- Detect simple patterns in user_prompt (e.g., "2 bedroom, 1 bath, kitchen, living")
- Parse programmatically without LLM for common cases
- Only invoke LLM for complex/ambiguous requests

### 4. Evaluate should check if daylight already computed
**File**: `python/nodes/evaluate.py`
**Issue**: Calls daylight_06 MCP tool even if layout already has daylight scores
**Required**:
- Check if rooms already have `daylight` attribute
- If yes, skip tool call and reuse existing scores
- Only call tool if scores missing

### 5. Log user-input-wait messages consistently
**File**: `python/nodes/*.py`
**Issue**: When node returns `final_response` (asking user), should log a clear message
**Required**:
- After choice, feedback, or any node returning final_response: log "⏸️ Waiting for user input"
- Include what options user has
- Helps distinguish user-wait from errors

### 6. Boundary node - add state updates
**File**: `python/nodes/boundary.py`
**Issue**: Modifies layout via MCP but unclear if saves properly
**Required**:
- Ensure `layout_json_string` updated in state after modification
- Save to file like adapt/evaluate do

### 7. Search node - handle empty topology
**File**: `python/nodes/search.py`
**Issue**: If topology graph is None/empty, search fails silently
**Required**:
- Check if topology_graph_json_string exists before search
- Return helpful error if missing

### 8. Session persistence improvements
**File**: `python/graph.py`
**Issue**: Session dict only carries 3 fields; may miss other state
**Required**:
- Consider carrying more fields (evaluation_json_string, preprocessing_result)
- Or clear unnecessary fields between turns