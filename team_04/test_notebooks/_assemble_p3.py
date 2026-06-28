"""
Assemble test_urban_context_P3.ipynb from individual cell files.
Reading each .py file guarantees no string-escaping issues.
"""
import json
from pathlib import Path

BASE    = Path(r'c:\Users\tuemi\Downloads\Glabtools\IAAC Repo\bimsc26-datamgmt-session03\AIA26_Studio\team_04\test_notebooks')
P2_PATH = BASE / 'test_urban_context_P2.ipynb'  # use as kernel/metadata template
P3_PATH = BASE / 'test_urban_context_P3.ipynb'

# Load template notebook for metadata
with open(P2_PATH, encoding='utf-8') as f:
    template = json.load(f)


def code(src):
    return {"cell_type": "code", "execution_count": None,
            "metadata": {}, "outputs": [], "source": src}


def md(src):
    return {"cell_type": "markdown", "metadata": {}, "source": src}


def read_py(fname):
    return (BASE / fname).read_text(encoding='utf-8')


# ── Cell 0: title markdown ────────────────────────────────────────────────────
C0 = md("""\
# Urban Site Intelligence — Building Placement Reasoning

**P3 · Road-aligned urban fabric · 30 m × 40 m site · Three urban conditions**

The agent reads the surrounding road network, identifies the primary road and junction type,
then proposes a building typology and footprint with full architectural reasoning.

| Scene | Junction | Road widths | Proposed typology |
|-------|----------|-------------|-------------------|
| **1 — Crossroads Corner** | Crossroads (X) | 5 m alley + 12 m secondary + 20 m main | **H-Building** — longest wing to main road |
| **2 — T-Junction Terminal** | T-junction (T) | 5 m alley + 12 m secondary + 28 m boulevard | **Wide Slab** — long facade faces view axis |
| **3 — Y-Junction Complex** | Y/complex | 4 m path + 15 m secondary + 30 m diagonal | **L-Building** — wraps the corner |

> **Surrounding buildings** are generated road-aligned (plot by plot, following road direction)
> for a realistic urban fabric — no uniform grid.
""")


# ── Cell 1: path setup ────────────────────────────────────────────────────────
C1 = code("""\
import os, sys, math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')

_cwd  = Path(os.getcwd()).resolve()
_root = next(
    (p for p in [_cwd, _cwd.parent, _cwd.parent.parent] if (p / 'team_04').is_dir()), None
)
if _root is None:
    raise RuntimeError('Cannot find team_04/ from ' + str(_cwd))
for _p in [str(_root), str(_root.parent)]:
    if _p not in sys.path: sys.path.insert(0, _p)
print('Root:', _root)
""")


# ── Cell 2: imports ───────────────────────────────────────────────────────────
C2 = code("""\
import warnings, math
from collections import Counter
import numpy as np
import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D
from shapely.geometry import LineString, Point, Polygon as SlyPoly
from shapely.ops import unary_union

from team_04.agent.tools.osm_context import (
    fetch_context_or_fallback, build_street_graph, INTERESTING_SITES,
)
from team_04.agent.tools.road_context import analyze_roads
from team_04.agent.tools.site_model import build_site_model
from team_04.agent.tools.urban_analysis import (
    full_urban_analysis, compute_centrality, compute_urban_importance,
    classify_intersection_advanced, detect_intersections_from_roads,
    SITE_TYPE_LABELS,
)

plt.rcParams.update({
    'figure.facecolor': '#F0F0F0', 'axes.facecolor': '#EBEBEB',
    'font.family': 'sans-serif', 'font.size': 10,
    'figure.dpi': 130, 'savefig.dpi': 150, 'savefig.bbox': 'tight',
})
print('Imports OK')
""")


# ── Cell 3-8: from files ──────────────────────────────────────────────────────
C3 = code(read_py('_p3_c3_helpers.py'))
C4 = code(read_py('_p3_c4_placement.py'))
C5 = code(read_py('_p3_c5_scenes.py'))
C6 = code(read_py('_p3_c6_pipeline.py'))
C7 = code(read_py('_p3_c7_figure.py'))
C8 = code(read_py('_p3_c8_reasoning.py'))


# ── Assemble ──────────────────────────────────────────────────────────────────
nb = dict(template)
nb['cells'] = [C0, C1, C2, C3, C4, C5, C6, C7, C8]
nb['metadata']['title'] = 'test_urban_context_P3'

with open(P3_PATH, 'w', encoding='utf-8') as f:
    json.dump(nb, f, ensure_ascii=False, indent=1)

print(f'P3 written: {len(nb["cells"])} cells  →  {P3_PATH}')


# ── Syntax-check every code cell ─────────────────────────────────────────────
import ast
ok = True
for i, c in enumerate(nb['cells']):
    if c['cell_type'] != 'code': continue
    src = c['source'] if isinstance(c['source'], str) else ''.join(c['source'])
    try:
        ast.parse(src)
        print(f'  Cell {i}: syntax OK')
    except SyntaxError as e:
        print(f'  Cell {i}: SYNTAX ERROR line {e.lineno}: {e.msg}')
        ok = False
print('All cells clean.' if ok else 'Syntax errors found — see above.')
