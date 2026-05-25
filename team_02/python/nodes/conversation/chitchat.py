"""
CHITCHAT node — peer/educational conversation adapted to user_type register.
Knows its own capabilities and limitations. Detects if user shifts to analysis
intent mid-conversation and writes intent="comfort" to trigger rerouting.
"""

from __future__ import annotations
from _runtime.llm import call_llm_simple


_SYSTEM_PROMPT_TEMPLATE = """\
You are Sensi, an expert in multi-sensory architectural comfort.
Your six dimensions of analysis are: thermal, visual, acoustic, spatial,
olfactory, and tactile comfort.

You are speaking with a {user_type_label}.

{register_instructions}

Answer the user's question clearly and helpfully. If they are asking about
comfort concepts, explain them in plain language with concrete architectural
examples. If they are asking something unrelated to architecture or comfort,
answer politely and briefly, then gently guide them back to what you can help
with most.

Important self-awareness: you CAN analyse apartment layouts (201, 202, 203)
across 6 comfort dimensions for a specific persona. You CANNOT:
  - generate 3D models or render images (Phase 3 — not yet available)
  - access real-world data or live databases
  - modify actual files outside of this session

If the user asks "what can you do?", explain your capabilities honestly.

Keep your response concise — no more than a short paragraph or two.
"""

_REGISTER = {
    "architect": (
        "professional architect",
        "Use confident, peer-level language. Technical terms are fine. "
        "Be efficient -- architects are busy."
    ),
    "client": (
        "homeowner or client (non-technical)",
        "Use warm, plain language. No jargon. Connect everything to daily life "
        "and lived experience. Be encouraging."
    ),
    "student": (
        "architecture student",
        "Use an educational, curious tone. Explain concepts with brief examples. "
        "Be friendly and enthusiastic -- make the learning feel insightful."
    ),
    "learner": (
        "student or curious learner",
        "Use an educational, curious tone. Explain concepts with brief examples. "
        "Be friendly and enthusiastic -- learning should be fun."
    ),
}

_INTENT_DETECT_PROMPT = """\
Does this message contain an explicit request to analyse a layout, check comfort scores,
detect conflicts, or get suggestions? Answer with just YES or NO.

Message: {raw_prompt}
"""


def build_chitchat_node(llm):
    """Return the chitchat node function, capturing the LLM instance."""

    def chitchat_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        user_type: str = state.get("user_type", "client")

        user_type_label, register_instructions = _REGISTER.get(
            user_type, _REGISTER["client"]
        )
        system = _SYSTEM_PROMPT_TEMPLATE.format(
            user_type_label=user_type_label,
            register_instructions=register_instructions,
        )

        print(f"[chitchat] Generating response for {user_type}...")
        response = call_llm_simple(llm, system, raw_prompt)

        # Detect if user has shifted to analysis intent
        detected_intent = "chitchat"
        try:
            intent_check = call_llm_simple(
                llm,
                "You detect whether a message is requesting layout analysis.",
                _INTENT_DETECT_PROMPT.format(raw_prompt=raw_prompt),
            )
            if intent_check.strip().upper().startswith("YES"):
                detected_intent = "comfort"
                print("[chitchat] Analysis intent detected -- routing to intent_classifier")
        except Exception:
            pass

        return {
            **state,
            "final_response": response,
            "intent": detected_intent,
        }

    return chitchat_node
