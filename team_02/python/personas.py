"""
personas.py — Single source of truth for all Comfort Copilot persona definitions.

Used by:
  - nodes/preprocess.py  → detect which persona the user mentioned
  - nodes/reason.py      → build the persona list in the system prompt
  - (Grasshopper scripts have their own copy — keep in sync manually)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

PERSONAS: dict[str, dict] = {
    "Elderly 65+": {
        "name": "Elderly 65+",
        "description": "Older adults highly sensitive to temperature stability, acoustic noise, and tactile surfaces. Prioritises safety and calm.",
        "keywords": ["elderly", "elder", "old", "senior", "aged", "65", "older adult", "grandparent", "retiree"],
        "thresholds": {
            "thermal": 0.60,
            "visual":  0.60,
            "acoustic": 0.65,
            "spatial": 0.50,
            "olfactory": 0.55,
            "tactile": 0.55,
        },
        "priority": ["acoustic", "thermal", "visual", "spatial", "tactile", "olfactory"],
    },

    "Child under 12": {
        "name": "Child under 12",
        "description": "Children who need spatial freedom to move, rich tactile surfaces to explore, and acoustic stimulation that is engaging but not overwhelming.",
        "keywords": ["child", "children", "kid", "kids", "baby", "toddler", "young child", "under 12"],
        "thresholds": {
            "thermal": 0.50,
            "visual":  0.50,
            "acoustic": 0.55,
            "spatial": 0.60,
            "olfactory": 0.45,
            "tactile": 0.60,
        },
        "priority": ["spatial", "tactile", "acoustic", "visual", "thermal", "olfactory"],
    },

    "Sensory Sensitive": {
        "name": "Sensory Sensitive",
        "description": "Individuals with heightened sensitivity across all senses — especially acoustic and olfactory. Requires calm, controlled environments.",
        "keywords": ["sensory", "sensitive", "hypersensitive", "autism", "spd", "sensory processing", "overwhelmed"],
        "thresholds": {
            "thermal": 0.65,
            "visual":  0.65,
            "acoustic": 0.70,
            "spatial": 0.55,
            "olfactory": 0.65,
            "tactile": 0.65,
        },
        "priority": ["acoustic", "olfactory", "tactile", "visual", "thermal", "spatial"],
    },

    "Young Active": {
        "name": "Young Active",
        "description": "Active young adults tolerant across most senses. Values spatial openness and visual stimulation. Low sensitivity thresholds.",
        "keywords": ["young", "active", "athletic", "adult", "healthy", "young adult"],
        "thresholds": {
            "thermal": 0.40,
            "visual":  0.40,
            "acoustic": 0.40,
            "spatial": 0.40,
            "olfactory": 0.40,
            "tactile": 0.40,
        },
        "priority": ["spatial", "visual", "acoustic", "thermal", "olfactory", "tactile"],
    },

    "Neutral": {
        "name": "Neutral",
        "description": "Balanced, average sensitivity across all senses. A useful default when no specific persona is provided.",
        "keywords": ["neutral", "average", "standard", "general", "default", "anyone"],
        "thresholds": {
            "thermal": 0.45,
            "visual":  0.45,
            "acoustic": 0.45,
            "spatial": 0.45,
            "olfactory": 0.45,
            "tactile": 0.45,
        },
        "priority": ["acoustic", "thermal", "visual", "spatial", "olfactory", "tactile"],
    },
}

DEFAULT_PERSONA = "Neutral"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def get_persona_names() -> list[str]:
    """Return the list of all available persona names."""
    return list(PERSONAS.keys())


def get_persona(name: str) -> dict:
    """Return a persona's full config by name. Falls back to Neutral if not found."""
    return PERSONAS.get(name, PERSONAS[DEFAULT_PERSONA])


def detect_persona_in_text(text: str) -> str | None:
    """
    Scan a user prompt for persona keywords.
    Returns the matched persona name, or None if no match found.
    """
    lower = text.lower()
    for name, config in PERSONAS.items():
        if any(keyword in lower for keyword in config["keywords"]):
            return name
    return None


def format_for_prompt() -> str:
    """
    Format all personas as a readable list for inclusion in the system prompt.
    Example output:
      - "Elderly 65+": Older adults highly sensitive to...
      - "Child under 12": Children who need spatial freedom...
    """
    lines = []
    for name, config in PERSONAS.items():
        lines.append(f'  - "{name}": {config["description"]}')
    return "\n".join(lines)
