from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _team_root() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BenchmarkPaths:
    root_dir: Path
    json_dir: Path
    csv_path: Path


def default_benchmark_paths() -> BenchmarkPaths:
    root_dir = _team_root() / "benchmarks"
    return BenchmarkPaths(
        root_dir=root_dir,
        json_dir=root_dir / "json",
        csv_path=root_dir / "benchmark_runs.csv",
    )


def write_benchmark_logs(
    *,
    prompt: str,
    default_provider: str | None,
    default_model: str | None,
    decision_provider: str | None,
    decision_model: str | None,
    report_provider: str | None,
    report_model: str | None,
    started_at: datetime,
    completed_at: datetime,
    final_state: dict[str, Any] | None,
    final_response: str | None,
    output_layout_path: Path | None,
    error_message: str | None = None,
    paths: BenchmarkPaths | None = None,
) -> dict[str, Any]:
    active_paths = paths or default_benchmark_paths()
    active_paths.root_dir.mkdir(parents=True, exist_ok=True)
    active_paths.json_dir.mkdir(parents=True, exist_ok=True)

    record = _build_benchmark_record(
        prompt=prompt,
        default_provider=default_provider,
        default_model=default_model,
        decision_provider=decision_provider,
        decision_model=decision_model,
        report_provider=report_provider,
        report_model=report_model,
        started_at=started_at,
        completed_at=completed_at,
        final_state=final_state or {},
        final_response=final_response,
        output_layout_path=output_layout_path,
        error_message=error_message,
    )

    json_path = active_paths.json_dir / f"{record['run_id']}.json"
    json_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _append_csv_summary(active_paths.csv_path, record, json_path)
    return record


def _build_benchmark_record(
    *,
    prompt: str,
    default_provider: str | None,
    default_model: str | None,
    decision_provider: str | None,
    decision_model: str | None,
    report_provider: str | None,
    report_model: str | None,
    started_at: datetime,
    completed_at: datetime,
    final_state: dict[str, Any],
    final_response: str | None,
    output_layout_path: Path | None,
    error_message: str | None,
) -> dict[str, Any]:
    normalized_started_at = _normalize_timestamp(started_at)
    normalized_completed_at = _normalize_timestamp(completed_at)
    tool_history = _normalize_tool_history(final_state.get("tool_history", []))
    tool_names = [record.get("tool", "") for record in tool_history if record.get("tool")]
    layout_written = bool(output_layout_path and output_layout_path.exists())
    final_layout = final_state.get("layout_json")
    run_id = f"{normalized_completed_at.strftime('%Y%m%dT%H%M%S%fZ')}_{uuid4().hex[:8]}"

    return {
        "run_id": run_id,
        "status": "failed" if error_message else "completed",
        "prompt": prompt,
        "started_at": normalized_started_at.isoformat(),
        "completed_at": normalized_completed_at.isoformat(),
        "duration_seconds": round((normalized_completed_at - normalized_started_at).total_seconds(), 3),
        "default_provider": default_provider,
        "default_model": default_model,
        "decision_provider": decision_provider or default_provider,
        "decision_model": decision_model or default_model,
        "report_provider": report_provider or default_provider,
        "report_model": report_model or default_model,
        "final_response": final_response or "",
        "error_message": error_message or "",
        "tool_call_count": len(tool_history),
        "tool_names": tool_names,
        "unique_tool_names": sorted(set(tool_names)),
        "geometry_id": final_state.get("geometry_id"),
        "violations": _ensure_json_safe_list(final_state.get("violations", [])),
        "evaluation_results": _ensure_json_safe_dict(final_state.get("evaluation_results", {})),
        "placement_fit_summary": _ensure_json_safe_dict(final_state.get("placement_fit_summary", {})),
        "layout_output_path": str(output_layout_path) if output_layout_path else "",
        "layout_written": layout_written,
        "layout_json_present": isinstance(final_layout, str) and bool(final_layout.strip()),
        "active_step_id": final_state.get("active_step_id"),
        "current_action": final_state.get("current_action"),
        "messages": _ensure_json_safe_list(final_state.get("messages", [])),
        "tool_history": tool_history,
    }


def _append_csv_summary(csv_path: Path, record: dict[str, Any], json_path: Path) -> None:
    row = _build_csv_row(record, json_path)
    write_header = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _build_csv_row(record: dict[str, Any], json_path: Path) -> dict[str, Any]:
    return {
        "run_id": record["run_id"],
        "status": record["status"],
        "started_at": record["started_at"],
        "completed_at": record["completed_at"],
        "duration_seconds": record["duration_seconds"],
        "default_provider": record["default_provider"],
        "default_model": record["default_model"],
        "decision_provider": record["decision_provider"],
        "decision_model": record["decision_model"],
        "report_provider": record["report_provider"],
        "report_model": record["report_model"],
        "tool_call_count": record["tool_call_count"],
        "unique_tool_names": " | ".join(record["unique_tool_names"]),
        "geometry_id": record["geometry_id"] or "",
        "violation_count": len(record["violations"]),
        "layout_written": record["layout_written"],
        "layout_json_present": record["layout_json_present"],
        "active_step_id": record["active_step_id"] or "",
        "current_action": record["current_action"] or "",
        "error_message": record["error_message"],
        "prompt": record["prompt"],
        "final_response": record["final_response"],
        "json_record_path": str(json_path),
    }


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_tool_history(tool_history: Any) -> list[dict[str, Any]]:
    if not isinstance(tool_history, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in tool_history:
        if isinstance(item, dict):
            normalized.append(_ensure_json_safe_dict(item))
    return normalized


def _ensure_json_safe_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        normalized[str(key)] = _ensure_json_safe_value(item)
    return normalized


def _ensure_json_safe_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [_ensure_json_safe_value(item) for item in value]


def _ensure_json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return _ensure_json_safe_dict(value)
    if isinstance(value, list):
        return _ensure_json_safe_list(value)
    if isinstance(value, tuple):
        return [_ensure_json_safe_value(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _ensure_json_safe_dict(asdict(value))
    return str(value)