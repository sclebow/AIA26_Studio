"""Architectural character + facade/tower intent → operation sequences.

The literal parser (feedback_reasoning.parse_action) handles concrete commands
("add 2 floors", "scale 1.2"). The Reason Node (reason_node.py) classifies broad
intent. This module fills the gap the user asked for: turning *architectural
language* — "make it more residential", "the facade feels too flat", "increase
tower separation", "make it more iconic" — into ORDERED operation lists the
feedback route can execute, each op already in the supported set:

    courtyard | patio | lengthen | reduce_depth | wing | align_facade |
    place_corner | place_edge | floors | set_floors | scale |
    stretch | compress | articulate_facade | chamfer | twist | taper

So an architect can speak naturally and get an intelligent massing change, not a
single move/rotate. No LLM — deterministic keyword → op mapping, ordered so the
most characteristic move leads.
"""
from __future__ import annotations

import re
from typing import Any

# Each entry: (regex over the lowercased prompt, [ops]). First match wins per
# category; multiple categories can contribute (see classify_character).
# An op is {"op": <name>, "transform": {...}, "text": <human label>}.

def _op(name: str, text: str, **transform: Any) -> dict[str, Any]:
    return {"op": name, "transform": transform, "text": text}


# --- CHARACTER intents (residential / commercial / iconic / elegant / human) ---
# NOTE: "less/not X" negations are listed FIRST so "less like an office" doesn't
# accidentally match the positive "office" rule below.
_CHARACTER_RULES: list[tuple[str, list[dict[str, Any]]]] = [
    # Less corporate / less office / less mall / less boxy / less institutional
    (r"less (like an? )?office|less (like a )?(mall|shopping)|(too much )?like an? (mall|shopping mall)|too (much )?(like a )?(mall|shopping)|less corporate|not (like )?(an? )?office|less boxy|less institutional|less rigid|loosen|too institutional|too corporate",
     [_op("chamfer", "soften the boxy massing", mode="round", amount_pct=0.1),
      _op("courtyard", "introduce a courtyard to break the corporate block", fraction=0.28)]),
    # Residential / village / campus / human / warm / welcoming / softer
    (r"residential|village|human scale|more human|warmer|welcoming|inviting|softer|homely|domestic",
     [_op("courtyard", "carve a courtyard for a residential, human-scale core", fraction=0.3),
      _op("reduce_depth", "reduce floor depth for daylight and intimacy", amount_pct=0.12),
      _op("chamfer", "soften the corners for a warmer character", mode="round", amount_pct=0.08)]),
    # Commercial / corporate / office / urban / premium / exclusive frontage
    (r"commercial|corporate|office|business|premium|exclusive|stronger urban|urban edge|retail",
     [_op("lengthen", "extend the street frontage for a strong commercial edge", direction="south", amount_pct=0.18),
      _op("scale", "increase the floor plate for larger commercial floors", scale=1.12)]),
    # Iconic / landmark / sculptural / dynamic / futuristic / stand out / memorable /
    # luxury / premium identity / stronger character / needs identity
    (r"iconic|landmark|sculptural|dynamic|futuristic|stand out|memorable|signature|striking|dramatic|luxur|premium|stronger (character|identity)|lacks? identity|needs? (a )?(stronger )?(character|identity)|more (character|identity)",
     [_op("twist", "twist the tower for an iconic, dynamic silhouette", total_degrees=12),
      _op("taper", "taper the massing for a landmark profile", top_scale=0.85)]),
    # Curvature / softer / organic  vs  sharper / crisp edges.
    (r"curvature|curved|softer (geometry|edges|form)|more organic|round the",
     [_op("chamfer", "soften the geometry with rounded corners", mode="round", amount_pct=0.14)]),
    (r"sharper edges|sharp(er)? (edges|geometry)|crisp|cleaner edges|more angular",
     [_op("chamfer", "crisp the edges for a sharper silhouette", mode="sharpen", amount_pct=0.08)]),
    # Elegant / slender / refined / clean / understated / minimal
    (r"elegant|slender|refined|clean(er)?|understated|minimal|less heavy|lighter|sophisticated",
     [_op("taper", "taper for slender, elegant proportions", top_scale=0.78),
      _op("chamfer", "crisp the geometry for a clean, refined silhouette", mode="sharpen", amount_pct=0.06)]),
]

# --- FACADE intents (flat / frontage / articulation / depth / rhythm) ---
_FACADE_RULES: list[tuple[str, list[dict[str, Any]]]] = [
    (r"facade.*(flat|boring|plain|monoton)|flat facade|too flat|lacks depth|no depth|break up the (long )?facade|articulat|rhythm|recess|projection|terrac|balcon",
     [_op("articulate_facade", "articulate the facade with recesses and rhythm", direction="south", count=3, depth_pct=0.08)]),
    (r"stronger frontage|active frontage|stronger (front|entrance)|street presence|entrance.*importan|more open ground",
     [_op("lengthen", "strengthen the frontage along the primary edge", direction="south", amount_pct=0.15),
      _op("articulate_facade", "give the frontage rhythm and depth", direction="south", count=2, depth_pct=0.06)]),
]

# --- TOWER / WING intents (separation / dominance / split / extend) ---
_TOWER_RULES: list[tuple[str, list[dict[str, Any]]]] = [
    (r"tower.*(separation|apart|away|further)|increase.*separation|pull the tower|move the tower away",
     [_op("place_edge", "pull the tower toward an edge to increase separation", direction="north")]),
    (r"tower.*(closer|reduce.*separation|bring.*tower)",
     [_op("place_corner", "draw the tower in toward the centre", corner="northeast")]),
    (r"(reduce|lower).*tower (height|dominan)|less dominant|tower too (tall|dominant)",
     [_op("floors", "lower the tower to reduce dominance", floors=-3)]),
    (r"(make|more).*tower (dominant|taller|prominent)|stronger tower|taller tower",
     [_op("floors", "raise the tower for more dominance", floors=4)]),
    (r"extend.*(central|centre|center) (wing|spine|axis)|strengthen.*central axis|central spine",
     [_op("lengthen", "extend the central spine", direction="north", amount_pct=0.2)]),
    (r"expand.*(side )?wings|wings.*(bigger|larger|expand)",
     [_op("wing", "expand the side wings", direction="east", factor=1.3)]),
    (r"pull back.*wings|reduce.*wings|wings.*(smaller|shorter)",
     [_op("wing", "pull back the side wings", direction="east", factor=0.8)]),
]

# --- SCALE / PROPORTION language not caught by the literal parser ---
_PROPORTION_RULES: list[tuple[str, list[dict[str, Any]]]] = [
    (r"taller and (slimmer|thinner|slender)|slender|thinner|less fat|tower.*(fat|wide|bulky)",
     [_op("taper", "make it taller and more slender", top_scale=0.72)]),
    (r"wider and lower|lower and wider|more horizontal|spread out",
     [_op("stretch", "make it wider and lower", axis="x", factor=1.25)]),
    (r"stretch.*horizontal|horizontal(ly)?|elongat",
     [_op("stretch", "stretch the mass horizontally", axis="x", factor=1.25)]),
    (r"compress|compact the mass|squeeze|tighten the mass",
     [_op("compress", "compress the mass", axis="x", factor=0.85)]),
    (r"too (bulky|heavy|massive|dense|boxy|aggressive)|feels heavy|visual weight too|monumental too|overwhelming|breathing room|open it up|give.*space",
     [_op("courtyard", "open the mass up with a courtyard for breathing room", fraction=0.3),
      _op("chamfer", "lighten the silhouette", mode="round", amount_pct=0.08)]),
    (r"more (monumental|presence|imposing|stronger presence|bigger|larger)|stronger presence|increase.*scale|increase.*volume",
     [_op("scale", "increase the overall scale and presence", scale=1.2)]),
]

_ALL_RULE_GROUPS = [
    ("character", _CHARACTER_RULES),
    ("facade", _FACADE_RULES),
    ("tower", _TOWER_RULES),
    ("proportion", _PROPORTION_RULES),
]


def classify_character(prompt: str) -> dict[str, Any] | None:
    """Map an architectural-language prompt to an intent + ordered op list.
    Returns {intent, category, operations: [...], summary} or None if nothing matched.
    The feedback route runs the operations in order through its existing handlers."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    low = prompt.lower().strip()
    operations: list[dict[str, Any]] = []
    matched_category = None
    matched_label = None
    for category, rules in _ALL_RULE_GROUPS:
        for pattern, ops in rules:
            if re.search(pattern, low):
                operations.extend(ops)
                matched_category = matched_category or category
                matched_label = matched_label or pattern.split("|")[0]
                break  # one rule per category
        if operations and category == matched_category:
            # keep scanning other categories so e.g. "residential with a flat facade"
            # can combine character + facade — but cap total ops to stay sane.
            continue
    if not operations:
        return None
    # De-dup ops by name+key transform so a combined prompt doesn't double-apply.
    seen = set()
    unique = []
    for o in operations:
        sig = (o["op"], tuple(sorted((o.get("transform") or {}).items())))
        if sig in seen:
            continue
        seen.add(sig)
        unique.append(o)
    unique = unique[:4]  # at most 4 moves per prompt
    return {
        "intent": matched_category,
        "category": matched_category,
        "operations": [dict(o) for o in unique],
        "summary": "; ".join(o["text"] for o in unique),
    }
