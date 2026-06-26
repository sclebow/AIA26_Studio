"""
Benchmark recorder for the AGENT_ui backend.

Records every real LangGraph pipeline run (one chat session = one BenchRun) with
the metrics the benchmark dashboard needs:

  - provider + model (anthropic/haiku|sonnet, google/flash|pro) → model performance
  - per-node timings (started→completed) → Gantt of pipeline stage durations
  - node-category call counts → API-calls breakdown, reason "turns"
  - recursion-limit hits
  - scoring breakdown (overall + grade + 5 weighted metrics) → score trend + per-model
  - placement quality (req/placed/zone/collision-free/wall) → module 01 (best-effort)
  - an event timeline (node, status, ms-offset)

Runs are persisted to ``backend/benchmarks/runs.json`` (append, survives restarts).
This module is self-contained and never imports team_03/python (read-only); it is
fed by ``agent_runner`` which already streams every node event + the scoring state.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_STORE_DIR = Path(__file__).resolve().parent / "benchmarks"
_STORE_FILE = _STORE_DIR / "runs.json"
_LOCK = threading.Lock()

# Cap the on-disk history so the file (and the dashboard payload) stays bounded.
_MAX_RUNS = 500


# How each graph node maps to an "API calls breakdown" category (module 03).
# Anything unmatched falls into "other".
_NODE_CATEGORY = {
    "profile_agent": "profile",
    "space_type_agent": "space",
    "populate_agent": "populate",
    "populate_check": "populate",
    "memory": "memory",
    "reason": "reason",
    "tool": "tools",
    "add_objects": "tools",
    "collision": "analysis",
    "visibility": "analysis",
    "orientation": "analysis",
    "path": "analysis",
    "path_analysis": "analysis",
    "reachability": "analysis",
    "enrich_graph": "analysis",
    "scoring": "analysis",
    "checkpoint": "other",
    "user_checkpoint": "other",
    "explain": "other",
    "output": "other",
    "setup": "setup",
}


def _load_runs() -> List[Dict[str, Any]]:
    try:
        if _STORE_FILE.exists():
            data = json.loads(_STORE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save_runs(runs: List[Dict[str, Any]]) -> None:
    try:
        _STORE_DIR.mkdir(parents=True, exist_ok=True)
        _STORE_FILE.write_text(
            json.dumps(runs[-_MAX_RUNS:], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        print(f"[benchmark] could not persist runs: {exc}")


# ---------------------------------------------------------------------------
# Recorder — one instance per pipeline run
# ---------------------------------------------------------------------------

class BenchRunRecorder:
    """Accumulates metrics for a single pipeline run, then persists a BenchRun.

    Lifecycle (driven from agent_runner.run):
        rec = BenchRunRecorder(prompt, layout_name, provider, model)
        rec.node_started(node) / rec.node_completed(node)   # per graph node
        rec.set_scoring(overall, grade, breakdown)          # when scoring is known
        rec.note_recursion_hit()                            # on a recursion error
        rec.set_layout_delta(base_layout, final_layout)     # placement quality
        run = rec.finalize(status="ok"|"error"|"aborted")   # → dict, also persisted
    """

    def __init__(
        self,
        prompt: str,
        layout_name: Optional[str],
        provider: Optional[str],
        model: Optional[str],
    ) -> None:
        self.run_id = uuid.uuid4().hex[:12]
        self.prompt = (prompt or "").strip()
        self.layout_name = layout_name or ""
        self.provider = (provider or "").lower()
        self.model = model or ""
        self.started_at = time.time()
        self._t0 = time.perf_counter()

        # node name → {start_offset_ms, total_ms, count}
        self._node_timings: Dict[str, Dict[str, float]] = {}
        self._open: Dict[str, float] = {}          # node → perf_counter at start
        self.timeline: List[Dict[str, Any]] = []   # {t_ms, node, status}
        self.category_calls: Dict[str, int] = {}   # category → call count
        self.reason_turns = 0
        self.tool_calls = 0
        self.recursion_hits = 0

        self.scoring: Optional[Dict[str, Any]] = None   # {overall, grade, metrics{}, weights{}}
        self.placement: Optional[Dict[str, Any]] = None  # module 01 metrics
        self.checkpoints = 0

    # ── timing / counts ──────────────────────────────────────────────────
    def _ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000.0, 1)

    def node_started(self, node: str) -> None:
        self._open[node] = time.perf_counter()
        t = self._node_timings.setdefault(node, {"start_ms": self._ms(), "total_ms": 0.0, "count": 0})
        t["count"] += 1
        cat = _NODE_CATEGORY.get(node, "other")
        self.category_calls[cat] = self.category_calls.get(cat, 0) + 1
        if node == "reason":
            self.reason_turns += 1
        self.timeline.append({"t_ms": self._ms(), "node": node, "status": "started"})

    def node_completed(self, node: str) -> None:
        start = self._open.pop(node, None)
        if start is not None:
            dur = (time.perf_counter() - start) * 1000.0
            t = self._node_timings.setdefault(node, {"start_ms": self._ms(), "total_ms": 0.0, "count": 0})
            t["total_ms"] = round(t["total_ms"] + dur, 1)
        self.timeline.append({"t_ms": self._ms(), "node": node, "status": "completed"})

    def node_error(self, node: str, detail: str = "") -> None:
        self._open.pop(node, None)
        self.timeline.append({"t_ms": self._ms(), "node": node, "status": "error", "detail": detail[:200]})

    def note_tool_calls(self, n: int) -> None:
        if n > 0:
            self.tool_calls += n

    def note_recursion_hit(self) -> None:
        self.recursion_hits += 1

    def note_checkpoint(self) -> None:
        self.checkpoints += 1

    # ── results ──────────────────────────────────────────────────────────
    def set_scoring(self, overall: Any, grade: Any, breakdown: Dict[str, Any]) -> None:
        """Record the latest scoring breakdown (last write wins → final score)."""
        breakdown = breakdown or {}
        if not breakdown and overall in (None, 0):
            return

        def _sc(tool: str) -> float:
            return round(float((breakdown.get(tool) or {}).get("score", 0) or 0), 1)

        def _wt(tool: str) -> float:
            return round(float((breakdown.get(tool) or {}).get("weight", 0) or 0), 3)

        tools = ["collision", "visibility", "path", "reachability", "orientation"]
        self.scoring = {
            "overall": round(float(overall or 0), 1),
            "grade": grade or "?",
            "metrics": {t: _sc(t) for t in tools},
            "weights": {t: _wt(t) for t in tools},
        }

    def set_placement_quality(self, metrics: Dict[str, Any]) -> None:
        """Best-effort module-01 metrics (req/placed/zone/collision-free/wall)."""
        if metrics:
            self.placement = metrics

    # ── finalize ─────────────────────────────────────────────────────────
    def finalize(self, status: str = "ok") -> Dict[str, Any]:
        # Close any still-open node (e.g. aborted mid-run).
        for node in list(self._open.keys()):
            self.node_completed(node)

        duration_s = round(time.perf_counter() - self._t0, 2)
        zones = max(self._node_timings.get("add_objects", {}).get("count", 0), 1)

        gantt = [
            {
                "node": node,
                "start_ms": round(t["start_ms"], 1),
                "total_ms": round(t["total_ms"], 1),
                "count": int(t["count"]),
            }
            for node, t in self._node_timings.items()
            if node != "setup" and t["total_ms"] > 0
        ]
        gantt.sort(key=lambda g: g["start_ms"])

        total_api_calls = sum(self.category_calls.values())
        tool_calls = self.tool_calls or self.category_calls.get("tools", 0)

        run: Dict[str, Any] = {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": time.time(),
            "status": status,
            "provider": self.provider,
            "model": self.model,
            "model_label": _model_label(self.provider, self.model),
            "layout_name": self.layout_name,
            "prompt": self.prompt[:240],
            "workflow": {
                "duration_s": duration_s,
                "duration_min": round(duration_s / 60.0, 2),
                "reason_turns": self.reason_turns,
                "turns_per_zone": round(self.reason_turns / zones, 1),
                "api_calls": total_api_calls,
                "tool_calls": tool_calls,
                "recursion_hits": self.recursion_hits,
                "checkpoints": self.checkpoints,
                "category_calls": dict(self.category_calls),
                "gantt": gantt,
            },
            "scoring": self.scoring,
            "placement": self.placement,
            "timeline": self.timeline[:200],
        }

        # Persist (append).
        with _LOCK:
            runs = _load_runs()
            runs.append(run)
            _save_runs(runs)
        return run


# ---------------------------------------------------------------------------
# Model labels + aggregates (consumed by the dashboard)
# ---------------------------------------------------------------------------

def _model_label(provider: str, model: str) -> str:
    """Short, human label for grouping (e.g. 'Gemini Flash', 'Sonnet')."""
    m = (model or "").lower()
    if "gemini" in m or provider == "google":
        if "pro" in m:
            return "Gemini Pro"
        if "flash" in m:
            return "Gemini Flash"
        return "Gemini"
    if "sonnet" in m:
        return "Sonnet"
    if "haiku" in m:
        return "Haiku"
    if "opus" in m:
        return "Opus"
    return model or provider or "unknown"


def _aggregate(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-model averages for the model-comparison + workflow modules."""
    by_model: Dict[str, Dict[str, Any]] = {}
    metrics = ["collision", "visibility", "path", "reachability", "orientation"]

    for r in runs:
        label = r.get("model_label") or "unknown"
        agg = by_model.setdefault(label, {
            "label": label,
            "provider": r.get("provider", ""),
            "runs": 0,
            "_overall": [],
            "_metrics": {m: [] for m in metrics},
            "_duration": [],
            "_turns": [],
            "_api": [],
        })
        agg["runs"] += 1
        sc = r.get("scoring") or {}
        if sc.get("overall") is not None:
            agg["_overall"].append(sc["overall"])
        for m in metrics:
            v = (sc.get("metrics") or {}).get(m)
            if v is not None:
                agg["_metrics"][m].append(v)
        wf = r.get("workflow") or {}
        if wf.get("duration_s") is not None:
            agg["_duration"].append(wf["duration_s"])
        if wf.get("reason_turns") is not None:
            agg["_turns"].append(wf["reason_turns"])
        if wf.get("api_calls") is not None:
            agg["_api"].append(wf["api_calls"])

    def _avg(xs: List[float]) -> Optional[float]:
        return round(sum(xs) / len(xs), 1) if xs else None

    models: List[Dict[str, Any]] = []
    for agg in by_model.values():
        models.append({
            "label": agg["label"],
            "provider": agg["provider"],
            "runs": agg["runs"],
            "overall": _avg(agg["_overall"]),
            "metrics": {m: _avg(agg["_metrics"][m]) for m in metrics},
            "avg_duration_s": _avg(agg["_duration"]),
            "avg_turns": _avg(agg["_turns"]),
            "avg_api_calls": _avg(agg["_api"]),
        })
    models.sort(key=lambda x: (x["overall"] is None, -(x["overall"] or 0)))
    return {"models": models, "metrics": metrics}


# ---------------------------------------------------------------------------
# Public read/clear API (used by api_routes)
# ---------------------------------------------------------------------------

def get_all() -> Dict[str, Any]:
    """All recorded runs (newest first) + per-model aggregates."""
    with _LOCK:
        runs = _load_runs()
    ordered = list(reversed(runs))
    return {
        "runs": ordered,
        "aggregate": _aggregate(runs),
        "count": len(runs),
    }


def clear_all() -> int:
    """Delete the entire benchmark history. Returns how many runs were removed."""
    with _LOCK:
        runs = _load_runs()
        n = len(runs)
        _save_runs([])
    return n
