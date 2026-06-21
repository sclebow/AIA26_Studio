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


# ---------------------------------------------------------------------------
# Version history — the original base layout + every approved revision saved by
# the pipeline to team_03/output/<name>_<timestamp>_final.json (close_session).
# ---------------------------------------------------------------------------

# "industrial_005_2026-06-07_22-41_final" → date "2026-06-07", time "22-41"
_VERSION_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})_final$")


def _output_dir() -> Path:
    """team_03/output/ — sibling of team_03/layout/, holds approved revisions."""
    return (LAYOUT_DIR.parent / "output").resolve()


def _version_label(stem: str, name: str) -> str:
    """Human-friendly label from an output file stem.

    "industrial_005_2026-06-07_22-41_final" → "2026-06-07 22:41".
    Falls back to the raw stem (minus the base name prefix) when it doesn't
    match the standard close_session timestamp pattern.
    """
    m = _VERSION_RE.search(stem)
    if m:
        return f"{m.group(1)} {m.group(2).replace('-', ':')}"
    rest = stem[len(name):].lstrip("_") if stem.startswith(name) else stem
    return rest or stem


def list_versions(name: str) -> List[Dict[str, Any]]:
    """Return the version history for base layout *name*, oldest → newest.

    The first entry is always the original base layout (kind="original");
    the rest are the timestamped revisions in team_03/output/ whose file name
    starts with "<name>_" and ends in "_final.json" (kind="version"), sorted
    by modification time so the slider runs original → latest.

    Each entry: {id, label, kind, file, timestamp, file_size}.
        id   — base name (original) or output file stem (version)
        file — output file name (versions only), used by load_version()
    """
    versions: List[Dict[str, Any]] = []

    base_path: Optional[Path] = None
    if LAYOUT_DIR.exists():
        for json_file in LAYOUT_DIR.rglob(f"{name}.json"):
            base_path = json_file
            break
    if base_path is not None:
        versions.append(
            {
                "id": name,
                "label": "Original",
                "kind": "original",
                "file": None,
                "timestamp": base_path.stat().st_mtime,
                "file_size": base_path.stat().st_size,
            }
        )

    out = _output_dir()
    if out.exists():
        revs = [
            f for f in out.glob(f"{name}_*_final.json")
            # Guard against a longer base name matching a shorter one: the char
            # right after the prefix must start a date (digit), not a letter.
            if f.name[len(name) + 1: len(name) + 2].isdigit()
        ]
        for f in sorted(revs, key=lambda p: p.stat().st_mtime):
            versions.append(
                {
                    "id": f.stem,
                    "label": _version_label(f.stem, name),
                    "kind": "version",
                    "file": f.name,
                    "timestamp": f.stat().st_mtime,
                    "file_size": f.stat().st_size,
                }
            )

    return versions


def load_version(file_name: str) -> Optional[Dict[str, Any]]:
    """Load a saved revision JSON from team_03/output/ by file name.

    Only reads files directly inside the output directory (basename is taken,
    so path-traversal segments are stripped). Returns None when not found.
    """
    out = _output_dir()
    if not out.exists():
        return None
    safe = Path(file_name).name  # strip any directory components
    if not safe.endswith(".json"):
        safe += ".json"
    path = out / safe
    if path.exists() and path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    return None
