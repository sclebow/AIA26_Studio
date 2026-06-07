"""
Benchmark runner for the `evaluate` node.

Run from team_06/python/:
    python utils/benchmark/benchmark_evaluate.py

Tests E1-E4 across all providers using hand-written brief + layout fixtures.
Results saved to utils/benchmark/benchmark_evaluate_results.json.
"""
from __future__ import annotations
import sys
import time
import json
from pathlib import Path

from benchmark_common import (
    PROVIDERS, _strip_fence, _tokens, make_llm, provider_label, print_table,
)
from nodes.evaluate import SYSTEM_PROMPT as EVALUATE_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_BRIEF_MATCH = json.dumps({
    "graph": {
        "programs": ["bedroom", "bedroom", "kitchen", "living"],
        "access_pairs": [],
        "adjacency_pairs": [["kitchen", "living"]],
        "not_adjacency_pairs": [],
    },
    "description": "",
})

_BRIEF_MISMATCH = json.dumps({
    "graph": {
        "programs": ["bedroom", "bedroom", "bedroom", "kitchen"],
        "access_pairs": [],
        "adjacency_pairs": [],
        "not_adjacency_pairs": [],
    },
    "description": "",
})

_LAYOUT_MATCH = json.dumps({
    "rooms": [
        {"type": "bedroom", "area": 12},
        {"type": "bedroom", "area": 10},
        {"type": "kitchen", "area": 8},
        {"type": "living",  "area": 20},
    ],
    "adjacencies": [["kitchen", "living"]],
})

_LAYOUT_MISMATCH = json.dumps({
    "rooms": [
        {"type": "bedroom", "area": 12},
        {"type": "kitchen", "area": 8},
    ],
    "adjacencies": [],
})

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

EVALUATE_TURNS = [
    {
        "id":     "E1",
        "brief":  _BRIEF_MATCH,
        "layout": _LAYOUT_MATCH,
        "check":  lambda p: isinstance(p.get("fit_score"), int) and p["fit_score"] >= 60,
    },
    {
        "id":     "E2",
        "brief":  _BRIEF_MISMATCH,
        "layout": _LAYOUT_MISMATCH,
        "check":  lambda p: isinstance(p.get("fit_score"), int) and p["fit_score"] < 60 and bool(p.get("concerns")),
    },
    {
        "id":     "E3",
        "brief":  _BRIEF_MATCH,
        "layout": _LAYOUT_MATCH,
        "check":  lambda p: bool(p.get("strengths")) and bool(p.get("summary", "").strip()),
    },
    {
        "id":     "E4",
        "brief":  _BRIEF_MATCH,
        "layout": json.dumps({}),
        "check":  lambda p: isinstance(p.get("fit_score"), int),
    },
]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_evaluate(llm, model: str) -> list[dict]:
    rows = []
    for turn in EVALUATE_TURNS:
        msgs = [
            {"role": "system", "content": EVALUATE_SYSTEM_PROMPT},
            {"role": "user",   "content": (
                f"Parsed brief JSON: {turn['brief']}\n"
                f"Layout JSON: {turn['layout']}\n"
                "Evaluate how well the layout matches the brief, including household needs, "
                "furniture needs, room relationships, and routine through the day."
            )},
        ]
        t0 = time.perf_counter()
        try:
            response              = llm.invoke(msgs)
            latency               = time.perf_counter() - t0
            parsed                = json.loads(_strip_fence(response.content))
            tokens_in, tokens_out = _tokens(response)
            correct               = turn["check"](parsed)
            error                 = None
            llm_output            = parsed
        except Exception as exc:
            latency               = time.perf_counter() - t0
            tokens_in = tokens_out = 0
            correct               = False
            error                 = type(exc).__name__
            llm_output            = None

        rows.append({
            "node": "evaluate", "test": turn["id"], "prompt_variant": "-",
            "provider": provider_label(model), "model": model,
            "latency": round(latency, 2),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "correct": correct, "error": error,
            "system_prompt": EVALUATE_SYSTEM_PROMPT,
            "response": llm_output,
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    all_rows: list[dict] = []

    for provider in PROVIDERS:
        print(f"\n> {provider.upper()}", flush=True)
        try:
            llm, model = make_llm(provider)
            print(f"  model: {model}")
        except Exception as exc:
            print(f"  x skipped -- {exc}")
            continue

        all_rows.extend(run_evaluate(llm, model))
        print(f"  done ({len(EVALUATE_TURNS)} calls)")

    if not all_rows:
        print("No results -- check your .env credentials.")
        sys.exit(1)

    print_table(all_rows)

    out = Path(__file__).parent / "benchmark_evaluate_results.json"
    out.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"\nFull results saved -> {out}")
