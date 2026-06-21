from __future__ import annotations
"""
Utility functions for reading/writing layouts in both:
  Single-level  : { "outline": [...], "rooms": [...], "structure": [...] }
  Multi-level   : { "levels": { "level_01": { "outline": [...], "rooms": [...], "structure": [...] },
                                "level_02": { ... } } }

Import this module in any node that needs to handle both formats.
"""

TOLERANCE = 0.01


def is_multilevel(layout: dict) -> bool:
    return isinstance(layout.get("levels"), dict)


def get_level_keys(layout: dict) -> list[str]:
    """Sorted level keys e.g. ['level_01', 'level_02']. Single-level returns ['level_01']."""
    if is_multilevel(layout):
        return sorted(layout["levels"].keys())
    return ["level_01"]


def get_level_count(layout: dict) -> int:
    return len(get_level_keys(layout)) if is_multilevel(layout) else 1


def get_outline(layout: dict, level_key: str | None = None) -> list:
    if is_multilevel(layout):
        lk = level_key or get_level_keys(layout)[0]
        return layout["levels"][lk].get("outline", [])
    return layout.get("outline", [])


def get_rooms(layout: dict, level_key: str | None = None) -> list:
    if is_multilevel(layout):
        lk = level_key or get_level_keys(layout)[0]
        return layout["levels"][lk].get("rooms", [])
    return layout.get("rooms", [])


def get_structure(layout: dict, level_key: str | None = None) -> list:
    """Return structure for a specific level, or flat list across all levels."""
    if is_multilevel(layout):
        if level_key:
            return layout["levels"][level_key].get("structure", [])
        result = []
        for lk in get_level_keys(layout):
            result.extend(layout["levels"][lk].get("structure", []))
        return result
    return layout.get("structure", [])


def set_structure(layout: dict, structure: list, level_key: str) -> dict:
    if is_multilevel(layout):
        layout["levels"][level_key]["structure"] = structure
    else:
        layout["structure"] = structure
    return layout


def iter_all_structure(layout: dict):
    """Yield (level_key, element) for every element across all levels."""
    if is_multilevel(layout):
        for lk in get_level_keys(layout):
            for el in layout["levels"][lk].get("structure", []):
                yield lk, el
    else:
        for el in layout.get("structure", []):
            yield "level_01", el


def find_element_in_layout(layout: dict, element_id: str) -> tuple[str | None, dict | None]:
    """Return (level_key, element) or (None, None) if not found."""
    for lk, el in iter_all_structure(layout):
        if el.get("id") == element_id:
            return lk, el
    return None, None


def get_level_index(layout: dict, level_key: str) -> int:
    """0-based index (0 = ground floor = level_01)."""
    if not is_multilevel(layout):
        return 0
    keys = get_level_keys(layout)
    return keys.index(level_key) if level_key in keys else 0


def levels_above_count(layout: dict, level_key: str) -> int:
    """Number of levels with higher index than level_key."""
    if not is_multilevel(layout):
        return 0
    keys = get_level_keys(layout)
    idx = keys.index(level_key) if level_key in keys else 0
    return len(keys) - 1 - idx


def load_multiplier_for_level(layout: dict, level_key: str) -> int:
    """
    How many floor slabs does a column at this level carry?
    level_01 in a 2-storey building carries 2 slabs (its own + level_02's).
    Top level always carries 1 slab.
    """
    if not is_multilevel(layout):
        return 1
    keys = get_level_keys(layout)
    n = len(keys)
    idx = keys.index(level_key) if level_key in keys else 0
    return n - idx  # level_01 → n, level_02 → n-1, ..., top → 1


def has_column_above(layout: dict, col_pos: list, level_key: str) -> bool:
    """True if ANY level above level_key has a column at col_pos (within TOLERANCE)."""
    if not is_multilevel(layout):
        return False
    keys = get_level_keys(layout)
    if level_key not in keys:
        return False
    idx = keys.index(level_key)
    x0, y0 = round(col_pos[0], 3), round(col_pos[1], 3)
    for lk in keys[idx + 1:]:
        for el in layout["levels"][lk].get("structure", []):
            if len(el.get("geometry", [])) == 1:
                x1, y1 = round(el["geometry"][0][0], 3), round(el["geometry"][0][1], 3)
                if abs(x1 - x0) < TOLERANCE and abs(y1 - y0) < TOLERANCE:
                    return True
    return False


def get_all_rooms(layout: dict) -> list:
    """All rooms across every level (flat list)."""
    if is_multilevel(layout):
        rooms = []
        for lk in get_level_keys(layout):
            rooms.extend(layout["levels"][lk].get("rooms", []))
        return rooms
    return layout.get("rooms", [])
