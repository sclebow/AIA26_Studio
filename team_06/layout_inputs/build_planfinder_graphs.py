"""
Build planfinder_graphs.json from Planfinder_Dataset/pf_jsons/.

Run from repo root with venv active:
    .venv/Scripts/python.exe team_06/layout_inputs/build_planfinder_graphs.py
"""

import sys
from pathlib import Path

REPO_ROOT      = Path(__file__).resolve().parents[2]
PLANFINDER_DIR = Path(__file__).resolve().parent / "Planfinder_Dataset" / "pf_jsons"
OUTPUT_PATH    = Path(__file__).resolve().parent / "planfinder_graphs.json"

sys.path.insert(0, str(REPO_ROOT / "team_06" / "python"))
from utils.parser.schema_to_graph import generate_graphs_from_directory

if __name__ == "__main__":
    print(f"Building Planfinder graphs from {PLANFINDER_DIR.name}/")
    generate_graphs_from_directory(str(PLANFINDER_DIR), str(OUTPUT_PATH))
