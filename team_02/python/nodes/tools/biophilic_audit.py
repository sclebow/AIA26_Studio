"""
BIOPHILIC_AUDIT placeholder — scores mock biophilic richness per room (plants, glazing, ventilation).
Sets biophilic_plants_needed=True if any room lacks plant elements.
TODO: Wire to MCP compute_biophilic_richness tool.
"""

from __future__ import annotations
import json


def build_biophilic_audit_node():
    """Return the biophilic_audit node function."""

    def biophilic_audit_node(state: dict) -> dict:
        layout_json_string: str = state.get("layout_json_string", "")
        persona_profile: dict = state.get("persona_profile") or {}

        print("[biophilic_audit] PLACEHOLDER — mock biophilic richness scoring")

        biophilic_summary = "(biophilic audit not yet implemented)"
        biophilic_plants_needed = False

        # Mock: parse basic biophilic signals from layout attributes
        try:
            layout = json.loads(layout_json_string)
            lines = ["BIOPHILIC RICHNESS AUDIT (mock):"]
            for room in layout.get("rooms", []):
                name = room.get("name", "?")
                attrs = room.get("attributes", {})
                glazing = float(attrs.get("glazingRatio", 0))
                ventilation = attrs.get("ventilationType", "none")
                furniture = room.get("furniture", [])
                has_plants = any(
                    "plant" in str(f.get("type", "")).lower() or
                    "natural" in str(f.get("material", "")).lower()
                    for f in furniture
                )
                # Mock richness score
                richness = 0.0
                if glazing > 0.3:
                    richness += 0.3
                if ventilation == "natural":
                    richness += 0.3
                if has_plants:
                    richness += 0.4
                else:
                    biophilic_plants_needed = True  # flag that plants could help

                status = "good" if richness > 0.5 else "low"
                lines.append(
                    f"  {name}: richness={richness:.1f} ({status}) | "
                    f"glazing={glazing:.0%}, ventilation={ventilation}, "
                    f"plants={'yes' if has_plants else 'no'}"
                )

            biophilic_summary = "\n".join(lines)
            print(f"[biophilic_audit] Audit complete, plants_needed={biophilic_plants_needed}")
        except Exception as exc:
            print(f"[biophilic_audit] Error ({exc})")
            biophilic_summary = "(biophilic audit failed)"

        return {
            **state,
            "biophilic_summary": biophilic_summary,
            "biophilic_plants_needed": biophilic_plants_needed,
        }

    return biophilic_audit_node
