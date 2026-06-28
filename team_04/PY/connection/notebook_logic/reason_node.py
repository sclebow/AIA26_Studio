"""Reason Node — architectural intent parser and geometry action generator.

Converts user feedback into geometry operations through intent classification,
synonym matching, and architectural reasoning.

Supports 10 intent categories:
1. Daylight — improve natural light, reduce self-shading, increase facade exposure
2. Views — face landmarks, preserve corridors, orient facade
3. Density — increase FAR, add floors, expand footprint
4. Compactness — open up, add breathing space, stretch wings
5. Height — adjust floors/tower height, modify podium
6. Open Space — increase plaza/green space, reduce footprint
7. Edge-Based — position near edges, face directions, align facade
8. Courtyard — create voids, introduce atrium, carve central space
9. Shape Transformation — change topology (H/U/L shape, wings)
10. Environmental — improve ventilation, daylight, solar access, heat control

Each intent maps to geometric actions through keyword extraction, embedding
similarity, and confidence scoring.

Output: architectural goals + geometry action list for manipulation engine.
"""

from __future__ import annotations

import math
from typing import Any, NamedTuple


# ============================================================================
# Intent Definitions
# ============================================================================

class IntentDefinition(NamedTuple):
    """Definition of an architectural intent category."""
    intent_id: str
    name: str
    description: str
    keywords: list[str]  # Primary keywords
    synonyms: list[str]  # Synonym phrases
    actions: list[str]  # Possible geometry actions
    confidence_boost: float  # Confidence multiplier if keywords match


# Intent Category Definitions

INTENT_DEFINITIONS: dict[str, IntentDefinition] = {
    "daylight": IntentDefinition(
        intent_id="daylight",
        name="Daylight & Natural Light",
        description="Improve natural light, reduce self-shading, increase facade exposure",
        keywords=[
            "daylight", "light", "sun", "sunlight", "exposure",
            "shade", "shading", "shadow", "shadows", "dark",
            "self-shading", "selfshading", "overshadowing",
            "bright", "brightness", "illuminate", "illumination",
            "facade", "window", "windows", "courtyard", "atrium"
        ],
        synonyms=[
            "more daylight", "increase natural light", "bring more sun",
            "reduce self shading", "reduce self-shading", "reduce overshadowing",
            "open the courtyard", "improve south light",
            "increase facade exposure", "better light", "sunlit",
            "light the interior", "daylit space", "maximize light"
        ],
        actions=[
            "rotate_building",
            "reduce_depth",
            "create_courtyard",
            "increase_spacing",
            "split_mass",
            "increase_facade_length",
            "carve_void",
            "modify_orientation"
        ],
        confidence_boost=1.2
    ),

    "views": IntentDefinition(
        intent_id="views",
        name="Views & Orientations",
        description="Improve views, face landmarks, preserve view corridors, orient facade",
        keywords=[
            "view", "views", "vista", "sightline", "orient",
            "orientation", "face", "facing", "toward", "towards",
            "park", "river", "water", "city", "skyline", "landmark",
            "corridor", "preserve", "opening", "outlook"
        ],
        synonyms=[
            "improve views", "face the park", "open toward city",
            "orient toward river", "preserve view corridor",
            "maximize vista", "sight line", "view quality",
            "view to landmark", "directional orientation"
        ],
        actions=[
            "rotate_building",
            "reposition_building",
            "orient_facade",
            "shift_mass",
            "rotate_facade",
            "align_to_direction",
            "create_opening"
        ],
        confidence_boost=1.15
    ),

    "density": IntentDefinition(
        intent_id="density",
        name="Density & Floor Area",
        description="Increase FAR, add more area, expand footprint, increase capacity",
        keywords=[
            "density", "dense", "far", "floor area", "area",
            "larger", "bigger", "expand", "increase",
            "capacity", "more", "additional", "add",
            "height", "floors", "coverage"
        ],
        synonyms=[
            "increase far", "make it larger", "add more area",
            "increase capacity", "more floor area", "denser",
            "expand footprint", "add volume", "maximize coverage"
        ],
        actions=[
            "add_floors",
            "expand_footprint",
            "increase_height",
            "expand_wings",
            "increase_coverage"
        ],
        confidence_boost=1.25
    ),

    "compactness": IntentDefinition(
        intent_id="compactness",
        name="Compactness & Openness",
        description="Open up mass, add breathing space, reduce density feel, stretch wings",
        keywords=[
            "compact", "dense", "tight", "closed", "confined",
            "cramped", "squeeze", "open", "breathe", "breathing",
            "space", "spacious", "spread", "stretch", "wings",
            "separate", "distance", "apart",
            "unbalanced", "balance", "balanced", "composition",
            "generic", "bulky", "heavy", "massing"
        ],
        synonyms=[
            "feels too compact", "open it up", "less dense",
            "more breathing space", "spread the mass",
            "break it up", "less crowded", "more separation",
            "feels unbalanced", "composition feels unbalanced",
            "feels generic", "too heavy", "too bulky", "massing is too heavy"
        ],
        actions=[
            "stretch_wings",
            "create_courtyard",
            "separate_masses",
            "increase_spacing",
            "split_mass",
            "reduce_coverage",
            "modify_footprint"
        ],
        confidence_boost=1.15
    ),

    "height": IntentDefinition(
        intent_id="height",
        name="Height & Vertical Scaling",
        description="Modify height, add/remove floors, adjust podium, tower modifications",
        keywords=[
            "height", "tall", "taller", "tower", "floors",
            "stories", "storeys", "level", "levels", "podium",
            "base", "upper", "lower", "rise", "vertical",
            "scale", "proportion", "profile"
        ],
        synonyms=[
            "make it taller", "increase tower height", "add floors",
            "reduce height", "lower the podium", "adjust height",
            "modify tower", "increase vertical", "taller profile"
        ],
        actions=[
            "modify_height",
            "add_floors",
            "remove_floors",
            "adjust_tower_height",
            "modify_podium",
            "change_profile"
        ],
        confidence_boost=1.2
    ),

    "openspace": IntentDefinition(
        intent_id="openspace",
        name="Open Space & Landscape",
        description="Increase plaza, green space, public realm, landscape area",
        keywords=[
            "open space", "plaza", "public realm", "landscape",
            "green", "green space", "park", "garden", "outdoor",
            "exterior", "pedestrian", "plaza area", "square",
            "courtyard", "open air", "terrace",
            "public", "walkability", "walkable", "transition",
            "transitions", "frontage", "active"
        ],
        synonyms=[
            "more green space", "larger plaza", "increase public realm",
            "more landscape", "add open space", "expand plaza",
            "pedestrian friendly", "outdoor space", "public garden",
            "public plaza", "improve walkability", "active frontage",
            "public-private transition", "public private transition"
        ],
        actions=[
            "reduce_footprint",
            "move_building",
            "increase_setback",
            "create_plaza",
            "reduce_coverage",
            "expand_openspace"
        ],
        confidence_boost=1.15
    ),

    "edgebased": IntentDefinition(
        intent_id="edgebased",
        name="Edge-Based Positioning",
        description="Position near edges, face directions, align with boundaries",
        keywords=[
            "edge", "edges", "north", "south", "east", "west",
            "corner", "side", "boundary", "perimeter", "street",
            "road", "main", "front", "back", "side",
            "align", "alignment", "adjacent", "border"
        ],
        synonyms=[
            "move toward north edge", "face east", "place near main road",
            "align with west edge", "street facing", "edge-aligned",
            "boundary hugging", "perimeter placement", "directional placement"
        ],
        actions=[
            "edge_attraction",
            "rotate_facade",
            "reposition_mass",
            "align_to_edge",
            "face_direction",
            "street_alignment"
        ],
        confidence_boost=1.25
    ),

    "courtyard": IntentDefinition(
        intent_id="courtyard",
        name="Courtyard & Central Void",
        description="Create courtyards, introduce atrium, carve central voids, open middle",
        keywords=[
            "courtyard", "atrium", "void", "voids", "central",
            "interior", "open", "carved", "carve", "hollow",
            "middle", "center", "core", "internal",
            "introduce", "add", "create", "internal space"
        ],
        synonyms=[
            "add courtyard", "introduce central void", "open the middle",
            "create atrium", "carve interior void", "add central space",
            "hollow interior", "interior courtyard", "central opening"
        ],
        actions=[
            "carve_void",
            "generate_courtyard",
            "create_atrium",
            "hollow_interior",
            "add_central_space",
            "modify_topology"
        ],
        confidence_boost=1.3
    ),

    "shapetransform": IntentDefinition(
        intent_id="shapetransform",
        name="Shape Transformation",
        description="Change topology (H/U/L/T shape), add wings, modify footprint graph",
        keywords=[
            "shape", "topology", "form", "geometry", "footprint",
            "h shape", "u shape", "l shape", "t shape",
            "wing", "wings", "arm", "arms", "segment",
            "transform", "convert", "change", "modify", "graph"
        ],
        synonyms=[
            "convert to h shape", "create u shape", "make it l shape",
            "add another wing", "three-arm layout", "shape conversion",
            "topology modification", "footprint reconfiguration"
        ],
        actions=[
            "regenerate_topology",
            "modify_footprint_graph",
            "change_shape",
            "add_wing",
            "remove_wing",
            "reconfigure_arms"
        ],
        confidence_boost=1.3
    ),

    "environmental": IntentDefinition(
        intent_id="environmental",
        name="Environmental Performance",
        description="Improve daylight, ventilation, solar access, reduce heat gain",
        keywords=[
            "environment", "environmental", "daylight", "ventilation",
            "ventilate", "airflow", "air", "solar", "sun",
            "heat", "thermal", "comfort", "performance",
            "efficiency", "passive", "sustainable", "green"
        ],
        synonyms=[
            "better daylight", "better ventilation", "reduce heat gain",
            "improve solar access", "passive design", "thermal comfort",
            "cross ventilation", "natural ventilation", "solar design"
        ],
        actions=[
            "run_sunlight_optimization",
            "rotate_building",
            "reposition_building",
            "modify_mass_depth",
            "create_openings",
            "increase_permeability"
        ],
        confidence_boost=1.2
    ),

    "privacy": IntentDefinition(
        intent_id="privacy",
        name="Privacy & Separation",
        description="Reduce overlooking, separate public/private zones, improve unit privacy",
        keywords=[
            "privacy", "private", "overlooking", "overlook",
            "circulation", "separation", "separate", "screen",
            "screening", "buffer", "seclusion", "secluded",
            "residential", "units", "upper", "semi-private", "semiprivate"
        ],
        synonyms=[
            "increase privacy", "reduce overlooking", "improve privacy",
            "separate public and private", "separate circulation",
            "private residential garden", "semi-private courtyard",
            "reduce overlooking between units", "private rear zone",
            "public-private transition", "improve privacy on upper floors"
        ],
        actions=[
            "create_courtyard",
            "separate_masses",
            "increase_spacing",
            "carve_void",
            "reposition_building",
            "rotate_building"
        ],
        confidence_boost=1.2
    ),

    "acoustics": IntentDefinition(
        intent_id="acoustics",
        name="Acoustics & Noise",
        description="Reduce noise exposure, shield from traffic/rail, improve acoustic comfort",
        keywords=[
            "noise", "noisy", "acoustic", "acoustics", "quiet",
            "quieter", "sound", "traffic", "highway", "railway",
            "rail", "buffer", "shield", "shielding", "loud"
        ],
        synonyms=[
            "reduce noise", "reduce traffic noise", "noise buffer",
            "acoustic comfort", "shield from noise", "quietest area",
            "away from the highway", "away from the railway",
            "protect from noise", "reduce noise exposure", "quiet residential"
        ],
        actions=[
            "reposition_building",
            "rotate_building",
            "separate_masses",
            "create_courtyard",
            "increase_setback",
            "shift_mass"
        ],
        confidence_boost=1.2
    ),
}


# ============================================================================
# Keyword Extraction & Matching
# ============================================================================

def extract_keywords(text: str) -> list[str]:
    """Extract and normalize keywords from user feedback.

    Args:
        text: User feedback text

    Returns:
        List of normalized keywords (lowercased, split)
    """
    if not text:
        return []

    # Lowercase and split
    normalized = text.lower().strip()

    # Split by common delimiters
    words = normalized.replace(",", " ").replace(".", " ").split()

    # Filter out common stop words
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at",
        "to", "for", "of", "is", "are", "was", "were", "be",
        "i", "me", "it", "we", "you", "they", "this", "that",
        "can", "could", "should", "would", "may", "might", "must",
        "please", "thanks", "try", "want"
    }

    keywords = [w for w in words if w and len(w) > 2 and w not in stop_words]
    return keywords


def calculate_keyword_match_score(
    user_keywords: list[str],
    intent_def: IntentDefinition
) -> float:
    """Calculate how well user keywords match an intent.

    Args:
        user_keywords: Keywords extracted from user feedback
        intent_def: Intent definition to match against

    Returns:
        Match score 0-1
    """
    if not user_keywords:
        return 0.0

    intent_keywords = set(intent_def.keywords)
    user_keyword_set = set(user_keywords)

    # Count matches
    matches = len(user_keyword_set & intent_keywords)

    if not matches:
        return 0.0

    # Score: matches / total user keywords
    score = matches / len(user_keyword_set)
    return min(1.0, score)


def calculate_synonym_match_score(text: str, intent_def: IntentDefinition) -> float:
    """Calculate how well text matches intent synonyms.

    Args:
        text: User feedback text
        intent_def: Intent definition to match against

    Returns:
        Match score 0-1
    """
    if not text or not intent_def.synonyms:
        return 0.0

    text_lower = text.lower()

    # Direct substring match (highest confidence)
    for synonym in intent_def.synonyms:
        if synonym.lower() in text_lower:
            return 1.0

    # Partial phrase match (medium confidence)
    for synonym in intent_def.synonyms:
        words = synonym.lower().split()
        if len(words) >= 2:
            # Check if multiple key words appear
            matching_words = sum(1 for w in words if w in text_lower)
            if matching_words >= len(words) - 1:  # Allow 1 word missing
                return 0.8

    return 0.0


# ============================================================================
# Intent Classification
# ============================================================================

class IntentResult(NamedTuple):
    """Result of intent analysis."""
    intent_id: str
    intent_name: str
    confidence: float
    keyword_match: float
    synonym_match: float
    matched_keywords: list[str]
    matched_synonyms: list[str]
    reasoning: list[str]
    actions: list[str]


def classify_intent(user_feedback: str) -> list[IntentResult]:
    """Classify user feedback into intent categories with confidence scores.

    Args:
        user_feedback: User's architectural feedback text

    Returns:
        List of IntentResult sorted by confidence (highest first)
    """
    if not user_feedback or not user_feedback.strip():
        return []

    keywords = extract_keywords(user_feedback)
    results: list[IntentResult] = []

    for intent_id, intent_def in INTENT_DEFINITIONS.items():
        # Calculate match scores
        keyword_score = calculate_keyword_match_score(keywords, intent_def)
        synonym_score = calculate_synonym_match_score(user_feedback, intent_def)

        # Combined confidence (weighted average)
        combined_score = (keyword_score * 0.4 + synonym_score * 0.6)

        # Apply boost if strong match
        if combined_score > 0:
            combined_score = min(1.0, combined_score * intent_def.confidence_boost)

        # Track reasoning
        reasoning = []
        matched_keywords = [k for k in keywords if k in intent_def.keywords]
        matched_synonyms = []

        if keyword_score > 0:
            reasoning.append(f"keyword match: {keyword_score:.0%}")
            if matched_keywords:
                reasoning.append(f"matched keywords: {', '.join(matched_keywords)}")

        if synonym_score > 0:
            reasoning.append(f"phrase match: {synonym_score:.0%}")
            for synonym in intent_def.synonyms:
                if synonym.lower() in user_feedback.lower():
                    matched_synonyms.append(synonym)

        # Only include if meaningful match
        if combined_score > 0.1:
            results.append(
                IntentResult(
                    intent_id=intent_id,
                    intent_name=intent_def.name,
                    confidence=round(combined_score, 2),
                    keyword_match=round(keyword_score, 2),
                    synonym_match=round(synonym_score, 2),
                    matched_keywords=matched_keywords,
                    matched_synonyms=matched_synonyms,
                    reasoning=reasoning,
                    actions=intent_def.actions
                )
            )

    # Sort by confidence (descending)
    results.sort(key=lambda r: r.confidence, reverse=True)
    return results


# ============================================================================
# Action Recommendation Engine
# ============================================================================

class ActionRecommendation(NamedTuple):
    """Recommended geometry action."""
    action_id: str
    action_name: str
    description: str
    parameters: dict[str, Any]
    priority: float  # 0-1
    reasoning: str


def recommend_actions(
    intent_results: list[IntentResult],
    current_building: dict[str, Any] | None = None
) -> list[ActionRecommendation]:
    """Recommend geometry actions based on classified intents.

    Args:
        intent_results: Results from classify_intent()
        current_building: Current building state (optional, for context-aware recommendations)

    Returns:
        List of ActionRecommendation sorted by priority
    """
    if not intent_results:
        return []

    recommendations: list[ActionRecommendation] = []
    action_priority_map: dict[str, float] = {}

    # Collect all actions from top intents
    for i, intent in enumerate(intent_results[:3]):  # Top 3 intents
        # Higher intents get higher priority boost
        priority_boost = 1.0 - (i * 0.1)

        for action in intent.actions:
            # Accumulate priority if action appears in multiple intents
            current_priority = action_priority_map.get(action, 0)
            new_priority = intent.confidence * priority_boost
            action_priority_map[action] = max(current_priority, new_priority)

    # Convert to recommendations
    action_descriptions = {
        "rotate_building": "Rotate building to optimize orientation",
        "reduce_depth": "Reduce building depth for better light penetration",
        "create_courtyard": "Create central courtyard for interior daylight",
        "increase_spacing": "Increase spacing between wings for more light",
        "split_mass": "Split building mass into separate volumes",
        "increase_facade_length": "Increase facade length for more windows",
        "carve_void": "Carve void or opening in building mass",
        "modify_orientation": "Modify building orientation for better exposure",
        "reposition_building": "Reposition building on site",
        "orient_facade": "Orient main facade toward key direction",
        "shift_mass": "Shift building mass on site",
        "rotate_facade": "Rotate facade to face desired direction",
        "align_to_direction": "Align building to cardinal direction",
        "create_opening": "Create opening/fenestration pattern",
        "add_floors": "Add additional floors to increase height",
        "expand_footprint": "Expand building footprint on site",
        "increase_height": "Increase overall building height",
        "expand_wings": "Expand existing wings",
        "increase_coverage": "Increase site coverage percentage",
        "stretch_wings": "Stretch building wings outward",
        "separate_masses": "Separate building into distinct masses",
        "reduce_coverage": "Reduce building site coverage",
        "modify_footprint": "Modify building footprint shape",
        "modify_height": "Modify building height",
        "add_tower": "Add tower element",
        "remove_floors": "Remove floors to reduce height",
        "adjust_tower_height": "Adjust tower height",
        "modify_podium": "Modify podium base",
        "change_profile": "Change building vertical profile",
        "move_building": "Move building on site",
        "increase_setback": "Increase setback from site edges",
        "create_plaza": "Create plaza or public space",
        "expand_openspace": "Expand open space around building",
        "edge_attraction": "Position building near selected edge",
        "street_alignment": "Align building with street/road",
        "face_direction": "Orient facade to face direction",
        "align_to_edge": "Align with site edge",
        "regenerate_topology": "Regenerate building topology",
        "modify_footprint_graph": "Modify footprint graph structure",
        "change_shape": "Change building shape/form",
        "add_wing": "Add wing to building",
        "remove_wing": "Remove wing from building",
        "reconfigure_arms": "Reconfigure multi-arm layout",
        "run_sunlight_optimization": "Run sunlight optimization algorithm",
        "create_openings": "Create window/opening pattern",
        "increase_permeability": "Increase facade permeability",
        "hollow_interior": "Hollow out interior for central space",
        "add_central_space": "Add central gathering space",
        "generate_courtyard": "Generate courtyard geometry",
        "create_atrium": "Create atrium space",
    }

    for action_id, priority in action_priority_map.items():
        description = action_descriptions.get(
            action_id,
            f"Apply {action_id} modification"
        )

        recommendations.append(
            ActionRecommendation(
                action_id=action_id,
                action_name=action_id.replace("_", " ").title(),
                description=description,
                parameters={},  # Will be filled by manipulation engine
                priority=round(priority, 2),
                reasoning=f"Recommended for {intent_results[0].intent_name}"
            )
        )

    # Sort by priority (descending)
    recommendations.sort(key=lambda r: r.priority, reverse=True)
    return recommendations


# ============================================================================
# Main Reasoning Engine
# ============================================================================

class ReasoningNode(NamedTuple):
    """Output of the reasoning engine."""
    primary_intent: str
    primary_intent_name: str
    confidence: float
    all_intents: list[IntentResult]
    architectural_goals: list[str]
    recommended_actions: list[ActionRecommendation]
    reasoning_summary: str
    can_execute: bool
    warnings: list[str]


def reason_about_feedback(
    user_feedback: str,
    current_building: dict[str, Any] | None = None
) -> ReasoningNode:
    """Main entry point: convert user feedback into architectural reasoning and actions.

    Args:
        user_feedback: User's natural language feedback
        current_building: Current building state (optional, for context-aware analysis)

    Returns:
        ReasoningNode with intents, goals, and recommended actions
    """
    warnings: list[str] = []

    # 1. Classify intents
    intent_results = classify_intent(user_feedback)

    if not intent_results:
        return ReasoningNode(
            primary_intent="unknown",
            primary_intent_name="Unknown Intent",
            confidence=0.0,
            all_intents=[],
            architectural_goals=[],
            recommended_actions=[],
            reasoning_summary="Could not classify feedback intent",
            can_execute=False,
            warnings=["No matching intent patterns found in feedback"]
        )

    # 2. Get primary intent
    primary = intent_results[0]

    # 3. Generate architectural goals
    goals = _generate_architectural_goals(primary, intent_results)

    # 4. Recommend actions
    actions = recommend_actions(intent_results, current_building)

    # 5. Build reasoning summary
    summary = f"Primary intent: {primary.intent_name} ({primary.confidence:.0%} confidence). "
    if primary.matched_synonyms:
        summary += f"Matched phrase: '{primary.matched_synonyms[0]}'. "
    summary += f"Recommended {len(actions)} actions: {', '.join(a.action_id for a in actions[:3])}."
    if len(actions) > 3:
        summary += f".. +{len(actions) - 3} more"

    return ReasoningNode(
        primary_intent=primary.intent_id,
        primary_intent_name=primary.intent_name,
        confidence=primary.confidence,
        all_intents=intent_results,
        architectural_goals=goals,
        recommended_actions=actions,
        reasoning_summary=summary,
        can_execute=len(actions) > 0,
        warnings=warnings
    )


def _generate_architectural_goals(
    primary_intent: IntentResult,
    all_intents: list[IntentResult]
) -> list[str]:
    """Generate high-level architectural goals from intents.

    Args:
        primary_intent: The primary intent
        all_intents: All classified intents

    Returns:
        List of architectural goal statements
    """
    goals: list[str] = []

    intent_to_goal = {
        "daylight": [
            "Maximize natural light penetration",
            "Reduce self-shading and internal shadows",
            "Improve facade exposure to sun"
        ],
        "views": [
            "Optimize sightlines to key landmarks",
            "Enhance visual connectivity",
            "Preserve important view corridors"
        ],
        "density": [
            "Increase floor area and capacity",
            "Maximize site utilization",
            "Improve FAR efficiency"
        ],
        "compactness": [
            "Create visual and spatial openness",
            "Improve breathing space between wings",
            "Reduce density perception"
        ],
        "height": [
            "Adjust vertical massing and profile",
            "Optimize floor count and tower height",
            "Balance scale with context"
        ],
        "openspace": [
            "Expand public realm and plaza",
            "Increase green and landscape area",
            "Improve pedestrian experience"
        ],
        "edgebased": [
            "Position building relative to site edges",
            "Align facade with street or landmark",
            "Optimize edge engagement"
        ],
        "courtyard": [
            "Create central void for light and air",
            "Introduce atrium or courtyard",
            "Improve interior spatial quality"
        ],
        "shapetransform": [
            "Reconfigure building topology",
            "Modify footprint geometry",
            "Optimize multi-wing arrangement"
        ],
        "environmental": [
            "Improve passive environmental performance",
            "Optimize solar access and ventilation",
            "Enhance thermal and light comfort"
        ],
        "privacy": [
            "Reduce overlooking between units",
            "Separate public and private zones",
            "Improve residential privacy and seclusion"
        ],
        "acoustics": [
            "Reduce noise exposure from roads/rail",
            "Shield outdoor spaces from traffic noise",
            "Improve acoustic comfort for residents"
        ],
    }

    # Add goals from primary intent
    if primary_intent.intent_id in intent_to_goal:
        goals.extend(intent_to_goal[primary_intent.intent_id])

    # Add supporting goals from secondary intents
    for intent in all_intents[1:3]:  # Top 2 secondary intents
        if intent.confidence > 0.5 and intent.intent_id in intent_to_goal:
            # Add one supporting goal
            secondary_goals = intent_to_goal[intent.intent_id]
            if secondary_goals:
                goals.append(secondary_goals[0])

    return goals


# ============================================================================
# Validation & Decision Support
# ============================================================================

def validate_actions_against_constraints(
    actions: list[ActionRecommendation],
    site_boundary: list[list[float]] | None = None,
    building_boundary: list[list[float]] | None = None
) -> dict[str, Any]:
    """Validate recommended actions against site and building constraints.

    Args:
        actions: Recommended actions
        site_boundary: Site polygon (optional)
        building_boundary: Building polygon (optional)

    Returns:
        Validation report with feasibility scores
    """
    report = {
        "total_actions": len(actions),
        "feasible_actions": 0,
        "warnings": [],
        "action_feasibility": {}
    }

    for action in actions:
        feasible = True
        warning = None

        # Check if building geometry needed
        if action.action_id in ["reduce_depth", "increase_facade_length", "carve_void"]:
            if not building_boundary:
                feasible = False
                warning = "Building boundary required for geometry analysis"

        # Check if site geometry needed
        if action.action_id in ["reposition_building", "move_building", "edge_attraction"]:
            if not site_boundary:
                feasible = False
                warning = "Site boundary required for placement analysis"

        if feasible:
            report["feasible_actions"] += 1
        else:
            report["warnings"].append(f"{action.action_id}: {warning}")

        report["action_feasibility"][action.action_id] = {
            "feasible": feasible,
            "warning": warning
        }

    return report


# ============================================================================
# Explanation & Feedback
# ============================================================================

def explain_reasoning(reasoning_node: ReasoningNode) -> str:
    """Generate human-readable explanation of the reasoning process.

    Args:
        reasoning_node: The output from reason_about_feedback()

    Returns:
        Human-readable explanation text
    """
    lines = []

    lines.append("=" * 70)
    lines.append("ARCHITECTURAL REASONING")
    lines.append("=" * 70)

    lines.append(f"\nPrimary Intent: {reasoning_node.primary_intent_name}")
    lines.append(f"Confidence: {reasoning_node.confidence:.0%}")

    if reasoning_node.all_intents:
        lines.append("\nIntent Classification:")
        for i, intent in enumerate(reasoning_node.all_intents[:5], 1):
            lines.append(f"  {i}. {intent.intent_name} ({intent.confidence:.0%})")

    if reasoning_node.architectural_goals:
        lines.append("\nArchitectural Goals:")
        for goal in reasoning_node.architectural_goals:
            lines.append(f"  • {goal}")

    if reasoning_node.recommended_actions:
        lines.append("\nRecommended Actions:")
        for i, action in enumerate(reasoning_node.recommended_actions[:5], 1):
            lines.append(f"  {i}. {action.action_name} ({action.priority:.0%})")
            lines.append(f"     {action.description}")

    lines.append("\nReasoning Summary:")
    lines.append(f"  {reasoning_node.reasoning_summary}")

    if reasoning_node.warnings:
        lines.append("\nWarnings:")
        for warning in reasoning_node.warnings:
            lines.append(f"  ⚠ {warning}")

    lines.append("\n" + "=" * 70)

    return "\n".join(lines)


# ============================================================================
# Output Serialization
# ============================================================================

def to_json(reasoning_node: ReasoningNode) -> dict[str, Any]:
    """Serialize ReasoningNode to JSON-compatible dict.

    Args:
        reasoning_node: The reasoning node to serialize

    Returns:
        JSON-compatible dictionary
    """
    return {
        "primary_intent": reasoning_node.primary_intent,
        "primary_intent_name": reasoning_node.primary_intent_name,
        "confidence": reasoning_node.confidence,
        "all_intents": [
            {
                "intent_id": i.intent_id,
                "intent_name": i.intent_name,
                "confidence": i.confidence,
                "keyword_match": i.keyword_match,
                "synonym_match": i.synonym_match,
                "matched_keywords": i.matched_keywords,
                "matched_synonyms": i.matched_synonyms,
            }
            for i in reasoning_node.all_intents
        ],
        "architectural_goals": reasoning_node.architectural_goals,
        "recommended_actions": [
            {
                "action_id": a.action_id,
                "action_name": a.action_name,
                "description": a.description,
                "priority": a.priority,
                "reasoning": a.reasoning,
            }
            for a in reasoning_node.recommended_actions
        ],
        "reasoning_summary": reasoning_node.reasoning_summary,
        "can_execute": reasoning_node.can_execute,
        "warnings": reasoning_node.warnings,
    }
