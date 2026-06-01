#!/usr/bin/env python3
"""Test slab thickness calculation for bedroom 3"""
import sys
import json

sys.path.insert(0, "team_05/python")
from python_copilot import process_with_copilot

# Load the layout
with open("team_05/team_05_edited_layout.json", "r") as f:
    layout = json.load(f)

print("=" * 70)
print("TEST: Bedroom 3 Slab Thickness Query")
print("=" * 70)

# Test the exact query from the dashboard
context = {
    "user_input": "calculate area of bed room 3 with slab thickness .9 m",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: calculate area of bed room 3 with slab thickness .9 m")
print("\nResponse:")
response = process_with_copilot(context)
print(response)

# Try a better phrased query
print("\n" + "=" * 70)
print("TEST: Better Phrased Query")
print("=" * 70)

context2 = {
    "user_input": "change bedroom 3 slab depth to 0.9 m and calculate cost",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: change bedroom 3 slab depth to 0.9 m and calculate cost")
print("\nResponse:")
response2 = process_with_copilot(context2)
print(response2)

# Try another phrasing
print("\n" + "=" * 70)
print("TEST: Another Phrasing")
print("=" * 70)

context3 = {
    "user_input": "bedroom 3 slab thickness 0.9m",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: bedroom 3 slab thickness 0.9m")
print("\nResponse:")
response3 = process_with_copilot(context3)
print(response3)
