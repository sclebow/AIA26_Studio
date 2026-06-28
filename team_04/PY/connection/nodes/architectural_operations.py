"""Architectural operations catalog — the canonical intents and the geometry
operations each intent can be satisfied by.

This is the bridge between LAYER 2 (intent) and LAYER 3 (reason node). An intent
is an architectural GOAL ("improve_daylight"); an operation is a concrete geometry
move the existing engine knows how to apply ("courtyard", "rotate", "reduce_depth").
Each intent lists its candidate operations in PREFERENCE order; the Reason Node
(intent_to_operations.choose_operation) walks that list and picks the first one
that is valid for the current shape, selected part, site and context.

No new geometry is invented here — every op_phrase maps to a phrase that
feedback_reasoning.parse_action already understands, so the operation flows
through the SAME validated backend as a manual move/rotate/scale.
"""
from __future__ import annotations

from typing import Any, NamedTuple


# The 12 canonical architectural intents (the spec's vocabulary). Each is a stable
# id the rest of the pipeline keys on, with a human label for the response text.
CANONICAL_INTENTS: dict[str, str] = {
    "increase_openness": "Increase openness / reduce bulk",
    "improve_daylight": "Improve daylight",
    "improve_views": "Improve views",
    "increase_density": "Increase density / floor area",
    "reduce_bulk": "Reduce bulk / massing",
    "strengthen_frontage": "Strengthen street frontage",
    "improve_privacy": "Improve privacy",
    "reduce_noise": "Reduce noise exposure",
    "improve_public_realm": "Improve public realm",
    "change_character": "Change architectural character",
    "orient_to_edge": "Orient to a site edge",
    "align_to_context": "Align to urban context",
    # Pass-through bucket for clear height/scale language that isn't really a design
    # GOAL but a direct massing change (kept so the classifier always has a target).
    "adjust_height": "Adjust height / floors",
}


class OperationOption(NamedTuple):
    """One candidate operation for satisfying an intent.

    op_phrase: a phrase feedback_reasoning.parse_action understands (so it runs
               through the existing validated backend).
    label:     human description used in the "Updated building: ..." response.
    needs:     pre-conditions the Reason Node checks before choosing this op
               (e.g. "selected_edge", "context", "courtyard"). Empty = always valid.
    grows:     True if the op enlarges the footprint (Reason Node deprioritises
               these when the building already nearly fills the site).
    """
    op_phrase: str
    label: str
    needs: tuple[str, ...] = ()
    grows: bool = False


# Intent → ordered candidate operations (best-first). The Reason Node selects the
# first VALID one. Direction defaults ("north") are placeholders the Reason Node
# rewrites from real edge/context metadata before the op is parsed.
INTENT_OPERATIONS: dict[str, list[OperationOption]] = {
    "increase_openness": [
        OperationOption("add courtyard", "carved a central courtyard"),
        OperationOption("reduce depth", "reduced the mass depth"),
        OperationOption("move 8m north", "pulled the mass back to open the site"),
    ],
    "reduce_bulk": [
        OperationOption("reduce depth", "reduced the mass depth"),
        OperationOption("add courtyard", "carved a central courtyard to lighten the mass"),
        OperationOption("scale 0.9", "scaled the footprint down"),
    ],
    "improve_daylight": [
        # Reduce depth FIRST: shallower floor plates are the textbook daylight move —
        # more of the floor reaches a window, and (unlike a courtyard) it does NOT add
        # solar-exposed facade, so in a hot climate it improves daylight WITHOUT raising
        # the overheating penalty. A courtyard helps interior light but increases gain.
        OperationOption("reduce depth", "reduced floor-plate depth so daylight reaches deeper"),
        OperationOption("add courtyard", "carved a courtyard to bring light to the core"),
        OperationOption("rotate 15 degrees", "rotated for better solar access"),
    ],
    "improve_views": [
        OperationOption("align long facade to {dir}", "oriented the long facade toward the view",
                        needs=("direction",)),
        OperationOption("rotate 15 degrees", "rotated to open the facade toward the view"),
    ],
    "increase_density": [
        OperationOption("add 2 floors", "added floor area"),
        OperationOption("lengthen the {dir} facade", "extended the footprint", needs=("direction",),
                        grows=True),
    ],
    "adjust_height": [
        OperationOption("add 2 floors", "added floors"),
        OperationOption("remove 1 floor", "removed a floor"),
    ],
    "strengthen_frontage": [
        OperationOption("align long facade to {dir}", "aligned the long facade to the frontage edge",
                        needs=("direction",)),
        OperationOption("place near {dir} edge", "brought the mass to the frontage edge",
                        needs=("direction",)),
        OperationOption("lengthen the {dir} facade", "lengthened the frontage", needs=("direction",),
                        grows=True),
    ],
    "improve_privacy": [
        OperationOption("add courtyard", "carved a courtyard to separate private zones"),
        OperationOption("move 8m north", "shifted the mass to reduce overlooking"),
        OperationOption("rotate 15 degrees", "rotated to reduce overlooking"),
    ],
    "reduce_noise": [
        OperationOption("move 8m {dir}", "moved the mass away from the noise source",
                        needs=("direction",)),
        OperationOption("rotate 15 degrees", "rotated to shield from noise"),
        OperationOption("add courtyard", "carved a sheltered courtyard away from noise"),
    ],
    "improve_public_realm": [
        OperationOption("reduce depth", "reduced the footprint to expand the public realm"),
        OperationOption("move 8m {dir}", "set the mass back to open ground-level space",
                        needs=("direction",)),
    ],
    "orient_to_edge": [
        OperationOption("align long facade to {dir}", "aligned the long facade to the edge",
                        needs=("direction",)),
        OperationOption("place near {dir} edge", "placed the mass against the edge",
                        needs=("direction",)),
    ],
    "align_to_context": [
        OperationOption("align long facade to {dir}", "aligned the building to the context edge",
                        needs=("direction", "context")),
        OperationOption("place near {dir} edge", "placed the mass toward the context feature",
                        needs=("direction", "context")),
    ],
    "change_character": [
        # Character language is handled by the architectural_character layer; if it
        # reaches here, a gentle proportion change is the safe default.
        OperationOption("articulate the south facade", "articulated the facade for character"),
        OperationOption("rotate 10 degrees", "adjusted the orientation for character"),
    ],
}


def operations_for(intent: str) -> list[OperationOption]:
    """Candidate operations for an intent (empty list if intent unknown)."""
    return INTENT_OPERATIONS.get(intent, [])


def is_known_intent(intent: str) -> bool:
    return intent in CANONICAL_INTENTS


def intent_label(intent: str) -> str:
    return CANONICAL_INTENTS.get(intent, intent.replace("_", " "))
