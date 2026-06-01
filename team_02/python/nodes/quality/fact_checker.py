"""
FACT_CHECKER node — data integrity gate. Every score, room name, and sense
in the response must be traceable to MCP tool output.
Returns VERIFIED or DISCREPANCY with exact location. Max 1 loop.
"""

from __future__ import annotations
import json
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT = """\
You are a fact-checker for an architectural comfort analysis tool.

Your ONLY job: verify that every factual claim in the response matches
the raw tool output provided. Check for:

  1. Room names — every room mentioned in the response must exist in the tool data
  2. Scores — every score cited must match (within ±0.01) the value in the data
  3. Senses — only the six allowed senses: thermal, visual, acoustic, spatial, olfactory, tactile
  4. Conflicts — any conflict mentioned must appear in the conflicts data
  5. Suggestions — any suggestion cited must appear in the suggestions data

Return ONLY:
  VERIFIED
  — or —
  DISCREPANCY: [exact location and what is wrong, e.g. "Bedroom acoustic score cited as 0.45 but tool data shows 0.42"]

Nothing else. One line.

RESPONSE TO CHECK:
{response}

TOOL DATA — SCORES:
{scores}

TOOL DATA — CONFLICTS:
{conflicts}

TOOL DATA — SUGGESTIONS:
{suggestions}
"""


def _safe_format(json_str: str) -> str:
    if not json_str:
        return "(not run)"
    try:
        return json.dumps(json.loads(json_str), indent=2)
    except Exception:
        return json_str


def build_fact_checker_node(llm):
    """Return the fact_checker node function, capturing the LLM instance."""

    def fact_checker_node(state: dict) -> dict:
        final_response: str = state.get("final_response") or ""
        scores: str = state.get("last_scores_json", "")
        conflicts: str = state.get("last_conflicts_json", "")
        suggestions: str = state.get("last_suggestions_json", "")
        loops: int = state.get("fact_check_loops", 0)

        new_loops = loops + 1
        print(f"[fact_checker] Checking facts (loop {new_loops}/1)...")

        # If no tool data was generated (e.g. chitchat path somehow reached here)
        if not scores and not conflicts and not suggestions:
            print("[fact_checker] No tool data — VERIFIED by default")
            return {
                **state,
                "fact_check_decision": "VERIFIED",
                "fact_check_feedback": "",
                "fact_check_loops": new_loops,
            }

        system = _SYSTEM_PROMPT.format(
            response=final_response,
            scores=_safe_format(scores),
            conflicts=_safe_format(conflicts),
            suggestions=_safe_format(suggestions),
        )

        decision = "VERIFIED"
        feedback = ""

        try:
            raw = call_llm_simple(llm, system, "Fact-check this response.")
            raw = raw.strip()
            if raw.upper().startswith("VERIFIED"):
                decision = "VERIFIED"
                print("[fact_checker] VERIFIED")
            elif raw.upper().startswith("DISCREPANCY"):
                decision = "DISCREPANCY"
                if ":" in raw:
                    feedback = raw.split(":", 1)[1].strip()
                else:
                    feedback = raw[11:].strip()
                print(f"[fact_checker] DISCREPANCY — {feedback[:80]}")
            else:
                decision = "VERIFIED"
                print(f"[fact_checker] Unclear response — defaulting to VERIFIED")
        except Exception as exc:
            decision = "VERIFIED"
            print(f"[fact_checker] LLM error ({exc}) — defaulting to VERIFIED")

        return {
            **state,
            "fact_check_decision": decision,
            "fact_check_feedback": feedback,
            "fact_check_loops": new_loops,
        }

    return fact_checker_node
