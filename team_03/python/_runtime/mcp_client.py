import json
from typing import Any
import httpx


class McpClient:
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

    def _rpc(self, method: str, params: dict[str, Any] | None = None,
             timeout: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        response = self._client.post(self._endpoint, json=payload,
                                     timeout=timeout)
        response.raise_for_status()

        body = response.json()

        if "error" in body:
            raise RuntimeError(f"MCP error for {method}: {body['error']}")

        if "result" not in body:
            raise RuntimeError(f"MCP response for {method} missing result")

        result = body["result"]
        if not isinstance(result, dict):
            raise RuntimeError(f"MCP response result for {method} must be an object")

        return result

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                # "protocolVersion": "2024-11-05",
                "clientInfo": {
                    "name": "aia26-studio-python-agent",
                    "version": "0.1.0",
                },
                "capabilities": {},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc("tools/list")
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise RuntimeError("tools/list result missing 'tools' array")
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: float | None = None) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments}, timeout=timeout)

        content = result.get("content")
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and "text" in item:
                    text_parts.append(str(item["text"]))
                else:
                    text_parts.append(json.dumps(item))
            return "\n".join(text_parts)

        if isinstance(content, str):
            return content

        return json.dumps(result)
