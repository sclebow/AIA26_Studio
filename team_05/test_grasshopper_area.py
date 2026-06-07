#!/usr/bin/env python3
"""Calculate Bedroom 3 area using Grasshopper MCP tools"""
import sys
import json

sys.path.insert(0, "team_05/python")
from swiftlet_mcp import check_connection, _call_tool

# Load the layout
with open("team_05/team_05_edited_layout.json", "r") as f:
    layout = json.load(f)

print("=" * 70)
print("GRASSHOPPER AREA CALCULATION - BEDROOM 3")
print("=" * 70)

# Check connection first
print("\n[1] Checking Grasshopper connection...")
ok, info = check_connection()
if ok:
    print(f"✅ Connected to Grasshopper")
    print(f"   Available tools: {info}")
else:
    print(f"❌ Not connected: {info}")
    print("\nPlease ensure:")
    print("1. Rhino/Grasshopper is open with team_05_working.gh")
    print("2. SwiftletBridge is running:")
    print("   Start-Process 'C:\\Users\\MOHA9808\\AppData\\Roaming\\McNeel\\Rhinoceros\\packages\\8.0\\swiftlet\\0.2.0\\SwiftletBridge.exe' -ArgumentList 'http://localhost:3001/mcp/'")
    sys.exit(1)

# Find bedroom 3
print("\n[2] Finding Bedroom 3 in layout...")
bedroom3 = None
for room in layout.get("rooms", []):
    if "bedroom 3" in room.get("name", "").lower():
        bedroom3 = room
        break

if not bedroom3:
    print("❌ Bedroom 3 not found in layout")
    sys.exit(1)

print(f"✅ Found: {bedroom3.get('name')}")
print(f"   Current area (from JSON): {bedroom3.get('area_m2')} m²")

# Call Grasshopper area calculation tool
print("\n[3] Calling Grasshopper 'compute_area_of_element' tool...")
try:
    layout_str = json.dumps(layout)
    result = _call_tool("compute_area_of_element", {
        "room_name": bedroom3.get("name"),
        "layout_json": layout_str,
        "layout_schema": layout_str
    })
    
    print("✅ Grasshopper response:")
    print(result)
    
    # Try to parse the response
    try:
        result_json = json.loads(result)
        if isinstance(result_json, dict):
            area = result_json.get("area") or result_json.get("area_m2")
            if area:
                print(f"\n{'=' * 70}")
                print(f"RESULT FROM GRASSHOPPER:")
                print(f"  Bedroom 3 Area = {area} m²")
                print(f"{'=' * 70}")
    except json.JSONDecodeError:
        pass
        
except Exception as e:
    print(f"❌ Error calling Grasshopper: {e}")
    sys.exit(1)

print("\n✅ Area calculation completed and reflected in Grasshopper!")
