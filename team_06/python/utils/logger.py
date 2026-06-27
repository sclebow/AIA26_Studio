from __future__ import annotations

import json
import logging
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[3] / "log.txt"

_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(message)s"))

logger = logging.getLogger("inhabit")
logger.setLevel(logging.INFO)
logger.addHandler(_handler)
logger.propagate = False


def log_run(
    session_id: str,
    user_prompt: str,
    llm_provider: str,
    llm_model: str,
    nodes_executed: list[str],
    selected_layout_id: str | None,
    agent_response: str | None,
    specifications: list[str],
    rooms: list[str],
    household: list[str],
    routine_status: str,
    routine_personas: list[str],
    routine_warning: str | None,
    evaluation_summary: str | None,
    duration_seconds: float,
    status: str,
    error: str | None = None,
) -> None:
    record = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "session_id": session_id,
        "user_prompt": user_prompt,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "nodes_executed": nodes_executed,
        "selected_layout_id": selected_layout_id,
        "agent_response": agent_response,
        "specifications": specifications,
        "rooms": rooms,
        "household": household,
        "routine_status": routine_status,
        "routine_personas": routine_personas,
        "routine_warning": routine_warning,
        "evaluation_summary": evaluation_summary,
        "duration_seconds": round(duration_seconds, 2),
        "status": status,
        "error": error,
    }
    logger.info(json.dumps(record, ensure_ascii=False))
