import json

# Simulate a move tool call payload
move_args = {"move_back": 1.0}

# The bridge/tool would inject tree/shape payloads; simulate minimal params
params = dict(move_args)
params.setdefault("position_xy", [0.0, 0.0])
params.setdefault("rotation_degrees", 0.0)

message = {
    "tool": "manipulation_tools",
    **params,
}

# Also include nested containers used by Grasshopper parsers
message["arguments"] = dict(params)
message["input"] = dict(params)
message["parameters"] = dict(params)

print(json.dumps(message, indent=2))
