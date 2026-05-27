"""
export_mermaid.py -- Export the Sensi graph as a Mermaid diagram  (v3 Bundle C)

The _DIAGRAM constant below IS the diagram for the v3 Bundle C architecture.
Running this script:
  1. Builds graph.py and verifies all expected nodes are present
  2. Saves sensi_graph.mermaid to the python/ folder

When you change graph.py structure (add/remove nodes):
  - Update _NODE_MAP below
  - Update _DIAGRAM to reflect the new structure
  - Run this script to verify and publish

Run from the python/ directory:
    python export_mermaid.py
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class _MockContext:
    llm_simple:       Any  = None
    llm:              Any  = None
    mcp_client:       Any  = None
    layout_input_dir: Path = field(default_factory=lambda: Path(".") / "randomized_layouts")
    layout_output_dir: Path = field(default_factory=lambda: Path(".") / "resulting_layout")


# Maps diagram node IDs → graph.py node names (for structural verification)
_NODE_MAP = {
    # Onboarding
    "GREET":             "greet",
    "QUIZ":              "quiz",
    "INSPIRE":           "inspire",
    "PERSONA_COMPILER":  "persona_compiler",
    # Layout mode — routing
    "INTENT_CLASSIFIER": "intent_classifier",
    "CHITCHAT":          "chitchat",
    "DETAIL_RESPOND":    "detail_respond",
    # Layout mode — layout
    "LOAD_LAYOUT":       "load_layout",
    "OVERVIEW_RESPOND":  "overview_respond",
    # Layout mode — analysis chain
    "ROUTE_INTENT":      "route_intent",
    "ANALYZE":           "analyze",
    "SCORE_INTERP":      "score_interpreter",
    "DETECT":            "detect",
    "CONFLICT_R":        "conflict_reasoner",
    "SUGGEST":           "suggest",
    "SUGGEST_CRIT":      "suggestion_critic",
    "RESPOND":           "respond",
    # Layout mode — quality loop  (fact_checker removed in Bundle C)
    "EVALUATOR":         "evaluator",
    "WHAT_NEXT":         "what_next",
    # Layout mode — tool paths (placeholders)
    "CHANGE_MATERIAL":    "change_material",
    "MODIFY_GLAZING":     "modify_glazing",
    "ADD_FURNITURE":      "add_furniture",
    "COMPARE_VERSIONS":   "compare_versions",
    "TOPOLOGIC":          "topologic_analysis",
    "PERSONA_COMPARISON": "persona_comparison",
    "BIOPHILIC_AUDIT":    "biophilic_audit",
}


def _verify_graph(app):
    """Warn about any node mismatches between diagram and compiled graph."""
    actual   = set(app.get_graph().nodes.keys()) - {"__start__", "__end__"}
    expected = set(_NODE_MAP.values())
    missing_in_diagram = actual   - expected
    missing_in_graph   = expected - actual
    ok = True
    if missing_in_diagram:
        print("WARNING -- in graph.py but NOT in diagram: {}".format(missing_in_diagram))
        ok = False
    if missing_in_graph:
        print("WARNING -- in diagram but NOT in graph.py: {}".format(missing_in_graph))
        ok = False
    if ok:
        print("OK -- all {} nodes verified against graph.py".format(len(actual)))


# ── THE DIAGRAM (v3 Bundle C) ─────────────────────────────────────────────────

_DIAGRAM = r"""---
config:
  flowchart:
    curve: basis
---
flowchart TB

    %% ── STYLES ─────────────────────────────────────────────────────────────
    classDef llm        fill:#D6E8F8,stroke:#4A90D9,stroke-width:2px,color:#1a1a1a
    classDef py         fill:#D5EFDC,stroke:#5BAD72,stroke-width:2px,color:#1a1a1a
    classDef mcp        fill:#FDDCBC,stroke:#E07B3A,stroke-width:2px,color:#1a1a1a
    classDef onboard    fill:#EAD5F5,stroke:#9B59B6,stroke-width:2.5px,color:#1a1a1a
    classDef specialist fill:#FCE4D6,stroke:#A0522D,stroke-width:2px,color:#1a1a1a
    classDef ph         fill:#FFFDE7,stroke:#F9A825,stroke-width:1.5px,stroke-dasharray:4 2,color:#555
    classDef terminal   fill:#2C3E50,stroke:#2C3E50,color:#fff
    classDef gate       fill:#F8F9FA,stroke:#6C757D,stroke-width:1.5px,stroke-dasharray:3 2,color:#555

    START([START]):::terminal
    END_F([END]):::terminal

    %% ── ① ONBOARDING ────────────────────────────────────────────────────────
    subgraph ONBOARDING["① ONBOARDING  —  runs once · skipped for returning users"]
        direction TB
        GREET["GREET  [LLM]\n'Hi, I'm Sensi — who are you?'"]:::onboard

        subgraph QUIZ_BOX["QUIZ  —  one question per turn  (6 turns)"]
            direction TB
            QUIZ["QUIZ  [LLM]\nQ0 Who are you?\nQ1 Comfortable space memory\nQ2 What bothers you in a space?\nQ3 How do you use your home?\nQ4 Specific needs or sensitivities?\nQ5 One non-negotiable quality?"]:::onboard
        end

        subgraph INSPIRE_BOX["INSPIRE  —  aesthetic profiler  (2 graph turns · PyQt5 GUI pipeline)"]
            direction TB
            INSPIRE["INSPIRE  [LLM]\nTurn A — GUI moodboard pipeline:\n  ① Atmosphere question  +  reference image upload\n  ② VLM analysis of uploaded images\n  ③ LLM generates Unsplash search queries\n  ④ Round 1: browse candidates → pick favourites\n  ⑤ Round 2: refined candidates → pick favourites\n  ⑥ Round 3: final candidates → pick favourites\n  ⑦ Moodboard approval\nTurn B — LLM synthesis:\n  merges VLM image analysis + written description\n  → inspire_summary  (feeds persona_compiler)"]:::onboard
        end

        PERSONA_COMPILER["PERSONA_COMPILER  [LLM]\nSynthesises quiz answers + inspire_summary\ninto full persona profile JSON\nSaves → team_02/persona.json\nSets onboarding_complete = True"]:::onboard
    end

    PERSONA_FILE[("persona.json\non disk")]:::gate

    %% ── ② ROUTING  (layout mode) ────────────────────────────────────────────
    subgraph ROUTING["② ROUTING  —  layout mode"]
        INTENT_CLASSIFIER["INTENT_CLASSIFIER  [LLM]\ncomfort · overview · tools\nfollow_up · inspire · chitchat"]:::llm
    end

    CHITCHAT["CHITCHAT  [LLM]\noff-topic questions · general chat\ndetects if user shifts to analysis"]:::llm
    DETAIL_RESPOND["DETAIL_RESPOND  [LLM]\nfollow_up answers using cached session data\nscore_interpretation · conflict_reasoning\nsuggestion_critique — no MCP re-run"]:::llm
    OVERVIEW_RESPOND["OVERVIEW_RESPOND  [PY]\nquick room list · no analysis"]:::py

    %% ── ③ LAYOUT ────────────────────────────────────────────────────────────
    LOAD_LAYOUT["LOAD_LAYOUT  [PY]\nreads layout JSON\nskips if already in session"]:::py

    %% ── ④ ROUTE INTENT ──────────────────────────────────────────────────────
    subgraph INTENT["④ ROUTE INTENT"]
        ROUTE_INTENT["ROUTE_INTENT  [LLM]\nanalyze · detect · full\nwhat-if · compare · biophilic · topologic"]:::llm
    end

    %% ── ⑤ MAIN ANALYSIS CHAIN ───────────────────────────────────────────────
    subgraph ANALYSIS["⑤ MAIN ANALYSIS CHAIN"]
        ANALYZE["ANALYZE  [MCP]\ncompute_comfort_scores\n6 senses · all rooms · per persona"]:::mcp
        SCORE_INTERP["SCORE_INTERPRETER  [LLM]\nwhat do scores mean for this persona?\n→ score_interpretation  (persisted)"]:::specialist
        DETECT["DETECT  [MCP]\ndetect_sensorial_conflicts\nflags senses below persona threshold"]:::mcp
        CONFLICT_R["CONFLICT_REASONER  [LLM]\nwhy did it fail? root cause\n→ conflict_reasoning  (persisted)"]:::specialist
        SUGGEST["SUGGEST  [MCP]\ngenerate_suggestions\nper failing sense per room"]:::mcp
        SUGGEST_CRIT["SUGGESTION_CRITIC  [LLM]\nfeasible? ranked by priority?\ncross-sense consequences?\n→ suggestion_critique  (persisted)"]:::specialist
    end

    %% ── ⑤a–d TOOL PATHS (placeholders) ─────────────────────────────────────
    subgraph TOOLS["⑤a–d TOOL PATHS  —  placeholders"]
        CHANGE_MATERIAL["CHANGE_MATERIAL  [PH·MCP]\nmodify material → re-score"]:::ph
        MODIFY_GLAZING["MODIFY_GLAZING  [PH·MCP]\nglazing ratio/type → re-score"]:::ph
        ADD_FURNITURE["ADD_FURNITURE  [PH·MCP]\nadd furniture/plants → re-score"]:::ph
        COMPARE_VERSIONS["COMPARE_VERSIONS  [PH·MCP]\nbefore/after score delta"]:::ph
        TOPOLOGIC["TOPOLOGIC_ANALYSIS  [PH·MCP]\nroom adjacency via TopologicPy"]:::ph
        PERSONA_COMPARISON["PERSONA_COMPARISON  [PH·LLM]\nsame layout · two personas"]:::ph
        BIOPHILIC_AUDIT["BIOPHILIC_AUDIT  [PH·LLM]\nTalk Green To Me"]:::ph
    end

    %% ── ⑥ QUALITY LOOP ──────────────────────────────────────────────────────
    subgraph QUALITY["⑥ QUALITY LOOP"]
        RESPOND["RESPOND  [LLM]\npersona-aware · depth-aware\nanalyze · detect · full formats"]:::llm
        EVALUATOR["EVALUATOR  [LLM]\ncoherent? complete? right tone?\nAPPROVED or REVISE  (max 1)"]:::specialist
    end

    %% ── ⑦ FEEDBACK LOOP ─────────────────────────────────────────────────────
    WHAT_NEXT["WHAT_NEXT  [LLM]\ndepth-aware feedback offer\nnames worst finding · suggests next action"]:::llm

    OUTPUT_WRITER[("OUTPUT_WRITER  [PY]\npost-graph · writes resulting_layout/")]:::py

    %% ── EDGES ────────────────────────────────────────────────────────────────

    %% Onboarding (sequential, one turn each)
    START --> GREET
    GREET -->|"turn 1 → END\n(wait for user)"| END_F
    GREET -.->|"turn 2+"| QUIZ
    QUIZ -->|"each turn → END\n(wait for answer)"| END_F
    QUIZ -->|"quiz_complete"| INSPIRE
    INSPIRE -->|"turn A → END\n(wait for aesthetic answer)"| END_F
    INSPIRE -->|"inspire_complete"| PERSONA_COMPILER
    PERSONA_COMPILER --> PERSONA_FILE
    PERSONA_COMPILER -->|"onboarding_complete\n→ END"| END_F

    %% Returning users skip onboarding
    PERSONA_FILE -.->|"detected at startup\nskip onboarding"| ROUTING

    %% Layout mode entry
    START -->|"onboarding_complete"| ROUTING

    %% Routing
    INTENT_CLASSIFIER -->|"comfort · overview · tools"| LOAD_LAYOUT
    INTENT_CLASSIFIER -->|"follow_up"| DETAIL_RESPOND
    INTENT_CLASSIFIER -->|"inspire"| INSPIRE
    INTENT_CLASSIFIER -->|"chitchat"| CHITCHAT
    DETAIL_RESPOND --> WHAT_NEXT
    CHITCHAT -->|"analysis intent"| INTENT_CLASSIFIER
    CHITCHAT --> WHAT_NEXT

    %% Layout
    LOAD_LAYOUT -->|"overview"| OVERVIEW_RESPOND --> WHAT_NEXT
    LOAD_LAYOUT -->|"analysis · tools"| ROUTE_INTENT

    %% Route intent → tool paths and analysis
    ROUTE_INTENT -->|"analyze · detect · full"| ANALYZE
    ROUTE_INTENT -->|"what-if material"| CHANGE_MATERIAL
    ROUTE_INTENT -->|"what-if glazing"| MODIFY_GLAZING
    ROUTE_INTENT -->|"compare"| PERSONA_COMPARISON
    ROUTE_INTENT -->|"biophilic"| BIOPHILIC_AUDIT
    ROUTE_INTENT -->|"topologic"| TOPOLOGIC

    %% Modification tools → re-score
    CHANGE_MATERIAL & MODIFY_GLAZING & ADD_FURNITURE -->|"re-score"| ANALYZE
    ANALYZE -->|"after mod"| COMPARE_VERSIONS --> SCORE_INTERP
    ANALYZE -->|"direct"| SCORE_INTERP

    %% Analysis chain
    SCORE_INTERP -->|"detect · full"| DETECT
    SCORE_INTERP -->|"analyze only"| RESPOND
    DETECT --> CONFLICT_R
    CONFLICT_R -->|"full"| SUGGEST --> SUGGEST_CRIT --> RESPOND
    CONFLICT_R -->|"detect"| RESPOND

    %% Spatial + persona comparison feeds
    TOPOLOGIC --> CONFLICT_R
    PERSONA_COMPARISON --> SCORE_INTERP
    BIOPHILIC_AUDIT -->|"needs plants"| ADD_FURNITURE
    BIOPHILIC_AUDIT -->|"direct"| SCORE_INTERP

    %% Quality loop  (fact_checker removed in Bundle C)
    RESPOND --> EVALUATOR
    EVALUATOR -->|"REVISE  max 1"| RESPOND
    EVALUATOR -->|"APPROVED"| WHAT_NEXT
    WHAT_NEXT -.->|"post-graph"| OUTPUT_WRITER

    %% Feedback
    WHAT_NEXT -->|"done"| END_F
"""


def main():
    from graph import build_graph

    ctx = _MockContext()
    app = build_graph(ctx)

    print("Verifying graph.py structure...")
    _verify_graph(app)
    print()

    output_path = Path(__file__).parent / "sensi_graph.mermaid"
    output_path.write_text(_DIAGRAM.lstrip('\n'), encoding="utf-8")

    print("Exported: {}".format(output_path))
    print("Open in VS Code (Mermaid Preview) or paste at https://mermaid.live")


if __name__ == "__main__":
    main()
