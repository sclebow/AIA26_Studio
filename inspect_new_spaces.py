#!/usr/bin/env python3
"""Inspect new spaces in updated JSON files"""
import json

print("=" * 70)
print("INSPECTING NEW SPACES (LIFTS, STAIRCASES, MEP)")
print("=" * 70)

# Check tower_option_2.json
print("\n[tower_option_2.json]")
with open('team_05/gh/floors/tower_option_2.json') as f:
    data = json.load(f)
    
print("Root keys:", list(data.keys()))
canonical = data.get('canonical_unit', {})
print("\nCanonical unit keys:", list(canonical.keys()))

for key in canonical.keys():
    items = canonical[key]
    if isinstance(items, list) and items:
        print(f"\n  {key}: {len(items)} items")
        if items:
            sample = items[0]
            name = sample.get('name') or sample.get('id') or sample.get('type', '?')
            cost = sample.get('total_cost', '?')
            color = sample.get('color') or sample.get('category', '?')
            print(f"    Sample: {name}")
            print(f"    Cost: {cost}, Color/Category: {color}")

# Check layout for new space definitions
layout = data.get('layout', {})
if layout:
    print(f"\nlayout keys: {list(layout.keys())}")
    
# Check core
core = data.get('core', {})
if core:
    print(f"\ncore keys: {list(core.keys())}")
    if 'lifts' in core:
        print(f"  lifts: {len(core.get('lifts', []))} items")
    if 'staircases' in core:
        print(f"  staircases: {len(core.get('staircases', []))} items")
    if 'mep' in core:
        print(f"  mep: {len(core.get('mep', []))} items")

print("\n" + "=" * 70)
print("CHECKING tower_floor04_swiftlet_heatmap.json")
print("=" * 70)

with open('team_05/gh/tower_floor04_swiftlet_heatmap.json') as f:
    data = json.load(f)

print("\nRoot keys:", list(data.keys()))
print("Total rooms:", len(data.get('rooms', [])))

# Sample room to see cost categories
if data.get('rooms'):
    sample = data['rooms'][0]
    print(f"\nSample room: {sample.get('name', 'unnamed')}")
    print(f"  Keys: {list(sample.keys())}")
    print(f"  Cost: {sample.get('total_cost', '?')}")
    print(f"  Category: {sample.get('category', '?')}")

print("\n" + "=" * 70)
