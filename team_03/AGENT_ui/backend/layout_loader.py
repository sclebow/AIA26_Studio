"""
Utilities for discovering, loading, and validating layout JSON files.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

# Absolute path to the shared layout directory.
LAYOUT_DIR = Path(
    r"E:\IAAC Local GIT Repositories\AIA26_Studio\team_03\layout"
)

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
