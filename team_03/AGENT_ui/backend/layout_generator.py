"""
AI Layout Generator — produce ONE valid layout JSON per call using Anthropic Sonnet.

Uses Sonnet by default for stronger geometry (LAYOUT_GEN_MODEL overrides). The model
choice here is independent of the chat pipeline's own model handling in pipeline_bridge.

  generate_one(req, variant_index) -> dict   (one normalized, validated LayoutJSON)

The system prompt is the schema/context document teaching Claude how to emit valid
layout JSON (backend/prompts/layout_generator_context.txt), plus an industrial
addendum and a strict output contract. The per-call user prompt injects the form
constraints (type, total-area range, program list with counts, free-text brief) and a
rotating variation directive so successive clicks differ even with the same form.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import layout_loader

# ---------------------------------------------------------------------------
# Paths / config
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
_PROMPT_PATH = _HERE.parent / "prompts" / "layout_generator_context.txt"
# backend/layout_generator.py → parents[3] == AIA26_Studio/ (repo root, holds .env)
_REPO_ROOT = _HERE.parents[3]

# Sonnet by default (stronger geometry); override with LAYOUT_GEN_MODEL in the environment.
DEFAULT_MODEL = "claude-sonnet-4-6"
_MAX_TOKENS = 8192
_TEMPERATURE = 0.8

_LAYER_KEYS = ("rooms", "doors", "windows", "furniture", "mep", "structure")


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _base_context() -> str:
    """The schema/context document — the single source of truth for the prompt."""
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(
            f"Layout generator prompt not found at {_PROMPT_PATH}: {exc}"
        ) from exc


_INDUSTRIAL_ADDENDUM = """
================================================================================
INDUSTRIAL ADDENDUM (when the layout type is "industrial")
================================================================================

This is an INDUSTRIAL / WAREHOUSE facility, not a dwelling. Adapt the schema:

  - Use the SAME JSON schema and geometry rules above, but with an industrial
    program vocabulary instead of residential rooms. Common spaces:
      warehouse, loading_dock, assembly, production, storage, cold_storage,
      office, meeting_room, reception, break_room, locker_room, wc,
      mechanical_room, electrical_room, server_room, corridor, circulation.
  - Spans are LARGER: warehouses/production halls are wide open spans (often
    10m-40m clear). Keep partition walls minimal in production/storage zones.
  - Loading docks sit on an exterior wall; place wide doors (2.5m-4.0m, type
    "sliding" or "fire") there for trucks/forklifts.
  - Offices/meeting/reception/break/locker/WC cluster together (often a 2-bay
    office block along one side); these have normal door widths (0.85m-1.0m).
  - Windows are sparse on the warehouse envelope; office areas get windows.
  - Circulation aisles must stay clear and wide (>= 1.5m) for forklift/pedestrian
    paths; reflect aisles as corridor rooms or generous clearances.
  - MEP matters: electrical_room, mechanical_room, server cooling — place them
    against structure, near the service/loading side.
  - Furniture = racking/shelving, workbenches, machinery footprints, pallet
    zones (rectangular footprints), office desks in the office block.
"""

_OUTPUT_CONTRACT = """
================================================================================
OUTPUT CONTRACT (STRICT)
================================================================================

Return ONLY a single JSON object: the layout itself, matching the schema above.
- No prose, no explanation, no markdown code fences — just the raw JSON object.
- It MUST start with '{' and end with '}'.
- Include ALL eight top-level fields: layoutId, outline, rooms, doors, windows,
  furniture, mep, structure (use [] for any layer you don't populate).
- Coordinates in meters, 2 decimals max. Close every polygon (first == last point).
"""

# Rotating variation directives so repeated "Generate" clicks yield distinct plans.
_VARIATION_DIRECTIVES: List[str] = [
    "Prioritize compact, efficient circulation and minimal corridor/aisle area; "
    "a near-square footprint.",
    "Prioritize an open-plan feel with generous shared/common space; merge living/"
    "dining or production/assembly into larger continuous zones.",
    "Prioritize daylight and perimeter access: give habitable/work rooms maximum "
    "exterior-wall exposure; use an elongated footprint.",
    "Prioritize zoning separation: cluster wet/service spaces on one side and "
    "quiet/work spaces on the other, connected by a clear central spine.",
]


def _system_prompt(layout_type: str) -> str:
    parts = [_base_context()]
    if (layout_type or "").strip().lower() == "industrial":
        parts.append(_INDUSTRIAL_ADDENDUM)
    parts.append(_OUTPUT_CONTRACT)
    return "\n".join(parts)


def _format_programs(programs: Any) -> str:
    """Render [{name, count}] as 'Bedroom x2, Bathroom x1, ...'."""
    if not isinstance(programs, list) or not programs:
        return "(no specific program given — choose a sensible default for the type)"
    chunks: List[str] = []
    for p in programs:
        if not isinstance(p, dict):
            continue
        name = str(p.get("name", "")).strip()
        if not name:
            continue
        try:
            count = max(1, int(p.get("count", 1)))
        except (TypeError, ValueError):
            count = 1
        chunks.append(f"{name} x{count}")
    return ", ".join(chunks) if chunks else "(no specific program given)"


def _user_prompt(req: Dict[str, Any], directive: str, nonce: str) -> str:
    layout_type = (req.get("layoutType") or "residential").strip().lower()
    try:
        area_min = float(req.get("areaMin", 0) or 0)
        area_max = float(req.get("areaMax", 0) or 0)
    except (TypeError, ValueError):
        area_min, area_max = 0.0, 0.0
    if area_max < area_min:
        area_min, area_max = area_max, area_min

    programs = _format_programs(req.get("programs"))
    brief = str(req.get("brief", "") or "").strip() or "(no extra notes)"

    area_line = (
        f"between {area_min:g} and {area_max:g} m²"
        if area_max > 0
        else "use a sensible total area for the program"
    )

    return (
        f"Generate ONE valid {layout_type} floor plan as a single JSON object.\n\n"
        f"Constraints:\n"
        f"- Total built area (sum of room areas / outline footprint): {area_line}.\n"
        f"- Required program (name x count): {programs}.\n"
        f"  Honor these counts (e.g. 'Bedroom x2' means two bedroom rooms).\n"
        f"- User brief: \"{brief}\"\n\n"
        f"Variation directive for this iteration: {directive}\n\n"
        f"Set \"layoutId\" to \"{layout_type}-AI-{nonce}\".\n"
        f"Remember the OUTPUT CONTRACT: return ONLY the raw JSON object."
    )


# ---------------------------------------------------------------------------
# Parsing / normalization
# ---------------------------------------------------------------------------

def _extract_json_object(text: str) -> Dict[str, Any]:
    """Tolerant extractor: strips markdown fences and pulls the first JSON object."""
    s = (text or "").strip()
    # Strip a leading/trailing ```json ... ``` fence if present.
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", s, re.DOTALL)
    if fence:
        s = fence.group(1)
    # Grab the outermost { ... } (greedy → first '{' to last '}').
    match = re.search(r"\{.*\}", s, re.DOTALL)
    candidate = match.group(0) if match else s
    parsed = json.loads(candidate)
    if not isinstance(parsed, dict):
        raise ValueError("Model did not return a JSON object.")
    return parsed


def _normalize(layout: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure all 8 top-level fields exist with the right shape for the frontend."""
    if not isinstance(layout.get("layoutId"), str) or not layout["layoutId"].strip():
        layout["layoutId"] = f"AI-{uuid.uuid4().hex[:8]}"
    outline = layout.get("outline")
    if not isinstance(outline, list):
        layout["outline"] = []
    for key in _LAYER_KEYS:
        if not isinstance(layout.get(key), list):
            layout[key] = []
    return layout


# ---------------------------------------------------------------------------
# Anthropic call
# ---------------------------------------------------------------------------

def _anthropic_key() -> str:
    """Load ANTHROPIC_API_KEY from the repo-root .env (same source the pipeline uses)."""
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=False)
    except Exception:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. The AI Layout Generator needs an Anthropic "
            "key (add ANTHROPIC_API_KEY to the repo-root .env)."
        )
    return key


async def generate_one(req: Dict[str, Any], variant_index: int = 0) -> Dict[str, Any]:
    """Generate, parse, normalize and validate ONE layout. Raises on failure."""
    import anthropic

    layout_type = (req.get("layoutType") or "residential").strip().lower()
    model = os.environ.get("LAYOUT_GEN_MODEL", DEFAULT_MODEL)
    directive = _VARIATION_DIRECTIVES[int(variant_index) % len(_VARIATION_DIRECTIVES)]
    nonce = uuid.uuid4().hex[:6]

    client = anthropic.AsyncAnthropic(api_key=_anthropic_key())
    response = await client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        system=_system_prompt(layout_type),
        messages=[{"role": "user", "content": _user_prompt(req, directive, nonce)}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    if not text.strip():
        raise RuntimeError("Model returned an empty response.")

    layout = _normalize(_extract_json_object(text))

    if not layout_loader.validate_layout(layout):
        raise ValueError("Generated layout is missing required keys (layoutId, outline, rooms).")
    if not layout.get("rooms"):
        raise ValueError("Generated layout has no rooms.")
    if not layout.get("outline"):
        raise ValueError("Generated layout has no outline.")

    return layout
