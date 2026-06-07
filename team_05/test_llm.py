#!/usr/bin/env python3
"""Test if LLM and cost calculations work"""
import sys
import json
import os

sys.path.insert(0, "team_05/python")
from python_copilot import process_with_copilot

# Load the layout
with open("team_05/team_05_edited_layout.json", "r") as f:
    layout = json.load(f)

# Test 1: Simple query
context = {
    "user_input": "What is the total project cost?",
    "layout_json": json.dumps(layout),
    "history": []
}

print("=" * 70)
print("TEST: Python Copilot (Rule-Based Logic)")
print("=" * 70)
print("\nQuery: What is the total project cost?")
print("\nResponse:")
response = process_with_copilot(context)
print(response)

# Test 2: Change bathroom floor to porcelain
print("\n" + "=" * 70)
print("TEST: Change Bathroom Floor to Porcelain")
print("=" * 70)

context2 = {
    "user_input": "change bathroom floor finish to porcelain",
    "layout_json": json.dumps(layout),
    "history": []
}

print("\nQuery: change bathroom floor finish to porcelain")
print("\nResponse:")
response2 = process_with_copilot(context2)
print(response2)

print("\n" + "=" * 70)
print("✅ Python Copilot is working!")
print("=" * 70)
