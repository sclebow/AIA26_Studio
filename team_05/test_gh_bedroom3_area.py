#!/usr/bin/env python3
"""Calculate Bedroom 3 area using Grasshopper Area-Based Cost Calculator"""
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
else:
    print(f"❌ Not connected: {info}")
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
print(f"   Current total cost: ${bedroom3.get('total_cost'):,.2f}")

# Call Grasshopper Area-Based Cost Calculator
print("\n[3] Calling Grasshopper 'Area-Based Cost Calculator Tool'...")
print("   (This will calculate area and cost in Grasshopper)")

try:
    layout_str = json.dumps(layout)
    result = _call_tool("Area-Based Cost Calculator Tool", {
        "room_name": bedroom3.get("name"),
        "layout_schema": layout_str
    })
    
    print("\n✅ Grasshopper response received!")
    print(f"\nRaw response (first 500 chars):\n{result[:500]}")
    
    # Try to parse the response
    try:
        result_json = json.loads(result)
        if isinstance(result_json, dict) and "rooms" in result_json:
            for room in result_json.get("rooms", []):
                if "bedroom 3" in room.get("name", "").lower():
                    print(f"\n{'=' * 70}")
                    print(f"BEDROOM 3 - CALCULATED BY GRASSHOPPER:")
                    print(f"{'=' * 70}")
                    print(f"  Room Name:       {room.get('name')}")
                    print(f"  Area (m²):       {room.get('area_m2')}")
                    print(f"  Rate (USD/m²):   ${room.get('rate_per_m2'):,.2f}")
                    print(f"  Total Cost:      ${room.get('total_cost'):,.2f}")
                    print(f"{'=' * 70}")
                    print("\n✅ Grasshopper successfully calculated and reflected Bedroom 3!")
                    break
    except json.JSONDecodeError:
        print("\nNote: Response is not JSON format")
        print(f"Full response:\n{result}")
        
except Exception as e:
    print(f"❌ Error calling Grasshopper: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
