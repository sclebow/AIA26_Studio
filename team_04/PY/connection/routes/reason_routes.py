"""Reason Node API routes — architectural feedback analysis and intent classification.

Exposes the reason node for converting user feedback into geometry operations.

Routes:
  POST /api/reason/analyze      — Analyze user feedback and generate reasoning
  GET  /api/reason/intents      — List all available intent categories
  POST /api/reason/validate     — Validate actions against constraints
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..notebook_logic import reason_node as rn

router = APIRouter(prefix="/api/reason", tags=["api-reason"])


# ============================================================================
# Request Models
# ============================================================================

class AnalyzeRequest(BaseModel):
    """Request to analyze architectural feedback."""
    user_feedback: str = Field(description="User's natural language feedback")
    current_building: dict[str, Any] | None = Field(
        default=None,
        description="Current building state (optional, for context-aware analysis)"
    )


class ValidateRequest(BaseModel):
    """Request to validate actions against constraints."""
    actions: list[str] = Field(description="List of action IDs to validate")
    site_boundary: list[list[float]] | None = Field(
        default=None,
        description="Site boundary polygon (optional)"
    )
    building_boundary: list[list[float]] | None = Field(
        default=None,
        description="Building boundary polygon (optional)"
    )


# ============================================================================
# Routes
# ============================================================================

@router.post("/analyze")
def analyze_feedback(body: AnalyzeRequest) -> dict[str, Any]:
    """Analyze user feedback and generate architectural reasoning.

    Converts natural language feedback into:
    - Intent classification (primary + secondary)
    - Architectural goals
    - Recommended geometry actions
    - Confidence scores and reasoning

    Example:
        {
          "user_feedback": "I want more daylight in the building",
          "current_building": {...}
        }

    Returns:
        {
          "primary_intent": "daylight",
          "confidence": 0.94,
          "recommended_actions": [
            {"action_id": "reduce_depth", "priority": 0.95, ...},
            {"action_id": "create_courtyard", "priority": 0.88, ...},
            ...
          ],
          ...
        }
    """
    if not body.user_feedback or not body.user_feedback.strip():
        raise HTTPException(status_code=422, detail="user_feedback cannot be empty")

    try:
        reasoning = rn.reason_about_feedback(
            body.user_feedback,
            current_building=body.current_building
        )

        return rn.to_json(reasoning)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/intents")
def list_intents() -> dict[str, Any]:
    """List all available intent categories with descriptions and keywords.

    Returns information about each intent:
    - name: Human-readable intent name
    - description: What this intent represents
    - keywords: Primary keywords that trigger this intent
    - synonyms: Example phrases that match this intent
    - actions: Possible geometry actions for this intent
    """
    intents_data = {}

    for intent_id, intent_def in rn.INTENT_DEFINITIONS.items():
        intents_data[intent_id] = {
            "id": intent_def.intent_id,
            "name": intent_def.name,
            "description": intent_def.description,
            "keywords": intent_def.keywords,
            "example_synonyms": intent_def.synonyms[:5],  # First 5 examples
            "synonym_count": len(intent_def.synonyms),
            "possible_actions": intent_def.actions,
        }

    return {
        "total_intents": len(intents_data),
        "intents": intents_data,
    }


@router.get("/intents/{intent_id}")
def get_intent_detail(intent_id: str) -> dict[str, Any]:
    """Get detailed information about a specific intent.

    Args:
        intent_id: Intent ID (e.g., 'daylight', 'views', 'density')

    Returns:
        Detailed intent definition with all synonyms and actions
    """
    intent_def = rn.INTENT_DEFINITIONS.get(intent_id)

    if not intent_def:
        raise HTTPException(status_code=404, detail=f"Intent '{intent_id}' not found")

    return {
        "id": intent_def.intent_id,
        "name": intent_def.name,
        "description": intent_def.description,
        "keywords": intent_def.keywords,
        "all_synonyms": intent_def.synonyms,
        "possible_actions": intent_def.actions,
        "confidence_boost": intent_def.confidence_boost,
    }


@router.post("/validate")
def validate_actions(body: ValidateRequest) -> dict[str, Any]:
    """Validate recommended actions against site and building constraints.

    Checks if each action can be executed given the available geometry.

    Args:
        actions: List of action IDs
        site_boundary: Site polygon (optional)
        building_boundary: Building polygon (optional)

    Returns:
        Validation report with feasibility for each action
    """
    if not body.actions:
        raise HTTPException(status_code=422, detail="actions cannot be empty")

    try:
        # Convert action IDs to ActionRecommendation objects
        action_recs = [
            rn.ActionRecommendation(
                action_id=action_id,
                action_name=action_id.replace("_", " ").title(),
                description="",
                parameters={},
                priority=1.0,
                reasoning="Validation check"
            )
            for action_id in body.actions
        ]

        report = rn.validate_actions_against_constraints(
            action_recs,
            site_boundary=body.site_boundary,
            building_boundary=body.building_boundary
        )

        return report
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/explain")
def explain(body: AnalyzeRequest) -> dict[str, Any]:
    """Get detailed explanation of the reasoning process.

    Analyzes feedback and returns human-readable explanation of:
    - Intent classification with confidence
    - Matched keywords and phrases
    - Architectural goals
    - Recommended actions with priorities
    - Any warnings or constraints

    Args:
        user_feedback: User's natural language feedback

    Returns:
        Human-readable explanation with intent hierarchy
    """
    if not body.user_feedback or not body.user_feedback.strip():
        raise HTTPException(status_code=422, detail="user_feedback cannot be empty")

    try:
        reasoning = rn.reason_about_feedback(
            body.user_feedback,
            current_building=body.current_building
        )

        explanation = rn.explain_reasoning(reasoning)

        return {
            "explanation": explanation,
            "reasoning_json": rn.to_json(reasoning)
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
def reason_health() -> dict[str, Any]:
    """Health check for reason node."""
    return {
        "status": "ok",
        "available_intents": len(rn.INTENT_DEFINITIONS),
        "intents": list(rn.INTENT_DEFINITIONS.keys()),
    }
