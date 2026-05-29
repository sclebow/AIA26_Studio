"""
graph.py -- Sensi state graph  (v3 Bundle C — follow_up path, fact_checker removed)

===========================================================================
WHAT CHANGED FROM v3 → Bundle C
===========================================================================

Layout mode (Bundle C — 2026-05-24):
  - intent_classifier now classifies 6 intents:
      comfort | overview | inspire | follow_up | chitchat | tools
  - follow_up path added:
      intent_classifier → detail_respond → what_next
      (uses cached session data — score_interpretation, conflict_reasoning,
       suggestion_critique — no MCP re-run)
  - fact_checker REMOVED (redundant for short persona-aware summaries)
  - Specialist outputs (score_interpretation, conflict_reasoning, suggestion_critique)
    persisted in session across turns and passed to JS via sensi_pyqt.py
  - respond prompt slimmed; what_next prompt tightened (depth-aware)

===========================================================================
ONBOARDING FLOW  (first session only)
===========================================================================

  Turn 1:  START → greet  → END
  Turn 2:  START → quiz (step 0: store intro, ask Q1)  → END
  Turn 3:  START → quiz (step 1: store Q1, ask Q2)     → END
  Turn 4:  START → quiz (step 2: store Q2, ask Q3)     → END
  Turn 5:  START → quiz (step 3: store Q3, ask Q4)     → END
  Turn 6:  START → quiz (step 4: store Q4, ask Q5)     → END
  Turn 7:  START → quiz (step 5: store Q5, done)       → inspire (asks question) → END
  Turn 8:  START → inspire (captures answer, done)     → persona_compiler → END
  Turn 9+: onboarding_complete=True → intent_classifier → layout mode

===========================================================================
LAYOUT MODE FLOW
===========================================================================

  ┌─ ROUTING ────────────────────────────────────────────────────────────────┐
  │  intent_classifier [LLM]                                                 │
  │    comfort | overview | tools  → load_layout                             │
  │    follow_up                   → detail_respond → what_next              │
  │    inspire                     → inspire                                 │
  │    chitchat                    → chitchat                                │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ ANALYSIS CHAIN ─────────────────────────────────────────────────────────┐
  │  load_layout → route_intent                                              │
  │  → analyze [MCP] → score_interpreter [LLM]                              │
  │  → detect [MCP] → conflict_reasoner [LLM]                               │
  │  → suggest [MCP] → suggestion_critic [LLM] → respond [LLM]              │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ TOOL PATHS (placeholders) ──────────────────────────────────────────────┐
  │  what-if:   change_material / modify_glazing / add_furniture             │
  │             → analyze (re-score) → compare_versions → score_interp      │
  │  topologic: topologic_analysis → conflict_reasoner                       │
  │  compare:   persona_comparison → score_interpreter                       │
  │  biophilic: biophilic_audit → (opt) add_furniture → score_interp        │
  └──────────────────────────────────────────────────────────────────────────┘
  ┌─ QUALITY LOOP ───────────────────────────────────────────────────────────┐
  │  respond → evaluator [LLM] ←→ respond  (max 1 revision)                 │
  │  evaluator → what_next [LLM] → END                                      │
  └──────────────────────────────────────────────────────────────────────────┘

===========================================================================
NODE SUMMARY
===========================================================================

  ONBOARDING
  greet              [LLM]     "Hi, I'm Sensi — who are you?"
  quiz               [LLM]     structured 6-step profiler
  inspire            [LLM]     mandatory aesthetic profiler; placeholder in layout mode
  persona_compiler   [LLM]     compiles quiz + inspire → persona.json on disk

  LAYOUT MODE — ROUTING
  intent_classifier  [LLM]     comfort / overview / inspire / follow_up / chitchat / tools
  chitchat           [LLM]     off-topic or general questions in layout mode
  detail_respond     [LLM]     follow_up answers — uses cached session analysis, no MCP

  LAYOUT MODE — LAYOUT
  load_layout        [PYTHON]  reads layout JSON from disk
  overview_respond   [PYTHON]  quick room list, no analysis

  LAYOUT MODE — ANALYSIS CHAIN
  route_intent       [LLM]     analyze / detect / full + what-if / compare / biophilic / topologic
  analyze            [MCP]     compute_comfort_scores
  score_interpreter  [LLM]     what the scores mean for this persona
  detect             [MCP]     detect_sensorial_conflicts
  conflict_reasoner  [LLM]     root cause analysis
  suggest            [MCP]     generate_suggestions
  suggestion_critic  [LLM]     feasibility and cross-sense consequences
  respond            [LLM]     final natural-language response

  LAYOUT MODE — QUALITY LOOP
  evaluator          [LLM]     coherence, completeness, tone check  (max 1 revision)
  what_next          [LLM]     depth-aware feedback loop offer

  LAYOUT MODE — TOOL PATHS (placeholders)
  change_material    [PH·MCP]  modify material → re-score
  modify_glazing     [PH·MCP]  glazing ratio/type → re-score
  add_furniture      [PH·MCP]  add furniture/plants → re-score
  compare_versions   [PH·MCP]  before/after score delta
  topologic_analysis [PH·MCP]  room adjacency via TopologicPy
  persona_comparison [PH·LLM]  same layout, two personas
  biophilic_audit    [PH·LLM]  Talk Green To Me mode
  output_writer      [PYTHON]  post-graph, writes resulting_layout/ (background)
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph

# ── Onboarding nodes ──────────────────────────────────────────────────────────
from nodes.onboarding.greet            import build_greet_node
from nodes.onboarding.quiz             import build_quiz_node
from nodes.onboarding.inspire          import build_inspire_node
from nodes.onboarding.persona_compiler import build_persona_compiler_node

# ── Layout mode — routing ─────────────────────────────────────────────────────
from nodes.routing.intent_classifier   import build_intent_classifier_node
from nodes.conversation.chitchat       import build_chitchat_node
from nodes.conversation.detail_respond import build_detail_respond_node

# ── Layout mode — layout ──────────────────────────────────────────────────────
from nodes.layout.load_layout  import build_load_layout_node
from nodes.layout.overview     import overview_respond_node

# ── Layout mode — analysis chain ─────────────────────────────────────────────
from nodes.routing.route_intent      import build_route_intent_node
from nodes.analysis.analyze          import build_analyze_node
from nodes.analysis.score_interpreter import build_score_interpreter_node
from nodes.analysis.detect           import build_detect_node
from nodes.analysis.conflict_reasoner import build_conflict_reasoner_node
from nodes.analysis.suggest          import build_suggest_node
from nodes.analysis.suggestion_critic import build_suggestion_critic_node
from nodes.quality.respond           import build_respond_node

# ── Layout mode — quality loop ────────────────────────────────────────────────
from nodes.quality.evaluator         import build_evaluator_node
from nodes.conversation.what_next    import build_what_next_node

# ── Layout mode — tool paths (placeholders) ───────────────────────────────────
from nodes.tools.change_material     import build_change_material_node
from nodes.tools.modify_glazing      import build_modify_glazing_node
from nodes.tools.add_furniture       import build_add_furniture_node
from nodes.tools.compare_versions    import build_compare_versions_node
from nodes.tools.topologic_analysis  import build_topologic_analysis_node
from nodes.tools.persona_comparison  import build_persona_comparison_node
from nodes.tools.biophilic_audit     import build_biophilic_audit_node

# ── Post-graph ────────────────────────────────────────────────────────────────
from nodes._shared.output_writer     import write_analysis_to_layout


# ---------------------------------------------------------------------------
# AgentState  --  everything the graph needs, passed between every node
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):

    # ── Input (set at the start of each turn) ───────────────────────────────
    raw_prompt:             str
    has_image:              bool

    # ── Onboarding gate ──────────────────────────────────────────────────────
    greeted:                bool       # True once GREET has run
    quiz_step:              int        # 0-based; incremented each quiz turn
    quiz_answers:           dict       # q0…q5 keyed answers
    quiz_complete:          bool       # True after step 5 answered
    inspire_prompted:        bool       # True after inspire asked its question
    inspire_summary:         str        # synthesised from user's aesthetic answer
    inspire_complete:        bool       # True after inspire captured the answer
    inspire_image_analysis:  str        # VLM aesthetic analysis (set by PyQt5 moodboard pipeline)
    inspire_moodboard_urls:  list       # final image URLs approved in moodboard (PyQt5 GUI)
    inspire_sense_picks:     dict       # {sense: count} of images selected per sense in moodboard
    onboarding_complete:     bool       # True after persona_compiler runs

    # ── User identity (set by quiz + persona_compiler, persisted across turns) ─
    user_name:              str        # first name extracted from q0 by quiz node
    preliminary_role:       str        # "architect"|"client"|"student" detected at q1
    user_type:              str        # "architect" | "client" | "student" (confirmed by persona_compiler)
    persona_profile:        dict       # full compiled persona object

    # ── Layout mode — top-level routing ──────────────────────────────────────
    intent:                 str        # "comfort"|"overview"|"inspire"|"follow_up"|"chitchat"|"tools"
    has_analysis_results:   bool       # True once any analysis has been run (persisted)

    # ── Layout ───────────────────────────────────────────────────────────────
    layout_id:              str | None
    layout_json_string:     str
    target_room_id:         str | None

    # ── Analysis routing ─────────────────────────────────────────────────────
    route_intent_decision:  str        # "analyze"|"detect"|"full"|"what-if"|etc.
    comfort_depth:          str        # "analyze" | "detect" | "full"
    pending_comparison:     bool       # True when a MOD tool just ran

    # ── MCP tool results ─────────────────────────────────────────────────────
    last_scores_json:       str
    last_conflicts_json:    str
    last_suggestions_json:  str
    original_scores_json:   str

    # ── Intermediate specialist outputs ──────────────────────────────────────
    score_interpretation:       str
    conflict_reasoning:         str
    suggestion_critique:        str
    adjacency_graph:            dict
    compare_versions_summary:   str
    biophilic_summary:          str
    biophilic_plants_needed:    bool
    persona_comparison_summary: str

    # ── Quality loop ─────────────────────────────────────────────────────────
    evaluator_decision:     str        # "APPROVED" | "REVISE"
    evaluator_feedback:     str
    evaluator_loops:        int        # max 1

    # ── Output ───────────────────────────────────────────────────────────────
    final_response:         str | None


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_start(state: AgentState) -> str:
    """
    Top-level entry routing.

    Onboarding sequence (strict order):
      not greeted              → greet
      greeted, not quiz done   → quiz
      quiz done, not inspire   → inspire
      inspire done             → persona_compiler  ← handled by _route_after_inspire
      onboarding done          → intent_classifier
    """
    if state.get("onboarding_complete"):
        return "intent_classifier"
    if state.get("quiz_complete"):
        return "inspire"
    if state.get("greeted"):
        return "quiz"
    return "greet"


def _route_after_intent_classifier(state: AgentState) -> str:
    intent = state.get("intent", "chitchat")
    if intent == "inspire":
        return "inspire"
    if intent in ("overview", "comfort", "tools"):
        return "load_layout"
    if intent == "follow_up":
        return "detail_respond"
    return "chitchat"


def _route_after_chitchat(state: AgentState) -> str:
    """Chitchat can detect analysis intent and redirect."""
    if state.get("intent") == "comfort":
        return "intent_classifier"
    return "what_next"


def _route_after_inspire(state: AgentState) -> str:
    """
    Dual-mode routing after inspire.

    Onboarding:  inspire asked question → wait (END)
                 inspire captured answer → persona_compiler
    Layout mode: always → what_next
    """
    if state.get("onboarding_complete"):
        # Layout mode: inspire was a placeholder → what_next
        return "what_next"
    if state.get("inspire_complete"):
        # Onboarding: answer captured → compile persona
        return "persona_compiler"
    # Onboarding: question just asked → wait for user answer
    return END


def _route_after_load_layout(state: AgentState) -> str:
    intent = state.get("intent", "comfort")
    if intent == "overview":
        return "overview_respond"
    return "route_intent"


def _route_after_route_intent(state: AgentState) -> str:
    decision = state.get("route_intent_decision", "analyze")
    if decision in ("analyze", "detect", "full"):
        return "analyze"
    if decision in ("what-if", "what-if-material", "modify-material"):
        return "change_material"
    if decision in ("what-if-glazing", "modify-glazing"):
        return "modify_glazing"
    if decision == "compare":
        return "persona_comparison"
    if decision == "biophilic":
        return "biophilic_audit"
    if decision == "topologic":
        return "topologic_analysis"
    return "analyze"


def _route_after_analyze(state: AgentState) -> str:
    if state.get("pending_comparison"):
        return "compare_versions"
    return "score_interpreter"


def _route_after_score_interpreter(state: AgentState) -> str:
    depth = state.get("comfort_depth", "analyze")
    if depth in ("detect", "full"):
        return "detect"
    return "respond"


def _route_after_conflict_reasoner(state: AgentState) -> str:
    depth = state.get("comfort_depth", "detect")
    if depth == "full":
        return "suggest"
    return "respond"


def _route_after_biophilic_audit(state: AgentState) -> str:
    if state.get("biophilic_plants_needed"):
        return "add_furniture"
    return "score_interpreter"


def _route_after_evaluator(state: AgentState) -> str:
    decision = state.get("evaluator_decision", "APPROVED")
    loops = state.get("evaluator_loops", 0)
    if decision == "REVISE" and loops < 1:
        return "respond"
    return "what_next"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    """
    Instantiate all nodes, wire up edges, and compile the StateGraph.

    persona.json is written to team_02/persona.json (one level above
    layout_input_dir). main.py checks for this file at startup; if it
    exists the session is pre-loaded and onboarding is skipped.
    """

    persona_path = str(ctx.layout_input_dir.parent / "personas" / "persona.json")

    # ── Onboarding nodes ──────────────────────────────────────────────────
    greet            = build_greet_node(ctx.llm_simple)
    quiz             = build_quiz_node(ctx.llm_simple)
    inspire          = build_inspire_node(ctx.llm_simple)
    persona_compiler = build_persona_compiler_node(ctx.llm_simple, persona_path)

    # ── Layout mode — routing ─────────────────────────────────────────────
    intent_classifier = build_intent_classifier_node(ctx.llm_simple)
    chitchat          = build_chitchat_node(ctx.llm_simple)
    detail_respond    = build_detail_respond_node(ctx.llm_simple)

    # ── Layout mode — layout ──────────────────────────────────────────────
    load_layout = build_load_layout_node(ctx.layout_input_dir)

    # ── Layout mode — analysis chain ──────────────────────────────────────
    route_intent      = build_route_intent_node(ctx.llm_simple)
    analyze           = build_analyze_node(ctx.mcp_client)
    score_interpreter = build_score_interpreter_node(ctx.llm_simple)
    detect            = build_detect_node(ctx.mcp_client)
    conflict_reasoner = build_conflict_reasoner_node(ctx.llm_simple)
    suggest           = build_suggest_node(ctx.mcp_client)
    suggestion_critic = build_suggestion_critic_node(ctx.llm_simple)
    respond           = build_respond_node(ctx.llm_simple)

    # ── Layout mode — quality loop ─────────────────────────────────────────
    evaluator = build_evaluator_node(ctx.llm_simple)
    what_next = build_what_next_node(ctx.llm_simple)

    # ── Layout mode — tool paths (placeholders) ────────────────────────────
    change_material    = build_change_material_node()
    modify_glazing     = build_modify_glazing_node()
    add_furniture      = build_add_furniture_node()
    compare_versions   = build_compare_versions_node()
    topologic_analysis = build_topologic_analysis_node()
    persona_comparison = build_persona_comparison_node()
    biophilic_audit    = build_biophilic_audit_node()

    g = StateGraph(AgentState)

    # ── Register nodes ─────────────────────────────────────────────────────

    # Onboarding
    g.add_node("greet",            greet)
    g.add_node("quiz",             quiz)
    g.add_node("inspire",          inspire)
    g.add_node("persona_compiler", persona_compiler)

    # Layout mode — routing
    g.add_node("intent_classifier", intent_classifier)
    g.add_node("chitchat",          chitchat)
    g.add_node("detail_respond",    detail_respond)

    # Layout mode — layout
    g.add_node("load_layout",      load_layout)
    g.add_node("overview_respond", overview_respond_node)

    # Layout mode — analysis chain
    g.add_node("route_intent",      route_intent)
    g.add_node("analyze",           analyze)
    g.add_node("score_interpreter", score_interpreter)
    g.add_node("detect",            detect)
    g.add_node("conflict_reasoner", conflict_reasoner)
    g.add_node("suggest",           suggest)
    g.add_node("suggestion_critic", suggestion_critic)
    g.add_node("respond",           respond)

    # Layout mode — quality loop
    g.add_node("evaluator", evaluator)
    g.add_node("what_next", what_next)

    # Layout mode — tool paths
    g.add_node("change_material",    change_material)
    g.add_node("modify_glazing",     modify_glazing)
    g.add_node("add_furniture",      add_furniture)
    g.add_node("compare_versions",   compare_versions)
    g.add_node("topologic_analysis", topologic_analysis)
    g.add_node("persona_comparison", persona_comparison)
    g.add_node("biophilic_audit",    biophilic_audit)

    # ── Wire edges ─────────────────────────────────────────────────────────

    # START → onboarding or layout mode
    g.add_conditional_edges(
        START,
        _route_start,
        {
            "greet":             "greet",
            "quiz":              "quiz",
            "inspire":           "inspire",
            "intent_classifier": "intent_classifier",
        },
    )

    # ONBOARDING spine
    g.add_edge("greet", END)                 # Turn 1: say hi, wait
    g.add_edge("quiz",  END)                 # Each quiz turn: answer + ask, wait

    # After inspire: wait / compile / what_next depending on mode
    g.add_conditional_edges(
        "inspire",
        _route_after_inspire,
        {
            "persona_compiler": "persona_compiler",
            "what_next":        "what_next",
            END:                END,
        },
    )

    g.add_edge("persona_compiler", END)      # Onboarding done, layout mode unlocked

    # LAYOUT MODE — intent routing
    g.add_conditional_edges(
        "intent_classifier",
        _route_after_intent_classifier,
        {
            "inspire":       "inspire",
            "load_layout":   "load_layout",
            "detail_respond": "detail_respond",
            "chitchat":      "chitchat",
        },
    )

    g.add_edge("detail_respond", "what_next")

    g.add_conditional_edges(
        "chitchat",
        _route_after_chitchat,
        {"intent_classifier": "intent_classifier", "what_next": "what_next"},
    )

    # LAYOUT MODE — layout
    g.add_conditional_edges(
        "load_layout",
        _route_after_load_layout,
        {"overview_respond": "overview_respond", "route_intent": "route_intent"},
    )
    g.add_edge("overview_respond", "what_next")

    # LAYOUT MODE — analysis chain
    g.add_conditional_edges(
        "route_intent",
        _route_after_route_intent,
        {
            "analyze":           "analyze",
            "change_material":   "change_material",
            "modify_glazing":    "modify_glazing",
            "persona_comparison": "persona_comparison",
            "biophilic_audit":   "biophilic_audit",
            "topologic_analysis": "topologic_analysis",
        },
    )

    # Modification tools → re-score via analyze
    g.add_edge("change_material", "analyze")
    g.add_edge("modify_glazing",  "analyze")
    g.add_edge("add_furniture",   "analyze")

    g.add_conditional_edges(
        "analyze",
        _route_after_analyze,
        {"compare_versions": "compare_versions", "score_interpreter": "score_interpreter"},
    )
    g.add_edge("compare_versions", "score_interpreter")

    g.add_conditional_edges(
        "score_interpreter",
        _route_after_score_interpreter,
        {"detect": "detect", "respond": "respond"},
    )

    g.add_edge("detect", "conflict_reasoner")

    g.add_conditional_edges(
        "conflict_reasoner",
        _route_after_conflict_reasoner,
        {"suggest": "suggest", "respond": "respond"},
    )

    g.add_edge("topologic_analysis", "conflict_reasoner")
    g.add_edge("persona_comparison", "score_interpreter")

    g.add_conditional_edges(
        "biophilic_audit",
        _route_after_biophilic_audit,
        {"add_furniture": "add_furniture", "score_interpreter": "score_interpreter"},
    )

    g.add_edge("suggest",           "suggestion_critic")
    g.add_edge("suggestion_critic", "respond")

    # QUALITY LOOP
    g.add_edge("respond", "evaluator")
    g.add_conditional_edges(
        "evaluator",
        _route_after_evaluator,
        {"respond": "respond", "what_next": "what_next"},
    )

    g.add_edge("what_next", END)

    return g.compile()


# ---------------------------------------------------------------------------
# run_agent  --  called once per user turn from main.py
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any, session: dict | None = None) -> tuple[str, dict]:
    """
    Run one turn of the Sensi agent.

    Args:
        prompt  : raw user input for this turn
        ctx     : Context object from bootstrap()
        session : persistent state carried across turns. Pass {} on first turn.
                  Pass a pre-loaded session (with onboarding_complete=True and
                  persona_profile set) to skip onboarding for returning users.

    Returns:
        (final_response, updated_session)
    """
    if session is None:
        session = {}

    initial_state: AgentState = {
        # This turn's input
        "raw_prompt": prompt,
        "has_image":  False,

        # ── Onboarding state (persisted) ──────────────────────────────────
        "greeted":             session.get("greeted", False),
        "quiz_step":           session.get("quiz_step", 0),
        "quiz_answers":        session.get("quiz_answers", {}),
        "quiz_complete":       session.get("quiz_complete", False),
        "inspire_prompted":       session.get("inspire_prompted", False),
        "inspire_summary":        session.get("inspire_summary", ""),
        "inspire_complete":       session.get("inspire_complete", False),
        "inspire_image_analysis": session.get("inspire_image_analysis", ""),
        "inspire_moodboard_urls": session.get("inspire_moodboard_urls", []),
        "inspire_sense_picks":    session.get("inspire_sense_picks", {}),
        "onboarding_complete":    session.get("onboarding_complete", False),

        # ── User identity (persisted) ──────────────────────────────────────
        "user_name":        session.get("user_name", ""),
        "preliminary_role": session.get("preliminary_role", "client"),
        "user_type":        session.get("user_type", ""),
        "persona_profile":  session.get("persona_profile"),

        # ── Layout (persisted) ────────────────────────────────────────────
        "layout_json_string": session.get("layout_json_string", ""),
        "layout_id":          session.get("layout_id"),

        # ── Persisted analysis context (kept across turns for follow_up) ──
        "has_analysis_results":  session.get("has_analysis_results", False),
        "score_interpretation":  session.get("score_interpretation", ""),
        "conflict_reasoning":    session.get("conflict_reasoning", ""),
        "suggestion_critique":   session.get("suggestion_critique", ""),
        # Cached raw MCP data (available to detail_respond on follow_up turns)
        "last_scores_json":      session.get("last_scores_json", ""),
        "last_conflicts_json":   session.get("last_conflicts_json", ""),
        "last_suggestions_json": session.get("last_suggestions_json", ""),

        # ── Per-turn fields (reset each turn) ────────────────────────────
        "intent":                "",
        "route_intent_decision": "",
        "comfort_depth":         "analyze",
        "target_room_id":        None,
        "pending_comparison":    False,
        "original_scores_json":  "",
        "compare_versions_summary": "",
        "biophilic_summary":     "",
        "biophilic_plants_needed": False,
        "persona_comparison_summary": "",
        "adjacency_graph":       {},
        "evaluator_decision":    "",
        "evaluator_feedback":    "",
        "evaluator_loops":       0,
        "final_response":        None,
    }

    app = build_graph(ctx)
    final_state = app.invoke(initial_state)

    response    = final_state.get("final_response") or ""
    intent      = final_state.get("intent", "")
    depth       = final_state.get("comfort_depth", "")
    scores_ready = bool(final_state.get("last_scores_json"))

    print("[run_agent] intent={} | depth={} | scores_ready={} | onboarding={}".format(
        intent, depth, scores_ready,
        final_state.get("onboarding_complete", False),
    ))

    # Post-graph: write analysis output JSON
    if intent in ("comfort", "tools") and scores_ready:
        try:
            write_analysis_to_layout(final_state, ctx.layout_output_dir)
        except Exception as exc:
            print("[run_agent] ERROR in output_writer: {}".format(exc))

    # Persist all session fields
    updated_session = {
        # Onboarding
        "greeted":             final_state.get("greeted",             session.get("greeted", False)),
        "quiz_step":           final_state.get("quiz_step",           session.get("quiz_step", 0)),
        "quiz_answers":        final_state.get("quiz_answers",        session.get("quiz_answers", {})),
        "quiz_complete":       final_state.get("quiz_complete",       session.get("quiz_complete", False)),
        "inspire_prompted":       final_state.get("inspire_prompted",       session.get("inspire_prompted", False)),
        "inspire_summary":        final_state.get("inspire_summary",        session.get("inspire_summary", "")),
        "inspire_complete":       final_state.get("inspire_complete",       session.get("inspire_complete", False)),
        "inspire_image_analysis": final_state.get("inspire_image_analysis") or session.get("inspire_image_analysis", ""),
        "inspire_moodboard_urls": final_state.get("inspire_moodboard_urls") or session.get("inspire_moodboard_urls", []),
        "inspire_sense_picks":    final_state.get("inspire_sense_picks")    or session.get("inspire_sense_picks", {}),
        "onboarding_complete":    final_state.get("onboarding_complete",    session.get("onboarding_complete", False)),
        # Identity
        "user_name":           final_state.get("user_name")           or session.get("user_name", ""),
        "preliminary_role":    final_state.get("preliminary_role")    or session.get("preliminary_role", "client"),
        "user_type":           final_state.get("user_type")           or session.get("user_type", ""),
        "persona_profile":     final_state.get("persona_profile")     or session.get("persona_profile"),
        # Layout
        "layout_json_string":  final_state.get("layout_json_string") or session.get("layout_json_string", ""),
        "layout_id":           final_state.get("layout_id")          or session.get("layout_id"),
        # Analysis results — OR fallback keeps last known values across chitchat/follow_up turns
        "last_scores_json":      final_state.get("last_scores_json")      or session.get("last_scores_json", ""),
        "last_conflicts_json":   final_state.get("last_conflicts_json")   or session.get("last_conflicts_json", ""),
        "last_suggestions_json": final_state.get("last_suggestions_json") or session.get("last_suggestions_json", ""),
        "comfort_depth":         final_state.get("comfort_depth", "")     or session.get("comfort_depth", ""),
        # Specialist interpretations — persist so detail_respond + intent_classifier can access them
        "score_interpretation":  final_state.get("score_interpretation")  or session.get("score_interpretation", ""),
        "conflict_reasoning":    final_state.get("conflict_reasoning")    or session.get("conflict_reasoning", ""),
        "suggestion_critique":   final_state.get("suggestion_critique")   or session.get("suggestion_critique", ""),
        # Flag: True once any analysis has ever been run this session
        "has_analysis_results":  bool(final_state.get("last_scores_json")) or session.get("has_analysis_results", False),
    }

    return response, updated_session
