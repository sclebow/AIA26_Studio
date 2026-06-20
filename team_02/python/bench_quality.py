"""
bench_quality.py — OLD→new quality comparison for the SMART tier (session 10).

We upgraded SMART from gemini-2.5-flash → gemini-3.5-flash (and the image model from
gemini-2.5-flash-image → gemini-3.1-flash-image). This harness proves the upgrade did
not regress the reasoning we actually read:

  1. Run one scripted layout session with BENCH_QUALITY=1 so every SMART node's REAL
     (system, user) prompt is captured (_runtime/llm.QUALITY_CAPTURE).
  2. Replay each sampled node's identical prompt through the OLD and NEW model, so the
     only variable is the model.
  3. Render the 3 room cases on the OLD image model; pair them against the NEW images
     produced by `imaging.benchmark` (google_<case>.png).
  4. Emit blind A/B pairs (quality-pairs.json) + a separate reveal map
     (quality-reveal.json) so a judge (Claude, rubric) can score without knowing which
     side is new.

Run (from team_02/python/, UTF-8): python bench_quality.py
Out: docs/week09/benchmark/quality-pairs.json, quality-reveal.json, old_*/qimg_* PNGs
"""
from __future__ import annotations
import os

os.environ["BENCH_QUALITY"] = "1"   # must be set BEFORE importing graph / llm

import base64
import json
import random
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

_PY = Path(__file__).resolve().parent          # team_02/python
_TEAM = _PY.parent                             # team_02
_REPO = _PY.parents[1]                          # AIA26_Studio
sys.path.insert(0, str(_PY))
load_dotenv(_REPO / ".env")

from _runtime.bootstrap import bootstrap          # noqa: E402
from _runtime import llm as LLM                    # noqa: E402
from api import contracts                          # noqa: E402
import graph as G                                  # noqa: E402

OLD_SMART = "gemini-2.5-flash"
NEW_SMART = "gemini-3.5-flash"
OLD_IMAGE = "gemini-2.5-flash-image"
NEW_IMAGE = "gemini-3.1-flash-image"   # already rendered by imaging.benchmark → google_<case>.png

# User-facing SMART reasoning nodes to sample (the outputs a human actually reads).
SAMPLED = ["score_interpreter", "conflict_reasoner", "suggestion_critic", "respond", "detail_respond"]

PROMPTS = [
    "Analyze the apartment.",
    "Run the full analysis — score every room, detect the sensory conflicts, and give me concrete suggestions to fix them.",
    "In the kitchen, change the floor to wood and add two potted plants.",
    "Why is the kitchen's acoustic comfort so low?",
]
LAYOUT_ID = "201"
SEED = 20260620   # deterministic A/B assignment (no wall-clock randomness)


def _ab_labels(old_is_a: bool) -> tuple[str, str]:
    """Map the coin flip to (A_label, B_label) for the blind reveal map."""
    return ("OLD", "NEW") if old_is_a else ("NEW", "OLD")


def _run_session(ctx) -> None:
    persona_path = ctx.layout_input_dir.parent / "personas" / "persona.json"
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    sess = contracts.session_for_returning_user(persona)
    sess["layout_id"] = LAYOUT_ID
    for i, p in enumerate(PROMPTS, 1):
        print(f"--- capture turn {i}/{len(PROMPTS)}: {p[:48]!r}")
        try:
            _resp, sess = G.run_agent(p, ctx, sess)
        except Exception as exc:
            print(f"  [qual] turn errored: {exc}")


def main() -> None:
    outdir = _TEAM / "docs" / "week09" / "benchmark"
    outdir.mkdir(parents=True, exist_ok=True)

    ctx = bootstrap()
    LLM.usage_reset()
    _run_session(ctx)                 # fills LLM.QUALITY_CAPTURE (on the NEW models)
    LLM.set_quality_capture(False)    # stop capturing so replay calls aren't recorded

    # First captured (system, user) per sampled node — one representative prompt each.
    picks: dict[str, dict] = {}
    for cap in LLM.QUALITY_CAPTURE:
        node = cap.get("node")
        if node in SAMPLED and node not in picks:
            picks[node] = cap

    rng = random.Random(SEED)
    pairs, reveal = [], []
    print("\n=== TEXT: replay each sampled node old vs new ===")
    for node in SAMPLED:
        cap = picks.get(node)
        if not cap:
            print(f"  [qual] no capture for {node} — skipping")
            continue
        system, user = cap["system"], cap["user"]
        old_out = LLM.call_llm_simple(ctx.llm_simple, system, user, provider="google", model=OLD_SMART)
        new_out = LLM.call_llm_simple(ctx.llm_simple, system, user, provider="google", model=NEW_SMART)
        old_is_a = rng.random() < 0.5
        a, b = (old_out, new_out) if old_is_a else (new_out, old_out)
        a_lbl, b_lbl = _ab_labels(old_is_a)
        pairs.append({"node": node, "user_excerpt": user[:700], "A": a, "B": b})
        reveal.append({"node": node, "A": a_lbl, "B": b_lbl})
        print(f"  {node:18} old {len(old_out):>5} chars | new {len(new_out):>5} chars")

    # ── IMAGES: render OLD, reuse NEW (google_<case>.png), blind A/B ──────────────
    print("\n=== IMAGES: render old, pair against new ===")
    from imaging.benchmark import CASES, PERSONA          # noqa: E402
    from imaging import build_room_prompt                 # noqa: E402
    from imaging.client import generate_image             # noqa: E402

    os.environ["IMAGE_PROVIDER"] = "google"
    img_pairs, img_reveal = [], []
    for case_id, room, scores in CASES:
        new_path = outdir / f"google_{case_id}.png"        # NEW (from imaging.benchmark)
        if not new_path.exists():
            print(f"  [qual] missing NEW image {new_path.name} — run `python -m imaging.benchmark` first")
            continue
        os.environ["GOOGLE_IMAGE_MODEL"] = OLD_IMAGE
        try:
            b64 = generate_image(build_room_prompt(room, scores, PERSONA))
        except Exception as exc:
            print(f"  [qual] OLD image {case_id} failed: {exc}")
            continue
        old_path = outdir / f"old_{case_id}.png"
        old_path.write_bytes(base64.b64decode(b64))
        old_is_a = rng.random() < 0.5
        a_src, b_src = (old_path, new_path) if old_is_a else (new_path, old_path)
        a_lbl, b_lbl = _ab_labels(old_is_a)
        shutil.copyfile(a_src, outdir / f"qimg_{case_id}_A.png")
        shutil.copyfile(b_src, outdir / f"qimg_{case_id}_B.png")
        img_pairs.append({"case": case_id, "A": f"qimg_{case_id}_A.png", "B": f"qimg_{case_id}_B.png"})
        img_reveal.append({"case": case_id, "A": a_lbl, "B": b_lbl})
        print(f"  {case_id:18} A/B written")

    (outdir / "quality-pairs.json").write_text(json.dumps({
        "text_models": {"old": OLD_SMART, "new": NEW_SMART},
        "image_models": {"old": OLD_IMAGE, "new": NEW_IMAGE},
        "rubric": ["groundedness", "persona_fidelity", "clarity", "no_hallucination", "usefulness"],
        "text_pairs": pairs,
        "image_pairs": img_pairs,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "quality-reveal.json").write_text(json.dumps({
        "text_models": {"old": OLD_SMART, "new": NEW_SMART},
        "image_models": {"old": OLD_IMAGE, "new": NEW_IMAGE},
        "text_reveal": reveal,
        "image_reveal": img_reveal,
    }, indent=2), encoding="utf-8")
    print(f"\nSaved quality-pairs.json + quality-reveal.json to {outdir}")


if __name__ == "__main__":
    main()
