"""
Utilities for discovering, loading, and validating layout JSON files.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve layout directory: env override → sibling /layout → fallback hardcoded path.
_env = os.environ.get("LAYOUT_DIR")
if _env:
    LAYOUT_DIR = Path(_env)
else:
    LAYOUT_DIR = (Path(__file__).parent / ".." / ".." / "layout").resolve()
if not LAYOUT_DIR.exists():
    LAYOUT_DIR = Path(r"C:\Users\ramyayoub\Desktop\IAAC\Master\Semester-3\AIA Studio\GRP-03_studio\AIA26_Studio\team_03\layout")
print(f"[layout_loader] LAYOUT_DIR: {LAYOUT_DIR} (exists: {LAYOUT_DIR.exists()})")

REQUIRED_KEYS = {"layoutId", "outline", "rooms"}


def list_layouts() -> List[Dict[str, Any]]:
    """
    Recursively find all *.json files under LAYOUT_DIR.

    Returns a list of dicts with keys:
        name     — stem of the file (e.g. "industrial_005")
        path     — absolute path string
        category — name of the immediate parent directory (e.g. "industrial_100")
        file_size — size in bytes
    """
    results: List[Dict[str, Any]] = []
    if not LAYOUT_DIR.exists():
        return results
    for json_file in sorted(LAYOUT_DIR.rglob("*.json")):
        results.append(
            {
                "name": json_file.stem,
                "path": str(json_file),
                "category": json_file.parent.name,
                "file_size": json_file.stat().st_size,
            }
        )
    return results


def load_layout(name: str) -> Optional[Dict[str, Any]]:
    """
    Find a layout file by stem name (e.g. "industrial_005") and return its
    parsed JSON.  Returns None when no matching file is found.
    """
    if not LAYOUT_DIR.exists():
        return None
    for json_file in LAYOUT_DIR.rglob("*.json"):
        if json_file.stem == name:
            with json_file.open("r", encoding="utf-8") as fh:
                return json.load(fh)
    return None


def save_layout(name: str, data: dict) -> Optional[Path]:
    """
    Find the layout file by stem name and overwrite it with *data*.
    Returns the Path written, or None if no matching file was found.
    """
    if not LAYOUT_DIR.exists():
        return None
    for json_file in LAYOUT_DIR.rglob("*.json"):
        if json_file.stem == name:
            with json_file.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            return json_file
    return None


def validate_layout(data: dict) -> bool:
    """
    Return True when *data* contains all required top-level keys.
    Required: layoutId, outline, rooms.
    """
    return REQUIRED_KEYS.issubset(data.keys())


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")


def _sanitize_name(name: str) -> str:
    """Reduce *name* to a safe file stem (alphanumerics, '_' and '-')."""
    cleaned = _SAFE_NAME_RE.sub("_", (name or "").strip()).strip("_")
    return cleaned or "AI_layout"


def save_generated_layout(name: str, data: dict, subdir: str = "AI_GENERATED") -> Path:
    """
    Write a NEW (AI-generated) layout into LAYOUT_DIR/<subdir>/<name>.json,
    creating the subdirectory if needed. Unlike save_layout(), this creates a new
    file rather than overwriting an existing one. Returns the Path written.
    """
    target_dir = LAYOUT_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{_sanitize_name(name)}.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path
