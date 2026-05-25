"""
session.py — workspace session lifecycle utilities.
No LangGraph dependency; pure stdlib only.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path


def create_session(base_layout_path: str | Path, workspace_path: str | Path) -> dict:
    # This is the starting point of every design run.
    # The base layout is the read-only source of truth — it is never modified.
    # A copy lands in workspace/session_active.json so all downstream mutations
    # stay isolated from the original file.
    base = Path(base_layout_path)
    workspace = Path(workspace_path)
    workspace.mkdir(parents=True, exist_ok=True)

    active = workspace / "session_active.json"
    shutil.copy2(base, active)

    return json.loads(active.read_text(encoding="utf-8"))


def save_session(layout_data: dict, workspace_path: str | Path) -> None:
    # Called after every object placement or analysis update so the in-memory
    # state is always reflected on disk. If the process crashes, the last
    # saved state can be resumed via detect_existing_session().
    active = Path(workspace_path) / "session_active.json"
    active.write_text(
        json.dumps(layout_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def close_session(
    workspace_path: str | Path,
    output_path: str | Path,
    layout_name: str,
) -> str:
    # Called only when the user approves the design at the checkpoint.
    # The final state is written to output/ with a timestamp so multiple
    # runs of the same layout never overwrite each other.
    # workspace/session_active.json is deleted to signal a clean slate.
    workspace = Path(workspace_path)
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)

    active = workspace / "session_active.json"
    layout_data = json.loads(active.read_text(encoding="utf-8"))

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    out_file = output / f"{layout_name}_{timestamp}_final.json"
    out_file.write_text(
        json.dumps(layout_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    active.unlink()
    return str(out_file)


def detect_existing_session(workspace_path: str | Path) -> bool:
    # The bootstrap module calls this on startup to decide whether to ask the
    # user "resume existing session?" or start fresh from a base layout.
    # Returns True only when a session_active.json is already present.
    return (Path(workspace_path) / "session_active.json").exists()
