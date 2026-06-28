from __future__ import annotations

import json
import inspect
from collections.abc import Callable
from typing import Any, Protocol

import httpx

from .tools import IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION
from .tools import ANALYZE_SITE_BOUNDARY_TOOL_DEFINITION
from .tools import MEASURE_BOUNDARY_PROXIMITY_TOOL_DEFINITION
from .tools import MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION
from .tools import MODIFY_BUILDING_WINGS_TOOL_DEFINITION
from .tools import VALIDATE_DESIGN_TOOL_DEFINITION
from .tools import REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION
from .tools import REQUESTED_POSITION_CHECKER_TOOL_DEFINITION
from .tools import DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION
from .tools import TOOL_DEFINITION as GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION
from .tools import analyze_site_boundary, measure_boundary_proximity
from .tools import direction_to_site_centroid
from .tools import generate_building_boundary
from .tools import validate_design
from .tools import mock_check_requested_position, mock_import_building_boundary, mock_remaining_buildable_positions, modify_building_boundary, modify_building_wings
from .tools.masterplan import MASTERPLAN_TOOL_DEFINITION, run_masterplan_tool


class ToolClient(Protocol):
    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        ...

    def close(self) -> None:
        ...


class HttpMcpClient:
    def __init__(self, endpoint: str, timeout_seconds: float) -> None:
        self._endpoint = endpoint
        self._timeout_seconds = timeout_seconds
        self._request_id = 0
        self._client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self._client.close()

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        response = self._client.post(self._endpoint, json=payload)
        response.raise_for_status()
        body = response.json()

        if "error" in body:
            raise RuntimeError(f"MCP error for {method}: {body['error']}")
        result = body.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"MCP response for {method} missing object result")
        return result

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "clientInfo": {"name": "team-04-agent", "version": "2.0.0"},
                "capabilities": {},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        tools = self._rpc("tools/list").get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("tools/list result missing 'tools' array")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")

        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(json.dumps(item))
            return "\n".join(parts)

        return json.dumps(result)


class LocalToolClient:
    def __init__(self, tools: dict[str, tuple[dict[str, Any], Callable[..., dict[str, Any]]]]) -> None:
        self._tools = dict(tools)
        self.calls: list[str] = []

    def list_tools(self) -> list[dict[str, Any]]:
        return [definition for definition, _ in self._tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        entry = self._tools.get(name)
        if entry is None:
            raise RuntimeError(f"Unknown local tool: {name}")
        self.calls.append(name)
        _, handler = entry
        signature = inspect.signature(handler)
        accepted_names = {
            parameter_name
            for parameter_name, parameter in signature.parameters.items()
            if parameter.kind in {
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            }
        }
        filtered_arguments = {
            key: value
            for key, value in arguments.items()
            if key in accepted_names
        }
        result = handler(**filtered_arguments)
        return json.dumps(result)

    def close(self) -> None:
        return None


class CompositeToolClient:
    def __init__(self, clients: list[ToolClient]) -> None:
        self._clients = list(clients)
        self._tool_owner_map: dict[str, ToolClient] = {}

        for client in self._clients:
            for tool in client.list_tools():
                name = str(tool.get("name", "")).strip()
                if name and name not in self._tool_owner_map:
                    self._tool_owner_map[name] = client

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()
        for client in self._clients:
            for tool in client.list_tools():
                name = str(tool.get("name", "")).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                tools.append(tool)
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        owner = self._tool_owner_map.get(name)
        if owner is None:
            raise RuntimeError(f"No registered tool client for tool: {name}")
        return owner.call_tool(name, arguments)

    @property
    def calls(self) -> list[str]:
        collected: list[str] = []
        for client in self._clients:
            if hasattr(client, "calls"):
                collected.extend(getattr(client, "calls"))
        return collected

    def close(self) -> None:
        for client in self._clients:
            client.close()


def build_default_local_tool_client() -> LocalToolClient:
    return LocalToolClient(
        {
            GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                GENERATE_BUILDING_BOUNDARY_TOOL_DEFINITION,
                generate_building_boundary,
            ),
            MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                MODIFY_BUILDING_BOUNDARY_TOOL_DEFINITION,
                modify_building_boundary,
            ),
            MODIFY_BUILDING_WINGS_TOOL_DEFINITION["name"]: (
                MODIFY_BUILDING_WINGS_TOOL_DEFINITION,
                modify_building_wings,
            ),
            VALIDATE_DESIGN_TOOL_DEFINITION["name"]: (
                VALIDATE_DESIGN_TOOL_DEFINITION,
                validate_design,
            ),
            DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION["name"]: (
                DIRECTION_TO_SITE_CENTROID_TOOL_DEFINITION,
                direction_to_site_centroid,
            ),
            ANALYZE_SITE_BOUNDARY_TOOL_DEFINITION["name"]: (
                ANALYZE_SITE_BOUNDARY_TOOL_DEFINITION,
                analyze_site_boundary,
            ),
            MEASURE_BOUNDARY_PROXIMITY_TOOL_DEFINITION["name"]: (
                MEASURE_BOUNDARY_PROXIMITY_TOOL_DEFINITION,
                measure_boundary_proximity,
            ),
            IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION["name"]: (
                IMPORT_BUILDING_BOUNDARY_TOOL_DEFINITION,
                mock_import_building_boundary,
            ),
            REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION["name"]: (
                REMAINING_BUILDABLE_POSITIONS_TOOL_DEFINITION,
                mock_remaining_buildable_positions,
            ),
            REQUESTED_POSITION_CHECKER_TOOL_DEFINITION["name"]: (
                REQUESTED_POSITION_CHECKER_TOOL_DEFINITION,
                mock_check_requested_position,
            ),
            MASTERPLAN_TOOL_DEFINITION["name"]: (
                MASTERPLAN_TOOL_DEFINITION,
                run_masterplan_tool,
            ),
        }
    )