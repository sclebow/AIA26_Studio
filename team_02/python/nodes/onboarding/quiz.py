"""
QUIZ node -- structured multi-turn onboarding profiler. (v2 -- redesigned)

Changes from v1:
  - Name extracted from q0 answer; stored as user_name in state
  - Role detected from q1 answer; stored as preliminary_role in state
  - ACK prompt personalised with name + role-aware tone
  - Questions updated to match new UI step structure:
      step 1 -> role (card picker in UI, formatted text sent to graph)
      step 2 -> space story (text area)
      step 3 -> sensory bothers (multi-select cards in UI)
      step 4 -> life stage + living situation (card pickers + optional other)
      step 5 -> non-negotiable (text input)

Flow (one question per turn):
  Step 0 (turn 2): User's response to GREET -> name extracted, Q1 asked
  Step 1 (turn 3): Role answer stored + role detected, Q2 asked
  Step 2 (turn 4): Space story stored, Q3 asked
  Step 3 (turn 5): Sensory bothers stored, Q4 asked
  Step 4 (turn 6): Life stage + living situation stored, Q5 asked
  Step 5 (turn 7): Non-negotiable stored -> quiz_complete = True -> INSPIRE

State consumed:  quiz_step, quiz_answers, raw_prompt, user_name, preliminary_role
State produced:  quiz_step (incremented), quiz_answers (updated),
                 user_name (str), preliminary_role (str),
                 quiz_complete (bool), final_response (str)
"""

from __future__ import annotations
from _runtime.llm import call_llm_simple


# -- Name extraction -----------------------------------------------------------

_NAME_EXTRACT_PROMPT = """\
Extract only the person's first name from the message below.
Return ONLY the first name -- nothing else, no punctuation, no explanation.
If no name is present or the message is too vague to tell, return "there".

Examples:
  "I'm Emilie" -> Emilie
  "My name is Joao, I'm an architect" -> Joao
  "hello!" -> there
  "it's me, alex" -> Alex
"""


def _extract_name(llm, raw: str) -> str:
    """Call LLM to pull the first name from the greet response. Fast and cheap."""
    try:
        result = call_llm_simple(llm, _NAME_EXTRACT_PROMPT, raw).strip()
        name = result.split()[0].rstrip(".,!") if result else "there"
        return name if name else "there"
    except Exception:
        return "there"


# -- Role detection ------------------------------------------------------------

def _detect_role(raw: str) -> str:
    """
    Detect role from the UI-formatted card answer for step 1.
    The UI sends text like: "I design spaces -- architect"
    Also handles free-text responses via keyword scan.
    """
    t = raw.lower()
    if "architect" in t or "design" in t:
        return "architect"
    if "student" in t or "learn" in t or "study" in t:
        return "student"
    return "client"


# -- Questions -----------------------------------------------------------------
# Index = the step AFTER which this question is asked.
# Step 0 answer = response to GREET's "who are you?" -- stored, then Q1 asked.
# The UI renders card pickers for steps 1, 3, 4 and formats each
# selection as natural language before sending to the graph.

_QUESTIONS: dict[int, str] = {
    1: (
        "How would you describe your relationship with spaces? "
        "Do you design them, live in them, or are you here to learn?"
    ),
    2: (
        "Tell me about a space that made you feel truly at home -- "
        "it could be anywhere. What made it feel right?"
    ),
    3: (
        "What usually pulls you out of comfort in a space? "
        "Think about temperature, noise, light, air quality, or feeling cramped."
    ),
    4: (
        "Tell me a bit about your life at home -- "
        "your life stage and who you share your space with."
    ),
    5: (
        "Last one -- if your ideal space had one non-negotiable quality, "
        "what would it be?"
    ),
}

_TOTAL_STEPS = 5  # Steps 0-5 inclusive (6 answers total, 5 follow-up questions)


# -- Step 1→2 ACK: role templates (replaces LLM call) -------------------------
# The UI sends one of exactly 3 fixed strings for step 1. Role is already
# detected deterministically by _detect_role — no LLM needed here.

_ROLE_ACKS: dict[str, str] = {
    "architect": "Design perspective — exactly what Sensi needs, {name}.",
    "client":    "Good to have you here, {name}.",
    "student":   "Love the curiosity, {name} — you're in the right place.",
}


# -- Step 3→4 ACK: sense-aware templates (replaces LLM call) ------------------
# Input is always "The senses that pull me out of comfort: X, Y, Z."
# We extract the senses directly and pick a fitting line.

def _ack_for_senses(name: str, q3_text: str) -> str:
    """Build a sense-aware ACK without an LLM call."""
    # Parse sense names out of the structured UI string
    lower = q3_text.lower()
    found = [s for s in ("thermal", "visual", "acoustic", "spatial", "olfactory", "tactile")
             if s in lower]

    if not found:
        return f"Noted, {name} — comfort is personal."
    if len(found) == 1:
        return f"{found[0].capitalize()} sensitivity noted, {name}."
    if len(found) <= 3:
        listed = " and ".join(f"{s}" for s in found) if len(found) == 2 \
            else ", ".join(found[:-1]) + f" and {found[-1]}"
        return f"{listed.capitalize()} — clear signals, {name}."
    # 4+ senses selected
    return f"Your senses are finely tuned, {name}."


# -- Step 4→5 ACK: life-stage template (replaces LLM call) -------------------
# Input is always "Life stage: X. Living situation: Y."

def _ack_for_life_stage(name: str, q4_text: str) -> str:
    """Build a life-stage-aware ACK without an LLM call."""
    lower = q4_text.lower()
    if "family" in lower or "kids" in lower or "children" in lower:
        return f"A shared home — that shapes comfort in real ways, {name}."
    if "partner" in lower or "spouse" in lower or "girlfriend" in lower \
            or "boyfriend" in lower or "husband" in lower or "wife" in lower:
        return f"Living with someone changes the comfort equation, {name}."
    if "alone" in lower or "just me" in lower or "by myself" in lower or "solo" in lower:
        return f"Your space, your rules then, {name}."
    if "grandma" in lower or "grandpa" in lower or "grandmother" in lower \
            or "grandfather" in lower:
        return f"Multi-generational living — that tells me a lot, {name}."
    if "flatmate" in lower or "roommate" in lower:
        return f"Shared spaces come with their own comfort negotiations, {name}."
    return f"Thanks for sharing that, {name}."


# -- Step 2→3 ACK: LLM call (the one worth keeping) ---------------------------
# This is the only free-text answer where the user shares something personal.
# The LLM earns its place here — one call, where warmth actually matters.

_ACK_STORY_PROMPT = """\
You are Sensi, a warm comfort companion.
The user just described a space that made them feel at home.

Their name is: {user_name}
Their role:    {user_role}

Write ONE short acknowledgment sentence — max 10 words — that:
  - Always includes their name
  - Responds warmly to the emotional quality of what they described
    (do NOT repeat their words verbatim)
  - Feels genuine, not generic

Then on a new line, ask: {next_question}

Output ONLY the acknowledgment + question. No headers, no markdown.
Tone: if architect, a light spatial reference is fine. Otherwise keep it warm and plain.
"""


# -- Quiz node factory ---------------------------------------------------------

def build_quiz_node(llm):
    """Return the quiz node function, capturing the LLM instance."""

    def quiz_node(state: dict) -> dict:
        raw_prompt:       str  = state.get("raw_prompt", "")
        quiz_step:        int  = state.get("quiz_step", 0)
        quiz_answers:     dict = dict(state.get("quiz_answers") or {})
        user_name:        str  = state.get("user_name", "")
        preliminary_role: str  = state.get("preliminary_role", "client")

        print(f"[quiz] Step {quiz_step} -- storing answer, preparing next question")

        # -- Store the current answer ------------------------------------------
        quiz_answers[f"q{quiz_step}"] = raw_prompt

        # -- Step 0: extract name from greet response --------------------------
        if quiz_step == 0 and not user_name:
            user_name = _extract_name(llm, raw_prompt)
            print(f"[quiz] Name extracted: {user_name}")

        # -- Step 1: detect role from card/text answer -------------------------
        if quiz_step == 1:
            preliminary_role = _detect_role(raw_prompt)
            print(f"[quiz] Role detected: {preliminary_role}")

        # -- Last step answered: quiz complete ---------------------------------
        if quiz_step >= _TOTAL_STEPS:
            print("[quiz] All answers collected -- quiz complete, routing to inspire")
            return {
                **state,
                "quiz_step":        quiz_step + 1,
                "quiz_answers":     quiz_answers,
                "user_name":        user_name,
                "preliminary_role": preliminary_role,
                "quiz_complete":    True,
                "final_response": (
                    f"Thank you, {user_name} -- that gives me a vivid picture of you. "
                    "Now for the part I love most: let's build your sensory world."
                ),
            }

        # -- Ask the next question ---------------------------------------------
        next_step     = quiz_step + 1
        next_question = _QUESTIONS[next_step]

        n = user_name or "there"

        if quiz_step == 0:
            # Step 0: name just extracted — hardcoded, no LLM.
            response = f"Nice to meet you, {n}! {next_question}"

        elif quiz_step == 1:
            # Step 1→2: role answer — always one of 3 structured strings.
            # Template is faster and just as warm as an LLM call here.
            ack = _ROLE_ACKS.get(preliminary_role, f"Got it, {n}.").format(name=n)
            response = f"{ack}\n{next_question}"
            print(f"[quiz] Step 1 ACK (template, role={preliminary_role})")

        elif quiz_step == 2:
            # Step 2→3: free-text space story — the one place the LLM earns
            # its keep. User shared something personal; a warm response matters.
            try:
                prompt = _ACK_STORY_PROMPT.format(
                    user_name     = n,
                    user_role     = preliminary_role,
                    next_question = next_question,
                )
                response = call_llm_simple(llm, prompt, raw_prompt)
                if not response.strip():
                    print("[quiz] LLM returned empty story ACK -- using fallback")
                    response = f"That sounds like a meaningful space, {n}.\n{next_question}"
            except Exception as exc:
                print(f"[quiz] LLM story ACK failed ({exc}) -- using fallback")
                response = f"That sounds like a meaningful space, {n}.\n{next_question}"

        elif quiz_step == 3:
            # Step 3→4: structured sense list — template, no LLM.
            ack = _ack_for_senses(n, raw_prompt)
            response = f"{ack}\n{next_question}"
            print(f"[quiz] Step 3 ACK (template)")

        elif quiz_step == 4:
            # Step 4→5: structured life-stage string — template, no LLM.
            ack = _ack_for_life_stage(n, raw_prompt)
            response = f"{ack}\n{next_question}"
            print(f"[quiz] Step 4 ACK (template)")

        else:
            # Catch-all for any unexpected step
            response = f"{n}, {next_question}"

        return {
            **state,
            "quiz_step":        next_step,
            "quiz_answers":     quiz_answers,
            "user_name":        user_name,
            "preliminary_role": preliminary_role,
            "quiz_complete":    False,
            "final_response":   response,
        }

    return quiz_node
