"""
One-shot corrector for the four Sensi example layouts.

Applies the MINIMAL, score-neutral geometry moves agreed in Session 2 to clear
every defect found by check_layout_geometry.py. It only ever changes furniture
RECTANGLES and door SEGMENTS (positions/sizes) and removes one corridor-blocking
plant — never room attributes, plant counts elsewhere, materials, types,
connectsRooms or window roomIds — so the attribute-driven comfort scores are
unchanged. Every move cites the rule it satisfies.

Idempotent: it sets absolute coordinates, so re-running is a no-op. Reads/writes
team_02/randomized_layouts/*.json with indent=2 (normalising the older
one-coordinate-per-line files to match Layout-204's style).

    python team_02/python/fix_example_layouts.py
"""
from __future__ import annotations

import json
import os


def rect(x0, y0, x1, y1):
    """Closed axis-aligned rectangle in the layouts' vertex order."""
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]


def seg(ax, ay, bx, by):
    return [[ax, ay], [bx, by]]


# layout file -> {furniture: {id: rect}, doors: {id: seg}, remove: [ids]}
EDITS = {
    "layout_201.json": {
        "furniture": {
            # Master Bed off the bedroom door: slide to the W wall, right edge at
            # the door jamb (x3) → 0.6 m landing into the room.
            "furn-6": rect(0, 5.5, 3, 7.5),
            # Guest Bed off its door (was 0.2 m): slide W so right edge clears the
            # door span (x8).
            "furn-8": rect(5, 5.2, 8, 7.7),
            # Living plant out of the Living↔Hallway door landing (was 0.1 m in).
            "furn-3": rect(5.5, 4.0, 6.0, 4.5),
        },
        "doors": {
            # Draw the bathroom door at its true 0.80 m leaf (was drawn 0.90).
            "door-5": seg(10, 4.1, 10, 4.9),
        },
    },
    "layout_202.json": {
        "furniture": {
            # Kitchen Island off the Living↔Kitchen door: shift E so left edge
            # clears the 0.6 m landing.
            "furn-4": rect(6.7, 1.5, 9.7, 2.8),
            # Study Desk + Bookshelf both onto the S wall so both study doors
            # (W and N) get clear landings/swings. The bookshelf stays clear of
            # the E-wall window (its y-range sits below the glazing).
            "furn-7": rect(7.0, 4.0, 9.0, 4.8),
            "furn-8": rect(9.0, 4.0, 10.0, 4.5),
        },
        "doors": {
            # Living↔Bedroom door was boxed by the sofa (one side) and bed (other)
            # with no clear swing. Slide it E along the same wall past the sofa
            # (x≥4.5) — one move fixes the swing + both approaches, no furniture
            # disturbed, adjacency unchanged.
            "door-2": seg(4.6, 4, 5.5, 4),
            # True 0.80 m leaves (were drawn 0.90).
            "door-4": seg(7, 5.05, 7, 5.85),
            "door-5": seg(8.05, 6, 8.85, 6),
        },
    },
    "layout_203.json": {
        "furniture": {
            # Living plant out of the cramped L-leg (blocked two doors) to a clear
            # spot by the south window — stays in the same room (score-neutral).
            "furn-3": rect(3.5, 0.3, 4.0, 0.8),
            # Dining Table shifted 0.1 m W to clear the Living↔Kitchen door landing.
            "furn-2": rect(5.4, 1, 8.4, 3),
            # Kitchen Counter relocated to the E wall so the Kitchen↔Master door has
            # a clear N-wall landing; island trimmed to keep a ~1.1 m work aisle.
            "furn-6": rect(13.5, 0.5, 14, 3.5),
            "furn-5": rect(10, 1, 12.4, 2.5),
            # Children's room re-set: bed off the foyer door, desk to the SE corner
            # clear of the guest door; guest bed to the NE corner so the shared
            # Children↔Guest door swings clear into the guest room.
            "furn-10": rect(2.6, 6.5, 5.1, 8.5),
            "furn-11": rect(5.1, 6.0, 6.0, 6.9),
            "furn-12": rect(7.0, 7.0, 9.0, 9.0),
            # Master Bed off the laundry door (slide E to x9.7).
            "furn-7": rect(9.7, 5, 12.7, 7.5),
            # Master Wardrobe off the E window (it sat flush over the glazing):
            # relocate to the free N-wall segment E of the N window.
            "furn-8": rect(12, 8, 14, 9),
        },
        "doors": {
            # True leaf widths (1.00 / 0.80 / 0.80; were all drawn 0.90).
            "door-1": seg(0.45, 6, 1.45, 6),
            "door-6": seg(2, 4.55, 2, 5.35),
            "door-7": seg(6.05, 4, 6.85, 4),
        },
    },
    "layout_204.json": {
        "furniture": {
            # Kitchen Island trimmed 0.1 m each side to clear the Dining↔Kitchen
            # and Kitchen↔Pantry door landings.
            "furn-5": rect(10.1, 1, 12.4, 2.3),
            # Three bedroom beds were parked 0.5 m in front of their hallway doors:
            # move each to the far wall of its own room.
            "furn-7": rect(0.5, 8.7, 3.5, 10.7),     # Master
            "furn-10": rect(7.3, 9.0, 10.3, 11.0),   # Bedroom 2 (bed N)
            "furn-11": rect(10.0, 6.3, 11.0, 7.3),   # Bedroom 2 desk → SE corner
            "furn-12": rect(13.5, 8.5, 15.5, 11.0),  # Bedroom 3
            # Master Wardrobe shortened so it clears the ensuite door landing.
            "furn-8": rect(4, 6.3, 4.9, 8.9),
            # Study Desk to the back wall so the study door landing/ swing is clear.
            "furn-9": rect(5.3, 7.3, 6.7, 8.0),
        },
        "doors": {
            # Draw every door at its true stated width (cased openings 1.40 / 1.10
            # and leaves 0.80 / 0.70 were all drawn at 0.90).
            "door-3": seg(6, 1.75, 6, 3.15),
            "door-4": seg(9.5, 1.9, 9.5, 3.0),
            "door-5": seg(13, 1.05, 13, 1.85),
            "door-7": seg(14.05, 5, 14.85, 5),
            "door-9": seg(5, 9.05, 5, 9.85),
            "door-10": seg(6.05, 6, 6.85, 6),
            "door-12": seg(11.55, 6, 12.35, 6),
            "door-14": seg(11, 9.3, 11, 10.0),
        },
        # Hallway Plant halves the 1.0 m corridor and no object fits → remove it.
        "remove": ["furn-13"],
    },
}


def apply(path, spec):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    changed = 0
    seen = set()

    furn_edits = spec.get("furniture", {})
    remove = set(spec.get("remove", []))
    kept = []
    for f in data.get("furniture", []):
        seen.add(f["id"])
        if f["id"] in remove:
            changed += 1
            continue
        if f["id"] in furn_edits:
            f["geometry"] = furn_edits[f["id"]]
            changed += 1
        kept.append(f)
    data["furniture"] = kept

    door_edits = spec.get("doors", {})
    for d in data.get("doors", []):
        seen.add(d["id"])
        if d["id"] in door_edits:
            d["geometry"] = door_edits[d["id"]]
            changed += 1

    # An EDIT id that matches nothing means a typo silently did nothing — surface it.
    # (A `remove` id that's already gone is fine: removal is idempotent.)
    missing = (set(furn_edits) | set(door_edits)) - seen
    if missing:
        raise SystemExit(f"{os.path.basename(path)}: spec references unknown id(s): {sorted(missing)}")

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return changed


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.join(here, "..", "randomized_layouts")
    for name, spec in EDITS.items():
        n = apply(os.path.join(root, name), spec)
        print(f"{name}: applied {n} change(s)")


if __name__ == "__main__":
    main()
