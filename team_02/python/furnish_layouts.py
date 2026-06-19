"""
Full furnishing pass for the four Sensi example layouts (Session 2, follow-up).

Replaces each layout's `furniture` list with a re-designed, realistically-scaled
set: every piece sized to a plausible real-world footprint, beds with access +
nightstands, bathrooms fitted with toilet / vanity / shower, kitchens with a sink
and fridge, and nothing parked in a doorway or floating in dead space. Rooms,
doors (already corrected), windows, structure and mep are left untouched, and
PLANT COUNTS per room are preserved so the demo's biophilic signal is unchanged.

Run check_layout_geometry.py afterwards — it must report zero.

    python team_02/python/furnish_layouts.py
"""
from __future__ import annotations

import json
import os


def F(fid, name, room, ftype, material, x0, y0, x1, y1):
    return {
        "id": fid,
        "name": name,
        "geometry": [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]],
        "attributes": {"roomId": room, "type": ftype, "material": material},
    }


# ─────────────────────────────────────────────────────────────────────────────
LAYOUTS = {
    "layout_201.json": [
        # Living (r1)
        F("furn-1",  "Living Sofa",      "room-1", "sofa",       "fabric",  0.6, 0.3, 3.0, 1.2),
        F("furn-2",  "Coffee Table",     "room-1", "table",      "wood",    1.25, 1.7, 2.35, 2.3),
        F("furn-3",  "Living Plant",     "room-1", "plant",      "natural", 0.3, 4.3, 0.8, 4.8),
        # Kitchen (r2)
        F("furn-4",  "Kitchen Island",   "room-2", "island",     "stone",   8.6, 1.3, 10.2, 2.2),
        F("furn-5",  "Kitchen Counter",  "room-2", "counter",    "ceramic", 8.2, 3.4, 11.6, 4.0),
        F("furn-6",  "Kitchen Sink",     "room-2", "sink",       "metal",   7.6, 3.4, 8.2, 4.0),
        F("furn-7",  "Refrigerator",     "room-2", "fridge",     "metal",   11.3, 0.3, 12.0, 1.0),
        # Master Bedroom (r3)
        F("furn-8",  "Master Bed",       "room-3", "bed",        "fabric",  0.4, 6.0, 1.9, 8.0),
        F("furn-9",  "Master Nightstand","room-3", "nightstand", "wood",    1.9, 7.55, 2.35, 7.95),
        F("furn-10", "Master Wardrobe",  "room-3", "dresser",    "wood",    4.4, 5.6, 5.0, 7.6),
        # Guest Bedroom (r4)
        F("furn-11", "Guest Bed",        "room-4", "bed",        "fabric",  5.4, 6.0, 6.9, 8.0),
        F("furn-12", "Guest Nightstand", "room-4", "nightstand", "wood",    6.9, 7.55, 7.35, 7.95),
        F("furn-13", "Guest Desk",       "room-4", "desk",       "wood",    9.4, 5.5, 10.0, 6.7),
        # Bathroom (r5)
        F("furn-14", "Toilet",           "room-5", "toilet",     "ceramic", 11.5, 4.6, 11.9, 5.25),
        F("furn-15", "Vanity",           "room-5", "vanity",     "wood",    11.4, 5.7, 12.0, 6.5),
        F("furn-16", "Shower",           "room-5", "shower",     "ceramic", 10.15, 6.9, 11.0, 7.8),
    ],
    "layout_202.json": [
        # Living Area (r1) — no plants (this demo is deliberately plant-free)
        F("furn-1",  "Dining Table",     "room-1", "table",      "glass",   0.6, 0.5, 2.0, 1.3),
        F("furn-2",  "Sofa",             "room-1", "sofa",       "fabric",  0.6, 2.4, 2.8, 3.3),
        # Kitchen (r2)
        F("furn-3",  "Kitchen Counter",  "room-2", "counter",    "stone",   6.1, 0.0, 9.4, 0.6),
        F("furn-4",  "Kitchen Sink",     "room-2", "sink",       "metal",   9.4, 0.0, 10.0, 0.6),
        F("furn-5",  "Kitchen Island",   "room-2", "island",     "metal",   6.6, 1.6, 8.2, 2.5),
        F("furn-6",  "Refrigerator",     "room-2", "fridge",     "metal",   9.3, 1.5, 10.0, 2.2),
        # Bedroom (r3)
        F("furn-7",  "Bed",              "room-3", "bed",        "fabric",  0.5, 5.0, 2.0, 7.0),
        F("furn-8",  "Bedside Table",    "room-3", "nightstand", "metal",   2.0, 6.55, 2.45, 6.95),
        F("furn-9",  "Wardrobe",         "room-3", "dresser",    "wood",    3.0, 4.0, 4.6, 4.6),
        # Study (r4)
        F("furn-10", "Study Desk",       "room-4", "desk",       "metal",   7.4, 4.0, 8.6, 4.6),
        F("furn-11", "Bookshelf",        "room-4", "bookshelf",  "metal",   7.0, 4.05, 7.3, 4.95),
        # Bathroom (r5) — 3 m² half-bath: toilet + sink only
        F("furn-12", "Toilet",           "room-5", "toilet",     "ceramic", 7.15, 6.25, 7.55, 6.9),
        F("furn-13", "Sink",             "room-5", "sink",       "ceramic", 9.3, 6.3, 9.8, 6.75),
    ],
    "layout_203.json": [
        # Open Living-Dining (r2) — 3 plants preserved
        F("furn-1",  "Living Sofa",      "room-2", "sofa",       "fabric",  1.0, 2.2, 3.6, 3.1),
        F("furn-2",  "Dining Table",     "room-2", "table",      "wood",    5.5, 1.2, 7.3, 2.1),
        F("furn-3",  "Living Plant 1",   "room-2", "plant",      "natural", 3.5, 0.3, 4.0, 0.8),
        F("furn-4",  "Living Plant 2",   "room-2", "plant",      "natural", 0.4, 4.5, 0.9, 5.0),
        # Kitchen (r3)
        F("furn-5",  "Kitchen Island",   "room-3", "island",     "stone",   10.0, 1.0, 11.8, 1.9),
        F("furn-6",  "Kitchen Counter",  "room-3", "counter",    "ceramic", 13.4, 0.5, 14.0, 3.5),
        F("furn-7",  "Kitchen Sink",     "room-3", "sink",       "metal",   9.2, 3.4, 9.8, 4.0),
        F("furn-8",  "Refrigerator",     "room-3", "fridge",     "metal",   9.1, 0.1, 9.8, 0.8),
        # Master Bedroom (r4)
        F("furn-9",  "Master Bed",       "room-4", "bed",        "fabric",  10.2, 7.0, 12.0, 9.0),
        F("furn-10", "Master Nightstand L","room-4","nightstand","wood",    9.75, 8.55, 10.2, 8.95),
        F("furn-11", "Master Nightstand R","room-4","nightstand","wood",    12.0, 8.55, 12.45, 8.95),
        F("furn-12", "Master Wardrobe",  "room-4", "dresser",    "wood",    12.0, 4.0, 14.0, 4.6),
        F("furn-13", "Master Plant",     "room-4", "plant",      "natural", 9.3, 5.7, 9.8, 6.2),
        # Children's Bedroom (r5)
        F("furn-14", "Children's Bed",   "room-5", "bed",        "fabric",  2.7, 7.0, 4.1, 8.9),
        F("furn-15", "Children's Desk",  "room-5", "desk",       "wood",    4.2, 6.0, 5.2, 6.5),
        # Guest Room (r6)
        F("furn-16", "Guest Bed",        "room-6", "bed",        "fabric",  7.0, 7.0, 8.5, 9.0),
        F("furn-17", "Guest Nightstand", "room-6", "nightstand", "wood",    8.5, 8.55, 8.95, 8.95),
        # Bathroom (r7)
        F("furn-18", "Toilet",           "room-7", "toilet",     "ceramic", 2.7, 4.1, 3.1, 4.75),
        F("furn-19", "Vanity",           "room-7", "vanity",     "wood",    3.3, 4.1, 4.0, 4.6),
        F("furn-20", "Shower",           "room-7", "shower",     "ceramic", 4.0, 5.0, 4.9, 5.9),
    ],
    "layout_204.json": [
        # Living Room (r1) — 1 plant preserved
        F("furn-1",  "Living Sofa",      "room-1", "sofa",       "fabric",  0.8, 0.4, 3.4, 1.3),
        F("furn-2",  "Coffee Table",     "room-1", "table",      "wood",    1.6, 1.9, 2.7, 2.5),
        F("furn-3",  "Living Plant",     "room-1", "plant",      "natural", 5.2, 3.9, 5.7, 4.4),
        # Dining Room (r2)
        F("furn-4",  "Dining Table",     "room-2", "table",      "wood",    6.9, 1.8, 8.7, 2.8),
        # Kitchen (r3)
        F("furn-5",  "Kitchen Island",   "room-3", "island",     "stone",   10.2, 1.1, 11.9, 2.0),
        F("furn-6",  "Kitchen Counter",  "room-3", "counter",    "ceramic", 10.3, 0.0, 12.8, 0.6),
        F("furn-7",  "Kitchen Sink",     "room-3", "sink",       "metal",   9.7, 0.0, 10.3, 0.6),
        F("furn-8",  "Refrigerator",     "room-3", "fridge",     "metal",   12.3, 4.2, 13.0, 4.9),
        # Pantry (r4)
        F("furn-9",  "Pantry Shelving",  "room-4", "bookshelf",  "wood",    15.4, 0.3, 15.9, 2.2),
        # Powder Room (r5) — half-bath: toilet + vanity
        F("furn-10", "Powder Toilet",    "room-5", "toilet",     "ceramic", 13.2, 3.0, 13.6, 3.65),
        F("furn-11", "Powder Vanity",    "room-5", "vanity",     "wood",    15.4, 2.7, 16.0, 3.5),
        # Master Bedroom (r7)
        F("furn-12", "Master Bed",       "room-7", "bed",        "fabric",  0.6, 9.0, 2.4, 11.0),
        F("furn-13", "Master Nightstand L","room-7","nightstand","wood",    0.15, 10.55, 0.6, 10.95),
        F("furn-14", "Master Nightstand R","room-7","nightstand","wood",    2.4, 10.55, 2.85, 10.95),
        F("furn-15", "Master Wardrobe",  "room-7", "dresser",    "wood",    4.4, 6.3, 5.0, 8.7),
        # Master Ensuite (r8)
        F("furn-16", "Ensuite Toilet",   "room-8", "toilet",     "ceramic", 5.2, 8.2, 5.6, 8.85),
        F("furn-17", "Ensuite Vanity",   "room-8", "vanity",     "wood",    6.3, 8.2, 6.9, 9.0),
        F("furn-18", "Ensuite Shower",   "room-8", "shower",     "ceramic", 5.2, 9.95, 6.1, 10.85),
        # Study (r9)
        F("furn-19", "Study Desk",       "room-9", "desk",       "wood",    5.3, 7.4, 6.5, 8.0),
        F("furn-20", "Study Bookshelf",  "room-9", "bookshelf",  "wood",    5.0, 6.1, 5.3, 7.0),
        # Bedroom 2 (r10)
        F("furn-21", "Bedroom 2 Bed",    "room-10", "bed",       "fabric",  7.4, 9.0, 8.9, 11.0),
        F("furn-22", "Bedroom 2 Nightstand","room-10","nightstand","wood",  8.9, 10.55, 9.35, 10.95),
        F("furn-23", "Bedroom 2 Desk",   "room-10", "desk",      "wood",    9.6, 6.0, 10.8, 6.6),
        F("furn-24", "Bedroom 2 Wardrobe","room-10","dresser",   "wood",    7.0, 6.3, 7.6, 8.1),
        # Family Bathroom (r11)
        F("furn-25", "Family Bath Toilet","room-11","toilet",    "ceramic", 11.1, 6.2, 11.5, 6.85),
        F("furn-26", "Family Bath Vanity","room-11","vanity",    "wood",    12.4, 6.2, 13.0, 6.8),
        F("furn-27", "Family Bath Shower","room-11","shower",    "ceramic", 11.1, 7.4, 12.0, 8.3),
        # Linen Store (r12)
        F("furn-28", "Linen Shelving",   "room-12", "bookshelf", "wood",    12.5, 8.8, 12.9, 10.7),
        # Bedroom 3 (r13)
        F("furn-29", "Bedroom 3 Bed",    "room-13", "bed",       "fabric",  13.6, 9.0, 15.1, 11.0),
        F("furn-30", "Bedroom 3 Nightstand","room-13","nightstand","wood",  15.1, 10.55, 15.55, 10.95),
        F("furn-31", "Bedroom 3 Wardrobe","room-13","dresser",   "wood",    13.0, 6.4, 13.6, 8.4),
        F("furn-32", "Bedroom 3 Desk",   "room-13", "desk",      "wood",    14.95, 6.0, 15.95, 6.6),
    ],
}


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "randomized_layouts")
    for name, furniture in LAYOUTS.items():
        path = os.path.join(root, name)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        rooms = {r["id"] for r in data.get("rooms", [])}
        bad = [f["id"] for f in furniture if f["attributes"]["roomId"] not in rooms]
        if bad:
            raise SystemExit(f"{name}: furniture references unknown room(s): {bad}")
        data["furniture"] = furniture
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"{name}: {len(furniture)} pieces")


if __name__ == "__main__":
    main()
