"""
graph.py — Sensi state graph (v4 — unified action_classifier, cache logic)

=============================================================================
WHAT CHANGED FROM v3 → v4
=============================================================================

  1. UNIFIED ROUTING: intent_classifier + route_intent → single action_classifier.
     One LLM call per turn for routing. `action` field replaces `intent` +
     `route_intent_decision` + `comfort_depth` (all three were needed before).

  2. CACHE LOGIC: for detect/full actions, if last_scores_json already exists
     for the current layout, skip the analyze node and go straight to detect.
     Avoids redundant re-scoring when the layout hasn't changed.

  3. PERSONA FIX: analyze/detect/suggest now pass real persona weights from
     onboarding (persona_profile.comfort_weights) to the scoring tools.

  4. TOOL PATHS NOW REACHABLE: edit, topologic, biophilic, compare all route
     correctly via action field.

  5. NEW STATE FIELDS: action, edit_ops, layout_diff, layout_diffs, graph_data,
     biophilic_data, target_room_hint, material_hint, layout_updated.

  6. NODE REORGANISATION:
     nodes/routing/   → action_classifier (replaces intent_classifier + route_intent)
     nodes/scoring/   → analyze, score_interpreter, detect, conflict_reasoner,
                         suggest, suggestion_critic
     nodes/editing/   → edit_planner, apply_edits (multi-edit; replace the 3 per-type
                         edit nodes), compare_versions, preview
     nodes/insights/  → topologic_analysis, biophilic_audit, persona_comparison

=============================================================================
LAYOUT MODE FLOW (v4)
=============================================================================

  ┌─ ROUTING ──────────────────────────────────────────────────────────────────┐
  │  action_classifier [LLM]  →  one of 13 actions                            │
  │                                                                            │
  │  follow_up   → detail_respond → what_next                                  │
  │  inspire     → inspire → what_next                                         │
  │  chitchat    → chitchat → what_next                                        │
  │  all others  → load_layout → dispatch                                      │
  └────────────────────────────────────────────────────────────────────────────┘
  ┌─ ANALYSIS (with cache) ────────────────────────────────────────────────────┐
  │  analyze              → analyze → score_interpreter → respond              │
  │  detect (no cache)    → analyze → score_interpreter → detect → conflict_r  │
  │  detect (cached)      → [skip analyze] → detect → conflict_reasoner        │
  │  full (no cache)      → analyze → score_interpreter → detect → suggest     │
  │  full (cached scores) → [skip analyze] → detect → suggest                 │
  │  → suggest → suggestion_critic → respond → evaluator → what_next          │
  └────────────────────────────────────────────────────────────────────────────┘
  ┌─ EDIT TOOLS (multi-edit: N ops in one turn, ONE re-score) ──────────────────┐
  │  edit → edit_planner [LLM: prompt → ops list]                              │
  │       → apply_edits  [mutate all ops; accumulate layout_diffs]            │
  │       → analyze → compare_versions → score_interpreter                    │
  │       → respond → evaluator → what_next                                   │
  │  (apply_edits → respond directly when zero resolvable ops — no re-score)   │
  └────────────────────────────────────────────────────────────────────────────┘
  ┌─ INSIGHT TOOLS ────────────────────────────────────────────────────────────┐
  │  topologic  → topologic_analysis → respond → evaluator → what_next        │
  │  biophilic  → biophilic_audit → [apply_edits if plants_needed]            │
  │               → analyze → compare_versions → score_interpreter → respond  │
  │  compare    → persona_comparison → score_interpreter → respond            │
  └────────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph

# ── Per-node benchmarking (gated on BENCH_NODES=1; see bench_nodes.py) ───────────
# When enabled, every node fn is wrapped with a wall-clock timer that also snapshots
# the LLM token counter (_runtime/llm) before/after, so we get latency + tokens + the
# tier each node ran on. No-op (zero overhead) when BENCH_NODES is unset.
_BENCH = os.environ.get("BENCH_NODES") == "1"
NODE_TIMINGS: list[dict] = []
_NODE_TIER = {
    "greet": "fast", "quiz": "fast", "action_classifier": "fast", "chitchat": "fast",
    "evaluator": "fast", "what_next": "fast",
    "inspire": "smart", "persona_compiler": "smart", "detail_respond": "smart",
    "score_interpreter": "smart", "conflict_reasoner": "smart", "suggestion_critic": "smart",
    "respond": "smart", "edit_planner": "smart",
}


def _bench_wrap(name: str, fn):
    if not _BENCH:
        return fn
    from _runtime import llm as _llm

    def wrapped(state):
        u0 = _llm.usage_snapshot(); t0 = time.perf_counter()
        out = fn(state)
        dt = time.perf_counter() - t0; u1 = _llm.usage_snapshot()
        NODE_TIMINGS.append({
            "node": name, "tier": _NODE_TIER.get(name, "-"),
            "latency_s": round(dt, 4),
            "llm_calls": u1["calls"] - u0["calls"],
            "in_tok": u1["input"] - u0["input"],
            "out_tok": u1["output"] - u0["output"],
        })
        return out

    return wrapped

# ── Onboarding ────────────────────────────────────────────────────────────────
from nodes.onboarding.greet            import build_greet_node
from nodes.onboarding.quiz             import build_quiz_node
from nodes.onboarding.inspire          import build_inspire_node
from nodes.onboarding.persona_compiler import build_persona_compiler_node

# ── Routing (unified) ─────────────────────────────────────────────────────────
from nodes.routing.action_classifier   import build_action_classifier_node
from nodes.conversation.chitchat       import build_chitchat_node
from nodes.conversation.detail_respond import build_detail_respond_node

# ── Layout ────────────────────────────────────────────────────────────────────
from nodes.layout.load_layout  import build_load_layout_node
from nodes.layout.overview     import overview_respond_node

# ── Scoring chain ─────────────────────────────────────────────────────────────
from nodes.scoring.analyze           import build_analyze_node
from nodes.scoring.score_interpreter import build_score_interpreter_node
from nodes.scoring.detect            import build_detect_node
from nodes.scoring.conflict_reasoner import build_conflict_reasoner_node
from nodes.scoring.suggest           import build_suggest_node
from nodes.scoring.suggestion_critic import build_suggestion_critic_node

# ── Quality loop ──────────────────────────────────────────────────────────────
from nodes.quality.respond   import build_respond_node
from nodes.quality.evaluator import build_evaluator_node
from nodes.conversation.what_next import build_what_next_node

# ── Edit tools ────────────────────────────────────────────────────────────────
from nodes.editing.edit_planner     import build_edit_planner_node
from nodes.editing.apply_edits      import build_apply_edits_node
from nodes.editing.compare_versions import build_compare_versions_node
from nodes.editing.preview          import build_preview_node

# ── Insight tools ─────────────────────────────────────────────────────────────
from nodes.insights.topologic_analysis import build_topologic_analysis_node
from nodes.insights.biophilic_audit    import build_biophilic_audit_node
from nodes.insights.persona_comparison import build_persona_comparison_node

# ── Post-graph ────────────────────────────────────────────────────────────────
from nodes._shared.output_writer import write_analysis_to_layout


# ---------------------------------------------------------------------------
# AgentState
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):

    # ── Input ────────────────────────────────────────────────────────────────
    raw_prompt:  str
    has_image:   bool

    # ── Onboarding ───────────────────────────────────────────────────────────
    greeted:               bool
    quiz_step:             int
    quiz_answers:          dict
    quiz_complete:         bool
    inspire_prompted:      bool
    inspire_summary:       str
    inspire_complete:      bool
    inspire_image_analysis: str
    inspire_moodboard_urls: list
    inspire_sense_picks:    dict
    onboarding_complete:    bool

    # ── User identity ────────────────────────────────────────────────────────
    user_name:       str
    preliminary_role: str
    user_type:       str
    persona_profile: dict

    # ── Routing ──────────────────────────────────────────────────────────────
    action:           str   # unified action: analyze|detect|full|overview|follow_up|
                            #   chitchat|inspire|edit|preview|topologic|biophilic|compare
    edit_ops:         list  # validated ops from edit_planner: [{op, room, ...params}, ...]
    target_room_hint: str   # LLM-extracted room name from prompt
    material_hint:    str   # LLM-extracted material name from prompt

    # ── Layout ───────────────────────────────────────────────────────────────
    layout_id:          str | None
    layout_json_string: str
    target_room_id:     str | None
    layout_not_found:   bool   # set by load_layout when a requested id has no file

    # ── Analysis results (cached across turns) ───────────────────────────────
    has_analysis_results:  bool
    last_scores_json:      str
    last_conflicts_json:   str
    last_suggestions_json: str
    original_scores_json:  str

    # ── Specialist interpretations (cached across turns) ─────────────────────
    score_interpretation:    str
    conflict_reasoning:      str
    suggestion_critique:     str

    # ── Edit / insight results ────────────────────────────────────────────────
    pending_comparison:           bool
    layout_diff:                  dict   # most-recent single edit (used by /api/report featured room + respond)
    layout_diffs:                 list   # ALL edits applied this turn (multi-edit) — one dict per change
    layout_updated:               bool   # True when layout JSON was mutated this turn
    # Predictive preview ("what if") — scored on a CLONE, never committed.
    preview_scores_json:          str    # hypothetical scores; NOT the canonical cache
    preview_diff:                 dict   # the hypothetical edit's diff (last, back-compat)
    preview_diffs:                list   # all hypothetical edits in a multi-op what-if
    preview_summary:              str    # predicted per-sense delta, human-readable
    adjacency_graph:              dict
    graph_data:                   dict   # {nodes, edges, metrics} for Cytoscape/D3
    compare_versions_summary:     str
    biophilic_summary:            str
    biophilic_plants_needed:      bool
    biophilic_data:               dict   # per-room richness scores
    persona_comparison_summary:   str
    persona_comparison_data:      dict

    # ── Quality loop ─────────────────────────────────────────────────────────
    evaluator_decision: str
    evaluator_feedback: str
    evaluator_loops:    int

    # ── Output ───────────────────────────────────────────────────────────────
    final_response: str | None


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_start(state: AgentState) -> str:
    if state.get("onboarding_complete"):
        return "action_classifier"
    if state.get("quiz_complete"):
        return "inspire"
    if state.get("greeted"):
        return "quiz"
    return "greet"


def _route_after_action_classifier(state: AgentState) -> str:
    action = state.get("action", "chitchat")
    if action == "follow_up":
        return "detail_respond"
    if action == "inspire":
        return "inspire"
    if action == "chitchat":
        return "chitchat"
    # All other actions need a layout loaded first
    return "load_layout"


def _route_after_chitchat(state: AgentState) -> str:
    if state.get("action") in ("analyze", "detect", "full"):
        return "action_classifier"
    return "what_next"


def _route_after_inspire(state: AgentState) -> str:
    if state.get("onboarding_complete"):
        return "what_next"
    if state.get("inspire_complete"):
        return "persona_compiler"
    return END


def _route_after_load_layout(state: AgentState) -> str:
    action     = state.get("action", "analyze")
    has_scores = bool(state.get("last_scores_json", "").strip())

    # Requested layout doesn't exist — load_layout already wrote the message.
    if state.get("layout_not_found"):
        return END

    if action == "overview":
        return "overview_respond"

    # Predictive preview ("what if") — score a hypothetical without committing.
    if action == "preview":
        return "preview"

    # Edit tools — one path: edit_planner decomposes, apply_edits mutates (multi-edit)
    if action == "edit":
        return "edit_planner"

    # Insight tools
    if action == "topologic":
        return "topologic_analysis"
    if action == "biophilic":
        return "biophilic_audit"
    if action == "compare":
        return "persona_comparison"

    # Analysis: cache-aware routing
    # detect/full can skip analyze if scores are already cached for this layout
    if action in ("detect", "full") and has_scores:
        print(f"[graph] Cache hit for action={action} — skipping analyze, jumping to detect")
        return "detect"

    return "analyze"


def _route_after_apply_edits(state: AgentState) -> str:
    # Re-score only when something actually changed; otherwise apply_edits already
    # wrote a clarifying final_response, so go straight to respond → what_next.
    return "analyze" if state.get("layout_updated") else "respond"


def _route_after_analyze(state: AgentState) -> str:
    if state.get("pending_comparison"):
        return "compare_versions"
    return "score_interpreter"


def _route_after_score_interpreter(state: AgentState) -> str:
    action = state.get("action", "analyze")
    if action in ("detect", "full"):
        return "detect"
    return "respond"


def _route_after_conflict_reasoner(state: AgentState) -> str:
    action = state.get("action", "detect")
    if action == "full":
        return "suggest"
    return "respond"


def _route_after_biophilic_audit(state: AgentState) -> str:
    # When greenery is missing, biophilic_audit has pre-seeded edit_ops with a single
    # plant op, so route through the unified edit path (mutate → re-score → compare).
    if state.get("biophilic_plants_needed"):
        return "apply_edits"
    return "score_interpreter"


def _route_after_evaluator(state: AgentState) -> str:
    decision = state.get("evaluator_decision", "APPROVED")
    loops    = state.get("evaluator_loops", 0)
    if decision == "REVISE" and loops < 1:
        return "respond"
    return "what_next"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    persona_path = str(ctx.layout_input_dir.parent / "personas" / "persona.json")

    # Benchmarking tiers (see docs/week08/benchmarking-findings.md):
    #   ctx.llm_fast  -> routing / classification / short internal text
    #   ctx.llm_smart -> user-facing prose & nuanced persona reasoning

    # Onboarding
    greet            = build_greet_node(ctx.llm_fast)
    quiz             = build_quiz_node(ctx.llm_fast)
    inspire          = build_inspire_node(ctx.llm_smart)
    persona_compiler = build_persona_compiler_node(ctx.llm_smart, persona_path)

    # Routing
    action_classifier = build_action_classifier_node(ctx.llm_fast)
    chitchat          = build_chitchat_node(ctx.llm_fast)
    detail_respond    = build_detail_respond_node(ctx.llm_smart)

    # Layout
    load_layout = build_load_layout_node(ctx.layout_input_dir)

    # Scoring chain
    analyze           = build_analyze_node(ctx.mcp_client)
    score_interpreter = build_score_interpreter_node(ctx.llm_smart)
    detect            = build_detect_node(ctx.mcp_client)
    conflict_reasoner = build_conflict_reasoner_node(ctx.llm_smart)
    suggest           = build_suggest_node(ctx.mcp_client)
    suggestion_critic = build_suggestion_critic_node(ctx.llm_smart)

    # Quality loop
    respond   = build_respond_node(ctx.llm_smart)
    evaluator = build_evaluator_node(ctx.llm_fast)
    what_next = build_what_next_node(ctx.llm_fast)

    # Edit tools — unified path: edit_planner (LLM decompose) → apply_edits (mutate)
    edit_planner     = build_edit_planner_node(ctx.llm_smart)
    apply_edits      = build_apply_edits_node()
    compare_versions = build_compare_versions_node()
    preview          = build_preview_node(ctx.mcp_client)

    # Insight tools
    topologic_analysis = build_topologic_analysis_node()
    biophilic_audit    = build_biophilic_audit_node()
    persona_comparison = build_persona_comparison_node(ctx.mcp_client)

    g = StateGraph(AgentState)

    # Register all nodes (wrapped with the per-node timer when BENCH_NODES=1)
    for _name, _fn in (
        ("greet",             greet),
        ("quiz",              quiz),
        ("inspire",           inspire),
        ("persona_compiler",  persona_compiler),
        ("action_classifier", action_classifier),
        ("chitchat",          chitchat),
        ("detail_respond",    detail_respond),
        ("load_layout",       load_layout),
        ("overview_respond",  overview_respond_node),
        ("analyze",           analyze),
        ("score_interpreter", score_interpreter),
        ("detect",            detect),
        ("conflict_reasoner", conflict_reasoner),
        ("suggest",           suggest),
        ("suggestion_critic", suggestion_critic),
        ("respond",           respond),
        ("evaluator",         evaluator),
        ("what_next",         what_next),
        ("edit_planner",      edit_planner),
        ("apply_edits",       apply_edits),
        ("compare_versions",  compare_versions),
        ("preview",           preview),
        ("topologic_analysis", topologic_analysis),
        ("biophilic_audit",   biophilic_audit),
        ("persona_comparison", persona_comparison),
    ):
        g.add_node(_name, _bench_wrap(_name, _fn))

    # ── Wire edges ────────────────────────────────────────────────────────────

    # Entry
    g.add_conditional_edges(START, _route_start, {
        "greet":             "greet",
        "quiz":              "quiz",
        "inspire":           "inspire",
        "action_classifier": "action_classifier",
    })

    # Onboarding spine
    g.add_edge("greet", END)
    g.add_edge("quiz",  END)
    g.add_conditional_edges("inspire", _route_after_inspire, {
        "persona_compiler": "persona_compiler",
        "what_next":        "what_next",
        END:                END,
    })
    g.add_edge("persona_compiler", END)

    # Layout mode — routing
    g.add_conditional_edges("action_classifier", _route_after_action_classifier, {
        "inspire":       "inspire",
        "load_layout":   "load_layout",
        "detail_respond": "detail_respond",
        "chitchat":      "chitchat",
    })
    g.add_edge("detail_respond", "what_next")
    g.add_conditional_edges("chitchat", _route_after_chitchat, {
        "action_classifier": "action_classifier",
        "what_next":         "what_next",
    })

    # Layout dispatch
    g.add_conditional_edges("load_layout", _route_after_load_layout, {
        "overview_respond":  "overview_respond",
        "analyze":           "analyze",
        "detect":            "detect",       # cache hit: jump straight to detect
        "edit_planner":      "edit_planner",
        "preview":           "preview",
        "topologic_analysis": "topologic_analysis",
        "biophilic_audit":   "biophilic_audit",
        "persona_comparison": "persona_comparison",
        END:                 END,            # requested layout not found
    })
    g.add_edge("overview_respond", "what_next")

    # Scoring chain
    g.add_conditional_edges("analyze", _route_after_analyze, {
        "compare_versions":  "compare_versions",
        "score_interpreter": "score_interpreter",
    })
    g.add_edge("compare_versions", "score_interpreter")
    g.add_conditional_edges("score_interpreter", _route_after_score_interpreter, {
        "detect":  "detect",
        "respond": "respond",
    })
    g.add_edge("detect", "conflict_reasoner")
    g.add_conditional_edges("conflict_reasoner", _route_after_conflict_reasoner, {
        "suggest": "suggest",
        "respond": "respond",
    })
    g.add_edge("suggest",           "suggestion_critic")
    g.add_edge("suggestion_critic", "respond")

    # Edit path: edit_planner (decompose) → apply_edits (mutate N ops) → analyze
    # (single re-score) → compare → score_interpreter → respond. apply_edits routes
    # straight to respond when nothing changed (zero resolvable ops).
    g.add_edge("edit_planner", "apply_edits")
    g.add_conditional_edges("apply_edits", _route_after_apply_edits, {
        "analyze": "analyze",
        "respond": "respond",
    })

    # Preview is terminal: it self-produces its predicted-ripple message (no re-score
    # of the real layout, no commit) and goes straight to the next-step offer.
    g.add_edge("preview", "what_next")

    # Insight tools
    g.add_edge("topologic_analysis", "respond")
    g.add_conditional_edges("biophilic_audit", _route_after_biophilic_audit, {
        "apply_edits":       "apply_edits",
        "score_interpreter": "score_interpreter",
    })
    g.add_edge("persona_comparison", "score_interpreter")

    # Quality loop
    g.add_edge("respond", "evaluator")
    g.add_conditional_edges("evaluator", _route_after_evaluator, {
        "respond":   "respond",
        "what_next": "what_next",
    })
    g.add_edge("what_next", END)

    return g.compile()


# ---------------------------------------------------------------------------
# run_agent
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any, session: dict | None = None) -> tuple[str, dict]:
    if session is None:
        session = {}

    initial_state: AgentState = {
        "raw_prompt": prompt,
        "has_image":  False,

        # Onboarding
        "greeted":              session.get("greeted", False),
        "quiz_step":            session.get("quiz_step", 0),
        "quiz_answers":         session.get("quiz_answers", {}),
        "quiz_complete":        session.get("quiz_complete", False),
        "inspire_prompted":     session.get("inspire_prompted", False),
        "inspire_summary":      session.get("inspire_summary", ""),
        "inspire_complete":     session.get("inspire_complete", False),
        "inspire_image_analysis": session.get("inspire_image_analysis", ""),
        "inspire_moodboard_urls": session.get("inspire_moodboard_urls", []),
        "inspire_sense_picks":    session.get("inspire_sense_picks", {}),
        "onboarding_complete":    session.get("onboarding_complete", False),

        # Identity
        "user_name":        session.get("user_name", ""),
        "preliminary_role": session.get("preliminary_role", "client"),
        "user_type":        session.get("user_type", ""),
        "persona_profile":  session.get("persona_profile"),

        # Layout
        "layout_json_string": session.get("layout_json_string", ""),
        "layout_id":          session.get("layout_id"),

        # Cached analysis (persisted across turns)
        "has_analysis_results":  session.get("has_analysis_results", False),
        "last_scores_json":      session.get("last_scores_json", ""),
        "last_conflicts_json":   session.get("last_conflicts_json", ""),
        "last_suggestions_json": session.get("last_suggestions_json", ""),
        "score_interpretation":  session.get("score_interpretation", ""),
        "conflict_reasoning":    session.get("conflict_reasoning", ""),
        "suggestion_critique":   session.get("suggestion_critique", ""),

        # Per-turn fields (reset each turn)
        "action":                 "",
        "edit_ops":               [],
        "target_room_hint":       "",
        "material_hint":          "",
        "target_room_id":         None,
        "layout_not_found":       False,
        "pending_comparison":     False,
        "original_scores_json":   "",
        "layout_diff":            {},
        "layout_diffs":           [],
        "layout_updated":         False,
        "preview_scores_json":    "",
        "preview_diff":           {},
        "preview_diffs":          [],
        "preview_summary":        "",
        "compare_versions_summary": "",
        "biophilic_summary":      "",
        "biophilic_plants_needed": False,
        "biophilic_data":         {},
        "adjacency_graph":        {},
        "graph_data":             {},
        "persona_comparison_summary": "",
        "persona_comparison_data":    {},
        "evaluator_decision":     "",
        "evaluator_feedback":     "",
        "evaluator_loops":        0,
        "final_response":         None,
    }

    app = build_graph(ctx)
    final_state = app.invoke(initial_state)

    response    = final_state.get("final_response") or ""
    action      = final_state.get("action", "")
    scores_ready = bool(final_state.get("last_scores_json"))

    edit_actions = {"edit"}
    print(f"[run_agent] action={action} | scores_ready={scores_ready} | layout_updated={final_state.get('layout_updated', False)}")

    # Post-graph: write output JSON. Skip when the requested layout wasn't found —
    # otherwise we'd persist stale scores under the (nonexistent) layout's name.
    if (action in ("analyze", "detect", "full", *edit_actions)
            and scores_ready
            and not final_state.get("layout_not_found")):
        try:
            write_analysis_to_layout(final_state, ctx.layout_output_dir)
        except Exception as exc:
            print(f"[run_agent] ERROR in output_writer: {exc}")

    # Persist session. Start from the incoming session so keys the GRAPH doesn't own
    # (e.g. the API-layer checkpoint state: checkpoints / committed_* / pending_diffs)
    # survive the round-trip; the explicit keys below override everything the graph manages.
    updated_session = {
        **session,
        "greeted":             final_state.get("greeted",             session.get("greeted", False)),
        "quiz_step":           final_state.get("quiz_step",           session.get("quiz_step", 0)),
        "quiz_answers":        final_state.get("quiz_answers",        session.get("quiz_answers", {})),
        "quiz_complete":       final_state.get("quiz_complete",       session.get("quiz_complete", False)),
        "inspire_prompted":    final_state.get("inspire_prompted",    session.get("inspire_prompted", False)),
        "inspire_summary":     final_state.get("inspire_summary",     session.get("inspire_summary", "")),
        "inspire_complete":    final_state.get("inspire_complete",    session.get("inspire_complete", False)),
        "inspire_image_analysis": final_state.get("inspire_image_analysis") or session.get("inspire_image_analysis", ""),
        "inspire_moodboard_urls": final_state.get("inspire_moodboard_urls") or session.get("inspire_moodboard_urls", []),
        "inspire_sense_picks":    final_state.get("inspire_sense_picks")    or session.get("inspire_sense_picks", {}),
        "onboarding_complete":    final_state.get("onboarding_complete",    session.get("onboarding_complete", False)),
        "user_name":           final_state.get("user_name")           or session.get("user_name", ""),
        "preliminary_role":    final_state.get("preliminary_role")    or session.get("preliminary_role", "client"),
        "user_type":           final_state.get("user_type")           or session.get("user_type", ""),
        "persona_profile":     final_state.get("persona_profile")     or session.get("persona_profile"),
        "layout_json_string":  final_state.get("layout_json_string")  or session.get("layout_json_string", ""),
        "layout_id":           final_state.get("layout_id")           or session.get("layout_id"),
        "last_scores_json":      final_state.get("last_scores_json")      or session.get("last_scores_json", ""),
        "last_conflicts_json":   final_state.get("last_conflicts_json")   or session.get("last_conflicts_json", ""),
        "last_suggestions_json": final_state.get("last_suggestions_json") or session.get("last_suggestions_json", ""),
        "score_interpretation":  final_state.get("score_interpretation")  or session.get("score_interpretation", ""),
        "conflict_reasoning":    final_state.get("conflict_reasoning")    or session.get("conflict_reasoning", ""),
        "suggestion_critique":   final_state.get("suggestion_critique")   or session.get("suggestion_critique", ""),
        "has_analysis_results":  bool(final_state.get("last_scores_json")) or session.get("has_analysis_results", False),
        # Per-turn fields (cleared next turn — used by server to build response payload)
        "layout_updated":         final_state.get("layout_updated", False),
        "layout_diff":            final_state.get("layout_diff", {}),
        "layout_diffs":           final_state.get("layout_diffs", []),
        "preview_scores_json":    final_state.get("preview_scores_json", ""),
        "preview_diff":           final_state.get("preview_diff", {}),
        "preview_diffs":          final_state.get("preview_diffs", []),
        "preview_summary":        final_state.get("preview_summary", ""),
        "graph_data":             final_state.get("graph_data", {}),
        "biophilic_data":         final_state.get("biophilic_data", {}),
        "persona_comparison_data": final_state.get("persona_comparison_data", {}),
        "action":                 final_state.get("action", ""),
    }

    return response, updated_session
