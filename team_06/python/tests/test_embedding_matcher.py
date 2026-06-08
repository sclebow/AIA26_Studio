"""
Standalone test for embedding_matcher.py.
Tests naturalistic user prompts against:
  - RPLAN sample descriptions (6 layouts)
  - Planfinder descriptions (518 layouts, non-empty only)

Run from repo root:
  $env:TRANSFORMERS_OFFLINE=1; $env:HF_HUB_OFFLINE=1; $env:PYTHONIOENCODING="utf-8"
  .venv/Scripts/python.exe team_06/python/tests/test_embedding_matcher.py

To use a custom prompt instead of the built-in ones:
  .venv/Scripts/python.exe team_06/python/tests/test_embedding_matcher.py "your prompt here"
"""

import json
import sys
import logging
import os
from pathlib import Path

# Suppress all debug output from embedding_matcher and transformers
logging.disable(logging.CRITICAL)
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# --- Paths ---
REPO_ROOT   = Path(__file__).resolve().parents[3]
TEAM_ROOT   = REPO_ROOT / "team_06"
RPLAN_DESC  = TEAM_ROOT / "layout_inputs" / "sample_descriptions.json"
PF_DESC_DIR = TEAM_ROOT / "layout_inputs" / "Planfinder_Dataset" / "pf_descriptions"

sys.path.insert(0, str(TEAM_ROOT / "python"))

# Monkey-patch prints inside embedding_matcher before import
import builtins
_real_print = builtins.print
def _quiet_print(*args, **kwargs):
    msg = " ".join(str(a) for a in args)
    if msg.startswith("[embedding_matcher]") or msg.startswith("Loading embedding") or "Loading weights" in msg:
        return
    _real_print(*args, **kwargs)
builtins.print = _quiet_print

from tools.embedding_matcher import match_layouts

builtins.print = _real_print  # restore after import

# ---------------------------------------------------------------------------
# Test prompts — naturalistic, lifestyle-driven (not room-list style)
# ---------------------------------------------------------------------------
PROMPTS = [
    {
        "id": "P1",
        "label": "Couple + 2 kids + dog, WFH partner needs desk",
        "text": (
            "I live with my partner Jack and our two children (ages 6 and 9) and we have a dog. "
            "I commute to the office every day but Jack works from home most days so he really "
            "needs a proper desk. The kids share a room for now. We'd love an open kitchen so "
            "whoever is cooking can still keep an eye on the children playing."
        ),
    },
    {
        "id": "P2",
        "label": "Single professional, long days out, minimal cooking",
        "text": (
            "It's just me, I'm out at work all day and usually grab food on the way home. "
            "I don't really cook so the kitchen doesn't need to be big. I want a quiet bedroom "
            "well away from the street and enough space for a sofa and a TV."
        ),
    },
    {
        "id": "P3",
        "label": "Couple, one partner has mobility issues, accessible bathroom critical",
        "text": (
            "My partner and I are moving in together. My partner uses a wheelchair so an "
            "accessible bathroom is essential — no step in the shower. We'd like separate "
            "his-and-hers morning routines so two bathrooms would be ideal. We both work "
            "from home occasionally so a small dedicated workspace would help."
        ),
    },
    {
        "id": "P4",
        "label": "Young student, tight budget, just needs sleep + study",
        "text": (
            "I'm a student living alone for the first time. I need something affordable — "
            "a small studio or a compact one-bedroom is fine. The most important thing is "
            "a decent place to study and sleep. I eat out or cook simple things so a tiny "
            "kitchen is enough. Natural light in the bedroom would be a bonus."
        ),
    },
    {
        "id": "P5",
        "label": "Family with baby + elderly parent needs own room",
        "text": (
            "We're a family of three — me, my husband, and our baby. My mother-in-law "
            "will also be moving in with us as she's getting older and needs some support. "
            "She needs her own bedroom with privacy. We need at least three bedrooms total. "
            "A big living area is important for us because we spend a lot of time together "
            "as a family and often have guests over for dinner."
        ),
    },
]

# ---------------------------------------------------------------------------
# Load descriptions
# ---------------------------------------------------------------------------
def load_rplan() -> list[dict]:
    return json.loads(RPLAN_DESC.read_text(encoding="utf-8"))


def load_planfinder(skip_empty: bool = True) -> list[dict]:
    items = []
    for f in sorted(PF_DESC_DIR.glob("*.json")):
        data = json.loads(f.read_text(encoding="utf-8"))
        if skip_empty and data.get("description", "").strip().lower() == "empty":
            continue
        items.append({
            "layoutId":   data["layoutId"],
            "description": data["description"],
            "area":        None,
            "roomTypes":   data.get("rooms_summary", ""),
        })
    return items


# ---------------------------------------------------------------------------
# Pretty print helpers
# ---------------------------------------------------------------------------
SEP  = "=" * 80
SEP2 = "-" * 60

# Force UTF-8 output on Windows so box-drawing chars don't crash
import io, sys
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def fmt_match(m: dict, rank: int) -> str:
    short_desc = m["description"][:200].replace("\n", " ") + ("…" if len(m["description"]) > 200 else "")
    rooms = m.get("roomTypes", "")
    return (
        f"  #{rank}  {m['layoutId']}  (score: {m['score']:.3f})\n"
        f"       rooms: {rooms}\n"
        f"       desc:  {short_desc}\n"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_tests():
    print("\nLoading datasets…")
    rplan_descs = load_rplan()
    pf_descs    = load_planfinder()
    print(f"  RPLAN sample:  {len(rplan_descs)} layouts")
    print(f"  Planfinder:    {len(pf_descs)} layouts (non-empty)")

    for p in PROMPTS:
        print(f"\n{SEP}")
        print(f"[{p['id']}] {p['label']}")
        print(f"QUERY:\n  {p['text']}")
        print()

        # --- RPLAN ---
        print(f"── RPLAN sample ({len(rplan_descs)} layouts) " + "─" * 40)
        builtins.print = _quiet_print
        r_rplan = match_layouts(p["text"], rplan_descs, top_k=3, min_score=0.0)
        builtins.print = _real_print
        if r_rplan["count"] == 0:
            print("  (no matches above threshold)\n")
        else:
            for i, m in enumerate(r_rplan["matches"], 1):
                print(fmt_match(m, i))

        # --- Planfinder ---
        print(f"── Planfinder ({len(pf_descs)} layouts) " + "─" * 40)
        builtins.print = _quiet_print
        r_pf = match_layouts(p["text"], pf_descs, top_k=3, min_score=0.0)
        builtins.print = _real_print
        if r_pf["count"] == 0:
            print("  (no matches above threshold)\n")
        else:
            for i, m in enumerate(r_pf["matches"], 1):
                print(fmt_match(m, i))

    print(f"\n{SEP}")
    print("All prompts tested.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single custom prompt from command line
        custom = " ".join(sys.argv[1:])
        rplan_descs = load_rplan()
        pf_descs    = load_planfinder()
        print(f"\nLoaded: {len(rplan_descs)} RPLAN  |  {len(pf_descs)} Planfinder layouts")
        print(f"\n{SEP}")
        print(f"QUERY:\n  {custom}\n")
        builtins.print = _quiet_print
        r_rplan = match_layouts(custom, rplan_descs, top_k=3, min_score=0.0)
        r_pf    = match_layouts(custom, pf_descs,    top_k=3, min_score=0.0)
        builtins.print = _real_print
        print(f"── RPLAN sample ({len(rplan_descs)} layouts) " + "─" * 40)
        for i, m in enumerate(r_rplan["matches"], 1):
            print(fmt_match(m, i))
        print(f"── Planfinder ({len(pf_descs)} layouts) " + "─" * 40)
        for i, m in enumerate(r_pf["matches"], 1):
            print(fmt_match(m, i))
    else:
        run_tests()
