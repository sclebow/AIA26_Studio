"""Optimize → navigate → compare workflow: persistence + accumulation tests.

Covers the spec's acceptance criteria for the Optimization Explorer regression:
  * Optimization results are persisted to optimization_history immediately after a run.
  * Every selected shape yields its variants (shape_NNN -> A, B) - none dropped.
  * A SECOND optimize run ACCUMULATES into history (does not overwrite the first).
  * Each persisted record carries geometry + objective_scores + overall_score so the
    Optimization Explorer can render/preview it and the comparison table shows real
    numbers (never fabricated; missing metrics are simply absent → N/A in the UI).
  * History survives a fresh read (the durable source the frontend reloads on navigation).

Run against a live server:  python test_optimization_persistence.py  [BASE_URL]
Exits non-zero if any assertion fails.
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"


def _post(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(BASE + path, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def _get(path: str) -> dict:
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())


def _setup_with_saved_shapes(n: int) -> tuple[str, str, list[str]]:
    """Create a session, site, context, one selected shape, and `n` saved variants."""
    sid = _post("/sessions", {"workflow_mode": "full"})["session_id"]
    _post(f"/sessions/{sid}/site/boundary", {"boundary": [[0, 0], [180, 0], [180, 140], [0, 140]]})
    _post(f"/sessions/{sid}/context/store", {
        "edges": [{"edge_id": "S", "a": [0, 0], "b": [180, 0], "display_name": "south",
                   "nearest": {"Primary Road": 20}}],
        "layers": {}, "center": {"lat": 12.97, "lng": 77.59}})
    opt = _post(f"/sessions/{sid}/generate-options", {"prompt": "6 floor building"})
    bid = opt["options"][0]["option_id"]
    _post(f"/sessions/{sid}/select-shape", {"option_id": bid})
    ids = []
    for k in range(n):
        _post(f"/sessions/{sid}/buildings/{bid}/feedback", {"feedback": "add 1 floor", "apply": True})
        sid_opt = _post(f"/sessions/{sid}/design-options/save", {"prompt": f"v{k}"}).get("shape_option_id")
        ids.append(sid_opt)
    return sid, bid, ids


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"{'[PASS]' if cond else '[FAIL]'} {name}")
        if not cond:
            failures.append(name)

    # --- run 1: optimize 4 saved shapes ---
    sid, _bid, ids = _setup_with_saved_shapes(4)
    res1 = _post(f"/sessions/{sid}/design-options/optimize-all", {"option_ids": ids})
    variants1 = res1.get("optimized_options", [])
    check("optimize returns 2 variants per selected shape (4 -> 8)", len(variants1) == 8)

    # every selected shape is represented (none dropped)
    parents = {v.get("source_shape_option_id") for v in variants1}
    check("every selected shape has variants", parents == set(ids))

    # each variant carries geometry + real scores (no fabricated metrics)
    check("variants carry geometry.boundary",
          all((v.get("geometry") or {}).get("boundary") for v in variants1))
    check("variants carry objective_scores",
          all(v.get("objective_scores") for v in variants1))
    check("variants carry an overall score (scores.total)",
          all((v.get("scores") or {}).get("total") is not None for v in variants1))

    # --- persisted to optimization_history (the durable store the explorer reloads) ---
    hist1 = _get(f"/sessions/{sid}/optimization-history")["optimization_history"]
    check("history persisted all 8 variants", len(hist1) == 8)
    check("history records carry geometry",
          all((h.get("geometry") or {}).get("boundary") for h in hist1))
    check("history records carry overall_score + objective_scores",
          all(h.get("overall_score") is not None and h.get("objective_scores") for h in hist1))

    # --- survives a fresh read (navigation/refresh): same records still there ---
    hist1b = _get(f"/sessions/{sid}/optimization-history")["optimization_history"]
    check("history survives re-read (navigation)", len(hist1b) == 8)

    # --- run 2: optimize a SUBSET again → history ACCUMULATES, not overwrites ---
    res2 = _post(f"/sessions/{sid}/design-options/optimize-all", {"option_ids": ids[:2]})
    check("second run returns 2×2 = 4 variants", len(res2.get("optimized_options", [])) == 4)
    hist2 = _get(f"/sessions/{sid}/optimization-history")["optimization_history"]
    check("second run ACCUMULATES into history (>= first run's 8)", len(hist2) >= 8)

    # --- comparison can mix variants from different parents (real metrics) ---
    by_id = {h["optimized_option_id"]: h for h in hist2}
    pick = [f"{ids[0]}A", f"{ids[1]}B", f"{ids[3]}A"]
    chosen = [by_id[p] for p in pick if p in by_id]
    check("can pick a mix of variants from 3 different parents", len(chosen) == 3)
    if len(chosen) == 3:
        real = sum(1 for h in chosen for k in ("solar", "wind", "density", "open_space")
                   if isinstance((h.get("objective_scores") or {}).get(k), (int, float)))
        check("mixed comparison exposes real per-metric numbers", real >= 6)

    print("=" * 52)
    print(f"RESULT: {'ALL PASS' if not failures else f'{len(failures)} FAILED: ' + ', '.join(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
