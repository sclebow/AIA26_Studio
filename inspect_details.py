#!/usr/bin/env python3
"""Detailed inspection of new spaces structure"""
import json

print("=" * 70)
print("DETAILED INSPECTION: NEW SPACES (LIFTS, STAIRCASES, MEP)")
print("=" * 70)

# tower_option_2.json
with open('team_05/gh/floors/tower_option_2.json') as f:
    data = json.load(f)

core = data.get('core', {})
print("\n[tower_option_2.json - CORE]")
print(f"  id: {core.get('id')}")
print(f"  description: {core.get('description')}")
print(f"  area_m2: {core.get('area_m2')}")
print(f"  cost_estimate: {core.get('cost_estimate')}")

components = core.get('components', [])
print(f"  components: {type(components).__name__} with {len(components) if isinstance(components, (list, dict)) else 0} items")

if isinstance(components, list):
    print(f"    List of {len(components)} component groups:")
    for i, comp in enumerate(components[:3]):  # Show first 3
        print(f"      [{i}] {comp.get('type', '?')}: {comp.get('name', '?')} - Cost: {comp.get('cost', comp.get('total_cost', '?'))}")
        if 'color' in comp:
            print(f"          Color: {comp.get('color')}")
        if 'color_hex' in comp:
            print(f"          Color Hex: {comp.get('color_hex')}")
elif isinstance(components, dict):
    for comp_type, comp_list in components.items():
        if isinstance(comp_list, list):
            print(f"\n    {comp_type}: {len(comp_list)} items")
            if comp_list:
                sample = comp_list[0]
                print(f"      Sample keys: {list(sample.keys())}")
                print(f"      Sample: {sample.get('name', sample.get('id', '?'))}")

print("\n" + "=" * 70)
print("[tower_floor04_swiftlet_heatmap.json - ROOMS SAMPLE]")
with open('team_05/gh/tower_floor04_swiftlet_heatmap.json') as f:
    data = json.load(f)

if data.get('rooms'):
    sample = data['rooms'][0]
    print(f"\nRoom 1: {sample['name']}")
    for k, v in sample.items():
        print(f"  {k}: {v}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
To properly display lifts, staircases, and MEP in the heatmap:
1. Identify all element types (rooms, columns, openings, lifts, staircases, mep)
2. Assign distinct colors to each type
3. Update build_floor_plan() to render all types
4. Update build_cost_df() to include all types in breakdown
5. Update analysis tabs to reference all space types
""")
