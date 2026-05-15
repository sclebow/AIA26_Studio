"""
nodes/respond.py -- RESPOND node for the Comfort Copilot state graph.

Intent-driven output: response format changes based on analysis depth.
  analyze -> score interpretation only
  detect  -> conflict-focused, scores as evidence
  full    -> suggestion-led, conflicts and scores as backing
"""

from __future__ import annotations
import json as _json
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = (
    "You are Comfort Copilot, an architectural comfort analyst specialising in "
    "multi-sensory wellbeing: thermal, visual, acoustic, spatial, olfactory, tactile.\n\n"
    "Write a plain-language response shaped around what the user asked for.\n"
    "Use ONLY the data provided. Never invent scores, conflicts, or suggestions.\n\n"
    "ALWAYS start with exactly one line:\n"
    "  For a <persona>, Layout <id>:\n\n"
    "Then follow the FORMAT INSTRUCTIONS in the user message exactly.\n\n"
    "Hard rules for ALL formats:\n"
    "- Use ONLY scores from PRE-PROCESSED ROOM DATA. Copy numbers exactly.\n"
    "- Best and Worst are pre-computed -- copy them, do not recalculate.\n"
    "- Persona name appears ONCE at the top only. Never repeat per room.\n"
    "- No markdown tables. No JSON. No tool names. Plain ASCII only.\n"
    "- Use a hyphen (-) not an em dash. No special characters.\n"
    "- Be concise. One room = one short block. No padding.\n"
)

_FORMAT_ANALYZE = (
    "FORMAT: Score interpretation (analyze only)\n"
    "Scores were computed. No conflicts or suggestions were run.\n\n"
    "For EACH room write:\n"
    "  <Room Name> (overall: X.XX)\n"
    "  - Best: <sense> (X.XX) - one short note for this persona\n"
    "  - Worst: <sense> (X.XX) - one short note for this persona\n"
    "  - Scores: thermal X.XX | visual X.XX | acoustic X.XX | spatial X.XX | olfactory X.XX | tactile X.XX\n"
    "  - One sentence: what this profile means for this persona here.\n\n"
    "End with ONE sentence summarising the layout for this persona.\n"
    "Do NOT mention conflicts or suggestions.\n"
)

_FORMAT_DETECT = (
    "FORMAT: Conflict report (detect only)\n"
    "Scores and conflicts were computed. No suggestions were run.\n\n"
    "Focus on what is failing and why. Scores are evidence, not the headline.\n\n"
    "For rooms WITH conflicts:\n"
    "  <Room Name>\n"
    "  - Issues: <sense> (X.XX), <sense> (X.XX) - below threshold for this persona\n"
    "  - Why it matters: one sentence on what this failure means for this persona.\n\n"
    "For rooms WITHOUT conflicts, one closing line:\n"
    "  Rooms without comfort issues: <Room Name>, <Room Name>, ...\n\n"
    "End with ONE sentence on the most critical risk area for this persona.\n"
    "Do NOT mention suggestions.\n"
)

_FORMAT_FULL = (
    "FORMAT: Actionable suggestions (full analysis)\n"
    "All three tools ran. Lead with what needs to change.\n"
    "Scores and conflicts are supporting evidence, not the headline.\n\n"
    "For rooms WITH suggestions:\n"
    "  <Room Name>\n"
    "  - Fix: <primary suggestion for highest-priority sense>\n"
    "  - Why: <flagged sense> scored X.XX, below threshold for this persona.\n"
    "  - Also address: <other flagged senses and their suggestions, one per line>\n\n"
    "For rooms WITHOUT suggestions, one closing line:\n"
    "  Rooms within comfort range: <Room Name>, <Room Name>, ...\n\n"
    "End with ONE sentence naming the single most important intervention.\n"
    "Do NOT list all scores for every room. Use scores only as evidence.\n"
)


def _preprocess_scores(scores_json):
    if not scores_json:
        return "(no scores available)"
    try:
        data = _json.loads(scores_json)
    except Exception:
        return scores_json

    lines = []
    for room in data.get("rooms", []):
        name    = room.get("roomName", "unknown")
        sc      = room.get("comfortScores", {})
        overall = room.get("overallScore", 0.0)
        if not sc:
            continue
        best_sense  = max(sc, key=lambda k: sc[k])
        worst_sense = min(sc, key=lambda k: sc[k])
        if best_sense == worst_sense:
            srt = sorted(sc, key=lambda k: sc[k], reverse=True)
            best_sense, worst_sense = srt[0], srt[-1]
        lines.append(
            "Room: {} | overall={:.2f} | best={}({:.2f}) worst={}({:.2f}) | "
            "thermal={:.2f} visual={:.2f} acoustic={:.2f} spatial={:.2f} olfactory={:.2f} tactile={:.2f}".format(
                name, overall,
                best_sense, sc[best_sense], worst_sense, sc[worst_sense],
                sc.get("thermal", 0), sc.get("visual", 0), sc.get("acoustic", 0),
                sc.get("spatial", 0), sc.get("olfactory", 0), sc.get("tactile", 0),
            )
        )
    return "\n".join(lines) if lines else "(no rooms found)"


def _preprocess_conflicts(conflicts_json):
    if not conflicts_json:
        return "not run"
    try:
        data = _json.loads(conflicts_json)
    except Exception:
        return conflicts_json
    flagged = data.get("flaggedRooms", [])
    if not flagged:
        return "no conflicts detected"
    lines = []
    for room in flagged:
        name   = room.get("roomName", "unknown")
        senses = []
        for c in room.get("conflicts", []):
            for s in ["thermal", "visual", "acoustic", "spatial", "olfactory", "tactile"]:
                if s in c and s not in senses:
                    senses.append(s)
        lines.append("{}: {}".format(name, ", ".join(senses)))
    return "\n".join(lines)


def _preprocess_suggestions(suggestions_json):
    if not suggestions_json:
        return "not run"
    try:
        data = _json.loads(suggestions_json)
    except Exception:
        return suggestions_json
    improvements = data.get("improvements", [])
    if not improvements:
        return "no suggestions generated"
    lines = []
    for room in improvements:
        name = room.get("roomName", "unknown")
        for s in room.get("suggestions", []):
            lines.append("{} / {}: {}".format(name, s.get("sense", "?"), s.get("suggestion", "")))
    return "\n".join(lines)


def build_respond_node(llm):
    """Return the respond node function, capturing the LLM instance."""

    def respond_node(state):
        persona     = state.get("persona_detected", "Neutral")
        layout_id   = state.get("layout_id", "?")
        depth       = state.get("comfort_depth", "analyze")
        scores      = state.get("last_scores_json", "")
        conflicts   = state.get("last_conflicts_json", "")
        suggestions = state.get("last_suggestions_json", "")
        raw_prompt  = state.get("raw_prompt", "")

        processed_scores      = _preprocess_scores(scores)
        processed_conflicts   = _preprocess_conflicts(conflicts) if conflicts else "not run"
        processed_suggestions = _preprocess_suggestions(suggestions) if suggestions else "not run"

        if depth == "full":
            fmt = _FORMAT_FULL
        elif depth == "detect":
            fmt = _FORMAT_DETECT
        else:
            fmt = _FORMAT_ANALYZE

        user_message = "\n".join([
            "User request: {}".format(raw_prompt),
            "Persona: {}".format(persona),
            "Layout ID: {}".format(layout_id),
            "",
            "--- FORMAT INSTRUCTIONS (follow exactly) ---",
            fmt,
            "",
            "--- PRE-PROCESSED ROOM DATA (copy scores exactly as shown) ---",
            processed_scores,
            "",
            "--- CONFLICTS ---",
            processed_conflicts,
            "",
            "--- SUGGESTIONS ---",
            processed_suggestions,
        ])

        print("[respond] Generating natural language report...")
        response = call_llm_simple(llm, _SYSTEM_PROMPT, user_message)
        return {**state, "final_response": response}

    return respond_node
