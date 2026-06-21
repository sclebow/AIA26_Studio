"""
imaging/benchmark.py — head-to-head image-provider benchmark (Google vs OpenAI).

Generates the same score-driven room prompts on both providers, times each call,
saves the PNGs, and writes a results table for the faculty showcase.

Run (from team_02/python/, UTF-8 on Windows):
    python -m imaging.benchmark
Outputs to team_02/docs/week08/benchmark/.
"""

from __future__ import annotations
import base64
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

_PY_DIR = Path(__file__).resolve().parents[1]          # team_02/python
_TEAM_DIR = Path(__file__).resolve().parents[2]        # team_02
_REPO = Path(__file__).resolve().parents[3]            # AIA26_Studio
sys.path.insert(0, str(_PY_DIR))
load_dotenv(_REPO / ".env")

from imaging import build_room_prompt  # noqa: E402
from imaging.client import generate_image  # noqa: E402

# Published per-image cost (USD, 1024², June 2026): Nano Banana flat; gpt-image-1 @ medium.
COST = {"google": 0.039, "openai": 0.042}
PROVIDERS = ["google", "openai"]

PERSONA = {"role": "architect"}
CASES = [
    ("living-room-poor", {"name": "Living Room", "attributes": {"roomType": "living room", "floorMaterial": "concrete"}},
     {"thermal": 0.30, "visual": 0.55, "acoustic": 0.20, "spatial": 0.80, "olfactory": 0.45, "tactile": 0.35}),
    ("bedroom-cosy", {"name": "Bedroom", "attributes": {"roomType": "bedroom", "floorMaterial": "wood"}},
     {"thermal": 0.85, "visual": 0.80, "acoustic": 0.78, "spatial": 0.75, "olfactory": 0.80, "tactile": 0.82}),
    ("kitchen-mixed", {"name": "Kitchen", "attributes": {"roomType": "kitchen", "floorMaterial": "ceramic"}},
     {"thermal": 0.40, "visual": 0.72, "acoustic": 0.30, "spatial": 0.60, "olfactory": 0.35, "tactile": 0.50}),
]


def main() -> None:
    outdir = _TEAM_DIR / "docs" / "week08" / "benchmark"
    outdir.mkdir(parents=True, exist_ok=True)
    results = []

    for provider in PROVIDERS:
        os.environ["IMAGE_PROVIDER"] = provider
        print(f"\n=== {provider.upper()} ===")
        for case_id, room, scores in CASES:
            prompt = build_room_prompt(room, scores, PERSONA)
            t0 = time.time()
            try:
                b64 = generate_image(prompt)
                dt = time.time() - t0
                path = outdir / f"{provider}_{case_id}.png"
                path.write_bytes(base64.b64decode(b64))
                kb = path.stat().st_size // 1024
                results.append({"provider": provider, "case": case_id, "latency_s": round(dt, 1),
                                "kb": kb, "cost_usd": COST[provider], "ok": True, "file": path.name})
                print(f"  {case_id:18} {dt:5.1f}s   {kb} KB")
            except Exception as exc:
                dt = time.time() - t0
                results.append({"provider": provider, "case": case_id, "latency_s": round(dt, 1),
                                "ok": False, "error": str(exc)[:200]})
                print(f"  {case_id:18} ERROR after {dt:.1f}s: {str(exc)[:120]}")

    # per-provider summary
    print("\n=== SUMMARY ===")
    summary = {}
    for provider in PROVIDERS:
        ok = [r for r in results if r["provider"] == provider and r["ok"]]
        if ok:
            avg = sum(r["latency_s"] for r in ok) / len(ok)
            cost = sum(r["cost_usd"] for r in ok)
            summary[provider] = {"images": len(ok), "avg_latency_s": round(avg, 1), "total_cost_usd": round(cost, 3),
                                 "cost_per_image_usd": COST[provider]}
            print(f"  {provider:8} {len(ok)} imgs | avg {avg:4.1f}s | ${cost:.3f} total (${COST[provider]}/img)")

    (outdir / "results.json").write_text(
        json.dumps({"summary": summary, "runs": results}, indent=2), encoding="utf-8")
    print(f"\nSaved images + results.json to {outdir}")


if __name__ == "__main__":
    main()
