"""
Benchmark runner for the `reason` node.

Run from team_06/python/:
    python utils/benchmark/benchmark_reason.py

Tests 3 household profiles (family, single, retired) × R1-R5 and multi-turn (MT1-MT2) across all providers.
Results saved to utils/benchmark/benchmark_reason_results.json.
"""
from __future__ import annotations
import sys
import time
import json
from pathlib import Path

from benchmark_common import (
    PROVIDERS, _strip_fence, _tokens, make_llm, provider_label,
    build_user_message, print_table,
)
from nodes.reason import SYSTEM_PROMPT as REASON_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Test cases — 3 household profiles, same Q1→Q5 question sequence each
# ---------------------------------------------------------------------------

_CHECK_DESCRIPTION = lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("description", "").strip())
_CHECK_ROOMS       = lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("graph", {}).get("programs")) and bool(p.get("graph", {}).get("not_adjacency_pairs"))
_CHECK_IGNORE      = lambda p: p.get("latest_prompt_useful") is False

REASON_TURN_SETS = [
    {
        "id": "family",
        "label": "Family with kids",
        "turns": [
            {"id": "R1", "input": "We are a couple, I am 42 my partner is 38, we have two kids aged 8 and 5", "check": _CHECK_DESCRIPTION},
            {"id": "R2", "input": "We have a medium-sized dog",                                                 "check": _CHECK_DESCRIPTION},
            {"id": "R3", "input": "I work from home, my partner works in an office, kids play in the living room after school", "check": _CHECK_DESCRIPTION},
            {"id": "R4", "input": "3 bedrooms, 2 bathrooms, kitchen next to living room, master bedroom not next to kids room", "check": _CHECK_ROOMS},
            {"id": "R5", "input": "Ok",                                                                         "check": _CHECK_IGNORE},
        ],
    },
    {
        "id": "single",
        "label": "Single professional",
        "turns": [
            {"id": "R1", "input": "I live alone, I am 35",                                                      "check": _CHECK_DESCRIPTION},
            {"id": "R2", "input": "I have a cat",                                                               "check": _CHECK_DESCRIPTION},
            {"id": "R3", "input": "I work from home full time and go to the gym in the mornings",               "check": _CHECK_DESCRIPTION},
            {"id": "R4", "input": "I need a bedroom, a home office, a kitchen, and a living room. Office should not be next to bedroom", "check": _CHECK_ROOMS},
            {"id": "R5", "input": "That looks fine",                                                            "check": _CHECK_IGNORE},
        ],
    },
    {
        "id": "retired",
        "label": "Retired couple",
        "turns": [
            {"id": "R1", "input": "My husband and I are both retired, I am 68 and he is 71",                   "check": _CHECK_DESCRIPTION},
            {"id": "R2", "input": "We have a small dog",                                                        "check": _CHECK_DESCRIPTION},
            {"id": "R3", "input": "We cook together every day, we enjoy reading and we each have a hobby room", "check": _CHECK_DESCRIPTION},
            {"id": "R4", "input": "One master bedroom, a spacious kitchen, living room, two hobby rooms. Kitchen should be next to living room, bedroom not next to hobby rooms", "check": _CHECK_ROOMS},
            {"id": "R5", "input": "Yes",                                                                        "check": _CHECK_IGNORE},
        ],
    },
]

# MT1 seeds the context; MT2 must accumulate on top of it
MULTITURN_SEQUENCE = [
    {
        "id":    "MT1",
        "input": "I want 2 bedrooms and a kitchen",
        "check": lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("graph", {}).get("programs")),
    },
    {
        "id":    "MT2",
        "input": "Also add a bathroom connected to the master bedroom",
        "check": lambda p: (
            bool(p.get("latest_prompt_useful")) and
            len(p.get("graph", {}).get("programs", [])) >= 3 and
            bool(p.get("graph", {}).get("access_pairs"))
        ),
    },
]

# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def run_reason(llm, model: str) -> list[dict]:
    rows = []
    for turn_set in REASON_TURN_SETS:
        for turn in turn_set["turns"]:
            msgs = [
                {"role": "system", "content": REASON_SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_message(turn["input"])},
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
                "node": "reason", "test": turn["id"], "turn_set": turn_set["id"],
                "provider": provider_label(model), "model": model,
                "latency": round(latency, 2),
                "tokens_in": tokens_in, "tokens_out": tokens_out,
                "correct": correct, "error": error,
                "system_prompt": REASON_SYSTEM_PROMPT,
                "response": llm_output,
            })
    return rows


def run_reason_multiturn(llm, model: str) -> list[dict]:
    rows = []
    prior_graph: dict | None = None
    prior_description = ""

    for turn in MULTITURN_SEQUENCE:
        msgs = [
            {"role": "system", "content": REASON_SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_message(turn["input"], prior_graph, prior_description)},
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
            prior_graph           = parsed.get("graph")
            prior_description     = parsed.get("description", "")
        except Exception as exc:
            latency               = time.perf_counter() - t0
            tokens_in = tokens_out = 0
            correct               = False
            error                 = type(exc).__name__
            llm_output            = None

        rows.append({
            "node": "reason_multiturn", "test": turn["id"], "prompt_variant": "current",
            "provider": provider_label(model), "model": model,
            "latency": round(latency, 2),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "correct": correct, "error": error,
            "system_prompt": REASON_SYSTEM_PROMPT,
            "response": llm_output,
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    all_rows: list[dict] = []
    turns_per_set      = len(REASON_TURN_SETS[0]["turns"])
    calls_per_provider = (len(REASON_TURN_SETS) * turns_per_set) + len(MULTITURN_SEQUENCE)

    for provider in PROVIDERS:
        print(f"\n> {provider.upper()}", flush=True)
        try:
            llm, model = make_llm(provider)
            print(f"  model: {model}")
        except Exception as exc:
            print(f"  x skipped -- {exc}")
            continue

        all_rows.extend(run_reason(llm, model))
        all_rows.extend(run_reason_multiturn(llm, model))
        print(f"  done ({calls_per_provider} calls)")

    if not all_rows:
        print("No results -- check your .env credentials.")
        sys.exit(1)

    print_table(all_rows)

    out = Path(__file__).parent / "benchmark_reason_results.json"
    out.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"\nFull results saved -> {out}")
