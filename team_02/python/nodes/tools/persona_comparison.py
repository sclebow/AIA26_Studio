"""
PERSONA_COMPARISON placeholder — compares comfort scores for primary vs secondary persona.
Requires persona_profile to have both primary_user and secondary_user populated.
TODO: Wire to two ANALYZE MCP calls, then compute delta.
"""

from __future__ import annotations
import json


def build_persona_comparison_node():
    """Return the persona_comparison node function."""

    def persona_comparison_node(state: dict) -> dict:
        persona_profile: dict = state.get("persona_profile") or {}
        layout_json_string: str = state.get("layout_json_string", "")

        print("[persona_comparison] PLACEHOLDER — mock dual-persona comparison")

        primary = persona_profile.get("primary_user", {})
        secondary = persona_profile.get("secondary_user")

        if not secondary:
            summary = (
                "PLACEHOLDER: Only one persona detected. "
                "Add a secondary user to the persona profile to enable comparison. "
                "Example: mention 'my elderly grandmother also lives here'."
            )
        else:
            primary_desc = primary.get("description", "primary user")
            secondary_desc = secondary.get("description", "secondary user")
            summary = (
                f"PLACEHOLDER: Persona comparison between {primary_desc} and "
                f"{secondary_desc} is not yet implemented. "
                f"When live, this will show who suffers where and why across "
                f"all six senses for the loaded layout."
            )

        print(f"[persona_comparison] {summary[:100]}")

        return {
            **state,
            "persona_comparison_summary": summary,
        }

    return persona_comparison_node
