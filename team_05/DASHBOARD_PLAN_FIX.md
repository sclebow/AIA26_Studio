# Dashboard Plan Import Issue & Fix

## Problem: `tower_option_2.json` was silently rejected

Your original `tower_option_2.json` file was not loading into the Streamlit dashboard. No error message appeared—the file was simply ignored during upload.

### Root Cause

The dashboard's file validation (in [streamlit_ui.py](streamlit_ui.py#L1272)) checks for a **`"rooms"` key at the root level**:

```python
if "rooms" not in loaded_layout:
    uploaded_ids.add(file_uid)
    continue  # ← silently skips the file!
```

Your JSON structure had rooms nested inside `"canonical_unit"`:

**❌ Original Structure (rejected):**
```json
{
  "project": {...},
  "canonical_unit": {
    "rooms": [...]      ← rooms nested here, not at root
  },
  "core": {...}
}
```

**✅ Expected Structure (accepted):**
```json
{
  "project": {...},
  "rooms": [...],         ← rooms must be at root level
  "totals": {...},
  "canonical_unit": {...}
}
```

---

## Solution

Created **`tower_option_2_fixed.json`** that:
1. Moves `rooms` array to the root level (from `canonical_unit.rooms`)
2. Keeps `project` and other metadata at root
3. Adds calculated `"totals"` object with cost summaries
4. Preserves `canonical_unit` data (columns, openings) for reference

### File Created
- **Location:** `team_05/gh/floors/tower_option_2_fixed.json`
- **Status:** ✅ Working in dashboard

### Verification
- ✅ File uploads successfully
- ✅ Appears in "Active Plan" dropdown
- ✅ Floor plan renders with cost heatmap
- ✅ All 7 rooms display correctly (Master Bedroom, Bedrooms 2-3, Bathroom, Living, Dining, Corridor)
- ✅ Costs per room calculated and displayed

---

## Dashboard Compatibility

### What the dashboard expects in JSON:

| Field | Required | Location | Description |
|-------|----------|----------|-------------|
| `rooms` | ✅ Yes | **Root level** | Array of room objects |
| `project` | ✅ Yes | Root | Project metadata |
| `totals` | ⚠️ Recommended | Root | Cost summaries (`{ rooms: X, grand: Y }`) |
| `area_m2` | Per room | Each room | Room area in m² |
| `rate_per_m2` | Per room | Each room | Construction cost per m² |
| `total_cost` | Per room | Each room | Room total cost |
| `category` | Per room | Each room | Room type (common, bedroom, wet, circulation) |
| `polygon` | Per room | Each room | [x,y] coordinates as array of arrays |

### Optional Nested Data
- `canonical_unit.columns` — Structural elements
- `canonical_unit.openings` — Doors/windows
- `core` — Shared building systems
- `layout` — Configuration metadata

---

## How to Upload Plans to the Dashboard

1. **Ensure JSON has root-level `"rooms"`** array
2. In PlanWise sidebar, click **"Add files"** → select JSON
3. File auto-loads if structure is valid
4. Select from **"Active Plan"** dropdown
5. Floor plan renders with costs

---

## Next Steps

To use multi-unit plans like your tower:
- Each unit (apartment) should be represented as separate room objects in the root `"rooms"` array
- Multiply costs by number of units (5 apartments × 154 m² = 770 m²)
- Consider creating a post-processing script to flatten multi-unit JSON structures automatically

**See also:** [schema examples](../layout_input/) for reference layouts.
