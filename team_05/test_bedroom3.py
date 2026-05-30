#!/usr/bin/env python3
"""Test increasing bedroom 3 cost"""
import sys
import json

sys.path.insert(0, "team_05/python")
from python_copilot import process_with_copilot

# Load the layout
with open("team_05/team_05_edited_layout.json", "r") as f:
    layout = json.load(f)

print("=" * 70)
print("TEST: Query about Bedroom 3")
print("=" * 70)

# First, let's see current bedroom 3 info
context1 = {
    "user_input": "bedroom 3",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: bedroom 3")
print("\nResponse:")
response1 = process_with_copilot(context1)
print(response1)

# Now test increase cost query
print("\n" + "=" * 70)
print("TEST: How to increase bedroom 3 cost")
print("=" * 70)

context2 = {
    "user_input": "how to increase cost of bedroom 3",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: how to increase cost of bedroom 3")
print("\nResponse:")
response2 = process_with_copilot(context2)
print(response2)

# Test changing to more expensive materials
print("\n" + "=" * 70)
print("TEST: Change bedroom 3 floor to marble")
print("=" * 70)

context3 = {
    "user_input": "change bedroom 3 floor finish to marble",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: change bedroom 3 floor finish to marble")
print("\nResponse:")
response3 = process_with_copilot(context3)
print(response3)
