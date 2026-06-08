"""
Shared helpers for benchmark_reason.py and benchmark_evaluate.py.
"""
from __future__ import annotations
import sys
import time
import json
from pathlib import Path
from itertools import groupby
from dotenv import load_dotenv

# utils/benchmark/ -> utils/ -> python/ -> team_06/ -> AIA26_Studio/
load_dotenv(Path(__file__).resolve().parents[4] / ".env")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # team_06/python/

from _runtime.llm import create_chat_llm, _resolve_llm_connection

PROVIDERS = ["cloudflare", "openai", "google", "anthropic"]
TIMEOUT   = 30.0


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


def make_llm(provider: str):
    api_key, base_url, model = _resolve_llm_connection(provider, None)
    llm = create_chat_llm(api_key, base_url, model, TIMEOUT)
    return llm, model


def provider_label(model: str) -> str:
    if model.startswith("@cf/"):  return "cloudflare"
    if "gemini" in model:         return "google"
    if "claude" in model:         return "anthropic"
    return "openai"


def build_user_message(user_input: str, prior_graph: dict | None = None, prior_description: str = "") -> str:
    graph = prior_graph or {"programs": [], "access_pairs": [], "adjacency_pairs": [], "not_adjacency_pairs": []}
    return (
        f"Current graph: {json.dumps(graph)}\n"
        f"Current description: {json.dumps(prior_description)}\n"
        f"Feedback history: []\n"
        f"User input: {user_input}\n"
        "Return the full updated search summary. Keep graph fields only for information that fits the graph structure. "
        "Put only non-graph information in description. Do not summarize the graph again in prose."
    )


def print_table(rows: list[dict]) -> None:
    col_model = max((len(r["model"]) for r in rows), default=20) + 2
    col_model = max(col_model, 20)

    header = (
        f"{'Node':<22} {'Test':<6} {'Variant':<12} "
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
        ok      = "v" if r["correct"] else "x"
        err     = r["error"] or ""
        variant = r.get("prompt_variant", "-")
        print(
            f"  {r['node']:<20} {r['test']:<6} {variant:<12} "
            f"{r['model']:<{col_model}} "
            f"{r['latency']:>8.2f}s  {r['tokens_in']:>6} {r['tokens_out']:>6}  "
            f"{ok:>4}  {err}"
        )
    print(sep)

    print("\nSummary")
    print("-" * 40)
    for provider, group in groupby(rows, key=lambda r: r["provider"]):
        g       = list(group)
        passed  = sum(1 for r in g if r["correct"])
        total   = len(g)
        avg_lat = sum(r["latency"] for r in g) / total
        errors  = sum(1 for r in g if r["error"])
        print(f"  {provider:<12}  {passed}/{total} correct  avg {avg_lat:.2f}s  {errors} errors")
