from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx


MCP_CONFIG_PATH = Path(__file__).resolve().parents[1] / "mcp.json"


def load_mcp_endpoint() -> str:
    if not MCP_CONFIG_PATH.exists():
        raise FileNotFoundError(f"MCP config not found: {MCP_CONFIG_PATH}")

    with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    servers = cfg.get("servers") or cfg.get("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("MCP config 'servers' or 'mcpServers' must be an object")

    swiftlet = servers.get("Swiftlet") or servers.get("swiftlet")
    if not swiftlet:
        raise ValueError("Swiftlet server not found in mcp.json")

    if isinstance(swiftlet.get("url"), str) and swiftlet["url"]:
        return swiftlet["url"]

    args = swiftlet.get("args")
    if isinstance(args, list) and args and isinstance(args[0], str) and args[0]:
        return args[0]

    raise ValueError("Swiftlet MCP url missing in mcp.json")


class SimpleMCPClient:
    def __init__(self, endpoint: str, timeout: float = 20.0):
        self.endpoint = endpoint
        self.timeout = timeout
        self._id = 0

    def _post(self, method: str, params: Dict[str, Any] | None = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": method,
            "params": params or {},
        }

        r = httpx.post(self.endpoint, json=payload, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()

        if "error" in data:
            raise RuntimeError(data["error"])

        return data.get("result")

    def close(self) -> None:
        """No-op close to match other MCP client implementations."""
        return None

    def initialize(self) -> Any:
        return self._post(
            "initialize",
            {
                "clientInfo": {
                    "name": "terrapilot-interface-bridge",
                    "version": "1.0",
                },
                "capabilities": {},
            },
        )

    def list_tools(self) -> List[str]:
        result = self._post("tools/list", {})
        tools = result.get("tools", []) if isinstance(result, dict) else []
        names = []

        for tool in tools:
            if isinstance(tool, dict):
                names.append(tool.get("name", ""))
            else:
                names.append(str(tool))

        return [n for n in names if n]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Any:
        return self._post(
            "tools/call",
            {
                "name": name,
                "arguments": arguments,
            },
        )


def pick_tool(available_tools: List[str], candidates: List[str]) -> str:
    lower_map = {t.lower(): t for t in available_tools}

    for c in candidates:
        if c in available_tools:
            return c

    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]

    raise ValueError(
        f"None of these tools were found: {candidates}. "
        f"Available tools: {available_tools}"
    )


def parse_move_command(text: str) -> Tuple[bool, Dict[str, Any], str]:
    t = text.lower().strip()

    if "move" not in t:
        return False, {}, ""

    pattern = re.search(
        r"move\s*(?:the building|building|shape)?\s*"
        r"(\d+(?:\.\d+)?)?\s*"
        r"(?:m|meter|meters)?\s*"
        r"(left|right|up|down|north|south|east|west)?",
        t,
    )

    distance = 1.0
    direction = "right"

    if pattern:
        if pattern.group(1):
            distance = float(pattern.group(1))
        if pattern.group(2):
            direction = pattern.group(2)

    direction_map = {
        "left": "Left",
        "west": "Left",
        "right": "Right",
        "east": "Right",
        "up": "Up",
        "north": "Up",
        "down": "Down",
        "south": "Down",
    }

    args = {
        "Left": 0.0,
        "Right": 0.0,
        "Up": 0.0,
        "Down": 0.0,
    }

    args[direction_map.get(direction, "Right")] = distance

    message = f"Move command detected: {distance} m {direction}"
    return True, args, message


def parse_rotate_command(text: str) -> Tuple[bool, Dict[str, Any], str]:
    t = text.lower().strip()

    if "rotate" not in t and "rotat" not in t:
        return False, {}, ""

    pattern = re.search(
        r"rotat\w*\s*(?:the building|building|shape)?\s*"
        r"(\d+(?:\.\d+)?)?\s*"
        r"(?:degree|degrees|deg|°)?\s*"
        r"(clockwise|counterclockwise|anti-clockwise|anticlockwise|cw|ccw)?",
        t,
    )

    angle = 15.0
    direction = "clockwise"

    if pattern:
        if pattern.group(1):
            angle = float(pattern.group(1))
        if pattern.group(2):
            direction = pattern.group(2)

    clockwise = direction in ["clockwise", "cw"]

    args = {
        "Clockwise": angle if clockwise else 0.0,
        "Anti-clockwise": 0.0 if clockwise else angle,
    }

    label = "clockwise" if clockwise else "counterclockwise"
    message = f"Rotate command detected: {angle}° {label}"
    return True, args, message


def run_interface_command(user_prompt: str) -> Dict[str, Any]:
    """
    Main function for Nihan's app.

    UI prompt
    → parse manipulation intent
    → call MCP Move / Rotate tool
    → return result to interface
    """

    endpoint = load_mcp_endpoint()
    # increase timeout for potentially long-running tool calls
    client = SimpleMCPClient(endpoint, timeout=60.0)

    client.initialize()
    available_tools = client.list_tools()

    move_ok, move_args, move_msg = parse_move_command(user_prompt)
    if move_ok:
        tool_name = pick_tool(
            available_tools,
            ["move", "Move", "move_building_04", "move_building"],
        )
        try:
            raw = client.call_tool(tool_name, move_args)
            client.close()
            return {
                "success": True,
                "action": "move",
                "tool": tool_name,
                "arguments": move_args,
                "message": move_msg,
                "raw_result": raw,
            }
        except Exception as e:
            client.close()
            return {
                "success": False,
                "action": "move",
                "tool": tool_name,
                "arguments": move_args,
                "message": f"MCP call failed: {e}",
                "raw_result": None,
            }

    rotate_ok, rotate_args, rotate_msg = parse_rotate_command(user_prompt)
    if rotate_ok:
        tool_name = pick_tool(
            available_tools,
            ["Rotate", "rotate", "rotate_building_04", "rotate_building"],
        )
        try:
            raw = client.call_tool(tool_name, rotate_args)
            client.close()
            return {
                "success": True,
                "action": "rotate",
                "tool": tool_name,
                "arguments": rotate_args,
                "message": rotate_msg,
                "raw_result": raw,
            }
        except Exception as e:
            client.close()
            return {
                "success": False,
                "action": "rotate",
                "tool": tool_name,
                "arguments": rotate_args,
                "message": f"MCP call failed: {e}",
                "raw_result": None,
            }

    return {
        "success": False,
        "action": None,
        "tool": None,
        "arguments": {},
        "message": "No supported manipulation command found. Try: 'move 10 m left' or 'rotate 30 clockwise'.",
        "raw_result": None,
    }


if __name__ == "__main__":
    print("TerraPilot Interface ↔ MCP Bridge Test")
    print("Examples:")
    print("- move 10 m left")
    print("- rotate 30 clockwise")
    print("- rotate 15 counterclockwise")
    print()

    while True:
        prompt = input("Command: ").strip()

        if prompt.lower() in ["q", "quit", "exit"]:
            break

        try:
            result = run_interface_command(prompt)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print("ERROR:", e)