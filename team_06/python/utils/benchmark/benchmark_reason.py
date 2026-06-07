"""
Benchmark runner for the `reason` node.

Run from team_06/python/:
    python utils/benchmark/benchmark_reason.py

Tests 3 input buckets (household, topology, additional) × 3 turns each, plus multi-turn (MT1-MT2), across all providers.
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
# Test cases — 9 test IDs × 3 user profiles = 27 single-prompt tests
# ---------------------------------------------------------------------------

_CHECK_STORED    = lambda p: p.get("latest_prompt_useful") is False and bool(p.get("description", "").strip())
_CHECK_SEARCH    = lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("graph", {}).get("programs"))
_CHECK_ADJACENCY = lambda p: bool(p.get("latest_prompt_useful")) and (
    bool(p.get("graph", {}).get("adjacency_pairs")) or
    bool(p.get("graph", {}).get("not_adjacency_pairs"))
)
_CHECK_COMBINED  = lambda p: (
    bool(p.get("latest_prompt_useful")) and
    bool(p.get("graph", {}).get("programs")) and
    bool(p.get("description", "").strip())
)
_CHECK_IGNORE    = lambda p: p.get("latest_prompt_useful") is False

USER_PROFILES = [
    {
        "id": "single",
        "tests": [
            {"id": "household-people",    "input": "I live alone, I am 35",                                                                                        "check": _CHECK_STORED},
            {"id": "household-lifestyle", "input": "I have a cat, I work from home full time",                                                                     "check": _CHECK_STORED},
            {"id": "rooms-basic",         "input": "1 bedroom and a bathroom",                                                                                     "check": _CHECK_SEARCH},
            {"id": "rooms-full",          "input": "bedroom, home office, kitchen, living room",                                                                   "check": _CHECK_SEARCH},
            {"id": "adjacency",           "input": "home office not next to bedroom, kitchen next to living room",                                                 "check": _CHECK_ADJACENCY},
            {"id": "combined-basic",      "input": "I live alone and work from home. I need a bedroom and a home office",                                          "check": _CHECK_COMBINED},
            {"id": "combined-full",       "input": "I am 35, single, I work from home. Bedroom, home office not next to bedroom, kitchen, living room",            "check": _CHECK_COMBINED},
            {"id": "ignore-ack",          "input": "Ok",                                                                                                           "check": _CHECK_IGNORE},
            {"id": "ignore-eval",         "input": "Evaluate the current layout",                                                                                  "check": _CHECK_IGNORE},
        ],
    },
    {
        "id": "family",
        "tests": [
            {"id": "household-people",    "input": "We are a couple with two kids aged 8 and 5",                                                                   "check": _CHECK_STORED},
            {"id": "household-lifestyle", "input": "We have a medium-sized dog, I work from home and my partner commutes",                                         "check": _CHECK_STORED},
            {"id": "rooms-basic",         "input": "3 bedrooms and 2 bathrooms",                                                                                   "check": _CHECK_SEARCH},
            {"id": "rooms-full",          "input": "3 bedrooms, 2 bathrooms, kitchen, living room, playroom",                                                      "check": _CHECK_SEARCH},
            {"id": "adjacency",           "input": "master bedroom not next to kids rooms, kitchen next to living room",                                           "check": _CHECK_ADJACENCY},
            {"id": "combined-basic",      "input": "We are a couple with 2 kids. 3 bedrooms, kitchen next to living room",                                         "check": _CHECK_COMBINED},
            {"id": "combined-full",       "input": "Family of 4 with a dog, I work from home. 3 bedrooms, master not next to kids room, kitchen next to living",   "check": _CHECK_COMBINED},
            {"id": "ignore-ack",          "input": "Ok",                                                                                                           "check": _CHECK_IGNORE},
            {"id": "ignore-eval",         "input": "Evaluate the current layout",                                                                                  "check": _CHECK_IGNORE},
        ],
    },
    {
        "id": "retired",
        "tests": [
            {"id": "household-people",    "input": "My husband and I are both retired, I am 68 and he is 71",                                                      "check": _CHECK_STORED},
            {"id": "household-lifestyle", "input": "We have a small dog, we cook together every day",                                                              "check": _CHECK_STORED},
            {"id": "rooms-basic",         "input": "One master bedroom and a large bathroom",                                                                      "check": _CHECK_SEARCH},
            {"id": "rooms-full",          "input": "master bedroom, large kitchen, living room, two hobby rooms",                                                  "check": _CHECK_SEARCH},
            {"id": "adjacency",           "input": "kitchen next to living room, bedroom not next to hobby rooms",                                                 "check": _CHECK_ADJACENCY},
            {"id": "combined-basic",      "input": "We are a retired couple. One bedroom, spacious kitchen next to living room",                                   "check": _CHECK_COMBINED},
            {"id": "combined-full",       "input": "Retired couple with a small dog, we cook daily. Master bedroom, large kitchen next to living, two hobby rooms", "check": _CHECK_COMBINED},
            {"id": "ignore-ack",          "input": "That sounds good",                                                                                             "check": _CHECK_IGNORE},
            {"id": "ignore-eval",         "input": "Can you evaluate the layout?",                                                                                 "check": _CHECK_IGNORE},
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
    for profile in USER_PROFILES:
        for test in profile["tests"]:
            msgs = [
                {"role": "system", "content": REASON_SYSTEM_PROMPT},
                {"role": "user",   "content": build_user_message(test["input"])},
            ]
            t0 = time.perf_counter()
            try:
                response              = llm.invoke(msgs)
                latency               = time.perf_counter() - t0
                parsed                = json.loads(_strip_fence(response.content))
                tokens_in, tokens_out = _tokens(response)
                correct               = test["check"](parsed)
                error                 = None
                llm_output            = parsed
            except Exception as exc:
                latency               = time.perf_counter() - t0
                tokens_in = tokens_out = 0
                correct               = False
                error                 = type(exc).__name__
                llm_output            = None

            rows.append({
                "node": "reason", "test": test["id"], "profile": profile["id"],
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
    calls_per_provider = (len(USER_PROFILES) * len(USER_PROFILES[0]["tests"])) + len(MULTITURN_SEQUENCE)

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
