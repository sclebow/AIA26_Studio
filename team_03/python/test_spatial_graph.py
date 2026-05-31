"""
Test and visualize the spatial relationship graph.

Usage:
    python test_spatial_graph.py                          # uses industrial_005
    python test_spatial_graph.py industrial_03            # specify layout name
    python test_spatial_graph.py --session                # uses workspace/session_active.json
    python test_spatial_graph.py --all                    # test all layouts
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for CI; override below for display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import networkx as nx

# Add parent so spatial_graph imports work
sys.path.insert(0, str(Path(__file__).parent))

from spatial_graph import (
    build_graph_from_layout,
    enrich_graph_from_analysis,
    graph_to_dict,
    dict_to_graph,
    serialize_for_llm,
)

# Use interactive backend when running interactively
try:
    matplotlib.use("TkAgg")
except Exception:
    try:
        matplotlib.use("Qt5Agg")
    except Exception:
        pass  # fall back to Agg (no window, saves to file)

# ── Colors and styles per node/edge type ──────────────────────────────

NODE_COLORS = {
    "room":      "#4FC3F7",   # light blue
    "door":      "#FFB74D",   # orange
    "wall":      "#90A4AE",   # blue-gray
    "window":    "#4DD0E1",   # cyan
    "furniture": "#81C784",   # green
    "mep":       "#E57373",   # red
}

NODE_SIZES = {
    "room":      900,
    "door":      400,
    "wall":      350,
    "window":    300,
    "furniture": 600,
    "mep":       500,
}

EDGE_COLORS = {
    "contained_in":  "#BDBDBD",   # gray
    "door_connects": "#FFB74D",   # orange
    "adjacent":      "#42A5F5",   # blue
    "near":          "#A5D6A7",   # light green
    "near_wall":     "#F48FB1",   # pink
    "near_window":   "#4DD0E1",   # cyan
    "blocks":        "#E53935",   # red
    "sightline":     "#7E57C2",   # purple
    "path":          "#26A69A",   # teal
}

EDGE_STYLES = {
    "contained_in":  "dotted",
    "door_connects": "solid",
    "adjacent":      "solid",
    "near":          "dashed",
    "near_wall":     "dashdot",
    "near_window":   "dashdot",
    "blocks":        "solid",
    "sightline":     "dashdot",
    "path":          "dashed",
}

# Short descriptions for the legend
EDGE_DESCRIPTIONS = {
    "contained_in":  "element belongs to room",
    "door_connects": "door links to room",
    "adjacent":      "rooms share a door",
    "near":          "furniture < 3m apart",
    "near_wall":     "furniture < 3m from wall",
    "near_window":   "furniture < 3m from window",
    "blocks":        "object blocks access to another",
    "sightline":     "direct line of sight between objects",
    "path":          "navigable route with distance",
}


def find_layout(name: str) -> Path:
    """Find a layout JSON by name in the layout/ directory."""
    layout_dir = Path(__file__).parent.parent / "layout"
    for f in layout_dir.rglob("*.json"):
        if name in f.stem:
            return f
    raise FileNotFoundError(f"No layout matching '{name}' in {layout_dir}")


def visualize_graph(G: nx.MultiGraph, title: str = "Spatial Graph"):
    """Draw the spatial graph with matplotlib."""
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    fig.patch.set_facecolor("#1E1E1E")
    ax.set_facecolor("#1E1E1E")

    # Use spatial positions where available, spring layout as fallback
    pos = {}
    for nid, data in G.nodes(data=True):
        center = data.get("center")
        if center and center[0] is not None:
            pos[nid] = (center[0], center[1])

    # For nodes without position, use spring layout seeded with known positions
    missing = [n for n in G.nodes() if n not in pos]
    if missing:
        spring_pos = nx.spring_layout(G, pos=pos if pos else None,
                                       fixed=list(pos.keys()) if pos else None,
                                       k=2.0, seed=42)
        for n in missing:
            pos[n] = spring_pos[n]

    # ── Draw edges by type ──
    for etype, color in EDGE_COLORS.items():
        edges = [(u, v) for u, v, d in G.edges(data=True) if d.get("etype") == etype]
        if edges:
            style = EDGE_STYLES.get(etype, "solid")
            width = 2.5 if etype in ("adjacent", "blocks") else 1.5
            alpha = 0.9 if etype in ("adjacent", "blocks", "path") else 0.5
            nx.draw_networkx_edges(G, pos, edgelist=edges, edge_color=color,
                                   style=style, width=width, alpha=alpha, ax=ax)

    # ── Draw nodes by type ──
    for ntype, color in NODE_COLORS.items():
        nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == ntype]
        if nodes:
            size = NODE_SIZES.get(ntype, 500)
            nx.draw_networkx_nodes(G, pos, nodelist=nodes, node_color=color,
                                   node_size=size, alpha=0.9, ax=ax,
                                   edgecolors="#333333", linewidths=1.5)

    # ── Labels ──
    labels = {}
    for nid, data in G.nodes(data=True):
        name = data.get("name", nid)
        if len(name) > 15:
            name = name[:13] + ".."
        labels[nid] = name

    nx.draw_networkx_labels(G, pos, labels, font_size=7, font_color="white",
                            font_weight="bold", ax=ax)

    # ── Legend (with descriptions) ──
    legend_elements = []
    for ntype, color in NODE_COLORS.items():
        count = sum(1 for _, d in G.nodes(data=True) if d.get("ntype") == ntype)
        if count > 0:
            legend_elements.append(
                mpatches.Patch(color=color, label=f"{ntype} ({count})"))

    for etype, color in EDGE_COLORS.items():
        count = sum(1 for _, _, d in G.edges(data=True) if d.get("etype") == etype)
        if count > 0:
            desc = EDGE_DESCRIPTIONS.get(etype, "")
            label = f"{etype} ({count}) — {desc}" if desc else f"{etype} ({count})"
            legend_elements.append(
                plt.Line2D([0], [0], color=color,
                           linestyle=EDGE_STYLES.get(etype, "solid"),
                           linewidth=2, label=label))

    ax.legend(handles=legend_elements, loc="upper left", fontsize=7,
              facecolor="#2D2D2D", edgecolor="#555555", labelcolor="white")

    ax.set_title(title, fontsize=14, color="white", pad=15)
    ax.axis("off")
    plt.tight_layout()
    try:
        plt.show()
    except Exception:
        out = Path(__file__).parent / f"{title.replace(' ', '_')}.png"
        plt.savefig(out, dpi=100, facecolor="#1E1E1E")
        print(f"Saved to {out}")
    plt.close()


def test_one_layout(layout_name: str):
    """Load a layout, build graph, print serialization, and visualize."""
    path = find_layout(layout_name)
    print(f"\n{'='*60}")
    print(f"Layout: {path.name}")
    print(f"{'='*60}")

    with open(path, "r") as f:
        layout = json.load(f)

    print(f"  Rooms:     {len(layout.get('rooms', []))}")
    print(f"  Doors:     {len(layout.get('doors', []))}")
    print(f"  Walls:     {len(layout.get('structure', []))}")
    print(f"  Windows:   {len(layout.get('windows', []))}")
    print(f"  Furniture: {len(layout.get('furniture', []))}")
    print(f"  MEP:       {len(layout.get('mep', []))}")

    G = build_graph_from_layout(layout)
    print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    edge_types = {}
    for _, _, d in G.edges(data=True):
        et = d.get("etype", "unknown")
        edge_types[et] = edge_types.get(et, 0) + 1
    print(f"Edge types: {edge_types}")

    # Test serialization roundtrip
    d = graph_to_dict(G)
    G2 = dict_to_graph(d)
    assert G2.number_of_nodes() == G.number_of_nodes(), "Roundtrip failed: node count mismatch"
    assert G2.number_of_edges() == G.number_of_edges(), "Roundtrip failed: edge count mismatch"
    print("Serialization roundtrip: OK")

    text = serialize_for_llm(G)
    lines = text.split("\n")
    print(f"\nLLM serialization ({len(lines)} lines):")
    print("-" * 40)
    print(text)
    print("-" * 40)

    visualize_graph(G, title=f"Spatial Graph -- {path.stem}")

    return G


def test_enrichment(G: nx.MultiGraph):
    """Test enrich_graph_from_analysis with fake analysis data."""
    print(f"\n{'='*60}")
    print("Testing enrichment with mock analysis data")
    print(f"{'='*60}")

    furniture_nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == "furniture"]
    room_nodes = [n for n, d in G.nodes(data=True) if d.get("ntype") == "room"]

    if len(furniture_nodes) < 2:
        print("Not enough furniture nodes to test enrichment -- skipping")
        return

    f1, f2 = furniture_nodes[0], furniture_nodes[1]
    f1_name = G.nodes[f1].get("name", f1)
    f2_name = G.nodes[f2].get("name", f2)

    collision = {
        "objects": [
            {
                "id": f1,
                "clearance_violation": {"deficit_m": 0.3, "min_clearance_m": 0.6, "required_m": 0.9},
                "use_point_analysis": {
                    "move_suggestion": {"direction": [0.5, 0.0], "distance_m": 0.4}
                },
                "functional_line_analysis": {
                    "blocked": True,
                    "blocking_object_id": f2,
                },
            },
            {
                "id": f2,
                "clearance_violation": None,
            },
        ]
    }

    visibility = [
        {"source": f1_name, "target": f2_name, "visible_seated": True, "visible_standing": True},
    ]

    path_data = None
    if len(room_nodes) >= 2:
        r1_name = G.nodes[room_nodes[0]].get("name", room_nodes[0])
        r2_name = G.nodes[room_nodes[1]].get("name", room_nodes[1])
        path_data = {
            "pairs": [
                {"source": r1_name, "target": r2_name, "distance": 12.5, "status": "reachable"},
            ]
        }

    reachability = {
        "results": [
            {"object_id": f1, "reachable": False, "height_ok": False, "radius_ok": True},
            {"object_id": f2, "reachable": True, "height_ok": True, "radius_ok": True},
        ]
    }

    orientation = {
        "results": [
            {"object_id": f1, "facing_ok": False, "angle_diff": 90.0},
            {"object_id": f2, "facing_ok": True, "angle_diff": 5.0},
        ]
    }

    edges_before = G.number_of_edges()
    G = enrich_graph_from_analysis(G, collision, visibility, path_data, reachability, orientation)
    edges_after = G.number_of_edges()

    print(f"Edges before enrichment: {edges_before}")
    print(f"Edges after enrichment:  {edges_after} (+{edges_after - edges_before})")

    text = serialize_for_llm(G)
    lines = text.split("\n")
    print(f"\nEnriched LLM serialization ({len(lines)} lines):")
    print("-" * 40)
    print(text)
    print("-" * 40)

    visualize_graph(G, title="Enriched Spatial Graph (with mock analysis)")


def test_from_file(file_path: Path):
    """Load a layout directly from a file path, build graph, print, visualize."""
    print(f"\n{'='*60}")
    print(f"Layout: {file_path.name}")
    print(f"{'='*60}")

    with open(file_path, "r") as f:
        layout = json.load(f)

    print(f"  Rooms:     {len(layout.get('rooms', []))}")
    print(f"  Doors:     {len(layout.get('doors', []))}")
    print(f"  Walls:     {len(layout.get('structure', []))}")
    print(f"  Windows:   {len(layout.get('windows', []))}")
    print(f"  Furniture: {len(layout.get('furniture', []))}")
    print(f"  MEP:       {len(layout.get('mep', []))}")

    G = build_graph_from_layout(layout)
    print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    edge_types = {}
    for _, _, d in G.edges(data=True):
        et = d.get("etype", "unknown")
        edge_types[et] = edge_types.get(et, 0) + 1
    print(f"Edge types: {edge_types}")

    text = serialize_for_llm(G)
    lines = text.split("\n")
    print(f"\nLLM serialization ({len(lines)} lines):")
    print("-" * 40)
    print(text)
    print("-" * 40)

    visualize_graph(G, title=f"Spatial Graph -- {file_path.stem} (session)")
    return G


if __name__ == "__main__":
    args = sys.argv[1:]

    if "--session" in args:
        session_file = Path(__file__).parent.parent / "workspace" / "session_active.json"
        if not session_file.exists():
            print(f"No active session found at: {session_file}")
            print("Run the agent first, or use a layout name instead.")
            sys.exit(1)
        G = test_from_file(session_file)
        test_enrichment(G)
    elif "--all" in args:
        layout_dir = Path(__file__).parent.parent / "layout"
        for f in sorted(layout_dir.rglob("*.json")):
            if "backup" not in f.name:
                test_one_layout(f.stem)
    else:
        name = args[0] if args else "industrial_005"
        G = test_one_layout(name)
        test_enrichment(G)
