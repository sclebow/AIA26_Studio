#!/usr/bin/env python3
"""Calculate Bedroom 2 area using Grasshopper"""
import sys
import json

sys.path.insert(0, "team_05/python")
from swiftlet_mcp import check_connection, _call_tool

# Load the layout
with open("team_05/team_05_edited_layout.json", "r") as f:
    layout = json.load(f)

print("=" * 70)
print("BEDROOM 2 - AREA CALCULATION VIA GRASSHOPPER")
print("=" * 70)

# Check connection
print("\n[1] Checking Grasshopper connection...")
ok, info = check_connection()
if not ok:
    print(f"❌ Not connected: {info}")
    sys.exit(1)
print(f"✅ Connected")

# Find bedroom 2
print("\n[2] Finding Bedroom 2...")
bedroom2 = None
for room in layout.get("rooms", []):
    if "bedroom 2" in room.get("name", "").lower():
        bedroom2 = room
        break

if not bedroom2:
    print("❌ Bedroom 2 not found")
    sys.exit(1)

print(f"✅ Found: {bedroom2.get('name')}")
print(f"   Area (from JSON): {bedroom2.get('area_m2')} m²")
print(f"   Rate: ${bedroom2.get('rate_per_m2'):,.2f}/m²")
print(f"   Total cost: ${bedroom2.get('total_cost'):,.2f}")

# Call Grasshopper
print("\n[3] Calculating area in Grasshopper...")
try:
    layout_str = json.dumps(layout)
    result = _call_tool("Area-Based Cost Calculator Tool", {
        "room_name": bedroom2.get("name"),
        "layout_schema": layout_str
    })
    
    # Parse response
    result_json = json.loads(result)
    if isinstance(result_json, dict) and "rooms" in result_json:
        for room in result_json.get("rooms", []):
            if "bedroom 2" in room.get("name", "").lower():
                print(f"\n{'=' * 70}")
                print(f"BEDROOM 2 - GRASSHOPPER CALCULATION RESULTS:")
                print(f"{'=' * 70}")
                print(f"  Room Name:       {room.get('name')}")
                print(f"  Area (m²):       {room.get('area_m2')}")
                print(f"  Rate (USD/m²):   ${room.get('rate_per_m2'):,.2f}")
                print(f"  Total Cost:      ${room.get('total_cost'):,.2f}")
                print(f"{'=' * 70}")
                print("\n✅ Area calculation completed in Grasshopper!")
                break
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
