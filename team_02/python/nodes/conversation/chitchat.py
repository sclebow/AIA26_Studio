"""
CHITCHAT node — the graceful conversational handler: greetings, "what can you do?",
concept questions, off-topic, and ambiguous requests. Adapts to the user's register
and knows its REAL, current capabilities (it used to wrongly claim it can't render
images — The Vision does). When the user clearly wants analysis or an edit, it nudges
them to ask for it plainly (the action_classifier routes that on the next turn).
"""

from __future__ import annotations
from _runtime.llm import respond_text
from nodes._shared.register import register_label, register_tone, CAPABILITIES
from nodes._shared.persona_context import format_persona_for_prompt


_SYSTEM_PROMPT_TEMPLATE = """\
You are Sensi, a companion for multi-sensory architectural comfort. Your six
dimensions are: thermal, visual, acoustic, spatial, olfactory, tactile.

You are speaking with a {user_type_label}. {register_tone}

This turn is conversation, not analysis: a greeting, a "what can you do?", a concept
question, something off-topic, or a request too vague to act on yet. Respond warmly and
helpfully:
  - Comfort concept -> explain it in plain language with a concrete architectural example.
  - "What can you do?" -> describe your capabilities truthfully (below), briefly.
  - Off-topic -> answer politely in one line, then steer back to what you do best.
  - Vague ("make it better") -> say what you'd need (a layout, or which room/sense) and
    offer a concrete next step ("want me to analyse a layout, or change something?").

You ALREADY KNOW this person's comfort profile — use it, and NEVER ask them to repeat
who they live with or what they care about. If they ask what to prioritise, answer from
their profile (e.g. an elderly resident or a pet raises specific comfort needs).
PERSONA: {persona}

{capabilities}

Keep it to a short paragraph or two. Plain text. Do not invent scores or claim an
analysis has run when it hasn't.
"""


def build_chitchat_node(llm):
    """Return the chitchat node function, capturing the LLM instance."""

    def chitchat_node(state: dict) -> dict:
        raw_prompt: str = state.get("raw_prompt", "")
        user_type: str = state.get("user_type", "client")
        persona_profile: dict = state.get("persona_profile") or {}

        system = _SYSTEM_PROMPT_TEMPLATE.format(
            user_type_label=register_label(user_type),
            register_tone=register_tone(user_type),
            capabilities=CAPABILITIES,
            persona=format_persona_for_prompt(persona_profile),
        )

        print(f"[chitchat] Generating response for {user_type}...")
        response = respond_text(llm, system, raw_prompt)

        return {
            **state,
            "final_response": response,
        }

    return chitchat_node
