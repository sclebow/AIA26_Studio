"""
contracts.py — pure payload-shaping helpers (stdlib only, no heavy imports).

These reproduce, byte-for-byte, the JSON objects the old QWebChannel bridge sent
to the browser (window.receiveResponse, window.receiveInit, window.receivePersona).
Keeping them dependency-free means they can be unit-tested without langgraph/Qt,
and it cleanly separates "what the frontend expects" from "how we run the agent."

Reference: sensi_pyqt.py SensiBridge._on_agent_response / _on_init_done /
_on_moodboard_done.
"""

from __future__ import annotations
from typing import Any


def screen_from_session(sess: dict) -> str:
    """Which screen the UI should show, derived from session flags.

    Mirrors SensiBridge._screen_from_session.
    """
    if not sess.get("quiz_complete"):
        return "quiz"
    if not sess.get("inspire_complete"):
        return "inspire"
    return "chat"


def agent_response_payload(message: str, sess: dict) -> dict[str, Any]:
    """Shape one agent turn's result. Mirrors _on_agent_response's receiveResponse."""
    return {
        "ok":                   True,
        "screen":               screen_from_session(sess),
        "message":              message,
        "quiz_step":            sess.get("quiz_step", 0),
        "quiz_complete":        sess.get("quiz_complete", False),
        "inspire_complete":     sess.get("inspire_complete", False),
        "onboarding_complete":  sess.get("onboarding_complete", False),
        "layout_id":            sess.get("layout_id"),
        # Analysis panel data - raw comfort-tool results
        "scores_json":          sess.get("last_scores_json", ""),
        "conflicts_json":       sess.get("last_conflicts_json", ""),
        "suggestions_json":     sess.get("last_suggestions_json", ""),
        "analysis_depth":       sess.get("comfort_depth", ""),
        # Specialist interpretations for panel narrative sections
        "score_interpretation": sess.get("score_interpretation", ""),
        "conflict_reasoning":   sess.get("conflict_reasoning", ""),
        "suggestion_critique":  sess.get("suggestion_critique", ""),
    }


def init_payload_from_persona(persona: dict) -> dict[str, Any]:
    """Init payload for a returning user with a saved persona.

    Mirrors the persona branch of SensiBridge.initApp (receiveInit).
    """
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
    """Init payload for a first-time user after the silent greeting turn.

    Mirrors SensiBridge._on_init_done (receiveInit).
    """
    return {
        "screen":      "quiz",
        "message":     message,
        "has_persona": False,
        "quiz_step":   sess.get("quiz_step", 0),
    }


def session_for_returning_user(persona: dict) -> dict[str, Any]:
    """Build the in-memory session for a returning user with a saved persona.

    Mirrors the session dict SensiBridge.initApp constructs.
    """
    return {
        "onboarding_complete": True,
        "greeted":             True,
        "quiz_complete":       True,
        "inspire_complete":    True,
        "persona_profile":     persona,
        "user_type":           persona.get("role", "client"),
    }


def patch_persona(sess: dict) -> dict[str, Any]:
    """Patch persona name/role from session if the LLM returned defaults.

    Mirrors the fallback logic in SensiBridge._on_moodboard_done.
    """
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
    """Compose the run_agent prompt that triggers persona_compiler.

    Mirrors the `context` string built in SensiBridge.buildMoodboard.
    """
    return (
        f"User name: {user_name}\n"
        f"{aesthetic_text}\n\n"
        f"[Moodboard context: user selected {n_picks} reference image(s) "
        f"across aesthetic refinement rounds.]"
    )
