"""
contracts.py — payload-shaping helpers.
Updated: adds layout_diff, graph_data, biophilic_data, layout_updated, action fields.
"""

from __future__ import annotations
from typing import Any


def screen_from_session(sess: dict) -> str:
    if not sess.get("quiz_complete"):
        return "quiz"
    if not sess.get("inspire_complete"):
        return "inspire"
    return "chat"


def agent_response_payload(message: str, sess: dict, final_state: dict | None = None) -> dict[str, Any]:
    """Shape one agent turn's result."""
    fs = final_state or {}
    return {
        "ok":                   True,
        "screen":               screen_from_session(sess),
        "message":              message,
        "quiz_step":            sess.get("quiz_step", 0),
        "quiz_complete":        sess.get("quiz_complete", False),
        "inspire_complete":     sess.get("inspire_complete", False),
        "onboarding_complete":  sess.get("onboarding_complete", False),
        "layout_id":            sess.get("layout_id"),
        # Action that ran this turn
        "action":               sess.get("action", ""),
        # Analysis panel data
        "scores_json":          sess.get("last_scores_json", ""),
        "conflicts_json":       sess.get("last_conflicts_json", ""),
        "suggestions_json":     sess.get("last_suggestions_json", ""),
        "analysis_depth":       sess.get("action", ""),   # action doubles as depth label
        # Specialist interpretations
        "score_interpretation": sess.get("score_interpretation", ""),
        "conflict_reasoning":   sess.get("conflict_reasoning", ""),
        "suggestion_critique":  sess.get("suggestion_critique", ""),
        # Edit tool feedback
        "layout_updated":       fs.get("layout_updated", False),
        "layout_diff":          fs.get("layout_diff", {}),
        # Insight tool data for frontend rendering
        "graph_data":           fs.get("graph_data", {}),
        "biophilic_data":       fs.get("biophilic_data", {}),
        "persona_comparison_data": fs.get("persona_comparison_data", {}),
    }


def init_payload_from_persona(persona: dict) -> dict[str, Any]:
    name = persona.get("name", "")
    msg = (
        f"Welcome back{', ' + name if name else ''}! "
        "Your comfort profile is loaded. "
        "Tell me which layout you'd like to explore."
    )
    return {
        "screen":      "chat",
        "message":     msg,
        "has_persona": True,
        "persona":     persona,
    }


def init_payload_from_greeting(message: str, sess: dict) -> dict[str, Any]:
    return {
        "screen":      "quiz",
        "message":     message,
        "has_persona": False,
        "quiz_step":   sess.get("quiz_step", 0),
    }


def session_for_returning_user(persona: dict) -> dict[str, Any]:
    return {
        "onboarding_complete": True,
        "greeted":             True,
        "quiz_complete":       True,
        "inspire_complete":    True,
        "persona_profile":     persona,
        "user_type":           persona.get("role", "client"),
    }


def patch_persona(sess: dict) -> dict[str, Any]:
    persona = dict(sess.get("persona_profile") or {})
    stored_name = persona.get("name", "")
    if not stored_name or stored_name.lower() in ("user", "there", ""):
        fallback_name = sess.get("user_name", "")
        if fallback_name and fallback_name.lower() not in ("there", ""):
            persona["name"] = fallback_name.strip().capitalize()
    stored_role = persona.get("role", "client")
    if stored_role == "client":
        sess_role = sess.get("user_type") or sess.get("preliminary_role", "client")
        if sess_role and sess_role not in ("client", "", None):
            persona["role"] = sess_role
    return persona


def moodboard_context(user_name: str, aesthetic_text: str, n_picks: int) -> str:
    return (
        f"User name: {user_name}\n"
        f"{aesthetic_text}\n\n"
        f"[Moodboard context: user selected {n_picks} reference image(s) "
        f"across aesthetic refinement rounds.]"
    )
