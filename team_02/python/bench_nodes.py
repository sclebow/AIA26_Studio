"""
bench_nodes.py — per-node latency / token / cost benchmark for the Sensi graph.

Closes the open item in docs/week08/benchmarking-findings.md ("cost/latency numbers
per tier to be captured"). Runs a scripted session that exercises the layout-mode
LLM nodes, times each node (wall-clock) and snapshots the LLM token counter around
it (graph.py NODE_TIMINGS, _runtime/llm usage), then aggregates per node:
calls · avg/median latency · input/output tokens · estimated cost by tier.

Run (from team_02/python/, UTF-8 on Windows, with the .venv that has the backend deps):
    set BENCH_NODES=1   (the script also sets it before importing the graph)
    python bench_nodes.py
Out: docs/week08/benchmark/node-bench.json  (+ a printed table)
"""

from __future__ import annotations
import os

os.environ["BENCH_NODES"] = "1"  # must be set BEFORE importing graph

import json
import statistics
import sys
from datetime import datetime, timezone
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

# Google pricing, USD per 1M tokens (ai.google.dev/gemini-api/docs/pricing, checked 2026-06-20).
PRICE = {
    "fast":  {"in": 0.25, "out": 1.50},   # gemini-3.1-flash-lite
    "smart": {"in": 1.50, "out": 9.00},   # gemini-3.5-flash
}

# A scripted layout-mode session that lights up the runtime LLM nodes:
#   analyze→score_interpreter→respond→evaluator→what_next, the full detect/conflict/
#   suggest/critic chain, the edit path (edit_planner→apply_edits→compare), a
#   follow-up (detail_respond) and small-talk (chitchat). action_classifier runs each turn.
PROMPTS = [
    "Analyze the apartment.",
    "Run the full analysis — score every room, detect the sensory conflicts, and give me concrete suggestions to fix them.",
    "In the kitchen, change the floor to wood and add two potted plants.",
    "Why is the kitchen's acoustic comfort so low?",
    "Thanks, this is really helpful!",
]
LAYOUT_ID = "201"


def _run_session(ctx) -> None:
    persona_path = ctx.layout_input_dir.parent / "personas" / "persona.json"
    persona = json.loads(persona_path.read_text(encoding="utf-8"))
    sess = contracts.session_for_returning_user(persona)
    sess["layout_id"] = LAYOUT_ID
    for i, p in enumerate(PROMPTS, 1):
        print(f"\n--- turn {i}/{len(PROMPTS)}: {p!r}")
        try:
            _resp, sess = G.run_agent(p, ctx, sess)
        except Exception as exc:  # keep the batch going
            print(f"  [bench] turn errored: {exc}")

    # Best-effort onboarding capture: greet only (quiz/inspire/persona_compiler are
    # multi-step / multimodal onboarding — measured separately, noted in the doc).
    try:
        print("\n--- onboarding probe: greet")
        G.run_agent("hi", ctx, {})
    except Exception as exc:
        print(f"  [bench] onboarding probe errored: {exc}")


def _aggregate() -> list[dict]:
    agg: dict[str, dict] = {}
    for r in G.NODE_TIMINGS:
        a = agg.setdefault(r["node"], {"tier": r["tier"], "calls": 0, "lat": [],
                                       "in": 0, "out": 0, "llm_calls": 0})
        a["calls"] += 1
        a["lat"].append(r["latency_s"])
        a["in"] += r["in_tok"]
        a["out"] += r["out_tok"]
        a["llm_calls"] += r["llm_calls"]

    rows = []
    for node, a in agg.items():
        price = PRICE.get(a["tier"])
        cost = (a["in"] / 1e6 * price["in"] + a["out"] / 1e6 * price["out"]) if price else 0.0
        rows.append({
            "node": node, "tier": a["tier"], "calls": a["calls"], "llm_calls": a["llm_calls"],
            "avg_latency_s": round(statistics.mean(a["lat"]), 3),
            "median_latency_s": round(statistics.median(a["lat"]), 3),
            "in_tok": a["in"], "out_tok": a["out"], "est_cost_usd": round(cost, 5),
        })
    # group: SMART first, then FAST, then no-LLM; slowest first within a group
    order = {"smart": 0, "fast": 1}
    rows.sort(key=lambda r: (order.get(r["tier"], 2), -r["avg_latency_s"]))
    return rows


def main() -> None:
    ctx = bootstrap()
    LLM.usage_reset()
    G.NODE_TIMINGS.clear()
    _run_session(ctx)
    rows = _aggregate()

    print("\n=== PER-NODE BENCHMARK ===")
    hdr = f"{'node':22} {'tier':6} {'calls':>5} {'avg s':>7} {'med s':>7} {'in tok':>8} {'out tok':>8} {'$/total':>9}"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        print(f"{r['node']:22} {r['tier']:6} {r['calls']:>5} {r['avg_latency_s']:>7.3f} "
              f"{r['median_latency_s']:>7.3f} {r['in_tok']:>8} {r['out_tok']:>8} {r['est_cost_usd']:>9.5f}")

    llm_rows = [r for r in rows if r["tier"] in ("fast", "smart")]
    tot_cost = round(sum(r["est_cost_usd"] for r in llm_rows), 5)
    for tier in ("fast", "smart"):
        tr = [r for r in llm_rows if r["tier"] == tier]
        if tr:
            print(f"\n  {tier.upper():5}: {len(tr)} nodes | "
                  f"avg {statistics.mean([r['avg_latency_s'] for r in tr]):.3f}s | "
                  f"${round(sum(r['est_cost_usd'] for r in tr),5)} over this session")
    print(f"\n  Total LLM cost for this scripted session: ${tot_cost}")

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layout_id": LAYOUT_ID,
        "prompts": PROMPTS,
        "pricing_usd_per_1m_tokens": PRICE,
        "fast_model": os.environ.get("GOOGLE_MODEL_FAST", ""),
        "smart_model": os.environ.get("GOOGLE_MODEL_SMART", ""),
        "session_total_cost_usd": tot_cost,
        "nodes": rows,
        "raw_timings": G.NODE_TIMINGS,
    }
    outdir = _TEAM / "docs" / "week09" / "benchmark"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "node-bench.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nSaved {outdir / 'node-bench.json'}")


if __name__ == "__main__":
    main()
