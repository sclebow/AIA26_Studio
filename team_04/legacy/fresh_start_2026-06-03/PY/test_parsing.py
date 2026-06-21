#!/usr/bin/env python
"""Test the parsing functions for move, rotate, and scale operations."""

from design_main import _parse_move_request, _parse_rotate_request, _parse_scale_request

# Test move parsing
print("MOVE PARSING:")
print('  Input: "move the building 2m left"')
result = _parse_move_request("move the building 2m left")
print(f"  Result: {result}")

# Test rotate parsing  
print("\nROTATE PARSING:")
print('  Input: "rotate the building 15 clockwise"')
result = _parse_rotate_request("rotate the building 15 clockwise")
print(f"  Result: {result}")

print('  Input: "rotate the building 30 degrees anticlockwise"')
result = _parse_rotate_request("rotate the building 30 degrees anticlockwise")
print(f"  Result: {result}")

# Test scale parsing
print("\nSCALE PARSING:")
print('  Input: "scale the building 1.2 times"')
result = _parse_scale_request("scale the building 1.2 times")
print(f"  Result: {result}")

print('  Input: "shrink the building by 20%"')
result = _parse_scale_request("shrink the building by 20%")
print(f"  Result: {result}")

print('  Input: "enlarge the building"')
result = _parse_scale_request("enlarge the building")
print(f"  Result: {result}")
