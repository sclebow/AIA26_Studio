"""Agent route — run the prompt-to-design workflow (JSON, non-streaming).

Thin wrapper over connection.notebook_logic.agent_runtime. The streaming Copilot
path stays on the pre-existing /sessions/{id}/chat SSE route; this gives a simple
one-shot endpoint that returns the full final state + traces in one response.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import agent_runtime

router = APIRouter(prefix="/api/agent", tags=["api-agent"])


class RunRequest(BaseModel):
    prompt: str = Field(min_length=1)
    layout: dict[str, Any] | None = None
    max_optimization_cycles: int = Field(default=3, ge=0, le=10)
    use_confirmed_site: bool = True


@router.post("/run")
def run(body: RunRequest) -> dict[str, Any]:
    try:
        return agent_runtime.run_and_summarize(
            body.prompt,
            layout=body.layout,
            max_optimization_cycles=body.max_optimization_cycles,
            use_confirmed_site=body.use_confirmed_site,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
