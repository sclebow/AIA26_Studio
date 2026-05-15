"""
graph.py -- Comfort Copilot state graph.

===========================================================================
FULL WORKFLOW  (node type shown in brackets)
===========================================================================

  USER PROMPT
      |
      v
  [PYTHON] PREPROCESS
      Reads the raw prompt. No LLM, no external calls.
      Classifies the top-level intent using keyword matching:
        "comfort"  -- a layout ID (201/202/203) was mentioned, or a comfort
                      keyword (detect, analyse, suggest...) with a layout loaded
        "overview" -- user wants to list rooms, no analysis needed
        "inspire"  -- image attached or atmosphere keyword
        "chitchat" -- everything else
      Also extracts layout_id and persona from the prompt text.
      |
      |-- [chitchat] --------------------> [LLM] CHITCHAT --> END
      |                                    Free-form conversational reply.
      |
      |-- [inspire] ---------------------> [PYTHON] INSPIRE --> END
      |                                    Placeholder. Phase 3 image generation.
      |
      |-- [comfort / overview] ------+
                                     |
                                     v
                               [PYTHON] LOAD_LAYOUT
                               Finds the layout JSON file by ID and reads it
                               from randomized_layouts/. Skips if the same
                               layout is already loaded in session state
                               (multi-turn: avoids reloading on follow-ups).
                                     |
                                     |-- [overview] --> [PYTHON] OVERVIEW_RESPOND --> END
                                     |                  Lists rooms (name, type, area,
                                     |                  height, orientation). No tools,
                                     |                  no persona, no scores.
                                     |
                                     |-- [comfort] ------+
                                                         |
                                                         v
                                                   [PYTHON] ASK_PERSONA
                                                   Checks if a persona was detected.
                                                   If yes: pass-through.
                                                   If no:  shows terminal picker
                                                           (Elderly / Child / Neutral...)
                                                         |
                                                         v
                                                   [LLM] ROUTE_INTENT
                                                   Reads the prompt and classifies
                                                   analysis depth:
                                                     "analyze" -- scores only
                                                     "detect"  -- scores + conflicts
                                                     "full"    -- scores + conflicts
                                                                  + suggestions
                                                   Python keyword fallback if LLM fails.
                                                         |
                                                         v
                                                   [MCP] ANALYZE
                                                   Calls compute_comfort_scores
                                                   in Grasshopper via MCP.
                                                   Sends: layout_json, persona,
                                                          room_ids (all or one).
                                                   Writes: last_scores_json to state.
                                                         |
                                                         |-- [analyze] --> [LLM] RESPOND
                                                         |                 (see below)
                                                         |
                                                         |-- [detect/full] ----+
                                                                               |
                                                                               v
                                                                         [MCP] DETECT
                                                                         Calls detect_sensorial_conflicts
                                                                         in Grasshopper via MCP.
                                                                         Sends: layout_json, persona,
                                                                                scores_json.
                                                                         Writes: last_conflicts_json.
                                                                               |
                                                                               |-- [detect] --> [LLM] RESPOND
                                                                               |
                                                                               |-- [full] -------+
                                                                                                 |
                                                                                                 v
                                                                                           [MCP] SUGGEST
                                                                                           Calls generate_suggestions
                                                                                           in Grasshopper via MCP.
                                                                                           Sends: layout_json, persona,
                                                                                                  scores_json,
                                                                                                  conflicts_json.
                                                                                           Writes: last_suggestions_json.
                                                                                                 |
                                                                                                 v
                                                                                           [LLM] RESPOND
                                                                   Intent-driven format selected by depth:
                                                                     analyze -> score interpretation per room
                                                                     detect  -> conflict-led, scores as evidence
                                                                     full    -> suggestion-led, conflicts + scores
                                                                   Python pre-processes tool outputs first to
                                                                   prevent LLM hallucination of scores/numbers.
                                                                                                 |
                                                                                                 v
                                                                                               END
                                                                                (+ output_writer saves
                                                                                 resulting_layout/Layout-{id}_modified.json
                                                                                 outside the graph, in run_agent)

===========================================================================
MCP TOOLS  (all hosted in Grasshopper via Swiftlet HTTP)
===========================================================================
  compute_comfort_scores      -- thermal/visual/acoustic/spatial/olfactory/tactile
  detect_sensorial_conflicts  -- flags rooms below persona threshold
  generate_suggestions        -- actionable fix per failing sense

===========================================================================
NODE SUMMARY
===========================================================================
  preprocess       [PYTHON]  keyword routing + persona/layout_id extraction
  load_layout      [PYTHON]  file I/O from randomized_layouts/
  overview_respond [PYTHON]  room list formatter, no tools
  ask_persona      [PYTHON]  terminal picker or pass-through
  route_intent     [LLM]     depth classification (analyze/detect/full)
  analyze          [MCP]     compute_comfort_scores
  detect           [MCP]     detect_sensorial_conflicts
  suggest          [MCP]     generate_suggestions
  respond          [LLM]     natural language report, format driven by depth
  chitchat         [LLM]     free-form conversation
  inspire          [PYTHON]  placeholder -- Phase 3
"""

from __future__ import annotations
from typing import Any, TypedDict
from langgraph.graph import END, START, StateGraph

from nodes.preprocess      import preprocess_node
from nodes.load_layout     import build_load_layout_node
from nodes.ask_persona     import ask_persona_node
from nodes.route_intent    import build_route_intent_node
from nodes.analyze         import build_analyze_node
from nodes.detect          import build_detect_node
from nodes.suggest         import build_suggest_node
from nodes.respond         import build_respond_node
from nodes.chitchat        import build_chitchat_node
from nodes.inspire         import inspire_node
from nodes.overview        import overview_respond_node
from nodes.output_writer   import write_analysis_to_layout


# ---------------------------------------------------------------------------
# State  --  shared dict passed between every node in the graph
# ---------------------------------------------------------------------------

class AgentState(TypedDict, total=False):
    # ---- Input (set at the start of each turn) ----------------------------
    raw_prompt:            str       # raw text from the user
    has_image:             bool      # True if an image was attached (Phase 3)

    # ---- Routing (set by preprocess, read by edges) -----------------------
    intent:                str       # "comfort" | "overview" | "inspire" | "chitchat"
    layout_id:             str | None   # e.g. "201"
    persona_detected:      str | None   # e.g. "Elderly 65+"
    needs_persona_ask:     bool         # True when comfort but no persona found
    comfort_depth:         str          # "analyze" | "detect" | "full"

    # ---- Session persistence (carried across turns via run_agent) ----------
    layout_json_string:    str          # full JSON of the currently loaded layout

    # ---- Optional room targeting ------------------------------------------
    target_room_id:        str | None   # e.g. "room-3"; None = all rooms
                                        # wired through to analyze node,
                                        # not yet populated by preprocess

    # ---- MCP tool results (accumulated within one turn) -------------------
    last_scores_json:      str          # from compute_comfort_scores      [MCP]
    last_conflicts_json:   str          # from detect_sensorial_conflicts  [MCP]
    last_suggestions_json: str          # from generate_suggestions        [MCP]

    # ---- Output -----------------------------------------------------------
    final_response:        str | None   # natural language reply to the user


# ---------------------------------------------------------------------------
# Routing functions  --  each reads state and returns the next node name
# ---------------------------------------------------------------------------

def _route_after_preprocess(state: AgentState) -> str:
    """Both comfort and overview need the layout loaded first."""
    intent = state.get("intent", "chitchat")
    if intent in ("comfort", "overview"):
        return "load_layout"
    if intent == "inspire":
        return "inspire"
    return "chitchat"


def _route_after_load_layout(state: AgentState) -> str:
    """Overview short-circuits here; comfort continues to persona check."""
    intent = state.get("intent", "comfort")
    if intent == "overview":
        return "overview_respond"
    return "ask_persona"


def _route_after_analyze(state: AgentState) -> str:
    """If depth needs conflict detection, go to detect; otherwise straight to respond."""
    depth = state.get("comfort_depth", "analyze")
    if depth in ("detect", "full"):
        return "detect"
    return "respond"


def _route_after_detect(state: AgentState) -> str:
    """If depth needs suggestions, go to suggest; otherwise straight to respond."""
    depth = state.get("comfort_depth", "detect")
    if depth == "full":
        return "suggest"
    return "respond"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_graph(ctx: Any) -> Any:
    """
    Instantiate all nodes, wire up edges, and compile the StateGraph.

    Nodes that need external resources (LLM, MCP) are built via factory
    functions so the resource is captured in a closure -- the graph itself
    stays stateless.
    """

    # [LLM]  llm_simple = plain text output (no JSON schema constraint)
    #        used by: route_intent, respond, chitchat
    # [LLM]  llm       = structured JSON output (reserved for future tool-calling)
    # [MCP]  mcp_client = HTTP connection to Grasshopper/Swiftlet

    load_layout  = build_load_layout_node(ctx.layout_input_dir)  # [PYTHON]
    route_intent = build_route_intent_node(ctx.llm_simple)        # [LLM]
    analyze      = build_analyze_node(ctx.mcp_client)             # [MCP]
    detect       = build_detect_node(ctx.mcp_client)              # [MCP]
    suggest      = build_suggest_node(ctx.mcp_client)             # [MCP]
    respond      = build_respond_node(ctx.llm_simple)             # [LLM]
    chitchat     = build_chitchat_node(ctx.llm_simple)            # [LLM]

    g = StateGraph(AgentState)

    # -- Register nodes -----------------------------------------------------
    g.add_node("preprocess",       preprocess_node)       # [PYTHON]
    g.add_node("load_layout",      load_layout)           # [PYTHON]
    g.add_node("overview_respond", overview_respond_node) # [PYTHON]
    g.add_node("ask_persona",      ask_persona_node)      # [PYTHON]
    g.add_node("route_intent",     route_intent)          # [LLM]
    g.add_node("analyze",          analyze)               # [MCP]
    g.add_node("detect",           detect)                # [MCP]
    g.add_node("suggest",          suggest)               # [MCP]
    g.add_node("respond",          respond)               # [LLM]
    g.add_node("chitchat",         chitchat)              # [LLM]
    g.add_node("inspire",          inspire_node)          # [PYTHON] placeholder

    # -- Wire edges ---------------------------------------------------------

    # Entry point
    g.add_edge(START, "preprocess")

    # After PREPROCESS: branch on intent
    #   comfort / overview -> load_layout (both need the file)
    #   inspire            -> inspire
    #   chitchat           -> chitchat
    g.add_conditional_edges(
        "preprocess",
        _route_after_preprocess,
        {
            "load_layout": "load_layout",
            "inspire":     "inspire",
            "chitchat":    "chitchat",
        },
    )

    # After LOAD_LAYOUT: branch on intent
    #   overview -> overview_respond (short-circuit, no analysis)
    #   comfort  -> ask_persona
    g.add_conditional_edges(
        "load_layout",
        _route_after_load_layout,
        {
            "overview_respond": "overview_respond",
            "ask_persona":      "ask_persona",
        },
    )

    # Overview path ends here (no scores, no LLM response)
    g.add_edge("overview_respond", END)

    # Comfort path: persona -> route_intent -> analyze (always runs first)
    g.add_edge("ask_persona",  "route_intent")
    g.add_edge("route_intent", "analyze")

    # After ANALYZE [MCP]: branch on depth
    #   analyze      -> respond (scores only, no conflict detection)
    #   detect/full  -> detect
    g.add_conditional_edges(
        "analyze",
        _route_after_analyze,
        {
            "detect":  "detect",
            "respond": "respond",
        },
    )

    # After DETECT [MCP]: branch on depth
    #   detect -> respond (conflicts + scores, no suggestions)
    #   full   -> suggest
    g.add_conditional_edges(
        "detect",
        _route_after_detect,
        {
            "suggest": "suggest",
            "respond": "respond",
        },
    )

    # After SUGGEST [MCP]: always respond (suggestions + conflicts + scores)
    g.add_edge("suggest",  "respond")

    # Terminal edges
    g.add_edge("respond",  END)
    g.add_edge("chitchat", END)
    g.add_edge("inspire",  END)

    return g.compile()


# ---------------------------------------------------------------------------
# run_agent  --  called once per user turn from main.py
# ---------------------------------------------------------------------------

def run_agent(prompt: str, ctx: Any, session: dict | None = None) -> tuple[str, dict]:
    """
    Run one turn of the Comfort Copilot agent.

    Args:
        prompt  : raw user input for this turn
        ctx     : Context object from bootstrap() -- holds LLM, MCP client,
                  layout_input_dir, layout_output_dir
        session : persistent state carried across turns
                  { layout_json_string, persona_detected, layout_id }
                  Pass None or {} on the first turn.

    Returns:
        (final_response, updated_session)
        Pass updated_session back into the next run_agent() call.

    Post-graph step (outside the graph):
        If the comfort path ran and scores were computed, output_writer.py
        writes the enriched layout to resulting_layout/Layout-{id}_modified.json.
        This is intentionally outside the graph so a write failure never
        blocks the text response from reaching the user.
    """
    if session is None:
        session = {}

    initial_state: AgentState = {
        # This turn's input
        "raw_prompt": prompt,
        "has_image":  False,

        # Carry over persistent fields from the previous turn
        "layout_json_string": session.get("layout_json_string", ""),
        "persona_detected":   session.get("persona_detected"),
        "layout_id":          session.get("layout_id"),

        # Reset per-turn fields (fresh each turn)
        "intent":                "",
        "needs_persona_ask":     False,
        "comfort_depth":         "analyze",
        "target_room_id":        None,
        "last_scores_json":      "",
        "last_conflicts_json":   "",
        "last_suggestions_json": "",
        "final_response":        None,
    }

    app = build_graph(ctx)

    print("\nWorkflow graph:")
    app.get_graph().print_ascii()

    # -- Run the graph ------------------------------------------------------
    final_state = app.invoke(initial_state)

    response = final_state.get("final_response") or ""
    intent   = final_state.get("intent", "")
    depth    = final_state.get("comfort_depth", "")
    scores_ready = bool(final_state.get("last_scores_json"))

    print("[run_agent] intent={} | depth={} | scores_ready={}".format(
        intent, depth, scores_ready
    ))

    # -- [POST-GRAPH] Write analysis to resulting_layout/ -------------------
    # Runs only when the comfort path executed and scores were computed.
    # Failure is non-fatal -- the user always gets their text response.
    if intent == "comfort" and scores_ready:
        try:
            write_analysis_to_layout(final_state, ctx.layout_output_dir)
        except Exception as exc:
            print("[run_agent] ERROR in output_writer: {}".format(exc))

    # -- Update session with persistent fields ------------------------------
    if intent == "comfort":
        # Full update: layout, persona, and ID may all have changed this turn
        updated_session = {
            "layout_json_string": final_state.get("layout_json_string", ""),
            "persona_detected":   final_state.get("persona_detected"),
            "layout_id":          final_state.get("layout_id"),
        }
    elif intent == "overview":
        # Overview loaded the layout but did not set a persona -- keep
        # the layout in session so the next comfort turn skips reloading.
        updated_session = {
            "layout_json_string": final_state.get("layout_json_string", ""),
            "persona_detected":   session.get("persona_detected"),  # unchanged
            "layout_id":          final_state.get("layout_id"),
        }
    else:
        # chitchat / inspire -- nothing layout-related changed
        updated_session = dict(session)

    return response, updated_session
