# TerraPilot - Quick Start Guide
## Team 04 - Getting Started

---

## 📚 What You Have

### Documentation
1. **TERRAPILOT_PLAN.md** - Complete detailed plan with all 23 tools
2. **ARCHITECTURE.md** - System architecture (existing)
3. **gh/tool_definitions/** - Detailed specs for each tool with examples
4. **This file** - Quick start instructions

### Code Structure
```
team_04/
├── gh/
│   ├── team_04_definition_cluster.ghcluster  ← Build INPUT + SHAPE tools here
│   ├── team_04_result_cluster.ghcluster      ← Build other tools here
│   ├── team_04_working.gh                    ← Test harness (don't modify)
│   └── tool_definitions/                     ← Read these specs
│       ├── README.md                         ← Template for all tools
│       ├── 01_site_boundary_reader.md        ← Full spec with examples
│       └── 05_parametric_shape_generator.md  ← Full spec with examples
└── python/
    ├── main.py
    ├── graph.py
    ├── nodes/
    │   └── reason.py                         ← UPDATED with TerraPilot prompts
    └── _runtime/
```

---

## 🚀 Implementation Steps

### Week 1: Foundation (Days 1-7)

#### Day 1-2: Tool 1 (site_boundary_reader_04)
**File:** `team_04_definition_cluster.ghcluster`

**Goal:** Read site coordinates and create boundary curve

**Steps:**
1. Open `team_04_definition_cluster.ghcluster` in Grasshopper
2. Create a new cluster (or edit existing)
3. Add cluster input: `input_json` (String)
4. Add cluster output: `output_json` (String)
5. Inside cluster:
   - Python component: Parse JSON input
   - Grasshopper: Create polyline from coordinates
   - Grasshopper: Calculate area, centroid, perimeter
   - Python component: Format JSON output
6. Test with example from `01_site_boundary_reader.md`

**Placeholder first:**
```python
# Simple placeholder that echoes input
import json
input_data = json.loads(input_json) if input_json else {}
output = {
    "success": True,
    "data": {"site_area_sqm": 10000, "placeholder": True},
    "metadata": {"tool_name": "site_boundary_reader_04"}
}
output_json = json.dumps(output, indent=2)
```

#### Day 3: Test MCP Connection
1. Save cluster changes
2. Open `team_04_working.gh`
3. Verify MCP server is configured correctly
4. From Python: `python main.py "show me the site"`
5. Should see tool discovered and called

#### Day 4-5: Tool 3 (shape_library_loader_04)
**File:** `team_04_definition_cluster.ghcluster`

**Goal:** Load predefined shapes (start with "bar" only)

**Steps:**
1. Create new cluster or add to existing
2. Accept JSON with `shape_type`, `base_width_m`, `base_length_m`
3. Generate simple rectangle for "bar" shape
4. Return footprint area and GFA

**Start simple:**
- Day 4: Just "bar" shape
- Day 5: Add "l_shape"

#### Day 6: Tool 5 (parametric_shape_generator_04)
**File:** `team_04_definition_cluster.ghcluster`

**Goal:** Create editable parametric geometry

**Steps:**
1. Build on Tool 3
2. Add rotation, position parameters
3. Return geometry_id for later reference
4. Test with different parameters

#### Day 7: Integration Test
**Goal:** Full workflow: Site → Shape → Output

1. Test sequence:
   ```python
   python main.py "Create a bar building on a 100x80 meter site"
   ```
2. Should call:
   - site_boundary_reader_04
   - parametric_shape_generator_04
3. Return success message

---

### Week 2: Validation (Days 8-14)

#### Tools to Implement
- Tool 6: site_fit_checker_04
- Tool 7: setback_checker_04
- Tool 8: area_requirement_checker_04
- Tool 9: adjacency_access_checker_04
- Tool 10: tree_constraint_checker_04

**File:** `team_04_result_cluster.ghcluster`

**Strategy:**
- 2 tools per day (Days 8-12)
- Day 13: Integration testing
- Day 14: Bug fixes and documentation

**Each tool follows same pattern:**
1. Parse JSON input
2. Perform geometric check (containment, distance, overlap)
3. Return Boolean + metrics
4. Use components: Curve Proximity, Point In Curve, Region Intersection

---

### Week 3: Manipulation (Days 15-21)

#### Tools to Implement
- Tool 11: scale_shape_tool_04
- Tool 12: stretch_arm_tool_04
- Tool 13: width_modifier_tool_04
- Tool 14: courtyard_modifier_tool_04
- Tool 15: rotate_mirror_tool_04
- Tool 16: bend_angle_tool_04
- Tool 17: terrace_step_tool_04

**File:** `team_04_result_cluster.ghcluster`

**Strategy:**
- 1 tool per day (Days 15-21)
- Each tool modifies existing geometry
- Must preserve geometry_id through transformations

**Key Challenge:** Geometry state management
- Solution: Store geometry_id in Rhino UserText
- Retrieve by ID, transform, save with same ID

---

### Week 4: Intelligence (Days 22-28)

#### Tools to Implement
- Tool 18: why_operation_selector_04 (Python side)
- Tool 19: spatial_intention_evaluator_04
- Tool 20: performance_evaluator_04
- Tool 21: shape_integrity_evaluator_04
- Tool 22: bake_geometry_id_04
- Tool 23: explain_decision_tool_04 (Python side)

**Files:** Mix of `team_04_result_cluster.ghcluster` and Python

**Strategy:**
- Days 22-24: Evaluation tools (19-21) in Grasshopper
- Days 25-26: Output tools (22) in Grasshopper
- Days 27-28: Python reasoning logic (18, 23)

**Python Tools (18 & 23):**
These are NOT Grasshopper tools. They are handled by the LLM in `nodes/reason.py`.
- Tool 18: Logic already in updated SYSTEM_PROMPT
- Tool 23: Automatically done by LLM when action="final"

---

## 🧪 Testing Workflow

### Test Each Tool Individually

**Example: Testing Tool 1**
```python
# In Python REPL or test script
from _runtime.bootstrap import bootstrap

ctx = bootstrap()

# Call tool directly
test_input = {
    "polygon_coordinates": [[0,0], [100,0], [100,80], [0,80]]
}

result = ctx.mcp_client.call_tool(
    "site_boundary_reader_04", 
    test_input
)

print(result)
# Should see JSON with site_area_sqm: 8000
```

### Test Full Agent Workflow

**Example: Complete workflow**
```bash
# From team_04/python/ directory
python main.py "Create an L-shaped building on a rectangular site"
```

**Expected behavior:**
1. Agent calls site_boundary_reader_04 (mock data if no site provided)
2. Agent calls parametric_shape_generator_04 with shape="l_shape"
3. Agent returns success message

### Test with Real Data

**Create test file:** `test_cases/site_01.json`
```json
{
  "polygon_coordinates": [
    [0, 145.1],
    [-140.9, 75.6],
    [-108.5, -112.4],
    [108.5, -112.4],
    [140.9, 75.6]
  ],
  "number_of_trees": 80,
  "tree_radius_m": 5
}
```

**Test script:** `test_cases/test_site_01.py`
```python
import json
from _runtime.bootstrap import bootstrap

ctx = bootstrap()

# Load test data
with open("site_01.json") as f:
    site_data = json.load(f)

# Call tool
result = ctx.mcp_client.call_tool("site_boundary_reader_04", site_data)
print(json.dumps(json.loads(result), indent=2))
```

---

## 🐛 Troubleshooting

### Issue: MCP server not discovering tools
**Solution:**
1. Check `team_04_working.gh` has Swiftlet component configured
2. Verify cluster names match exactly: `*_04` suffix
3. Restart Rhino/Grasshopper
4. Check mcp.json has correct endpoint

### Issue: JSON parsing errors
**Solution:**
1. Validate JSON syntax (use jsonlint.com)
2. Ensure quotes are correct (double quotes, not single)
3. Check for trailing commas (not allowed in JSON)
4. Use `json.dumps()` in Python to format output

### Issue: Geometry not appearing in Rhino
**Solution:**
1. Check layer visibility
2. Use `Bake` component in Grasshopper (for testing)
3. Zoom extents in Rhino
4. Verify coordinates are reasonable (not too small/large)

### Issue: Tool returns empty result
**Solution:**
1. Add print statements to Python components
2. Check Grasshopper component warnings (orange/red)
3. Verify input data format matches tool spec
4. Test with simpler input first

---

## 📊 Progress Tracking

### Week 1 Checklist
- [ ] Tool 1: site_boundary_reader_04 (placeholder)
- [ ] Tool 1: site_boundary_reader_04 (full implementation)
- [ ] Tool 3: shape_library_loader_04 (bar shape)
- [ ] Tool 3: shape_library_loader_04 (l_shape)
- [ ] Tool 5: parametric_shape_generator_04
- [ ] MCP connection working
- [ ] Full workflow test passes

### Week 2 Checklist
- [ ] Tool 6: site_fit_checker_04
- [ ] Tool 7: setback_checker_04
- [ ] Tool 8: area_requirement_checker_04
- [ ] Tool 9: adjacency_access_checker_04
- [ ] Tool 10: tree_constraint_checker_04
- [ ] Integration test: validation workflow

### Week 3 Checklist
- [ ] Tool 11: scale_shape_tool_04
- [ ] Tool 12: stretch_arm_tool_04
- [ ] Tool 13: width_modifier_tool_04
- [ ] Tool 14: courtyard_modifier_tool_04
- [ ] Tool 15: rotate_mirror_tool_04
- [ ] Tool 16: bend_angle_tool_04
- [ ] Tool 17: terrace_step_tool_04
- [ ] Integration test: manipulation workflow

### Week 4 Checklist
- [ ] Tool 19: spatial_intention_evaluator_04
- [ ] Tool 20: performance_evaluator_04
- [ ] Tool 21: shape_integrity_evaluator_04
- [ ] Tool 22: bake_geometry_id_04
- [ ] Tool 18 & 23: Python reasoning (already in prompts)
- [ ] Full system test
- [ ] Documentation complete

---

## 💡 Pro Tips

### Start DRY, Then Add Detail
1. **Week 1**: Placeholder that returns mock data
2. **Week 2**: Real geometric operations
3. **Week 3**: Polish, error handling, edge cases
4. **Week 4**: Optimization, visualization

### Use Grasshopper Groups
Organize your clusters with clear groups:
- 🔵 INPUT PARSING
- 🟢 GEOMETRY OPERATIONS
- 🟡 CALCULATIONS
- 🟠 OUTPUT FORMATTING

### Test Incrementally
After each component addition:
1. Right-click → Bake to see geometry
2. Add Panel components to see data
3. Use Param Viewer for complex objects

### Version Control
Commit after each working tool:
```bash
git add team_04/
git commit -m "feat: Tool 1 site_boundary_reader_04 working"
git push origin team_04
```

### Pair Programming
- One person: Grasshopper visual programming
- One person: Python scripting in components
- Switch roles daily

---

## 📞 Getting Help

### Within Team
- Share screen during implementation
- Review each other's tools before integration
- Document assumptions in code comments

### From Instructors
- Scott Lebow: Grasshopper/MCP questions
- Faculty: Architecture/design logic questions

### Resources
- Grasshopper forum: discourse.mcneel.com
- MCP docs: (check repo for links)
- Python JSON: docs.python.org/3/library/json.html

---

## 🎯 Success Metrics

### By End of Week 1
✅ Can read site and place a shape  
✅ Agent responds to simple prompts  
✅ MCP connection stable  

### By End of Week 2
✅ Can validate designs against constraints  
✅ Agent identifies violations  
✅ All constraint tools working  

### By End of Week 3
✅ Can manipulate shapes in response to issues  
✅ Agent makes intelligent tool choices  
✅ Complex multi-step workflows work  

### By End of Week 4
✅ Full TerraPilot system operational  
✅ Generates explanations of decisions  
✅ Produces high-quality architectural proposals  

---

## 🎓 Learning Objectives

### Technical Skills
- Grasshopper visual programming
- Python scripting in GH
- JSON data handling
- MCP tool creation
- LangGraph agent workflows

### Architectural Skills
- Parametric design thinking
- Constraint-based design
- Site analysis
- Building typologies
- Performance evaluation

### AI Skills
- LLM prompt engineering
- Tool-using agents
- Multi-step reasoning
- Explainable AI

---

**You have a complete roadmap. Start with Tool 1, test it, then move forward systematically. Good luck! 🚀**

**Questions?** Add them to this file and commit so everyone can see answers.
