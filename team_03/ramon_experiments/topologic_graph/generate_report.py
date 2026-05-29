"""
Generate the Spatial Graph Report PDF with embedded diagrams.
Run from any directory — all paths are resolved relative to this script.
"""

import json
import sys
import math
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.patches as FancyArrowPatch
from matplotlib.patches import FancyBboxPatch
import networkx as nx

# ── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PYTHON_DIR = SCRIPT_DIR.parent.parent / "python"
LAYOUT_DIR = SCRIPT_DIR.parent.parent / "layout"
OUTPUT_DIR = SCRIPT_DIR
DIAGRAMS_DIR = SCRIPT_DIR / "_diagrams"
DIAGRAMS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(PYTHON_DIR))
from spatial_graph import (
    build_graph_from_layout,
    enrich_graph_from_analysis,
    graph_to_dict,
    dict_to_graph,
    serialize_for_llm,
)

# ── Color palette ────────────────────────────────────────────────────────
BG       = "#1a1a2e"
BG_LIGHT = "#16213e"
ACCENT   = "#0f3460"
BLUE     = "#53a8e2"
GREEN    = "#4ecca3"
RED      = "#e84545"
ORANGE   = "#fc9d28"
PURPLE   = "#9b59b6"
TEAL     = "#1abc9c"
GRAY     = "#95a5a6"
WHITE    = "#ecf0f1"
YELLOW   = "#f1c40f"

NODE_COLORS = {"room": BLUE, "door": ORANGE, "furniture": GREEN, "mep": RED}
NODE_SIZES  = {"room": 1100, "door": 500, "furniture": 700, "mep": 600}
EDGE_COLORS = {
    "contained_in": GRAY, "door_connects": ORANGE, "adjacent": BLUE,
    "near": GREEN, "blocks": RED, "sightline": PURPLE, "path": TEAL,
}
EDGE_STYLES = {
    "contained_in": "dotted", "door_connects": "solid", "adjacent": "solid",
    "near": "dashed", "blocks": "solid", "sightline": "dashdot", "path": "dashed",
}


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 1: Architecture flow
# ══════════════════════════════════════════════════════════════════════════
def make_architecture_diagram():
    fig, ax = plt.subplots(figsize=(12, 7))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.5, 10.5)
    ax.set_ylim(-0.5, 7)
    ax.axis("off")

    # Title
    ax.text(5, 6.5, "Agent Architecture — Spatial Graph Integration",
            ha="center", va="center", fontsize=16, color=WHITE, fontweight="bold")

    # Boxes: (x, y, w, h, label, color)
    boxes = [
        (0.2, 4.5, 2.0, 0.8, "reason.py\n(LLM Brain)", BLUE),
        (3.5, 5.5, 2.2, 0.7, "add_objects.py\n(Placement)", GREEN),
        (3.5, 3.5, 2.2, 0.7, "tools.py\n(MCP Tools)", GRAY),
        (7.0, 5.5, 2.8, 0.7, "collision / visibility\norientation", ORANGE),
        (7.0, 4.3, 2.8, 0.7, "path_analysis\nreachability", ORANGE),
        (7.0, 3.1, 2.8, 0.7, "enrich_graph\n(Graph B Update)", PURPLE),
        (7.0, 1.9, 2.8, 0.7, "scoring.py\n(Quality Score)", TEAL),
        (3.5, 1.0, 2.2, 0.7, "user_checkpoint\n(Approval)", YELLOW),
        (0.2, 1.0, 2.0, 0.8, "spatial_graph.py\n(Graph B)", RED),
    ]

    for bx, by, bw, bh, label, color in boxes:
        rect = FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0.1",
                               facecolor=color + "33", edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        ax.text(bx + bw/2, by + bh/2, label, ha="center", va="center",
                fontsize=8, color=WHITE, fontweight="bold")

    # Arrows
    arrow_kw = dict(arrowstyle="-|>", color=WHITE, lw=1.5, mutation_scale=15)

    arrows = [
        # reason -> add_objects
        ((2.2, 5.0), (3.5, 5.85)),
        # reason -> tools
        ((2.2, 4.7), (3.5, 3.85)),
        # add_objects -> analysis
        ((5.7, 5.85), (7.0, 5.85)),
        # analysis group1 -> group2
        ((8.4, 5.5), (8.4, 5.0)),
        # group2 -> enrich_graph
        ((8.4, 4.3), (8.4, 3.8)),
        # enrich_graph -> scoring
        ((8.4, 3.1), (8.4, 2.6)),
        # scoring -> checkpoint
        ((7.0, 2.25), (5.7, 1.35)),
        # checkpoint -> reason (loop back)
        ((3.5, 1.35), (2.2, 4.5)),
        # spatial_graph.py feeds reason
        ((2.2, 1.4), (2.2, 4.5)),
    ]
    for start, end in arrows:
        ax.annotate("", xy=end, xytext=start, arrowprops=arrow_kw)

    # Labels on arrows
    ax.text(2.8, 5.6, "place", fontsize=7, color=GREEN, ha="center", style="italic")
    ax.text(2.8, 4.2, "analyze", fontsize=7, color=GRAY, ha="center", style="italic")
    ax.text(6.4, 6.0, "auto pipeline", fontsize=7, color=ORANGE, ha="center", style="italic")
    ax.text(9.5, 3.5, "enrich", fontsize=7, color=PURPLE, ha="left", style="italic")
    ax.text(6.3, 1.9, "score", fontsize=7, color=TEAL, ha="center", style="italic")
    ax.text(1.0, 3.0, "graph_text\nto LLM", fontsize=7, color=RED, ha="center", style="italic")

    # State box
    rect = FancyBboxPatch((0.2, 2.2), 2.0, 0.6, boxstyle="round,pad=0.05",
                           facecolor=BG_LIGHT, edgecolor=ACCENT, linewidth=1, linestyle="--")
    ax.add_patch(rect)
    ax.text(1.2, 2.5, "AgentState (RAM)\nspatial_graph + text", ha="center", va="center",
            fontsize=7, color=GRAY, style="italic")

    plt.tight_layout()
    out = DIAGRAMS_DIR / "01_architecture.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 2: Data flow — where each piece comes from
# ══════════════════════════════════════════════════════════════════════════
def make_dataflow_diagram():
    fig, ax = plt.subplots(figsize=(12, 5.5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.5, 12)
    ax.set_ylim(-0.5, 5.5)
    ax.axis("off")

    ax.text(6, 5.1, "Data Flow: From Layout JSON to LLM Context",
            ha="center", fontsize=14, color=WHITE, fontweight="bold")

    # Stage boxes
    stages = [
        (0.5, 3.0, 2.5, 1.6, "Layout JSON\n\nrooms[]\ndoors[]\nfurniture[]\nmep[]", BLUE),
        (4.0, 3.0, 2.5, 1.6, "build_graph_\nfrom_layout()\n\nnodes + edges\ncontained_in\nadjacent, near", GREEN),
        (7.5, 3.0, 2.5, 1.6, "enrich_graph_\nfrom_analysis()\n\n+ clearance_ok\n+ move_direction\n+ blocks edge", PURPLE),
        (7.5, 0.5, 2.5, 1.6, "serialize_\nfor_llm()\n\nROOMS:\nFURNITURE:\nISSUES:", ORANGE),
        (4.0, 0.5, 2.5, 1.6, "LLM Context\n\n\"Toilet: move\n[+0.5,+0.0]\n0.4m to fix\nclearance\"", RED),
    ]
    for bx, by, bw, bh, label, color in stages:
        rect = FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0.1",
                               facecolor=color + "22", edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        ax.text(bx + bw/2, by + bh/2, label, ha="center", va="center",
                fontsize=7.5, color=WHITE, family="monospace")

    # Analysis tools feeding enrich
    tool_y = 3.2
    for i, (name, color) in enumerate([
        ("collision.py", RED), ("visibility.py", PURPLE),
        ("reachability.py", TEAL), ("orientation.py", YELLOW),
    ]):
        tx = 10.5
        ty = tool_y + i * 0.35
        ax.text(tx, ty, name, fontsize=7, color=color, ha="left", va="center")
        ax.annotate("", xy=(10.0, 3.8), xytext=(tx - 0.05, ty),
                    arrowprops=dict(arrowstyle="-|>", color=color, lw=1, alpha=0.6))

    # Flow arrows
    arrow_kw = dict(arrowstyle="-|>", color=WHITE, lw=2, mutation_scale=15)
    ax.annotate("", xy=(4.0, 3.8), xytext=(3.0, 3.8), arrowprops=arrow_kw)
    ax.annotate("", xy=(7.5, 3.8), xytext=(6.5, 3.8), arrowprops=arrow_kw)
    ax.annotate("", xy=(8.75, 2.1), xytext=(8.75, 3.0), arrowprops=arrow_kw)
    ax.annotate("", xy=(6.5, 1.3), xytext=(7.5, 1.3), arrowprops=arrow_kw)

    plt.tight_layout()
    out = DIAGRAMS_DIR / "02_dataflow.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 3: Real spatial graph from industrial_005 layout
# ══════════════════════════════════════════════════════════════════════════
def make_graph_visualization(layout_name="industrial_005"):
    layout_path = None
    for f in LAYOUT_DIR.rglob("*.json"):
        if layout_name in f.stem and "backup" not in f.name:
            layout_path = f
            break
    if not layout_path:
        print(f"Layout {layout_name} not found, skipping graph diagram")
        return None

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    G = build_graph_from_layout(layout)

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    # Positions from geometry
    pos = {}
    for nid, data in G.nodes(data=True):
        center = data.get("center")
        if center and center[0] is not None:
            pos[nid] = (center[0], center[1])
    missing = [n for n in G.nodes() if n not in pos]
    if missing:
        spring = nx.spring_layout(G, pos=pos if pos else None,
                                   fixed=list(pos.keys()) if pos else None,
                                   k=2.5, seed=42)
        for n in missing:
            pos[n] = spring[n]

    # Draw edges
    for etype, color in EDGE_COLORS.items():
        edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == etype]
        if edges:
            style = EDGE_STYLES.get(etype, "solid")
            width = 2.5 if etype in ("adjacent", "blocks") else 1.5
            alpha = 0.9 if etype in ("adjacent", "blocks") else 0.5
            nx.draw_networkx_edges(G, pos, edgelist=edges, edge_color=color,
                                   style=style, width=width, alpha=alpha, ax=ax)

    # Draw nodes
    for ntype, color in NODE_COLORS.items():
        nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == ntype]
        if nodes:
            size = NODE_SIZES.get(ntype, 500)
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_color=color,
                                   node_size=size, alpha=0.9, ax=ax,
                                   edgecolors="#333", linewidths=1.5)

    # Labels
    labels = {}
    for nid, data in G.nodes(data=True):
        name = data.get("name", nid)
        labels[nid] = name[:14] + ".." if len(name) > 16 else name
    nx.draw_networkx_labels(G, pos, labels, font_size=6.5, font_color=WHITE,
                            font_weight="bold", ax=ax)

    # Legend
    legend_elements = []
    for ntype, color in NODE_COLORS.items():
        count = sum(1 for _, d in G.nodes(data=True) if d.get("ntype") == ntype)
        if count:
            legend_elements.append(mpatches.Patch(color=color, label=f"{ntype} ({count})"))
    for etype, color in EDGE_COLORS.items():
        count = sum(1 for _, _, d in G.edges(data=True) if d.get("etype") == etype)
        if count:
            legend_elements.append(
                plt.Line2D([0], [0], color=color, linestyle=EDGE_STYLES.get(etype, "solid"),
                           linewidth=2, label=f"{etype} ({count})"))

    ax.legend(handles=legend_elements, loc="upper left", fontsize=8,
              facecolor=BG_LIGHT, edgecolor=ACCENT, labelcolor=WHITE)
    ax.set_title(f"Spatial Graph — {layout_path.stem}\n"
                 f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges",
                 fontsize=13, color=WHITE, pad=15)
    ax.axis("off")
    plt.tight_layout()
    out = DIAGRAMS_DIR / "03_graph_base.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 4: Enriched graph (with mock analysis)
# ══════════════════════════════════════════════════════════════════════════
def make_enriched_graph(layout_name="industrial_005"):
    layout_path = None
    for f in LAYOUT_DIR.rglob("*.json"):
        if layout_name in f.stem and "backup" not in f.name:
            layout_path = f
            break
    if not layout_path:
        return None

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    G = build_graph_from_layout(layout)

    furniture = [n for n, d in G.nodes(data=True) if d.get("ntype") == "furniture"]
    rooms = [n for n, d in G.nodes(data=True) if d.get("ntype") == "room"]

    if len(furniture) >= 2 and len(rooms) >= 2:
        f1, f2 = furniture[0], furniture[1]
        f1n = G.nodes[f1].get("name", f1)
        f2n = G.nodes[f2].get("name", f2)
        r1n = G.nodes[rooms[0]].get("name", rooms[0])
        r2n = G.nodes[rooms[1]].get("name", rooms[1])

        G = enrich_graph_from_analysis(G,
            collision_results={"objects": [
                {"id": f1, "clearance_violation": {"deficit_m": 0.3},
                 "use_point_analysis": {"move_suggestion": {"direction": [0.5, 0.0], "distance_m": 0.4}},
                 "functional_line_analysis": {"blocked": True, "blocking_object_id": f2}},
                {"id": f2, "clearance_violation": None},
            ]},
            visibility_results=[
                {"source": f1n, "target": f2n, "visible_seated": True, "visible_standing": True},
            ],
            path_results={"pairs": [
                {"source": r1n, "target": r2n, "distance": 12.5, "status": "reachable"},
            ]},
            reachability_results={"results": [
                {"object_id": f1, "reachable": False, "height_ok": False, "radius_ok": True},
                {"object_id": f2, "reachable": True, "height_ok": True, "radius_ok": True},
            ]},
            orientation_results={"results": [
                {"object_id": f1, "facing_ok": False, "angle_diff": 90.0},
                {"object_id": f2, "facing_ok": True, "angle_diff": 5.0},
            ]},
        )

    fig, ax = plt.subplots(figsize=(12, 8))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)

    pos = {}
    for nid, data in G.nodes(data=True):
        center = data.get("center")
        if center and center[0] is not None:
            pos[nid] = (center[0], center[1])
    missing = [n for n in G.nodes() if n not in pos]
    if missing:
        spring = nx.spring_layout(G, pos=pos if pos else None,
                                   fixed=list(pos.keys()) if pos else None, k=2.5, seed=42)
        for n in missing:
            pos[n] = spring[n]

    for etype, color in EDGE_COLORS.items():
        edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == etype]
        if edges:
            style = EDGE_STYLES.get(etype, "solid")
            width = 3.0 if etype in ("blocks", "sightline", "path") else 1.5
            alpha = 1.0 if etype in ("blocks", "sightline", "path") else 0.4
            nx.draw_networkx_edges(G, pos, edgelist=edges, edge_color=color,
                                   style=style, width=width, alpha=alpha, ax=ax)

    # Highlight nodes with issues
    for ntype, color in NODE_COLORS.items():
        nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == ntype]
        if nodes:
            issue_nodes = [n for n in nodes if
                          G.nodes[n].get("clearance_ok") is False or
                          G.nodes[n].get("reachable") is False or
                          G.nodes[n].get("facing_ok") is False]
            ok_nodes = [n for n in nodes if n not in issue_nodes]

            if ok_nodes:
                nx.draw_networkx_nodes(G, pos, nodelist=ok_nodes, node_color=color,
                                       node_size=NODE_SIZES.get(ntype, 500), alpha=0.9,
                                       ax=ax, edgecolors="#333", linewidths=1.5)
            if issue_nodes:
                nx.draw_networkx_nodes(G, pos, nodelist=issue_nodes, node_color=RED,
                                       node_size=NODE_SIZES.get(ntype, 500) + 200, alpha=0.95,
                                       ax=ax, edgecolors=YELLOW, linewidths=3)

    labels = {}
    for nid, data in G.nodes(data=True):
        name = data.get("name", nid)
        extras = []
        if data.get("clearance_ok") is False:
            extras.append("CLEARANCE!")
        if data.get("reachable") is False:
            extras.append("UNREACH!")
        if data.get("facing_ok") is False:
            extras.append("FACING!")
        label = name[:14] + ".." if len(name) > 16 else name
        if extras:
            label += "\n" + " ".join(extras)
        labels[nid] = label

    nx.draw_networkx_labels(G, pos, labels, font_size=6, font_color=WHITE,
                            font_weight="bold", ax=ax)

    legend_elements = [
        mpatches.Patch(color=RED, label="Issue node (violation)"),
        mpatches.Patch(color=GREEN, label="OK furniture"),
        mpatches.Patch(color=BLUE, label="Room"),
        plt.Line2D([0], [0], color=RED, lw=3, label="blocks"),
        plt.Line2D([0], [0], color=PURPLE, lw=2, linestyle="dashdot", label="sightline"),
        plt.Line2D([0], [0], color=TEAL, lw=2, linestyle="dashed", label="path"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=8,
              facecolor=BG_LIGHT, edgecolor=ACCENT, labelcolor=WHITE)
    ax.set_title(f"Enriched Spatial Graph — After Analysis\n"
                 f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges "
                 f"(+analysis edges & attributes)",
                 fontsize=13, color=WHITE, pad=15)
    ax.axis("off")
    plt.tight_layout()
    out = DIAGRAMS_DIR / "04_graph_enriched.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()

    # Also get the serialized text for the report
    return out, serialize_for_llm(G)


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 5: Node and edge type legend
# ══════════════════════════════════════════════════════════════════════════
def make_legend_diagram():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
    fig.patch.set_facecolor(BG)

    # Node types
    ax1.set_facecolor(BG)
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 6)
    ax1.axis("off")
    ax1.set_title("Node Types", fontsize=13, color=WHITE, fontweight="bold")

    node_info = [
        ("room", BLUE, "Rooms with area, centroid", "area, center, name"),
        ("door", ORANGE, "Doors connecting rooms", "width, connectsRooms"),
        ("furniture", GREEN, "Placed objects", "roomId, center, bbox"),
        ("mep", RED, "MEP elements", "system, roomId"),
    ]
    for i, (ntype, color, desc, attrs) in enumerate(node_info):
        y = 5 - i * 1.3
        ax1.add_patch(plt.Circle((1.5, y), 0.35, color=color, ec="#333", lw=2))
        ax1.text(1.5, y, ntype, ha="center", va="center", fontsize=8,
                 color="white", fontweight="bold")
        ax1.text(2.5, y + 0.15, desc, fontsize=9, color=WHITE, va="center")
        ax1.text(2.5, y - 0.25, f"attrs: {attrs}", fontsize=7, color=GRAY,
                 va="center", style="italic")

    # Edge types
    ax2.set_facecolor(BG)
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 9)
    ax2.axis("off")
    ax2.set_title("Edge Types", fontsize=13, color=WHITE, fontweight="bold")

    edge_info = [
        ("contained_in", GRAY, "dotted", "Furniture/MEP belongs to room", "structural"),
        ("door_connects", ORANGE, "solid", "Door links to room", "structural"),
        ("adjacent", BLUE, "solid", "Rooms share a door", "structural"),
        ("near", GREEN, "dashed", "Furniture within 3m (same room)", "structural"),
        ("blocks", RED, "solid", "Object blocks functional line", "analysis"),
        ("sightline", PURPLE, "dashdot", "Line-of-sight check", "analysis"),
        ("path", TEAL, "dashed", "Navigable path between points", "analysis"),
    ]
    for i, (etype, color, style, desc, source) in enumerate(edge_info):
        y = 8 - i * 1.1
        ax2.plot([0.5, 2.0], [y, y], color=color, linestyle=style, linewidth=3)
        ax2.text(2.3, y + 0.15, f"{etype}", fontsize=9, color=WHITE, va="center",
                 fontweight="bold")
        ax2.text(2.3, y - 0.25, f"{desc} [{source}]", fontsize=7, color=GRAY,
                 va="center", style="italic")

    plt.tight_layout()
    out = DIAGRAMS_DIR / "05_legend.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM 6: Lifecycle / persistence
# ══════════════════════════════════════════════════════════════════════════
def make_lifecycle_diagram():
    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(-0.5, 11)
    ax.set_ylim(-0.5, 5)
    ax.axis("off")

    ax.text(5.25, 4.6, "Graph Lifecycle During Agent Session",
            ha="center", fontsize=14, color=WHITE, fontweight="bold")

    steps = [
        (0.3, 2.5, 2.0, 1.2, "1. INIT\n\nbuild_graph_\nfrom_layout()\n\nBase nodes\n+ edges", BLUE),
        (2.8, 2.5, 2.0, 1.2, "2. REASON\n\nserialize_\nfor_llm()\n\nLLM reads\ngraph text", GREEN),
        (5.3, 2.5, 2.0, 1.2, "3. PLACE\n\nrebuild from\nnew layout\n\nStale edges\nremoved", ORANGE),
        (7.8, 2.5, 2.0, 1.2, "4. ENRICH\n\nenrich_graph_\nfrom_analysis()\n\n+ issues\n+ relations", PURPLE),
    ]

    for bx, by, bw, bh, label, color in steps:
        rect = FancyBboxPatch((bx, by), bw, bh, boxstyle="round,pad=0.1",
                               facecolor=color + "22", edgecolor=color, linewidth=2)
        ax.add_patch(rect)
        ax.text(bx + bw/2, by + bh/2, label, ha="center", va="center",
                fontsize=7.5, color=WHITE, family="monospace")

    arrow_kw = dict(arrowstyle="-|>", color=WHITE, lw=2, mutation_scale=15)
    ax.annotate("", xy=(2.8, 3.1), xytext=(2.3, 3.1), arrowprops=arrow_kw)
    ax.annotate("", xy=(5.3, 3.1), xytext=(4.8, 3.1), arrowprops=arrow_kw)
    ax.annotate("", xy=(7.8, 3.1), xytext=(7.3, 3.1), arrowprops=arrow_kw)

    # Loop back arrow
    ax.annotate("", xy=(3.8, 4.0), xytext=(8.8, 4.0),
                arrowprops=dict(arrowstyle="-|>", color=YELLOW, lw=2,
                                connectionstyle="arc3,rad=0.3"))
    ax.text(6.3, 4.4, "loop until approved", fontsize=8, color=YELLOW,
            ha="center", style="italic")

    # Persistence note
    rect = FancyBboxPatch((0.3, 0.3), 9.5, 1.2, boxstyle="round,pad=0.1",
                           facecolor=BG_LIGHT, edgecolor=ACCENT, linewidth=1, linestyle="--")
    ax.add_patch(rect)
    ax.text(5.05, 1.15, "Storage:", fontsize=9, color=WHITE, ha="center", fontweight="bold")
    ax.text(5.05, 0.75, "RAM only (AgentState dict) — rebuilt each iteration, never saved to disk",
            fontsize=8, color=GRAY, ha="center")
    ax.text(5.05, 0.45, "Layout JSON saved to session_active.json | Graph is ephemeral computation",
            fontsize=8, color=GRAY, ha="center")

    plt.tight_layout()
    out = DIAGRAMS_DIR / "06_lifecycle.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# PDF GENERATION
# ══════════════════════════════════════════════════════════════════════════
def build_pdf(diagram_paths, serialized_text):
    from fpdf import FPDF

    def _sanitize(text):
        """Replace unicode chars that latin-1 core fonts can't encode."""
        return (text
                .replace("\u2014", "-")   # em-dash
                .replace("\u2013", "-")   # en-dash
                .replace("\u2018", "'").replace("\u2019", "'")
                .replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2022", "-")   # bullet
                .replace("\u2192", "->").replace("\u2190", "<-")
                .replace("\u2194", "<->"))

    class PDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 8, "Spatial Relationship Graph - Technical Report", align="C")
                self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f"Team 03 - AIA26 Studio | Page {self.page_no()}/{{nb}}", align="C")

        def section_title(self, num, title):
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(83, 168, 226)
            self.cell(0, 10, _sanitize(f"{num}. {title}"), new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(83, 168, 226)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)

        def body_text(self, text):
            self.set_font("Helvetica", "", 10)
            self.set_text_color(50, 50, 50)
            self.multi_cell(0, 5.5, _sanitize(text))
            self.ln(2)

        def code_block(self, text):
            self.set_font("Courier", "", 8)
            self.set_fill_color(240, 240, 245)
            self.set_text_color(30, 30, 30)
            x = self.get_x()
            w = self.w - 2 * self.l_margin
            self.multi_cell(w, 4.2, _sanitize(text), fill=True)
            self.ln(3)

        def bullet(self, text, indent=10):
            self.set_font("Helvetica", "", 10)
            self.set_text_color(50, 50, 50)
            x = self.get_x()
            self.set_x(x + indent)
            self.cell(5, 5.5, "-")
            self.multi_cell(self.w - 2 * self.l_margin - indent - 5, 5.5, _sanitize(text))

    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Cover page ──
    pdf.add_page()
    pdf.ln(50)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 15, "Spatial Relationship Graph", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "Technical Report", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_draw_color(83, 168, 226)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "AIA26 Studio - Team 03", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Accessibility Agent - Spatial Flow Copilot", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%B %d, %Y')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, "Module: spatial_graph.py", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Integration: graph.py, reason.py, add_objects.py", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Section 1: Overview ──
    pdf.add_page()
    pdf.section_title("1", "Overview")
    pdf.body_text(
        "The Spatial Relationship Graph (internally called 'Graph B') is a NetworkX MultiGraph "
        "that encodes topological relationships between architectural elements in a floor plan layout. "
        "It was developed to address a core limitation identified during the studio review: the agent "
        "was placing objects without any structured spatial understanding — essentially guessing "
        "positions rather than reasoning about the space.\n\n"
        "The graph provides the LLM with a compact, structured representation of:\n"
    )
    pdf.bullet("Room connectivity (which rooms connect through which doors)")
    pdf.bullet("Object containment (which furniture belongs to which room)")
    pdf.bullet("Proximity relationships (which objects are near each other)")
    pdf.bullet("Analysis results (clearance violations, visibility, reachability)")
    pdf.bullet("Actionable issues with specific move vectors and deficit distances")
    pdf.ln(3)
    pdf.body_text(
        "Instead of the LLM receiving raw JSON coordinates and trying to infer spatial relationships, "
        "it now receives a pre-computed graph with explicit relationships and actionable directives "
        "like 'move [+0.9, +0.4] 0.4m to fix clearance (has 0.6m, needs 0.9m)'."
    )

    # ── Section 1b: Before vs After comparison ──
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(232, 69, 69)
    pdf.cell(0, 8, "Why does this matter?", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 7, "BEFORE (without graph) - the LLM received raw JSON:", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        '{"rooms": [{"id": "room-1", "name": "Workshop",\n'
        '  "geometry": [[0,0],[20,0],[20,10],[0,10],[0,0]]}],\n'
        ' "furniture": [{"id": "furn-1", "name": "cnc_machine",\n'
        '  "geometry": [[2,2],[4,2],[4,4],[2,4],[2,2]]}]}\n\n'
        'Tool result: {"objects": [{"id": "furn-1",\n'
        '  "clearance_violation": {"deficit_m": 0.3,\n'
        '  "min_clearance_m": 0.6, "required_m": 0.9,\n'
        '  "blocked_cells": 10, "warning_cells": 5}}]}...'
    )
    pdf.body_text(
        "The LLM had to: (1) parse coordinate arrays, (2) mentally compute room boundaries, "
        "(3) calculate distances between objects, (4) infer which way to move, "
        "(5) guess how far to move. Often it repositioned randomly or repeated the same mistake."
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 7, "AFTER (with graph) - the LLM receives structured context:", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "FURNITURE in Workshop:\n"
        '  furn-1 "cnc_machine" at(2.3,2.6) clearance=FAIL(-0.3m)\n'
        "RELATIONS:\n"
        "  cnc_machine --near(1.2m)--> workbench\n"
        "  storage_rack --blocks--> cnc_machine\n"
        "ISSUES:\n"
        "  cnc_machine: move [+0.9,+0.4] 0.4m to fix clearance (has 0.6m, needs 0.9m)"
    )
    pdf.body_text(
        "The LLM reads: 'cnc_machine is at (2.3, 2.6), needs 0.3m more clearance, "
        "move it +0.9 in X and +0.4 in Y'. It calculates: x=2.3+0.9=3.2, y=2.6+0.4=3.0. Done."
    )

    pdf.ln(2)
    # Comparison table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(42, 42, 60)
    pdf.set_text_color(255, 255, 255)
    col_w = [75, 55, 60]
    headers = ["Question the LLM needs to answer", "Without graph", "With graph"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(50, 50, 50)
    rows = [
        ("Which rooms are connected?", "Parse connectsRooms\nfrom JSON", "Workshop <--door-2\n(0.9m)--> Office"),
        ("What objects are nearby?", "Calculate distances\nmentally", "desk --near(0.8m)-->\noffice_chair"),
        ("Is there a problem?", "Parse collision_results\nJSON blob", "clearance=FAIL(-0.3m)"),
        ("How to fix it?", "Guess", "move [+0.9,+0.4] 0.4m"),
        ("Does object A block B?", "Cannot determine", "rack --blocks--> cnc"),
        ("Auto-correct after failure?", "No, waits for user", "Yes, up to 3 attempts\nwith correction msg"),
    ]
    for label, before, after in rows:
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        pdf.set_font("Helvetica", "B", 8)
        pdf.multi_cell(col_w[0], 6, label, border=1)
        y_after_label = pdf.get_y()

        pdf.set_xy(x_start + col_w[0], y_start)
        pdf.set_font("Helvetica", "", 8)
        pdf.multi_cell(col_w[1], 6, before, border=1)
        y_after_before = pdf.get_y()

        pdf.set_xy(x_start + col_w[0] + col_w[1], y_start)
        pdf.multi_cell(col_w[2], 6, after, border=1)
        y_after_after = pdf.get_y()

        pdf.set_y(max(y_after_label, y_after_before, y_after_after))

    pdf.ln(3)
    pdf.body_text(
        "The graph does not add new information - it reorganizes what already existed "
        "(layout JSON + analysis results) into a format the LLM can act on directly, "
        "instead of interpret."
    )

    # ── Section 2: Architecture ──
    pdf.add_page()
    pdf.section_title("2", "Architecture Integration")
    pdf.body_text(
        "The spatial graph integrates into the existing LangGraph agent workflow (Graph A) as data "
        "flowing through the AgentState. It does not modify the workflow structure — it adds two new "
        "state fields and one new node.\n\n"
        "New state fields in AgentState:\n"
    )
    pdf.bullet("spatial_graph: dict — the full NetworkX graph as a JSON-serializable dictionary")
    pdf.bullet("spatial_graph_text: str — compact text serialization for LLM context injection")
    pdf.ln(3)
    pdf.body_text("New node in the pipeline: enrich_graph - runs after all analysis tools, "
                  "before the routing decision. Reads analysis results and adds them as graph "
                  "attributes and edges.")
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(232, 69, 69)
    pdf.cell(0, 7, "Auto-correction loop", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "When analysis detects violations after a placement (clearance failures, unreachable "
        "objects, blocked paths), the graph automatically loops back to the LLM with a "
        "CORRECTION MESSAGE injected into the conversation history. This message contains:\n"
    )
    pdf.bullet("The specific issues found (CLEARANCE VIOLATION, UNREACHABLE, WRONG FACING, BLOCKS)")
    pdf.bullet("Exact move vectors from the analysis tools (e.g. 'move [+0.50, +0.00] by 0.4m')")
    pdf.bullet("Instructions to call place_object with corrected coordinates")
    pdf.ln(2)
    pdf.body_text(
        "The LLM receives this as a user message and responds by repositioning the problematic "
        "objects. The loop runs up to 3 times (MAX_ADJUSTMENTS). Two routing points trigger it:\n"
    )
    pdf.bullet("After Group 1 (collision): hard collision violations -> reason + correction")
    pdf.bullet("After enrich_graph: >30% paths unreachable or <70% objects reachable -> reason + correction")
    pdf.ln(2)
    pdf.body_text(
        "Example correction message the LLM receives:\n"
    )
    pdf.code_block(
        "AUTOMATIC CORRECTION (attempt 1/3)\n"
        "The analysis found 3 issue(s) that need fixing:\n\n"
        "- cnc_machine: CLEARANCE VIOLATION (deficit 0.3m). Fix: move [+0.50, +0.00] by 0.4m\n"
        "- cnc_machine: UNREACHABLE (height out of reach range)\n"
        "- cnc_machine BLOCKS the functional line of workbench. Move cnc_machine out of the way.\n\n"
        "Use the move vectors above to reposition objects.\n"
        "Call place_object with the corrected coordinates.\n"
        "Do NOT call analysis tools - they run automatically after placement."
    )

    if diagram_paths.get("architecture"):
        pdf.ln(3)
        pdf.image(str(diagram_paths["architecture"]), x=10, w=190)

    # ── Section 3: Data flow ──
    pdf.add_page()
    pdf.section_title("3", "Data Flow")
    pdf.body_text(
        "The graph is built and updated at three points during the agent's execution cycle:\n"
    )
    pdf.bullet("INIT: build_graph_from_layout() creates the base graph from the layout JSON "
               "with structural nodes and edges (rooms, doors, containment, adjacency, proximity).")
    pdf.bullet("PLACEMENT: After add_objects places furniture, the graph is rebuilt from scratch "
               "from the updated layout. Previous analysis edges are discarded since positions changed.")
    pdf.bullet("ENRICHMENT: After all 5 analysis tools run (collision, visibility, path, "
               "reachability, orientation), enrich_graph_from_analysis() adds analysis-derived "
               "attributes and edges to the graph.")
    pdf.ln(3)
    pdf.body_text("The spatial graph does NOT calculate anything itself — it is a translator that "
                  "reorganizes outputs from the analysis nodes into a structured, LLM-readable format.")

    if diagram_paths.get("dataflow"):
        pdf.ln(3)
        pdf.image(str(diagram_paths["dataflow"]), x=10, w=190)

    # ── Section 4: Node and edge types ──
    pdf.add_page()
    pdf.section_title("4", "Node and Edge Types")
    pdf.body_text(
        "The graph contains only actionable elements — rooms, doors, furniture, and MEP. "
        "Windows, structure, and outline are excluded as they don't participate in spatial "
        "reasoning decisions.\n\n"
        "Edges are divided into two categories:\n"
    )
    pdf.bullet("Structural edges: built from the layout JSON (contained_in, door_connects, "
               "adjacent, near). These represent the physical structure of the space.")
    pdf.bullet("Analysis edges: added by enrich_graph_from_analysis() after tools run "
               "(blocks, sightline, path). These represent computed spatial relationships.")

    if diagram_paths.get("legend"):
        pdf.ln(3)
        pdf.image(str(diagram_paths["legend"]), x=10, w=190)

    # ── Section 5: Graph visualization ──
    pdf.add_page()
    pdf.section_title("5", "Graph Visualization - Base Graph")
    pdf.body_text(
        "Below is the spatial graph built from the industrial_005 layout (2 rooms, 3 doors, "
        "14 furniture, 4 MEP). Node positions correspond to their real spatial coordinates "
        "from the layout geometry."
    )

    if diagram_paths.get("graph_base"):
        pdf.ln(2)
        pdf.image(str(diagram_paths["graph_base"]), x=5, w=200)

    # ── Section 6: Enriched graph ──
    pdf.add_page()
    pdf.section_title("6", "Enriched Graph - After Analysis")
    pdf.body_text(
        "After the 5 analysis tools run, enrich_graph_from_analysis() adds issue attributes "
        "to nodes and relationship edges between them. Nodes with violations are highlighted "
        "in red with yellow borders. New edge types appear: blocks (red), sightline (purple), "
        "path (teal)."
    )

    if diagram_paths.get("graph_enriched"):
        pdf.ln(2)
        pdf.image(str(diagram_paths["graph_enriched"]), x=5, w=200)

    # ── Section 7: Base vs Enriched comparison ──
    pdf.add_page()
    pdf.section_title("7", "Base Graph vs Enriched Graph")
    pdf.body_text(
        "Both are the same nx.MultiGraph object. The difference is where the data comes from. "
        "The base graph is built purely from the layout JSON (static geometry). The enriched "
        "graph is the same object with analysis results layered on top. "
        "enrich_graph_from_analysis() adds attributes and edges - it does not create a new graph."
    )

    pdf.ln(2)
    # Comparison table
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(42, 42, 60)
    pdf.set_text_color(255, 255, 255)
    col_w = [45, 70, 75]
    headers = ["", "Base Graph", "Enriched Graph"]
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(50, 50, 50)
    rows = [
        ("Data source", "Layout JSON only", "Layout JSON + 5 analysis tools"),
        ("When created", "At init + after each placement", "After analysis pipeline runs"),
        ("Node attributes", "name, area, center, roomId", "+ clearance_ok, deficit_m,\nreachable, facing_ok, angle_diff,\nmove_direction, move_distance_m"),
        ("Edge types", "contained_in, door_connects,\nadjacent, near", "+ blocks, sightline, path"),
        ("ISSUES section", "No", "Yes - with move vectors\nand deficit distances"),
        ("Purpose", "Structural understanding\nof the space", "Actionable evaluation\nwith fix directives"),
    ]
    for label, base, enriched in rows:
        pdf.set_font("Helvetica", "B", 8.5)
        h = 7 * max(base.count("\n"), enriched.count("\n"), 0) + 7
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        pdf.multi_cell(col_w[0], 7, label, border=1)
        y_after_label = pdf.get_y()
        pdf.set_xy(x_start + col_w[0], y_start)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(col_w[1], 7, base, border=1)
        y_after_base = pdf.get_y()
        pdf.set_xy(x_start + col_w[0] + col_w[1], y_start)
        pdf.multi_cell(col_w[2], 7, enriched, border=1)
        y_after_enriched = pdf.get_y()
        pdf.set_y(max(y_after_label, y_after_base, y_after_enriched))

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 7, "Base graph serialization (what the LLM sees before analysis):", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "FURNITURE in Workshop:\n"
        '  furn-1 "cnc_machine" at(5.0,3.0)           <-- position only, no evaluation\n'
        '  furn-2 "workbench" at(8.0,4.0)\n'
    )

    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 7, "Enriched graph serialization (what the LLM sees after analysis):", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "FURNITURE in Workshop:\n"
        '  furn-1 "cnc_machine" at(5.0,3.0) clearance=FAIL(-0.3m) reachable=NO facing=WRONG\n'
        '  furn-2 "workbench" at(8.0,4.0) clearance=OK reachable=YES facing=OK\n'
        "RELATIONS:\n"
        "  storage_rack --blocks--> cnc_machine        <-- new edge from collision.py\n"
        "  cnc_machine --sightline(visible)--> workbench  <-- new edge from visibility.py\n"
        "ISSUES:\n"
        "  cnc_machine: move [+0.5,+0.0] 0.4m to fix clearance\n"
        "  cnc_machine: unreachable (height)\n"
        "  cnc_machine: facing wrong (off by 90.0deg)"
    )

    pdf.body_text(
        "The key insight: the base graph gives the LLM structural context (what is where), "
        "while the enriched graph gives it actionable intelligence (what is wrong and how to fix it). "
        "Both are the same Python object at different points in the pipeline."
    )

    # ── Section 8: LLM serialization ──
    pdf.add_page()
    pdf.section_title("8", "LLM Serialization Output")
    pdf.body_text(
        "The serialize_for_llm() function converts the enriched graph into a compact text "
        "format (~30-50 lines) that is injected into the LLM's context. This is what the "
        "reasoning node actually sees — not raw JSON, but structured text with clear sections "
        "and an ISSUES block with actionable directives.\n\n"
        "Example output from industrial_005 with mock analysis:"
    )
    pdf.ln(2)
    if serialized_text:
        pdf.code_block(serialized_text)

    pdf.body_text(
        "The ISSUES section is the most important part — it tells the LLM exactly what is wrong "
        "and how to fix it, with specific move vectors and distances. This replaces the previous "
        "approach where the LLM had to parse verbose JSON tool outputs and guess corrections."
    )

    # ── Section 9: Lifecycle ──
    pdf.add_page()
    pdf.section_title("9", "Lifecycle and Persistence")
    pdf.body_text(
        "The spatial graph is ephemeral — it lives only in RAM as part of the LangGraph "
        "AgentState dictionary. It is never saved to disk. The lifecycle follows the agent's "
        "iteration loop:\n"
    )
    pdf.bullet("Created once at startup from the base layout")
    pdf.bullet("Rebuilt from scratch after each furniture placement (stale analysis edges removed)")
    pdf.bullet("Enriched after each analysis pipeline run")
    pdf.bullet("Read by the reason node before each LLM call")
    pdf.bullet("Discarded when the agent process exits")
    pdf.ln(3)
    pdf.body_text(
        "Only the layout JSON is persisted to disk (session_active.json during the session, "
        "timestamped output file on approval). The graph can always be reconstructed from "
        "the layout + analysis results, so persistence is unnecessary."
    )

    if diagram_paths.get("lifecycle"):
        pdf.ln(3)
        pdf.image(str(diagram_paths["lifecycle"]), x=10, w=190)

    # ── Section 9: Files modified ──
    pdf.add_page()
    pdf.section_title("10", "Files Modified")

    files = [
        ("spatial_graph.py (NEW)", "~300 lines",
         "Core module with 5 functions: build_graph_from_layout(), enrich_graph_from_analysis(), "
         "serialize_for_llm(), graph_to_dict(), dict_to_graph(). Plus geometry helpers."),
        ("graph.py", "~15 lines added",
         "Added spatial_graph and spatial_graph_text to AgentState. Added enrich_graph_node. "
         "Rewired pipeline: reachability -> enrich_graph -> scoring. Added graph construction "
         "to _build_initial_state()."),
        ("nodes/reason.py", "~10 lines added",
         "Added spatial graph section to SYSTEM_PROMPT. Added context injection of "
         "spatial_graph_text before LLM call."),
        ("nodes/add_objects.py", "~12 lines added",
         "Added graph rebuild after placement in both code paths (full layout return and "
         "summary-only return from MCP tool)."),
    ]

    for fname, size, desc in files:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(78, 204, 163)
        pdf.cell(0, 7, f"{fname}  ({size})", new_x="LMARGIN", new_y="NEXT")
        pdf.body_text(desc)
        pdf.ln(1)

    # ── Section 10: Next steps ──
    pdf.section_title("11", "Next Steps (Phase 2)")
    pdf.body_text(
        "The current implementation covers Phase 1: the Reality Graph — representing the current "
        "state of the layout. The professor's feedback identified a two-graph concept:\n"
    )
    pdf.bullet("Reality Graph (Phase 1 - DONE): What the layout looks like now. "
               "Built from layout JSON + analysis results.")
    pdf.bullet("Target Graph (Phase 2 - TODO): What the layout should look like. "
               "Represents the user's design intent and accessibility requirements.")
    pdf.bullet("Graph Comparison (Phase 2): Diff between target and reality to generate "
               "a prioritized action plan for the agent.")
    pdf.ln(3)
    pdf.body_text(
        "Phase 2 would allow the agent to work toward a goal state rather than just reacting "
        "to violations — shifting from reactive correction to proactive planning."
    )

    # ── Section 11: Testing & Demo Commands ──
    pdf.add_page()
    pdf.section_title("12", "Testing and Demo Commands")
    pdf.body_text(
        "All commands run from the team_03/python/ directory. "
        "The test script requires no external dependencies (no Rhino/Grasshopper). "
        "The full agent demo requires Rhino + Grasshopper with Swiftlet running."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(232, 69, 69)
    pdf.cell(0, 8, "IMPORTANT: Base layout vs Active session", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "There are two different sources of layout data, and this distinction is critical "
        "for understanding test results:\n"
    )
    pdf.bullet("layout/industrial_100/industrial_01.json - The BASE layout file. Read-only, never modified. "
               "Contains the original rooms and doors but NO furniture (0 furniture). "
               "This is what the test script reads by default.")
    pdf.bullet("workspace/session_active.json - The ACTIVE SESSION file. Updated every time the agent "
               "places or moves furniture. Contains the current state with all placed objects. "
               "This is what the agent works with.")
    pdf.ln(2)
    pdf.body_text(
        "When you run the agent and it places 5 pieces of furniture, those exist ONLY in "
        "session_active.json. The base layout remains untouched. To visualize the graph with "
        "the furniture the agent placed, you must use --session:"
    )
    pdf.code_block(
        "# Reads base layout (0 furniture) - will show only rooms and doors:\n"
        "python test_spatial_graph.py industrial_01\n\n"
        "# Reads active session (with placed furniture) - shows the full graph:\n"
        "python test_spatial_graph.py --session"
    )

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "Visualize the spatial graph (standalone, no Rhino needed)", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "cd team_03/python\n\n"
        "# From active session (furniture placed by agent):\n"
        "python test_spatial_graph.py --session\n\n"
        "# From a base layout (original, no furniture):\n"
        "python test_spatial_graph.py industrial_005\n"
        "python test_spatial_graph.py industrial_01\n"
        "python test_spatial_graph.py residential_01\n\n"
        "# All base layouts sequentially:\n"
        "python test_spatial_graph.py --all"
    )
    pdf.body_text(
        "This opens two matplotlib windows. The first shows the base graph "
        "(structural nodes and edges). Close it to see the second window with enriched "
        "graph (mock analysis data: clearance violations, sightlines, blocks). "
        "The terminal prints the LLM serialization text."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "Run the full agent (requires Rhino + Grasshopper + Swiftlet)", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "cd team_03/python\n\n"
        "# Layout without furniture (agent places objects):\n"
        'python main.py --layout industrial_01 "place a cnc machine and a workbench for wheelchair access"\n\n'
        "# Layout with furniture (agent analyzes existing):\n"
        'python main.py --layout industrial_005 "analyze this layout for wheelchair accessibility"'
    )
    pdf.body_text(
        "The spatial graph prints automatically at two key moments:\n"
    )
    pdf.bullet("[spatial_graph] at startup - shows the initial graph with rooms, doors, and any existing furniture")
    pdf.bullet("[enrich_graph] after analysis pipeline - shows the enriched graph with clearance violations, "
               "sightlines, path distances, reachability, and the ISSUES section with move vectors")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "Inspect the live workspace graph (while agent is running)", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "# In a second terminal, while the agent is running:\n"
        "cd team_03/python\n\n"
        "python -c \"\n"
        "import json\n"
        "from spatial_graph import build_graph_from_layout, serialize_for_llm\n"
        "layout = json.loads(open('../workspace/session_active.json').read())\n"
        "G = build_graph_from_layout(layout)\n"
        "print(serialize_for_llm(G))\n"
        "\""
    )
    pdf.body_text(
        "This reads the live session file and builds a fresh graph from it. "
        "Useful to check what the agent is working with at any point during the session."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "Expected terminal output during agent run", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "[spatial_graph] Initial graph: 8 nodes, 10 edges\n"
        "SPATIAL GRAPH (8 nodes, 10 edges)\n"
        "\n"
        "ROOMS:\n"
        '  room-1 "Workshop" area=140.0m2\n'
        '  room-2 "Office" area=30.0m2\n'
        "CONNECTIVITY:\n"
        "  Workshop <--door-2(0.9m)--> Office\n"
        "  ...\n"
        "\n"
        "Reasoning with LLM...\n"
        "Placing object: cnc_machine:2.0x1.5x1.2:x=5.0,y=3.0\n"
        "\n"
        "[enrich_graph] Spatial graph: 10 nodes, 15 edges\n"
        "SPATIAL GRAPH (10 nodes, 15 edges)\n"
        "\n"
        "FURNITURE in Workshop:\n"
        '  furn-1 "cnc_machine" at(5.0,3.0) clearance=OK reachable=YES\n'
        "ISSUES:\n"
        "  workbench: move [+0.3,+0.0] 0.2m to fix clearance"
    )

    # ── Save ──
    out_path = OUTPUT_DIR / "spatial_graph_report.pdf"
    pdf.output(str(out_path))
    return out_path


# ══════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating diagrams...")

    diagrams = {}
    diagrams["architecture"] = make_architecture_diagram()
    print("  [1/6] Architecture diagram")

    diagrams["dataflow"] = make_dataflow_diagram()
    print("  [2/6] Data flow diagram")

    diagrams["graph_base"] = make_graph_visualization()
    print("  [3/6] Base graph visualization")

    result = make_enriched_graph()
    serialized = ""
    if result:
        diagrams["graph_enriched"], serialized = result
        print("  [4/6] Enriched graph visualization")

    diagrams["legend"] = make_legend_diagram()
    print("  [5/6] Legend diagram")

    diagrams["lifecycle"] = make_lifecycle_diagram()
    print("  [6/6] Lifecycle diagram")

    print("\nBuilding PDF...")
    pdf_path = build_pdf(diagrams, serialized)
    print(f"\nDone! Report saved to:\n  {pdf_path}")
