from __future__ import annotations
from pathlib import Path
from typing import TYPE_CHECKING, Any
from _runtime.session import close_session

if TYPE_CHECKING:
    from graph import AgentState


def output_node(state: AgentState) -> dict:
    # Called only after user_approved=True.
    # Writes the final layout to output/ with a timestamp, then deletes the
    # workspace session file so the next run starts clean.
    output_path = close_session(
        state["workspace_path"],
        Path(state["workspace_path"]).parent / "output",
        state["layout_name"],
    )
    print(f"\nLayout saved to: {output_path}")
    return {"final_response": f"Layout approved and saved to {output_path}"}
