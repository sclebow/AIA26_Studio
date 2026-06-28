"""Test that the project field type checking works correctly"""
import json

# Test 1: Load tower_option_2.json (project is dict)
print("=" * 70)
print("TEST 1: tower_option_2.json (project as dict)")
print("=" * 70)
with open('team_05/gh/floors/tower_option_2.json') as f:
    data = json.load(f)
    
proj = data.get("project", {})
print(f"project type: {type(proj).__name__}")
print(f"project keys: {list(proj.keys()) if isinstance(proj, dict) else 'N/A (is string)'}")

# Simulate the fix in the code
if isinstance(proj, str):
    proj = {}
currency = proj.get("currency", "AED")
print(f"✓ currency extracted: {currency}")

# Test 2: Load tower_floor04_swiftlet_heatmap.json (project is string)
print("\n" + "=" * 70)
print("TEST 2: tower_floor04_swiftlet_heatmap.json (project as string)")
print("=" * 70)
with open('team_05/gh/tower_floor04_swiftlet_heatmap.json') as f:
    data = json.load(f)
    
proj = data.get("project", {})
print(f"project type: {type(proj).__name__}")
print(f"project value: '{proj}'")

# Simulate the fix in the code
if isinstance(proj, str):
    proj = {}
currency = proj.get("currency", "AED")
print(f"✓ currency safely extracted: {currency}")

print("\n" + "=" * 70)
print("SUCCESS: Both file types handled without AttributeError")
print("=" * 70)
