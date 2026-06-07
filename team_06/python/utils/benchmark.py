"""
Benchmark runner for team_06 LLM nodes.

Run from team_06/python/:
    python utils/benchmark.py

Tests the `reason` node across all four configured providers
(Cloudflare, OpenAI, Google, Anthropic) and prints a results table.
Results are also saved to utils/benchmark_results.json.
"""
from __future__ import annotations
import sys
import time
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _runtime.llm import create_chat_llm, _resolve_llm_connection
from nodes.reason import SYSTEM_PROMPT as REASON_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Providers to test — reads model names from .env at runtime
# ---------------------------------------------------------------------------

PROVIDERS = ["cloudflare", "openai", "google", "anthropic"]
TIMEOUT   = 30.0

# ---------------------------------------------------------------------------
# Reason node — graph payload extraction
# ---------------------------------------------------------------------------

# Each dict: id, input, check (callable — takes the parsed JSON, returns bool)
REASON_TURNS = [
    {
        "id":    "R1",
        "input": "I want 2 bedrooms and a bathroom connected to the master bedroom",
        "check": lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("graph", {}).get("programs")),
    },
    {
        "id":    "R2",
        "input": "Kitchen next to living, bedroom not next to kitchen",
        "check": lambda p: bool(p.get("latest_prompt_useful")) and (
            bool(p.get("graph", {}).get("adjacency_pairs")) or
            bool(p.get("graph", {}).get("not_adjacency_pairs"))
        ),
    },
    {
        "id":    "R3",
        "input": "We are a couple with a dog, we both work from home",
        "check": lambda p: bool(p.get("latest_prompt_useful")) and bool(p.get("description", "").strip()),
    },
    {
        "id":    "R4",
        "input": "Ok",
        "check": lambda p: p.get("latest_prompt_useful") is False,
    },
    {
        "id":    "R5",
        "input": "Evaluate the current layout",
        "check": lambda p: p.get("latest_prompt_useful") is False,
    },
]

# Multi-turn sequence: MT1 seeds the context, MT2 must accumulate on top of it
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
            len(p.get("graph", {}).get("programs", [])) >= 3 and  # programs from MT1 preserved
            bool(p.get("graph", {}).get("access_pairs"))
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_fence(content: str) -> str:
    s = content.strip()
    if s.startswith("```"):
        lines = s.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return s


def _tokens(response) -> tuple[int, int]:
    meta = getattr(response, "usage_metadata", None)
    if not isinstance(meta, dict):
        return 0, 0
    return meta.get("input_tokens", 0), meta.get("output_tokens", 0)


def _make_llm(provider: str):
    api_key, base_url, model = _resolve_llm_connection(provider, None)
    llm = create_chat_llm(api_key, base_url, model, TIMEOUT)
    return llm, model


def _provider_label(model: str) -> str:
    if model.startswith("@cf/"):  return "cloudflare"
    if "gemini" in model:         return "google"
    if "claude" in model:         return "anthropic"
    return "openai"


def _build_user_message(user_input: str, prior_graph: dict | None = None, prior_description: str = "") -> str:
    graph = prior_graph or {"programs": [], "access_pairs": [], "adjacency_pairs": [], "not_adjacency_pairs": []}
    return (
        f"Current graph: {json.dumps(graph)}\n"
        f"Current description: {json.dumps(prior_description)}\n"
        f"Feedback history: []\n"
        f"User input: {user_input}\n"
        "Return the full updated search summary. Keep graph fields only for information that fits the graph structure. "
        "Put only non-graph information in description. Do not summarize the graph again in prose."
    )


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

def run_reason(llm, model: str) -> list[dict]:
    rows = []
    for turn in REASON_TURNS:
        msgs = [
            {"role": "system", "content": REASON_SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_message(turn["input"])},
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
            "node": "reason", "test": turn["id"], "provider": _provider_label(model),
            "model": model, "latency": round(latency, 2),
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
            {"role": "user",   "content": _build_user_message(turn["input"], prior_graph, prior_description)},
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
            "node": "reason_multiturn", "test": turn["id"], "provider": _provider_label(model),
            "model": model, "latency": round(latency, 2),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "correct": correct, "error": error,
            "system_prompt": REASON_SYSTEM_PROMPT,
            "response": llm_output,
        })
    return rows


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def print_table(rows: list[dict]) -> None:
    col_model = max(len(r["model"]) for r in rows) + 2
    col_model = max(col_model, 20)

    header = (
        f"{'Node':<20} {'Test':<12} "
        f"{'Model':<{col_model}} "
        f"{'Latency':>9}  {'In':>6} {'Out':>6}  {'OK':>4}  {'Error'}"
    )
    sep = "-" * len(header)
    print(f"\n{sep}\n{header}\n{sep}")

    prev_provider = None
    for r in rows:
        if r["provider"] != prev_provider:
            print(f"  [{r['provider'].upper()}]")
            prev_provider = r["provider"]
        ok  = "✓" if r["correct"] else "✗"
        err = r["error"] or ""
        print(
            f"  {r['node']:<18} {r['test']:<12} "
            f"{r['model']:<{col_model}} "
            f"{r['latency']:>8.2f}s  {r['tokens_in']:>6} {r['tokens_out']:>6}  "
            f"{ok:>4}  {err}"
        )
    print(sep)

    print("\nSummary")
    print("-" * 40)
    from itertools import groupby
    for provider, group in groupby(rows, key=lambda r: r["provider"]):
        g       = list(group)
        passed  = sum(1 for r in g if r["correct"])
        total   = len(g)
        avg_lat = sum(r["latency"] for r in g) / total
        errors  = sum(1 for r in g if r["error"])
        print(f"  {provider:<12}  {passed}/{total} correct  "
              f"avg {avg_lat:.2f}s  {errors} parse errors")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    all_rows: list[dict] = []

    for provider in PROVIDERS:
        print(f"\n▶ {provider.upper()}", flush=True)
        try:
            llm, model = _make_llm(provider)
            print(f"  model: {model}")
        except Exception as exc:
            print(f"  ✗ skipped — {exc}")
            continue

        all_rows.extend(run_reason(llm, model))
        all_rows.extend(run_reason_multiturn(llm, model))
        print(f"  done ({len(REASON_TURNS) + len(MULTITURN_SEQUENCE)} calls)")

    if not all_rows:
        print("No results — check your .env credentials.")
        sys.exit(1)

    print_table(all_rows)

    out = Path(__file__).parent / "benchmark_results.json"
    out.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"\nFull results saved → {out}")
