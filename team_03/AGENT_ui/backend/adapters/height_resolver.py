"""
height_resolver.py — Resolve furniture/equipment height from multiple sources.

Resolution order:
  1. Direct attribute — furniture_item["attributes"]["height"]
  2. Knowledge base lookup — worker_ergonomics.json workbench/surface rules
  3. Keyword fallback — _TYPE_HEIGHT table from nodes/reachability.py
  4. Default — 0.9 m

The knowledge base is loaded once at module import time from
team_03/python/knowledge/industrial/worker_ergonomics.json.
The _TYPE_HEIGHT keyword table is replicated from reachability.py so this
module has no runtime import dependency on the pipeline code.
"""

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_KNOWLEDGE_DIR = (
    Path(__file__).resolve().parents[3] / "python" / "knowledge" / "industrial"
)
_ERGONOMICS_FILE = _KNOWLEDGE_DIR / "worker_ergonomics.json"

# ---------------------------------------------------------------------------
# Default height when nothing else resolves
# ---------------------------------------------------------------------------

_DEFAULT_HEIGHT = 0.9  # metres

# ---------------------------------------------------------------------------
# _TYPE_HEIGHT keyword table — mirrored from nodes/reachability.py
# Tuple of keyword tuples mapped to estimated functional height in metres.
# Order matters: first match wins.
# ---------------------------------------------------------------------------

_TYPE_HEIGHT: list[tuple[tuple[str, ...], float]] = [
    (("shelf", "rack"),              1.6),
    (("table", "desk", "counter"),   0.85),
    (("machine", "cnc", "conveyor"), 1.0),
]

# ---------------------------------------------------------------------------
# Knowledge-base name→height lookup
# Built from worker_ergonomics.json at import time.
#
# Mapping strategy: the ergonomics JSON uses rule names like
#   "workbench_height_light_assembly" → 0.9 m
#   "workbench_height_heavy_assembly" → 0.8 m
# We extract any fact whose rule name contains height-related keywords and
# map its constituent tokens to the height value so a fuzzy name lookup
# can match them at runtime.
# ---------------------------------------------------------------------------

_KB_NAME_TO_HEIGHT: dict[str, float] = {}
_KB_LOAD_ERROR: str | None = None

def _load_knowledge_base() -> None:
    global _KB_LOAD_ERROR
    if not _ERGONOMICS_FILE.exists():
        _KB_LOAD_ERROR = f"knowledge base not found: {_ERGONOMICS_FILE}"
        return
    try:
        with open(_ERGONOMICS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        for fact in data.get("facts", []):
            rule = fact.get("rule", "")
            value_m = fact.get("value_m")
            if value_m is None:
                continue
            # Index by the full rule name (lowercased, underscores stripped)
            clean = rule.lower().replace("_", " ")
            _KB_NAME_TO_HEIGHT[clean] = float(value_m)
            # Also index each meaningful token individually for fuzzy lookup
            for token in rule.lower().split("_"):
                if len(token) > 3 and token not in ("from", "with", "for", "and"):
                    _KB_NAME_TO_HEIGHT.setdefault(token, float(value_m))
    except Exception as exc:
        _KB_LOAD_ERROR = str(exc)


_load_knowledge_base()


# ---------------------------------------------------------------------------
# Internal lookup helpers
# ---------------------------------------------------------------------------

def _lookup_knowledge_base(name: str) -> float | None:
    """
    Try to match furniture name against the knowledge-base entries.
    Performs a simple substring search: returns the height of the first
    knowledge-base key that appears as a substring in `name`, or whose
    tokens all appear in `name`.

    Returns None if no match found.
    """
    if not _KB_NAME_TO_HEIGHT:
        return None
    name_lower = name.lower()

    # Exact substring match against full rule labels first
    for key, height in _KB_NAME_TO_HEIGHT.items():
        if len(key) > 5 and key in name_lower:
            return height

    # Single-token match (e.g. "workbench" matches "assembly workbench")
    for key, height in _KB_NAME_TO_HEIGHT.items():
        if " " not in key and key in name_lower:
            return height

    return None


def _keyword_fallback(name: str) -> float | None:
    """
    Match furniture name against the _TYPE_HEIGHT keyword tuples.
    Returns the height for the first matching keyword group, or None.
    """
    name_lower = name.lower()
    for keywords, height in _TYPE_HEIGHT:
        if any(kw in name_lower for kw in keywords):
            return height
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_height(furniture_item: dict) -> float:
    """
    Resolve the functional height of a furniture/equipment item.

    Resolution order:
      1. furniture_item["attributes"]["height"]  (explicit value in layout JSON)
      2. Knowledge base lookup by name           (worker_ergonomics.json)
      3. Keyword fallback (_TYPE_HEIGHT table)   (from reachability.py)
      4. Default: 0.9 m

    Args:
        furniture_item: a single furniture/object dict from the layout JSON,
                        expected to have keys like "name", "id", "attributes".

    Returns:
        height in metres as a float.
    """
    # 1. Direct attribute
    height = furniture_item.get("attributes", {}).get("height")
    if height is not None:
        try:
            return float(height)
        except (TypeError, ValueError):
            pass

    name = (
        furniture_item.get("name")
        or furniture_item.get("type")
        or furniture_item.get("id")
        or ""
    )

    # 2. Knowledge base lookup
    height = _lookup_knowledge_base(name)
    if height is not None:
        return height

    # 3. Keyword fallback
    height = _keyword_fallback(name)
    if height is not None:
        return height

    # 4. Default
    return _DEFAULT_HEIGHT


def resolve_heights_for_layout(layout: dict) -> dict[str, float]:
    """
    Resolve heights for every furniture/object item in the layout.

    Args:
        layout: parsed layout JSON

    Returns:
        dict mapping object id (or name as fallback) to height in metres.
    """
    objects = layout.get("furniture") or layout.get("objects") or []
    result: dict[str, float] = {}
    for item in objects:
        key = item.get("id") or item.get("name") or "unknown"
        result[key] = resolve_height(item)
    return result


def get_knowledge_base_status() -> dict:
    """
    Return status information about the knowledge base load.

    Useful for health checks and debugging.
    """
    return {
        "loaded": bool(_KB_NAME_TO_HEIGHT),
        "entry_count": len(_KB_NAME_TO_HEIGHT),
        "source": str(_ERGONOMICS_FILE),
        "error": _KB_LOAD_ERROR,
    }
