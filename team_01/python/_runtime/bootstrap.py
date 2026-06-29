from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _runtime.config import load_settings
from _runtime.llm import create_chat_llm
from nodes.tools import get_action_tools


@dataclass
class Context:
    """Everything the graph needs for local execution."""

    llm: Any
    tools: list[dict[str, Any]]
    layout_data: dict[str, Any]
    max_iterations: int
    edited_layout_path: Path


def bootstrap() -> Context:
    settings = load_settings()

    repo_root = Path(__file__).resolve().parents[3]
    layout_path = repo_root / "layout_input" / "layout_schema.json"
    layout_data: dict[str, Any] = json.loads(layout_path.read_text(encoding="utf-8"))

    llm = create_chat_llm(
        api_key=settings.api_key,
        base_url=settings.base_url,
        llm_model=settings.llm_model,
        timeout_seconds=settings.request_timeout_seconds,
        provider=settings.provider,
    )

    tools = get_action_tools()

    team_dir = Path(__file__).resolve().parents[2]
    team_name = team_dir.name
    edited_layout_path = repo_root / f"{team_name}_edited_layout.json"

    return Context(
        llm=llm,
        tools=tools,
        layout_data=layout_data,
        max_iterations=settings.max_iterations,
        edited_layout_path=edited_layout_path,
    )
