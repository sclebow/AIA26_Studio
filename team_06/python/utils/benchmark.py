"""
Benchmark runner for team_06 LLM nodes.

Run from team_06/python/:
    python utils/benchmark.py

Tests the `reason` and `topology` nodes across all four configured providers
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

# ---------------------------------------------------------------------------
# Providers to test — reads model names from .env at runtime
# ---------------------------------------------------------------------------

PROVIDERS = ["cloudflare", "openai", "google", "anthropic"]
TIMEOUT   = 30.0

# ---------------------------------------------------------------------------
# Reason node — structured household extraction
# ---------------------------------------------------------------------------

REASON_SYSTEM_PROMPT = (
    "You are an architect assistant. "
    "Extract structured information from the user input as a JSON object with exactly "
    "these fields: households (list), pets (list), activities (list), rooms (list). "
    "If a field has no data, use an empty list. "
    "Return only the JSON object — no explanation, no markdown fences."
)

# Each tuple: (expected_field, user_input)
REASON_TURNS = [
    ("households", "I am 42, my partner is 38, we have two kids aged 8 and 5."),
    ("pets",       "We have a medium-sized dog."),
    ("activities", "We cook daily. I work from home. Kids play in the living room."),
    ("rooms",      "We want 3 bedrooms, 2 bathrooms. Kitchen next to living room."),
]

# ---------------------------------------------------------------------------
# Topology node — room graph extraction (LLM fallback path)
# ---------------------------------------------------------------------------

TOPOLOGY_SYSTEM_PROMPT = (
    "Extract room types and their adjacencies from the description. "
    'Return only JSON in this exact shape: {"programs": ["room_type", ...], '
    '"edges": [["room1", "room2"], ...]}. '
    "No explanation, no markdown fences."
)

TOPOLOGY_TESTS = [
    ("T1", "3 bedrooms, 1 bathroom, kitchen, living room. Bedroom next to bathroom."),
    ("T2", "studio with kitchen and bathroom"),
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


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------

def run_reason(llm, model: str) -> list[dict]:
    rows = []
    for field, user_input in REASON_TURNS:
        msgs = [
            {"role": "system", "content": REASON_SYSTEM_PROMPT},
            {"role": "user",   "content": user_input},
        ]
        t0 = time.perf_counter()
        try:
            response              = llm.invoke(msgs)
            latency               = time.perf_counter() - t0
            parsed                = json.loads(_strip_fence(response.content))
            tokens_in, tokens_out = _tokens(response)
            correct               = bool(parsed.get(field))
            error                 = None
            llm_output            = parsed
        except Exception as exc:
            latency               = time.perf_counter() - t0
            tokens_in = tokens_out = 0
            correct               = False
            error                 = type(exc).__name__
            llm_output            = None

        rows.append({
            "node": "reason", "test": field, "provider": _provider_label(model),
            "model": model, "latency": round(latency, 2),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "correct": correct, "error": error,
            "response": llm_output,
        })
    return rows


def run_topology(llm, model: str) -> list[dict]:
    rows = []
    for test_id, description in TOPOLOGY_TESTS:
        msgs = [
            {"role": "system", "content": TOPOLOGY_SYSTEM_PROMPT},
            {"role": "user",   "content": description},
        ]
        t0 = time.perf_counter()
        try:
            response              = llm.invoke(msgs)
            latency               = time.perf_counter() - t0
            parsed                = json.loads(_strip_fence(response.content))
            tokens_in, tokens_out = _tokens(response)
            correct               = isinstance(parsed.get("programs"), list) and len(parsed["programs"]) > 0
            error                 = None
            llm_output            = parsed
        except Exception as exc:
            latency               = time.perf_counter() - t0
            tokens_in = tokens_out = 0
            correct               = False
            error                 = type(exc).__name__
            llm_output            = None

        rows.append({
            "node": "topology", "test": test_id, "provider": _provider_label(model),
            "model": model, "latency": round(latency, 2),
            "tokens_in": tokens_in, "tokens_out": tokens_out,
            "correct": correct, "error": error,
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
        f"{'Node':<10} {'Test':<12} "
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
            f"  {r['node']:<8} {r['test']:<12} "
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
        all_rows.extend(run_topology(llm, model))
        print(f"  done ({len(REASON_TURNS) + len(TOPOLOGY_TESTS)} calls)")

    if not all_rows:
        print("No results — check your .env credentials.")
        sys.exit(1)

    print_table(all_rows)

    out = Path(__file__).parent / "benchmark_results.json"
    out.write_text(json.dumps(all_rows, indent=2), encoding="utf-8")
    print(f"\nFull results saved → {out}")
