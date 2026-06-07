"""
Generate a session report PDF documenting changes made to the spatial graph system.
Run from any directory — paths resolved relative to this script.

Usage:
    python generate_session_report.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import networkx as nx

# ── Paths ────────────────────────────────────────────────────────────────
SCRIPT_DIR  = Path(__file__).parent
PYTHON_DIR  = SCRIPT_DIR.parent.parent / "python"
LAYOUT_DIR  = SCRIPT_DIR.parent.parent / "layout"
OUTPUT_DIR  = SCRIPT_DIR
DIAGRAMS_DIR = SCRIPT_DIR / "_diagrams"
DIAGRAMS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(PYTHON_DIR))
from spatial_graph import build_graph_from_layout, serialize_for_llm

# ── Colors ───────────────────────────────────────────────────────────────
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
PINK     = "#e91e63"

NODE_COLORS = {
    "room": BLUE, "door": ORANGE, "wall": GRAY,
    "window": TEAL, "furniture": GREEN, "mep": RED,
}
NODE_SIZES = {
    "room": 1100, "door": 500, "wall": 400,
    "window": 350, "furniture": 700, "mep": 600,
}
EDGE_COLORS = {
    "contained_in": GRAY, "door_connects": ORANGE, "adjacent": BLUE,
    "near": GREEN, "near_wall": PINK, "near_window": TEAL,
    "blocks": RED, "sightline": PURPLE, "path": TEAL,
}
EDGE_STYLES = {
    "contained_in": "dotted", "door_connects": "solid", "adjacent": "solid",
    "near": "dashed", "near_wall": "dashdot", "near_window": "dashdot",
    "blocks": "solid", "sightline": "dashdot", "path": "dashed",
}


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM: Updated graph with walls + windows
# ══════════════════════════════════════════════════════════════════════════
def make_full_graph(layout_name="industrial_005"):
    layout_path = None
    for f in LAYOUT_DIR.rglob("*.json"):
        if layout_name in f.stem and "backup" not in f.name:
            layout_path = f
            break
    if not layout_path:
        print(f"Layout {layout_name} not found")
        return None, ""

    layout = json.loads(layout_path.read_text(encoding="utf-8"))
    G = build_graph_from_layout(layout)
    text = serialize_for_llm(G)

    fig, ax = plt.subplots(figsize=(14, 9))
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
        spring = nx.spring_layout(
            G, pos=pos if pos else None,
            fixed=list(pos.keys()) if pos else None,
            k=2.5, seed=42,
        )
        for n in missing:
            pos[n] = spring[n]

    # Draw edges by type
    for etype, color in EDGE_COLORS.items():
        edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == etype]
        if edges:
            style = EDGE_STYLES.get(etype, "solid")
            width = 2.5 if etype in ("adjacent", "near_wall", "near_window") else 1.2
            alpha = 0.8 if etype in ("near_wall", "near_window") else 0.5
            nx.draw_networkx_edges(
                G, pos, edgelist=edges, edge_color=color,
                style=style, width=width, alpha=alpha, ax=ax,
            )

    # Draw nodes by type
    for ntype, color in NODE_COLORS.items():
        nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == ntype]
        if nodes:
            size = NODE_SIZES.get(ntype, 500)
            nx.draw_networkx_nodes(
                G, pos, nodelist=nodes, node_color=color,
                node_size=size, alpha=0.9, ax=ax,
                edgecolors="#333", linewidths=1.5,
            )

    # Labels
    labels = {}
    for nid, data in G.nodes(data=True):
        name = data.get("name", nid)
        labels[nid] = name[:14] + ".." if len(name) > 16 else name
    nx.draw_networkx_labels(
        G, pos, labels, font_size=5.5, font_color=WHITE,
        font_weight="bold", ax=ax,
    )

    # Legend
    import matplotlib.patches as mpatches
    legend_elements = []
    for ntype, color in NODE_COLORS.items():
        count = sum(1 for _, d in G.nodes(data=True) if d.get("ntype") == ntype)
        if count:
            legend_elements.append(mpatches.Patch(color=color, label=f"{ntype} ({count})"))
    for etype, color in EDGE_COLORS.items():
        count = sum(1 for _, _, d in G.edges(data=True) if d.get("etype") == etype)
        if count:
            legend_elements.append(
                plt.Line2D([0], [0], color=color,
                           linestyle=EDGE_STYLES.get(etype, "solid"),
                           linewidth=2, label=f"{etype} ({count})"))

    ax.legend(
        handles=legend_elements, loc="upper left", fontsize=7,
        facecolor=BG_LIGHT, edgecolor=ACCENT, labelcolor=WHITE,
        ncol=2,
    )
    ax.set_title(
        f"Complete Spatial Graph — {layout_path.stem}\n"
        f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges "
        f"(rooms, doors, walls, windows, furniture, mep)",
        fontsize=12, color=WHITE, pad=15,
    )
    ax.axis("off")
    plt.tight_layout()
    out = DIAGRAMS_DIR / "session_graph_full.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()

    # Node/edge counts for the report
    counts = {}
    for ntype in NODE_COLORS:
        counts[f"n_{ntype}"] = sum(1 for _, d in G.nodes(data=True) if d.get("ntype") == ntype)
    for etype in EDGE_COLORS:
        counts[f"e_{etype}"] = sum(1 for _, _, d in G.edges(data=True) if d.get("etype") == etype)
    counts["total_nodes"] = G.number_of_nodes()
    counts["total_edges"] = G.number_of_edges()

    return out, text, counts


# ══════════════════════════════════════════════════════════════════════════
# DIAGRAM: Voronoi clearance concept
# ══════════════════════════════════════════════════════════════════════════
def make_voronoi_diagram():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    fig.patch.set_facecolor(BG)
    fig.suptitle(
        "Collision Clearance Fix: Voronoi Boundary Method",
        fontsize=14, color=WHITE, fontweight="bold", y=0.98,
    )

    for ax, title, subtitle in [
        (ax1, "BEFORE (wrong)", "min_clearance_m = distance from free cell to nearest obstacle"),
        (ax2, "AFTER (correct)", "min_clearance_m = actual gap between object surfaces"),
    ]:
        ax.set_facecolor(BG)
        ax.set_xlim(-0.5, 10.5)
        ax.set_ylim(-0.5, 7)
        ax.axis("off")
        ax.set_title(title, fontsize=12, color=WHITE if ax == ax2 else RED, fontweight="bold")
        ax.text(5, -0.2, subtitle, ha="center", fontsize=7.5, color=GRAY, style="italic")

    # ── Left panel: BEFORE ──
    # Wall
    ax1.add_patch(FancyBboxPatch((0, 0), 0.8, 6.5, boxstyle="round,pad=0.05",
                                  facecolor=GRAY + "66", edgecolor=GRAY, lw=2))
    ax1.text(0.4, 6.8, "WALL", ha="center", fontsize=8, color=GRAY, fontweight="bold")
    # Furniture
    ax1.add_patch(FancyBboxPatch((3, 2), 2, 2.5, boxstyle="round,pad=0.05",
                                  facecolor=GREEN + "44", edgecolor=GREEN, lw=2))
    ax1.text(4, 3.25, "FURNITURE", ha="center", fontsize=9, color=GREEN, fontweight="bold")
    # Adjacent cell markers
    for i in range(5):
        y = 1.5 + i * 0.5
        ax1.plot(2.7, y + 0.5, "x", color=RED, markersize=8, markeredgewidth=2)
    ax1.annotate("d=1 cell\n= 0.1m", xy=(2.7, 3.5), xytext=(5.5, 5.5),
                 fontsize=8, color=RED, fontweight="bold",
                 arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.5))
    ax1.text(5.5, 1, "Every object shows\nmin_clearance = 0.1m\n(always 1 cell)",
             fontsize=9, color=RED, ha="center",
             bbox=dict(boxstyle="round", facecolor=RED + "22", edgecolor=RED))

    # ── Right panel: AFTER ──
    # Wall
    ax2.add_patch(FancyBboxPatch((0, 0), 0.8, 6.5, boxstyle="round,pad=0.05",
                                  facecolor=GRAY + "66", edgecolor=GRAY, lw=2))
    ax2.text(0.4, 6.8, "WALL", ha="center", fontsize=8, color=GRAY, fontweight="bold")
    # Furniture
    ax2.add_patch(FancyBboxPatch((3, 2), 2, 2.5, boxstyle="round,pad=0.05",
                                  facecolor=GREEN + "44", edgecolor=GREEN, lw=2))
    ax2.text(4, 3.25, "FURNITURE", ha="center", fontsize=9, color=GREEN, fontweight="bold")
    # Voronoi boundary
    ax2.axvline(x=1.9, color=YELLOW, linestyle="--", linewidth=2, alpha=0.7)
    ax2.text(1.9, 6.8, "Voronoi\nboundary", ha="center", fontsize=7, color=YELLOW)
    # Real gap measurement
    ax2.annotate("", xy=(0.8, 1), xytext=(3.0, 1),
                 arrowprops=dict(arrowstyle="<->", color=BLUE, lw=2.5))
    ax2.text(1.9, 0.5, "real gap = 2.2m", ha="center", fontsize=10, color=BLUE, fontweight="bold")
    ax2.text(5.5, 1, "gap = dist(a) + dist(b)\nat Voronoi boundary\n= surface-to-surface",
             fontsize=9, color=GREEN, ha="center",
             bbox=dict(boxstyle="round", facecolor=GREEN + "22", edgecolor=GREEN))

    plt.tight_layout()
    out = DIAGRAMS_DIR / "session_voronoi.png"
    plt.savefig(out, dpi=180, facecolor=BG, bbox_inches="tight")
    plt.close()
    return out


# ══════════════════════════════════════════════════════════════════════════
# PDF GENERATION
# ══════════════════════════════════════════════════════════════════════════
def build_pdf(graph_img, voronoi_img, serialized_text, counts):
    from fpdf import FPDF

    def _s(text):
        return (text
                .replace("\u2014", "-").replace("\u2013", "-")
                .replace("\u2018", "'").replace("\u2019", "'")
                .replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2022", "-")
                .replace("\u2192", "->").replace("\u2190", "<-")
                .replace("\u2194", "<->"))

    class PDF(FPDF):
        def header(self):
            if self.page_no() > 1:
                self.set_font("Helvetica", "I", 8)
                self.set_text_color(150, 150, 150)
                self.cell(0, 8, "Session Report - 2026-05-22", align="C")
                self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f"Team 03 - AIA26 Studio | Page {self.page_no()}/{{nb}}", align="C")

        def section_title(self, num, title):
            self.set_font("Helvetica", "B", 14)
            self.set_text_color(83, 168, 226)
            self.cell(0, 10, _s(f"{num}. {title}"), new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(83, 168, 226)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)

        def body_text(self, text):
            self.set_font("Helvetica", "", 10)
            self.set_text_color(50, 50, 50)
            self.multi_cell(0, 5.5, _s(text))
            self.ln(2)

        def code_block(self, text):
            self.set_font("Courier", "", 8)
            self.set_fill_color(240, 240, 245)
            self.set_text_color(30, 30, 30)
            self.multi_cell(self.w - 2 * self.l_margin, 4.2, _s(text), fill=True)
            self.ln(3)

        def bullet(self, text, indent=10):
            self.set_font("Helvetica", "", 10)
            self.set_text_color(50, 50, 50)
            x = self.get_x()
            self.set_x(x + indent)
            self.cell(5, 5.5, "-")
            self.multi_cell(self.w - 2 * self.l_margin - indent - 5, 5.5, _s(text))

    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Cover ──
    pdf.add_page()
    pdf.ln(40)
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 15, "Session Report", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 16)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 10, "Spatial Graph, Collision & Interactive Visualizer", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    pdf.set_draw_color(83, 168, 226)
    pdf.line(60, pdf.get_y(), 150, pdf.get_y())
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 8, "AIA26 Studio - Team 03", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Industrial Spatial Flow Agent", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"Date: {datetime.now().strftime('%B %d, %Y')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(15)
    pdf.set_font("Helvetica", "I", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, "Files created: spatial_graph.py, test_spatial_graph.py, visualize_interactive.py", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Files modified: collision.py, graph.py, reason.py, prompts.py, add_objects.py", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "New directory: python/view_graph/ (HTML output + local vis.js)", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Docs: CLAUDE.md, session report PDF", align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Section 1: Summary ──
    pdf.add_page()
    pdf.section_title("1", "Session Summary")
    pdf.body_text(
        "The spatial graph layer was implemented and integrated into the LangGraph pipeline. "
        "Key changes:\n\n"
        "1. Created spatial_graph.py - a pure NetworkX module that builds a MultiGraph from "
        "layout JSON (rooms, doors, walls, windows, furniture, mep) with typed nodes and edges "
        "(contained_in, door_connects, adjacent, near, near_wall, near_window).\n\n"
        "2. Integrated the graph into the agent pipeline: AgentState fields, enrich_graph_node "
        "(runs after all 5 analysis tools), correction message injection for LLM auto-fix, "
        "graph rebuild after each placement.\n\n"
        "3. Fixed collision clearance (collision.py): Voronoi boundary method computes real "
        "surface-to-surface gaps instead of constant 0.1m.\n\n"
        "4. Added walls and windows as graph nodes with near_wall/near_window proximity edges. "
        "Walls filtered from FINDINGS (structural, not movable).\n\n"
        "5. Fixed clearance_ok to use deficit_m <= 0 instead of checking dict presence.\n\n"
        "6. Created test_spatial_graph.py standalone visualizer with edge descriptions in legend.\n\n"
        "7. Injected spatial_graph_text into LLM context (reason.py) and added SPATIAL GRAPH "
        "section to SYSTEM_PROMPT (prompts.py)."
    )

    # ── Section 2: Collision Fix ──
    pdf.add_page()
    pdf.section_title("2", "Collision Clearance Fix (Voronoi Boundary Method)")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(232, 69, 69)
    pdf.cell(0, 8, "The Problem", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "All 19 furniture/MEP objects in the test layout showed identical clearance values: "
        "'has 0.1m, needs 0.4m' with a deficit of -0.3m. This happened because min_clearance_m "
        "was computed inside the violation cell loop, tracking the minimum dist * cell_size "
        "for cells attributed to each object. Since dist measures BFS distance from any free "
        "cell to the nearest obstacle surface, and the cells immediately adjacent to any object "
        "always have dist=1 (= 0.1m at 0.10m grid resolution), every object bottomed out at 0.1m."
    )
    pdf.code_block(
        "BEFORE (all identical):\n"
        "  CLEARANCE  Toilet: has 0.1m, needs 0.4m -> move [...] 0.4m\n"
        "  CLEARANCE  Sink: has 0.1m, needs 0.4m -> move [...] 0.4m\n"
        "  CLEARANCE  Assembly Station 1: has 0.1m, needs 0.4m -> move [...] 0.4m\n"
        "  CLEARANCE  cnc_machine: has 0.1m, needs 0.4m -> move [...] 0.4m\n"
        "  ... (all 19 objects show 0.1m)"
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "The Solution", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "After the violation cell loop, a Voronoi boundary scan computes the real gap between "
        "each object and its nearest other obstacle (wall, furniture, or MEP). The algorithm:\n\n"
        "1. Iterate all free cells in the grid (dist > 0)\n"
        "2. For each free cell, check its 4-connected neighbors\n"
        "3. If a neighbor's nearest-obstacle attribution differs (nearest[cell] != nearest[neighbor]), "
        "we are at a Voronoi boundary between two obstacles\n"
        "4. The gap at that boundary = (dist[cell] + dist[neighbor]) * cell_size\n"
        "5. Track the minimum gap for each object across all its Voronoi boundaries\n\n"
        "This gives the actual surface-to-surface distance between the object and its "
        "nearest neighbor, not the per-cell distance to any obstacle."
    )
    pdf.code_block(
        "# Core of the Voronoi boundary scan:\n"
        "for idx in range(total):\n"
        "    d = dist[idx]\n"
        "    if d <= 0: continue\n"
        "    oi = nearest[idx]\n"
        "    for neighbor in 4_connected(idx):\n"
        "        dn = dist[neighbor]\n"
        "        oj = nearest[neighbor]\n"
        "        if oj != oi:  # Voronoi boundary!\n"
        "            gap = (d + dn) * cell_size\n"
        "            obj_real_clearance[oi] = min(gap, ...)\n"
        "            obj_real_clearance[oj] = min(gap, ...)"
    )
    pdf.code_block(
        "AFTER (differentiated per object):\n"
        "  CLEARANCE  Toilet: has 0.35m, needs 0.4m -> move [...] 0.15m\n"
        "  Assembly Station 1: clearance=OK (gap 1.2m > 0.4m required)\n"
        "  cnc_machine: has 0.28m, needs 0.4m -> move [...] 0.22m"
    )

    if voronoi_img:
        pdf.ln(2)
        pdf.image(str(voronoi_img), x=5, w=200)

    pdf.body_text(
        "\nNo changes were needed in the Grasshopper component. The GH script independently "
        "re-runs the grid analysis for visualization only. The Python side (collision.py) "
        "is the authoritative source for all clearance values consumed by the agent and spatial graph."
    )

    # ── Section 3: Walls & Windows ──
    pdf.add_page()
    pdf.section_title("3", "Walls and Windows in the Spatial Graph")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(232, 69, 69)
    pdf.cell(0, 8, "What was missing", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "The spatial graph previously included 4 element types: rooms, doors, furniture, and MEP. "
        "The layout JSON has 7 layers. Of the missing 3 (outline, structure, windows), structure "
        "and windows carry important spatial information:\n"
    )
    pdf.bullet("Structure (walls): 6 walls in the test layout (4 exterior load-bearing, 2 interior "
               "partitions). Essential for knowing if furniture is against a wall, which walls are "
               "structural vs. partition, and wall-proximity relationships.")
    pdf.bullet("Windows: 16 windows with type (awning/sliding/fixed) and roomId. Important for "
               "egress checks (NFPA 101), light/ventilation access, and blocking detection.")
    pdf.bullet("Outline was not added — the exterior boundary is already represented by the "
               "exterior walls in structure[].")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(78, 204, 163)
    pdf.cell(0, 8, "What was added", new_x="LMARGIN", new_y="NEXT")

    pdf.body_text("New node types:")
    pdf.code_block(
        "wall node:\n"
        "  ntype='wall', name, wall_type (load-bearing/partition),\n"
        "  material (concrete/drywall), length, p1, p2 (segment endpoints)\n\n"
        "window node:\n"
        "  ntype='window', name, window_type (awning/sliding/fixed),\n"
        "  roomId, width, p1, p2 (segment endpoints)\n"
        "  + contained_in edge to parent room"
    )

    pdf.body_text("New edge types:")
    pdf.code_block(
        "near_wall:\n"
        "  furniture -> wall, distance_m (point-to-segment), threshold 3m\n"
        "  Uses _point_to_segment_distance() for accurate projection\n\n"
        "near_window:\n"
        "  furniture -> window, same room only, same distance method"
    )

    pdf.body_text("New helper function:")
    pdf.code_block(
        "def _point_to_segment_distance(px, py, x1, y1, x2, y2):\n"
        "    # Orthogonal projection of point onto segment,\n"
        "    # clamped to endpoints. Returns shortest distance.\n"
        "    t = clamp(0, 1, dot(P-A, B-A) / |B-A|^2)\n"
        "    return dist(P, A + t*(B-A))"
    )

    pdf.body_text("Serialization changes:")
    pdf.bullet("STRUCTURE: section lists each wall with type and length")
    pdf.bullet("WINDOWS: compact format grouped by room with type counts")
    pdf.bullet("near_wall and near_window appear in RELATIONS")
    pdf.bullet("MAX_SERIALIZE_LINES increased from 50 to 80")

    # ── Section 4: Graph Visualization ──
    pdf.add_page()
    pdf.section_title("4", "Updated Graph Visualization")

    if counts:
        pdf.body_text(
            f"The updated graph from industrial_005 now has {counts['total_nodes']} nodes "
            f"and {counts['total_edges']} edges:\n"
        )
        pdf.code_block(
            f"Nodes: {counts.get('n_room', 0)} rooms, {counts.get('n_door', 0)} doors, "
            f"{counts.get('n_wall', 0)} walls, {counts.get('n_window', 0)} windows, "
            f"{counts.get('n_furniture', 0)} furniture, {counts.get('n_mep', 0)} mep\n\n"
            f"Edges: {counts.get('e_contained_in', 0)} contained_in, "
            f"{counts.get('e_door_connects', 0)} door_connects, "
            f"{counts.get('e_adjacent', 0)} adjacent, "
            f"{counts.get('e_near', 0)} near, "
            f"{counts.get('e_near_wall', 0)} near_wall, "
            f"{counts.get('e_near_window', 0)} near_window"
        )

    if graph_img:
        pdf.image(str(graph_img), x=5, w=200)

    # ── Section 5: LLM Serialization ──
    pdf.add_page()
    pdf.section_title("5", "Updated LLM Serialization")
    pdf.body_text(
        "The serialize_for_llm() output now includes STRUCTURE and WINDOWS sections. "
        "Below is the complete output from industrial_005 (base layout, no analysis enrichment):"
    )
    pdf.ln(2)
    if serialized_text:
        pdf.code_block(serialized_text)

    # ── Section 6: Pipeline Integration ──
    pdf.add_page()
    pdf.section_title("6", "Pipeline Integration (graph.py, reason.py, prompts.py, add_objects.py)")

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "graph.py - AgentState + enrich_graph_node", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "Two new fields added to AgentState: spatial_graph (dict, node-link format) and "
        "spatial_graph_text (str, compact LLM serialization). Both use _keep_last reducer "
        "for parallel branch safety.\n\n"
        "enrich_graph_node runs after reachability and before the group2 routing decision. It:\n"
        "1. Deserializes the graph from state\n"
        "2. Calls enrich_graph_from_analysis() with all 5 analysis results\n"
        "3. Prints ANSI-colored FINDINGS (red=clearance, yellow=unreachable/facing)\n"
        "4. Walls filtered from FINDINGS (_skip_ntypes = {'wall'})\n"
        "5. If findings + objects placed: builds correction message with exact move vectors\n"
        "6. Returns updated spatial_graph + spatial_graph_text\n\n"
        "Wiring: reachability -> enrich_graph -> _route_after_group2 -> {reason, scoring}"
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "reason.py - Context injection", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "spatial_graph_text is injected into the LLM context before each call, alongside "
        "space_config and profile_config. The LLM sees the full graph topology and any "
        "issues with exact move vectors."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "prompts.py - SPATIAL GRAPH section", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "Added a SPATIAL GRAPH section to SYSTEM_PROMPT instructing the LLM to check the "
        "ISSUES section for violations with exact move vectors, and to use move_object with "
        "those vectors instead of guessing new positions."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "add_objects.py - Graph rebuild after placement", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "After both the MCP path and the fallback manual path, the spatial graph is rebuilt "
        "from scratch (base edges only, no analysis enrichment). Previous analysis edges "
        "no longer apply when positions change. Wrapped in try/except so graph failure "
        "doesn't break the placement pipeline."
    )

    # ── Section 7: clearance_ok + wall filtering ──
    pdf.add_page()
    pdf.section_title("7", "clearance_ok Fix + Wall Filtering")
    pdf.body_text(
        "Two related fixes ensure walls don't pollute the FINDINGS output:\n\n"
        "1. clearance_ok evaluation: Previously set to False whenever a clearance_violation "
        "dict existed, regardless of deficit value. Fixed to check deficit_m <= 0."
    )
    pdf.code_block(
        "# BEFORE:\n"
        "if cv:\n"
        "    G.nodes[oid]['clearance_ok'] = False  # always False if cv exists\n\n"
        "# AFTER:\n"
        "if cv:\n"
        "    deficit = cv.get('deficit_m', 0)\n"
        "    G.nodes[oid]['clearance_ok'] = deficit <= 0  # OK if no real deficit"
    )
    pdf.body_text(
        "2. Wall filtering: After adding wall nodes to the graph, collision enrichment "
        "started setting clearance attributes on walls (because wall IDs now exist in G). "
        "Walls show 0.2m clearance (= wall thickness at Voronoi boundary), which is not "
        "actionable. Fixed with _skip_ntypes = {'wall'} in three locations:\n"
    )
    pdf.bullet("enrich_graph_from_analysis() in spatial_graph.py - skips collision enrichment for walls")
    pdf.bullet("enrich_graph_node FINDINGS loop in graph.py - excludes walls from terminal output")
    pdf.bullet("serialize_for_llm() ISSUES section - already filtered to furniture/mep only")

    # ── Section 8: Edge Descriptions ──
    pdf.section_title("8", "Edge Descriptions in Graph Visualization")
    pdf.body_text(
        "The test_spatial_graph.py legend now shows a short description for each edge type, "
        "making the visualization self-documenting:"
    )
    pdf.code_block(
        "EDGE_DESCRIPTIONS = {\n"
        "    'contained_in':  'element belongs to room',\n"
        "    'door_connects': 'door links to room',\n"
        "    'adjacent':      'rooms share a door',\n"
        "    'near':          'furniture < 3m apart',\n"
        "    'near_wall':     'furniture < 3m from wall',\n"
        "    'near_window':   'furniture < 3m from window',\n"
        "    'blocks':        'object blocks access to another',\n"
        "    'sightline':     'direct line of sight between objects',\n"
        "    'path':          'navigable route with distance',\n"
        "}"
    )
    pdf.body_text(
        "Legend format: 'edge_type (count) - description'. "
        "Example: 'near_wall (12) - furniture < 3m from wall'."
    )

    # ── Section 9: Interactive Graph Visualizer ──
    pdf.add_page()
    pdf.section_title("9", "Interactive Graph Visualizer (visualize_interactive.py)")

    pdf.body_text(
        "A complete rewrite of the graph visualizer using raw HTML + vis.js 9.1.2 (dropped pyvis). "
        "Apple-minimalist aesthetic with muted colors, glass-morphism panels, and fixed architectural "
        "node positions reflecting the actual floor plan layout."
    )

    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "Core Features", new_x="LMARGIN", new_y="NEXT")
    pdf.bullet("Architectural positions: nodes placed at real layout coordinates (flipped Y), "
               "physics disabled, fixed:true - no force-directed bouncing")
    pdf.bullet("Dark/Light theme toggle with localStorage persistence and CSS custom properties")
    pdf.bullet("Legend filtering: click to filter by type, shift-click for multi-select, "
               "non-matching elements fade to 8% opacity")
    pdf.bullet("Detail panel: click any node to open right-side panel with metadata, "
               "type description, and clickable connected neighbors")
    pdf.bullet("Drag snap-back: nodes draggable but spring back to original position on release "
               "(550ms ease-out cubic animation via requestAnimationFrame)")
    pdf.bullet("New element highlights: blue #007AFF border that fades after 4s, 'new' badge")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "Live Refresh System", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "The visualizer auto-refreshes when the pipeline regenerates the HTML file. "
        "A background HTTP server daemon (port 7477) with CORS headers serves the file. "
        "Two detection modes:\n\n"
        "1. HTTP smart detection: fetch() compares PAGE_TS millisecond timestamp embedded in HTML. "
        "Only reloads when the timestamp changes.\n\n"
        "2. Blind reload fallback: for file:// origins where fetch() is blocked by same-origin "
        "policy. Uses location.reload() with adaptive backoff (2-10s) via sessionStorage. "
        "Preserves viewport (zoom/pan) across reloads via network.moveTo()."
    )

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "Pipeline Integration", new_x="LMARGIN", new_y="NEXT")
    pdf.body_text(
        "The graph auto-updates at three pipeline points:\n\n"
        "1. Startup (_build_initial_state in graph.py): generates initial HTML from base layout\n\n"
        "2. After placement (add_objects.py): rebuilds graph, highlights new/moved furniture "
        "via viz_highlight_ids state field\n\n"
        "3. After enrichment (enrich_graph_node in graph.py): marks enrichment edges as new, "
        "merges carry-over highlights from viz_highlight_ids\n\n"
        "viz_highlight_ids is an Annotated[list[str] | None, _keep_last] field in AgentState "
        "that carries furniture IDs highlighted by add_objects into enrich_graph_node."
    )

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(83, 168, 226)
    pdf.cell(0, 8, "File Structure", new_x="LMARGIN", new_y="NEXT")
    pdf.code_block(
        "python/\n"
        "  visualize_interactive.py          # Main visualizer module (~1190 lines)\n"
        "  view_graph/\n"
        "    spatial_graph_interactive.html   # Generated HTML (auto-updated)\n"
        "    lib/vis-9.1.2/                   # Local vis.js 9.1.2\n"
        "    lib/bindings/                    # vis.js bindings\n"
        "    lib/tom-select/                  # Tom Select library"
    )

    # ── Section 10: Files changed ──
    pdf.add_page()
    pdf.section_title("10", "All Files Modified")

    files = [
        ("spatial_graph.py", "NEW - Spatial graph module",
         "Pure NetworkX module (~570 lines). build_graph_from_layout(), "
         "enrich_graph_from_analysis(), serialize_for_llm(), graph_to_dict(), "
         "dict_to_graph(). Point-to-segment distance for wall/window proximity. "
         "Walls skipped in collision enrichment. clearance_ok based on deficit_m <= 0."),
        ("test_spatial_graph.py", "NEW - Standalone visualizer",
         "Matplotlib dark theme, nodes colored by type, edges styled by type. "
         "Legend with edge descriptions. Modes: --session, layout name, --all."),
        ("graph.py", "Spatial graph integration",
         "AgentState: +2 fields (spatial_graph, spatial_graph_text). "
         "enrich_graph_node inline. _build_correction_message(). "
         "Rewired reachability -> enrich_graph -> group2 routing. "
         "Initial graph built at startup. Walls filtered from FINDINGS."),
        ("nodes/collision.py", "Voronoi boundary method",
         "Added ~35 lines after the violation cell loop. Scans Voronoi boundaries "
         "(adjacent free cells with different nearest-obstacle attribution). "
         "Real surface-to-surface gap. Overwrites min_clearance_m in obj_violation_data."),
        ("nodes/reason.py", "Context injection",
         "Injects spatial_graph_text into LLM context before each call."),
        ("prompts.py", "SYSTEM_PROMPT update",
         "Added SPATIAL GRAPH section instructing LLM to use move vectors from ISSUES."),
        ("nodes/add_objects.py", "Graph rebuild",
         "Rebuilds spatial graph after both MCP and fallback placement paths. "
         "Base edges only (no analysis enrichment). try/except for graceful degradation."),
        ("MASTER_CLAUDE_V2.md", "Documentation",
         "Updated architecture, spatial graph layer docs, component descriptions, "
         "changelog with all changes from this session."),
        ("visualize_interactive.py", "NEW - Interactive graph visualizer",
         "Apple-minimalist HTML + vis.js 9.1.2 (~1190 lines). Fixed architectural positions, "
         "dark/light toggle, legend filtering, detail panel, drag snap-back, live auto-refresh "
         "via HTTP server (port 7477) with smart change detection and adaptive backoff fallback. "
         "Output: view_graph/spatial_graph_interactive.html."),
        ("generate_session_report.py", "This report",
         "PDF report generator with diagrams and comprehensive change documentation."),
    ]

    for fname, change, desc in files:
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(78, 204, 163)
        pdf.cell(0, 7, _s(f"{fname}  --  {change}"), new_x="LMARGIN", new_y="NEXT")
        pdf.body_text(desc)
        pdf.ln(1)

    # ── Save ──
    out_path = OUTPUT_DIR / "session_report_2026-05-22.pdf"
    pdf.output(str(out_path))
    return out_path


# ══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Generating session report...")

    print("  [1/3] Full graph visualization")
    result = make_full_graph()
    graph_img, serialized, counts = (None, "", {})
    if result:
        graph_img, serialized, counts = result

    print("  [2/3] Voronoi concept diagram")
    voronoi_img = make_voronoi_diagram()

    print("  [3/3] Building PDF...")
    pdf_path = build_pdf(graph_img, voronoi_img, serialized, counts)
    print(f"\nDone! Report saved to:\n  {pdf_path}")
