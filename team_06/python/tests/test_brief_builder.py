import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "team_06" / "python"))

import app  # noqa: E402


def test_build_brief_removes_graph_restatement_from_description():
    payload = json.dumps({
        "graph": {
            "programs": ["bed", "living"],
            "access_pairs": [],
            "adjacency_pairs": [],
            "not_adjacency_pairs": [],
        },
        "household": [],
        "description": "1 bedroom and 1 living room",
    })

    brief = app._build_brief(payload)

    assert brief is not None
    assert brief["rooms"]
    assert brief["description"] == ""
    assert brief["specifications"] == []


def test_build_brief_keeps_non_graph_facts_in_description_and_specifications():
    payload = json.dumps({
        "graph": {
            "programs": [],
            "access_pairs": [],
            "adjacency_pairs": [],
            "not_adjacency_pairs": [],
        },
        "household": [
            {"name": "", "relationship": "", "info": "35 years old"},
        ],
        "description": "works from home full time; has a cat",
    })

    brief = app._build_brief(payload)

    assert brief is not None
    assert brief["description"] == "works from home full time; has a cat; lives alone; 35 years old"
    assert brief["specifications"] == [
        "works from home full time",
        "has a cat",
        "lives alone",
        "35 years old",
    ]