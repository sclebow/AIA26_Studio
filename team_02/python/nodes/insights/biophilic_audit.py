"""
BIOPHILIC_AUDIT — real biophilic richness scoring per room.
Fixed: reads furniture from layout.furniture[] (not room-nested), returns structured biophilic_data.
"""

from __future__ import annotations
import json
from nodes.editing import _edits


def build_biophilic_audit_node():
    def biophilic_audit_node(state: dict) -> dict:
        layout_str = state.get("layout_json_string", "")
        layout     = _edits.load(layout_str)

        if layout is None:
            return {**state, "biophilic_summary": "(no layout)", "biophilic_plants_needed": False, "biophilic_data": {}}

        # Build furniture-per-room map (correct schema: top-level furniture with roomId)
        furniture_by_room: dict = {}
        for f in layout.get("furniture", []):
            rid = f.get("attributes", {}).get("roomId")
            if rid:
                furniture_by_room.setdefault(rid, []).append(f.get("attributes", {}))

        rooms_data = []
        biophilic_plants_needed = False
        lines = ["BIOPHILIC RICHNESS AUDIT:"]

        for room in layout.get("rooms", []):
            rid        = room.get("id", "")
            name       = room.get("name", "?")
            attrs      = room.get("attributes", {})
            glazing    = float(attrs.get("glazingRatio", 0))
            vent       = attrs.get("ventilationType", "none")
            floor_mat  = attrs.get("floorMaterial", "")
            furn_list  = furniture_by_room.get(rid, [])

            plant_count = sum(1 for f in furn_list if f.get("type", "").lower() == "plant"
                              or f.get("material", "").lower() == "natural")
            has_plants  = plant_count > 0
            has_natural_mat = any(f.get("material", "").lower() in ("natural", "wood", "cork")
                                  for f in furn_list)

            # Richness score (0-1): glazing 30% + ventilation 30% + plants 40%
            richness = 0.0
            if glazing >= 0.25:
                richness += 0.30
            elif glazing >= 0.10:
                richness += 0.15
            if vent == "natural":
                richness += 0.30
            elif vent == "mixed":
                richness += 0.15
            if has_plants:
                richness += min(0.40, 0.20 * plant_count)
            if has_natural_mat and not has_plants:
                richness += 0.10

            if not has_plants:
                biophilic_plants_needed = True

            status = "rich" if richness >= 0.70 else "moderate" if richness >= 0.40 else "low"
            lines.append(
                f"  {name}: richness={richness:.2f} ({status}) | "
                f"glazing={glazing:.0%}, ventilation={vent}, plants={plant_count}"
            )
            rooms_data.append({
                "id":            rid,
                "name":          name,
                "richness_score": round(richness, 2),
                "status":        status,
                "has_plants":    has_plants,
                "plant_count":   plant_count,
                "glazing_ratio": glazing,
                "ventilation":   vent,
                "floor_material": floor_mat,
            })

        biophilic_summary = "\n".join(lines)
        biophilic_data = {
            "rooms":                rooms_data,
            "plants_needed":        biophilic_plants_needed,
            "rooms_without_plants": [r["name"] for r in rooms_data if not r["has_plants"]],
        }

        print(f"[biophilic_audit] {len(rooms_data)} rooms | plants_needed={biophilic_plants_needed}")
        return {
            **state,
            "biophilic_summary":      biophilic_summary,
            "biophilic_plants_needed": biophilic_plants_needed,
            "biophilic_data":         biophilic_data,
        }

    return biophilic_audit_node
