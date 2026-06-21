"""
export_mermaid.py -- Export the Sensi graph as a Mermaid diagram  (v4)

The _DIAGRAM constant below IS the diagram for the current v4 architecture:
  - unified action_classifier (replaces v3's intent_classifier + route_intent)
  - in-process comfort tools via LocalToolClient (migrated OUT of the MCP /
    Grasshopper bridge -- Rhino/Grasshopper/Swiftlet are no longer required)
  - web (React + FastAPI + SSE) onboarding pipeline (the old PyQt5 GUI is gone)
  - predictive preview ("what if") node

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
    llm_fast:         Any  = None   # routing / classification / short text tier
    llm_smart:        Any  = None   # user-facing prose & nuanced reasoning tier
    mcp_client:       Any  = None   # name kept for parity; real ctx holds a LocalToolClient
    layout_input_dir: Path = field(default_factory=lambda: Path(".") / "randomized_layouts")
    layout_output_dir: Path = field(default_factory=lambda: Path(".") / "resulting_layout")


# Maps diagram node IDs → graph.py node names (for structural verification)
_NODE_MAP = {
    # Onboarding
    "GREET":             "greet",
    "QUIZ":              "quiz",
    "INSPIRE":           "inspire",
    "PERSONA_COMPILER":  "persona_compiler",
    # Routing (unified — v4)
    "ACTION_CLASSIFIER": "action_classifier",
    "CHITCHAT":          "chitchat",
    "DETAIL_RESPOND":    "detail_respond",
    # Layout
    "LOAD_LAYOUT":       "load_layout",
    "OVERVIEW_RESPOND":  "overview_respond",
    # Analysis chain
    "ANALYZE":           "analyze",
    "SCORE_INTERP":      "score_interpreter",
    "DETECT":            "detect",
    "CONFLICT_R":        "conflict_reasoner",
    "SUGGEST":           "suggest",
    "SUGGEST_CRIT":      "suggestion_critic",
    # Quality loop
    "RESPOND":           "respond",
    "EVALUATOR":         "evaluator",
    "WHAT_NEXT":         "what_next",
    # Edit tools (unified multi-edit path)
    "EDIT_PLANNER":      "edit_planner",
    "APPLY_EDITS":       "apply_edits",
    "COMPARE_VERSIONS":  "compare_versions",
    "PREVIEW":           "preview",
    # Insight tools
    "TOPOLOGIC":          "topologic_analysis",
    "BIOPHILIC_AUDIT":    "biophilic_audit",
    "PERSONA_COMPARISON": "persona_comparison",
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


# ── THE DIAGRAM (v4) ───────────────────────────────────────────────────────────

_DIAGRAM = r"""---
config:
  flowchart:
    curve: basis
---
flowchart TB

    %% ── STYLES ─────────────────────────────────────────────────────────────
    %% llm  = LLM reasoning step          tool = in-process comfort tool (pure Python)
    %% py   = deterministic Python step    onboard = one-time onboarding
    classDef llm      fill:#D6E8F8,stroke:#4A90D9,stroke-width:2px,color:#1a1a1a
    classDef tool     fill:#CDEFD9,stroke:#3FAE6F,stroke-width:2px,color:#1a1a1a
    classDef py       fill:#FCE9C8,stroke:#E0913A,stroke-width:2px,color:#1a1a1a
    classDef onboard  fill:#EAD5F5,stroke:#9B59B6,stroke-width:2.5px,color:#1a1a1a
    classDef terminal fill:#2C3E50,stroke:#2C3E50,color:#fff
    classDef gate     fill:#F8F9FA,stroke:#6C757D,stroke-width:1.5px,stroke-dasharray:3 2,color:#555
    %% Act 3 (The Vision) — its own lively palette so the output reads as a destination
    classDef report   fill:#CDE7F2,stroke:#3F93B5,stroke-width:2px,color:#1a1a1a
    classDef vision   fill:#F6CFE9,stroke:#C2479A,stroke-width:3px,color:#1a1a1a
    classDef output   fill:#F7E6BE,stroke:#D9A441,stroke-width:2px,color:#1a1a1a
    classDef state    fill:#E8E4F3,stroke:#7E6BB0,stroke-width:2px,color:#1a1a1a

    START([START]):::terminal
    END_F([END]):::terminal

    %% ── LEGEND ──────────────────────────────────────────────────────────────
    subgraph LEGEND["LEGEND"]
        direction LR
        L_LLM["LLM reasoning"]:::llm
        L_TOOL["in-process comfort tool"]:::tool
        L_PY["deterministic Python"]:::py
        L_ON["onboarding (once)"]:::onboard
    end

    %% ── ① ONBOARDING — runs once · skipped for returning users (persona.json) ─
    subgraph ONBOARDING["① ONBOARDING — runs once · skipped if persona.json exists"]
        direction TB
        GREET["GREET<br/>'Hi, I'm Sensi — who are you?'"]:::onboard
        QUIZ["QUIZ<br/>one question per turn (6 turns)<br/>captures sensory priorities + sensitivities"]:::onboard
        INSPIRE["INSPIRE<br/>web moodboard pipeline (FastAPI + SSE)<br/>image search → VLM tags → sense picks"]:::onboard
        PERSONA_COMPILER["PERSONA_COMPILER<br/>quiz + inspire → persona_profile JSON<br/>(comfort_weights per sense) → personas/persona.json"]:::onboard
        GREET -.-> QUIZ -.-> INSPIRE -.-> PERSONA_COMPILER
    end

    PERSONA_FILE[("persona.json on disk")]:::gate

    %% ── ② ROUTING (layout mode) — one LLM call per turn ──────────────────────
    subgraph ROUTING["② ROUTING — layout mode"]
        ACTION_CLASSIFIER["ACTION_CLASSIFIER<br/>ONE call → one of 12 actions:<br/>analyze · detect · full · overview · follow_up<br/>chitchat · inspire · edit · preview<br/>topologic · biophilic · compare"]:::llm
    end

    CHITCHAT["CHITCHAT<br/>off-topic; detects shift to analysis"]:::llm
    DETAIL_RESPOND["DETAIL_RESPOND<br/>follow-up from CACHED session data<br/>no re-scoring"]:::llm
    OVERVIEW_RESPOND["OVERVIEW_RESPOND<br/>quick room list · no analysis"]:::py

    %% ── ③ LAYOUT ─────────────────────────────────────────────────────────────
    LOAD_LAYOUT["LOAD_LAYOUT<br/>read layout JSON · resolve target room<br/>skip if already in session"]:::py

    %% ── ④ ANALYSIS CHAIN (cache-aware) ───────────────────────────────────────
    subgraph ANALYSIS["④ ANALYSIS CHAIN — cache-aware"]
        ANALYZE["ANALYZE<br/>compute_comfort_scores<br/>6 senses · all rooms · persona-weighted<br/>baseScores · comfortScores · adjustments"]:::tool
        SCORE_INTERP["SCORE_INTERPRETER<br/>what do the scores mean for this persona?"]:::llm
        DETECT["DETECT<br/>detect_sensorial_conflicts<br/>senses below persona threshold"]:::tool
        CONFLICT_R["CONFLICT_REASONER<br/>root cause of each conflict"]:::llm
        SUGGEST["SUGGEST<br/>generate_suggestions<br/>one fix per failing sense"]:::tool
        SUGGEST_CRIT["SUGGESTION_CRITIC<br/>feasible? ranked? cross-sense cost?"]:::llm
    end

    %% ── ⑤ EDIT TOOLS — multi-edit: N ops in one turn, ONE re-score ───────────
    subgraph EDITS["⑤ EDIT TOOLS — decompose → mutate all → re-score → compare"]
        EDIT_PLANNER["EDIT_PLANNER<br/>prompt → ops list<br/>'add 2 plants and change glazing' → 2 ops"]:::llm
        APPLY_EDITS["APPLY_EDITS<br/>mutate every op · accumulate layout_diffs"]:::py
        COMPARE_VERSIONS["COMPARE_VERSIONS<br/>before/after delta per sense"]:::py
        PREVIEW["PREVIEW — 'what if'<br/>score a CLONE · predicted ripple · NOT committed"]:::tool
    end

    %% ── ⑥ INSIGHT TOOLS ──────────────────────────────────────────────────────
    subgraph INSIGHTS["⑥ INSIGHT TOOLS"]
        TOPOLOGIC["TOPOLOGIC_ANALYSIS<br/>room adjacency graph (NetworkX)<br/>degree · betweenness · bridges · zones"]:::py
        BIOPHILIC_AUDIT["BIOPHILIC_AUDIT<br/>greenery richness per room"]:::py
        PERSONA_COMPARISON["PERSONA_COMPARISON<br/>same layout · two personas"]:::tool
    end

    %% ── ⑦ QUALITY LOOP ───────────────────────────────────────────────────────
    subgraph QUALITY["⑦ QUALITY LOOP"]
        RESPOND["RESPOND<br/>persona-aware · action-aware formatting"]:::llm
        EVALUATOR["EVALUATOR<br/>coherent? complete? APPROVED / REVISE (max 1)"]:::llm
    end

    WHAT_NEXT["WHAT_NEXT<br/>names worst finding · suggests next action"]:::llm
    OUTPUT_WRITER[("OUTPUT_WRITER (post-graph)<br/>writes resulting_layout/")]:::gate

    %% Shared memory the analysis leaves behind — the bridge to Act 3.
    SESSION[("session memory<br/>scores · current layout · persona")]:::state

    %% ── ⑧ ACT 3 — THE VISION (the output: each room's scores become an image) ────
    %% A separate screen with its own REST endpoints, opened after the analysis. It
    %% reads the cached scores from the session and turns each room into a render.
    subgraph REPORT["⑧ ACT 3 — THE VISION · the output"]
        direction TB
        REPORT_API["/api/report<br/>scores → a prompt per room"]:::report
        RENDER["/api/render-room<br/>prompt + scores → rendered room"]:::report
        COMPARE["before / after · initial → now<br/>/api/compare-initial"]:::report
        IMG_MODEL{{"image generation<br/>Google Nano Banana · OpenAI gpt-image-1"}}:::vision
        EXPORTS[("download<br/>PNG · JSON: edited layout + scores + prompts")]:::output
        REPORT_API --> RENDER --> IMG_MODEL
        COMPARE --> IMG_MODEL
        RENDER --> EXPORTS
    end

    %% ── EDGES ─────────────────────────────────────────────────────────────────

    %% Onboarding spine (one turn each, waits for user)
    START --> GREET
    GREET -->|"turn 1 → END"| END_F
    QUIZ -->|"each turn → END"| END_F
    PERSONA_COMPILER -->|"onboarding_complete → END"| END_F
    PERSONA_COMPILER --> PERSONA_FILE
    PERSONA_FILE -.->|"detected at startup → skip onboarding"| ROUTING

    %% Layout mode entry
    START -->|"onboarding_complete"| ACTION_CLASSIFIER

    %% Routing
    ACTION_CLASSIFIER -->|"follow_up"| DETAIL_RESPOND
    ACTION_CLASSIFIER -->|"chitchat"| CHITCHAT
    ACTION_CLASSIFIER -->|"inspire"| INSPIRE
    ACTION_CLASSIFIER -->|"all analysis / tool actions"| LOAD_LAYOUT
    DETAIL_RESPOND --> WHAT_NEXT
    CHITCHAT -->|"analysis intent"| ACTION_CLASSIFIER
    CHITCHAT -->|"done"| WHAT_NEXT

    %% Layout dispatch
    LOAD_LAYOUT -->|"overview"| OVERVIEW_RESPOND --> WHAT_NEXT
    LOAD_LAYOUT -->|"analyze · (detect/full, no cache)"| ANALYZE
    LOAD_LAYOUT -->|"detect/full · CACHE HIT (skip analyze)"| DETECT
    LOAD_LAYOUT -->|"edit (one or more changes)"| EDIT_PLANNER
    LOAD_LAYOUT -->|"preview / what-if"| PREVIEW
    LOAD_LAYOUT -->|"topologic"| TOPOLOGIC
    LOAD_LAYOUT -->|"biophilic"| BIOPHILIC_AUDIT
    LOAD_LAYOUT -->|"compare"| PERSONA_COMPARISON
    LOAD_LAYOUT -.->|"layout not found → END"| END_F

    %% Analysis chain
    ANALYZE -->|"after an edit"| COMPARE_VERSIONS
    ANALYZE -->|"direct"| SCORE_INTERP
    COMPARE_VERSIONS --> SCORE_INTERP
    SCORE_INTERP -->|"detect · full"| DETECT
    SCORE_INTERP -->|"analyze only"| RESPOND
    DETECT --> CONFLICT_R
    CONFLICT_R -->|"full"| SUGGEST --> SUGGEST_CRIT --> RESPOND
    CONFLICT_R -->|"detect"| RESPOND

    %% Edit path → single re-score (or straight to respond when nothing resolved)
    EDIT_PLANNER --> APPLY_EDITS
    APPLY_EDITS -->|"changed"| ANALYZE
    APPLY_EDITS -->|"zero ops"| RESPOND
    PREVIEW --> WHAT_NEXT

    %% Insight tools
    TOPOLOGIC --> RESPOND
    BIOPHILIC_AUDIT -->|"needs plants (pre-seeds edit_ops)"| APPLY_EDITS
    BIOPHILIC_AUDIT -->|"direct"| SCORE_INTERP
    PERSONA_COMPARISON --> SCORE_INTERP

    %% Quality loop + feedback
    RESPOND --> EVALUATOR
    EVALUATOR -->|"REVISE (max 1)"| RESPOND
    EVALUATOR -->|"APPROVED"| WHAT_NEXT
    WHAT_NEXT -.->|"post-graph"| OUTPUT_WRITER
    WHAT_NEXT -->|"done"| END_F

    %% Where Act 3 gets its data: the analysis turn caches the scores and the current
    %% (edited) layout on the session; The Vision reads them — it never re-runs the graph.
    ANALYZE -.->|"caches scores"| SESSION
    SESSION -.->|"later · user opens The Vision · reads scores"| REPORT_API
    SESSION -.->|"scores + room attributes"| RENDER
    SESSION -.->|"current layout (vs the initial on-disk)"| COMPARE
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
