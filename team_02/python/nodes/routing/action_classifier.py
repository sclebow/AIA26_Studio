"""
ACTION_CLASSIFIER node — single LLM call that replaces intent_classifier + route_intent.

Outputs one `action` field that encodes BOTH what to do AND at what depth.
No second routing hop needed.

Actions:
  analyze         — compute comfort scores only
  detect          — scores + identify conflicts
  full            — scores + conflicts + suggestions
  overview        — list rooms, no scoring
  follow_up       — specific question about existing results (use cache)
  chitchat        — general conversation
  inspire         — atmosphere/image generation
  edit            — apply one OR MORE layout edits (material / glazing / furniture)
                    in a single turn → re-score once → compare
  topologic       — room adjacency graph analysis
  biophilic       — biophilic richness audit
  compare         — compare layout across two personas
"""

from __future__ import annotations
import json
import re
from _runtime.llm import call_llm_simple
from nodes._shared.utils import layout_digits


# ── Keyword fallback ──────────────────────────────────────────────────────────

_KEYWORD_MAP = [
    # Preview must come FIRST: "what if I change the floor" is a simulation, not a
    # commit, so it must win over the edit keywords below.
    ("preview",          ("what if", "what would happen", "what happens if", "would it help",
                          "simulate", "preview", "what would it", "show me what", "if i changed",
                          "if i added", "if i made", "hypothetical")),
    # All edit kinds (material / glazing / furniture) collapse to one `edit` action;
    # edit_planner decomposes the prompt into the individual ops downstream.
    ("edit",             ("change material", "change floor", "change wall", "change ceiling",
                          "wood floor", "wooden floor", "carpet", "concrete floor", "tile floor",
                          "floor to", "material to", "wall to", "make it wood", "make it fabric",
                          "glazing", "window size", "more light", "bigger window", "skylight",
                          "triple glazing", "double glazing", "single glazing",
                          "add", "plant", "add rug", "add sofa", "add furniture",
                          "put a plant", "place a")),
    ("topologic",        ("topolog", "adjacency", "connectivity", "room connection", "flow",
                          "which rooms connect", "room graph")),
    ("biophilic",        ("biophilic", "nature", "greenery", "green", "biophilia",
                          "talk green", "natural elements")),
    ("compare",          ("compare persona", "compare for", "how does", "versus", " vs ",
                          "for elderly", "for child", "for sensitive", "two personas")),
    ("inspire",          ("image", "visualise", "visualize", "atmosphere", "mood",
                          "generate", "inspire", "picture", "render", "vibe")),
    ("overview",         ("overview", "list rooms", "show rooms", "what rooms",
                          "room list", "what's in")),
    ("full",             ("improve", "suggest", "recommendation", "what should i", "fix",
                          "make better", "enhance", "full analysis", "full report")),
    ("detect",           ("detect", "conflict", "problem", "issue", "what is wrong",
                          "failing", "fails", "poor", "bad score")),
    ("follow_up",        ("why is", "why does", "what does", "tell me more", "explain",
                          "how does", "what causes", "which room", "priorit",
                          "tell me about", "what about", "how is", "how's",
                          "what can you tell", "tell me more about")),
]


def _keyword_fallback(prompt: str, has_scores: bool) -> str:
    p = prompt.lower()
    for action, keywords in _KEYWORD_MAP:
        if any(kw in p for kw in keywords):
            if action == "follow_up" and not has_scores:
                return "chitchat"
            return action
    if any(kw in p for kw in ("analyse", "analyze", "score", "assess", "check comfort",
                               "comfort", "thermal", "acoustic", "visual")):
        return "analyze"
    return "chitchat"


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a routing assistant for an architectural comfort analysis copilot.

Read the user's message and return a JSON object:
{{
  "action": "<one of the actions below>",
  "layout_id": "<layout number mentioned (e.g. 201, 204), or null>",
  "target_room": "<room name mentioned, or null>",
  "material": "<material mentioned (wood/concrete/fabric/etc.), or null>"
}}

ACTIONS — pick exactly one:

  analyze         — user wants comfort scores computed (thermal/visual/acoustic/spatial/olfactory/tactile).
                    Use for: "analyse", "score", "assess", "check comfort", "run analysis".

  detect          — user wants to find problems/conflicts in the scores.
                    Use for: "detect", "conflicts", "what is wrong", "issues", "failing".

  full            — user wants a complete report with improvement suggestions.
                    Use for: "full analysis", "improve", "suggest", "fix", "recommendations".

  overview        — user wants to see the room list with no scoring.
                    Use for: "list rooms", "what rooms", "overview of layout".

  follow_up       — user is asking a SPECIFIC question about results they already saw.
                    Use for: "why is X low", "explain the acoustic issue", "which room first".
                    ONLY use if has_prior_analysis=true AND the question is explanatory (why/what does/explain).
                    Never use for requests to change or re-run something.

  chitchat        — greeting, general question, "what can you do?", off-topic.

  inspire         — user wants images, atmosphere generation, mood visualisation.

  edit            — user wants to APPLY one or more changes to the layout: change a material
                    (floor / wall / furniture), modify glazing (window size / type / more light),
                    and/or add furniture or plants. A SINGLE message may request SEVERAL edits at
                    once — they all map to this one action.
                    Use for: "change floor to wood", "make the walls concrete", "bigger windows",
                    "triple glazing", "add a plant", "put a rug", and combinations like
                    "add 2 plants and change the glazing in the bedroom".

  preview         — user wants to SIMULATE a change to see its effect WITHOUT applying it.
                    The change is hypothetical — do not commit it.
                    Use for: "what if I change the floor to wood", "what would happen if I add a plant",
                    "simulate triple glazing", "preview a carpet in the bedroom".

  topologic       — user wants room adjacency/connectivity analysis.
                    Use for: "topologic", "adjacency", "room connections", "spatial flow".

  biophilic       — user wants a biophilic richness audit.
                    Use for: "biophilic", "greenery", "nature", "plants audit".

  compare         — user wants to compare how the layout feels for different personas.
                    Use for: "compare personas", "how does this work for elderly", "versus".

Key rules:
  - Any request to change a material, modify glazing, or add furniture/plants → edit
    (even if SEVERAL such changes are asked for in one message).
  - follow_up ONLY if has_prior_analysis=true; otherwise → chitchat or analyze
  - When in doubt between analyze/full: if any improvement word ("fix", "improve", "suggest") → full

has_prior_analysis: {has_prior_analysis}
Return ONLY the JSON. No explanation. No markdown fences.
"""


# ── Node factory ──────────────────────────────────────────────────────────────

def build_action_classifier_node(llm):
    """Return the action_classifier node, capturing the LLM instance."""

    def action_classifier_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        has_prior_analysis = bool(state.get("last_scores_json", "").strip())
        layout_id = state.get("layout_id")

        # Deterministic LOAD intent — the layout picker sends "load layout N", and loading
        # must NOT score (just render the plan and wait). Resolve it here, BEFORE the LLM,
        # so it can never be misrouted to analyze. Kept literal ("load / open / switch to …
        # layout") so it can't overlap the edit bucket ("add a plant", "place a …").
        pl = raw_prompt.strip().lower()
        if re.match(r"^(load|open|switch\s+to)\b", pl) and "layout" in pl:
            m = re.search(r"\blayout[-_ ]?(\d+)\b", pl) or re.search(r"\b(\d{3,})\b", pl)
            load_id = m.group(1) if m else layout_id
            print(f"[action_classifier] deterministic load intent -> action=load, layout_id={load_id}")
            return {**state, "action": "load", "layout_id": load_id,
                    "target_room_hint": None, "material_hint": None}

        print(f"[action_classifier] Classifying (has_prior_analysis={has_prior_analysis})...")

        action = "chitchat"
        target_room = None
        material = None

        system = _SYSTEM_PROMPT.format(has_prior_analysis=str(has_prior_analysis).lower())

        try:
            raw = call_llm_simple(llm, system, raw_prompt)
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.splitlines()
                clean = "\n".join(lines[1:-1]).strip()
            parsed = json.loads(clean)

            candidate = parsed.get("action", "chitchat").lower().strip()
            valid_actions = {
                "analyze", "detect", "full", "overview", "follow_up", "chitchat",
                "inspire", "edit", "preview", "topologic", "biophilic", "compare",
            }
            if candidate in valid_actions:
                action = candidate
            else:
                action = _keyword_fallback(raw_prompt, has_prior_analysis)
                print(f"[action_classifier] Unknown '{candidate}' — fallback: {action}")

            extracted_id = layout_digits(parsed.get("layout_id"))
            if extracted_id:
                layout_id = extracted_id

            target_room = parsed.get("target_room")
            material = parsed.get("material")

            print(f"[action_classifier] action={action} | layout_id={layout_id} | room={target_room} | material={material}")

        except Exception as exc:
            action = _keyword_fallback(raw_prompt, has_prior_analysis)
            if layout_id is None:
                m = re.search(r"\blayout\s*[-_ ]?(\d+)\b", raw_prompt, re.IGNORECASE)
                if not m:
                    m = re.search(r"\b(\d{3,})\b", raw_prompt)  # bare layout number
                if m:
                    layout_id = m.group(1)
            print(f"[action_classifier] LLM error ({exc}) — fallback: {action}")

        # Guard: a question about a specific room or sense AFTER an analysis has run
        # is a follow_up (answered from cached data by detail_respond). The small
        # routing model is inconsistent here — it has labelled "tell me about the
        # study room" as both 'chitchat' (generic boilerplate) and 'overview' (lists
        # ALL rooms). Both are wrong once scores exist, so we deterministically
        # upgrade them to follow_up when a concrete subject is referenced.
        if action in ("chitchat", "overview") and has_prior_analysis:
            pl = raw_prompt.lower()
            is_question = ("?" in raw_prompt) or any(
                w in pl for w in ("what", "how", "why", "which", "tell me", "explain", "about")
            )
            # 'overview' only counts as misrouted when a SPECIFIC room/sense is named
            # (a bare "list the rooms" should stay overview); chitchat upgrades on a
            # named subject too.
            names_specific = bool(target_room) or any(
                s in pl for s in (
                    "kitchen", "bedroom", "living", "bathroom", "study", "dining",
                    "hallway", "pantry", "thermal", "visual", "acoustic", "spatial",
                    "olfactory", "tactile",
                )
            )
            if is_question and names_specific:
                print(f"[action_classifier] upgraded {action} -> follow_up (specific room/sense question w/ prior analysis)")
                action = "follow_up"

        # Edit-cache consistency: an edit re-scores the layout and invalidates the
        # old conflicts/suggestions (analyze clears them — correct, they're stale).
        # A follow_up that asks ABOUT conflicts/suggestions would then find nothing
        # cached and answer from emptiness. Upgrade it to a fresh detect/full so the
        # answer is computed on the CURRENT layout instead of silently coming back
        # blank. (No extra cost on the normal path — only fires when the relevant
        # cache is missing.)
        if action == "follow_up":
            pl = raw_prompt.lower()
            has_conflicts   = bool(state.get("last_conflicts_json", "").strip())
            has_suggestions = bool(state.get("last_suggestions_json", "").strip())
            wants_suggest = any(w in pl for w in (
                "suggest", "improve", "fix", "recommend", "make better", "enhance", "how do i"))
            wants_conflict = any(w in pl for w in (
                "conflict", "problem", "issue", "wrong", "clash", "fail"))
            if wants_suggest and not has_suggestions:
                print("[action_classifier] follow_up wants suggestions but none cached -> upgrading to full")
                action = "full"
            elif wants_conflict and not has_conflicts:
                print("[action_classifier] follow_up wants conflicts but none cached -> upgrading to detect")
                action = "detect"

        return {
            **state,
            "action": action,
            "layout_id": layout_id,
            "target_room_hint": target_room,
            "material_hint": material,
        }

    return action_classifier_node
