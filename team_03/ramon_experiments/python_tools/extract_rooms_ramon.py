"""
GHPython component: Extract destination room name(s) from layout_json.

Reads the rooms list from a layout JSON string and outputs either:
  - one specific room (when `room_filter` matches a room name or id), OR
  - all rooms (when `room_filter` is empty / None / "all" / "*").

INPUTS:
    layout_json  (str)  - The layout JSON string. If empty/invalid,
                          falls back to layout_input/layout_schema.json on disk.
    room_filter  (str)  - Optional. Name or id of a single room to extract.
                          Leave empty (or use "all" / "*") to return every room.

OUTPUTS:
    rooms  (list)  - List of room names matching the filter (all rooms if none).
    ids    (list)  - Corresponding room ids, in the same order as `rooms`.
    info   (str)   - Status / debug message.
"""

import json

LAYOUT_FILE_FALLBACK = r"C:\IAAC Repositories 2026\AIA26_Studio\layout_input\layout_schema.json"


def _coerce_to_string(value):
    """Accept str, list of str, or anything stringifiable; join lists with newlines."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return "\n".join(str(v) for v in value)
    except TypeError:
        return str(value)


def _load_layout_text(wired_value):
    """Return a valid layout JSON string from the wire, or from disk as fallback."""
    try:
        candidate = _coerce_to_string(wired_value)
        if candidate and candidate.strip():
            json.loads(candidate)
            return candidate, "wire"
    except Exception:
        pass
    try:
        with open(LAYOUT_FILE_FALLBACK, "r") as f:
            text = f.read()
        json.loads(text)
        return text, "disk fallback"
    except Exception:
        return None, None


# ---------- Outputs ----------
rooms = []
ids = []
info = ""

# Resolve room_filter (treat missing input as "all")
try:
    _ = room_filter
    if room_filter is None:
        filter_value = ""
    else:
        filter_value = str(room_filter).strip()
except NameError:
    filter_value = ""

want_all = filter_value == "" or filter_value.lower() in ("all", "*")

# Load layout
layout_text, source = _load_layout_text(layout_json if "layout_json" in dir() else None)
if layout_text is None:
    info = "[ERROR] Could not load layout_json (wire empty/invalid AND disk fallback failed)"
else:
    try:
        layout = json.loads(layout_text)
        room_list = layout.get("rooms", [])
        if not isinstance(room_list, list) or len(room_list) == 0:
            info = "[ERROR] Layout has no 'rooms' list"
        elif want_all:
            for r in room_list:
                rooms.append(r.get("name", ""))
                ids.append(r.get("id", ""))
            info = "[OK] Returning ALL rooms ({}) | source: {}".format(len(rooms), source)
        else:
            target = filter_value.lower()
            matched = None
            for r in room_list:
                name = str(r.get("name", "")).lower()
                rid = str(r.get("id", "")).lower()
                if name == target or rid == target:
                    matched = r
                    break
            if matched is None:
                available = [r.get("name", "?") for r in room_list]
                info = "[NO MATCH] Room '{}' not found. Available: {} | source: {}".format(
                    filter_value, ", ".join(available), source
                )
            else:
                rooms.append(matched.get("name", ""))
                ids.append(matched.get("id", ""))
                info = "[OK] Returning room '{}' (id={}) | source: {}".format(
                    rooms[0], ids[0], source
                )
    except Exception as e:
        info = "[ERROR] Failed to parse layout: {}".format(e)
