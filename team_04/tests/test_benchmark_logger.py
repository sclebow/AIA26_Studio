from __future__ import annotations

import csv
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.benchmark_logger import BenchmarkPaths, write_benchmark_logs


class BenchmarkLoggerTests(unittest.TestCase):
    def test_write_benchmark_logs_creates_json_and_csv_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            paths = BenchmarkPaths(
                root_dir=root_dir,
                json_dir=root_dir / "json",
                csv_path=root_dir / "benchmark_runs.csv",
            )
            output_layout_path = root_dir / "team_04_edited_layout.json"
            output_layout_path.write_text('{"ok": true}\n', encoding="utf-8")

            record = write_benchmark_logs(
                prompt="Generate one building.",
                default_provider="cloudflare",
                default_model="@cf/meta/llama-3.1-8b-instruct",
                decision_provider="cloudflare",
                decision_model="@cf/meta/llama-3.1-8b-instruct",
                report_provider="openai",
                report_model="gpt-4.1-mini",
                started_at=datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 6, 1, 8, 0, 2, tzinfo=timezone.utc),
                final_state={
                    "geometry_id": "shape-001",
                    "active_step_id": "report",
                    "current_action": "report",
                    "violations": [],
                    "messages": ["ok"],
                    "tool_history": [
                        {"tool": "generate_building_boundary", "message": "executed"},
                        {"tool": "setback_checker", "message": "executed"},
                    ],
                },
                final_response="Completed.",
                output_layout_path=output_layout_path,
                paths=paths,
            )

            json_path = paths.json_dir / f"{record['run_id']}.json"
            self.assertTrue(json_path.exists())
            self.assertTrue(paths.csv_path.exists())
            self.assertEqual(record["status"], "completed")
            self.assertEqual(record["tool_call_count"], 2)
            self.assertEqual(record["unique_tool_names"], ["generate_building_boundary", "setback_checker"])

            parsed_json = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(parsed_json["final_response"], "Completed.")
            self.assertTrue(parsed_json["layout_written"])

            with paths.csv_path.open("r", encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "completed")
            self.assertEqual(rows[0]["tool_call_count"], "2")

    def test_write_benchmark_logs_records_failures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root_dir = Path(temp_dir)
            paths = BenchmarkPaths(
                root_dir=root_dir,
                json_dir=root_dir / "json",
                csv_path=root_dir / "benchmark_runs.csv",
            )

            record = write_benchmark_logs(
                prompt="Generate one building.",
                default_provider="openai",
                default_model="gpt-4.1-mini",
                decision_provider="openai",
                decision_model="gpt-4.1-mini",
                report_provider="openai",
                report_model="gpt-4.1-mini",
                started_at=datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc),
                completed_at=datetime(2026, 6, 1, 8, 0, 1, tzinfo=timezone.utc),
                final_state={},
                final_response="",
                output_layout_path=root_dir / "missing.json",
                error_message="network timeout",
                paths=paths,
            )

            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["error_message"], "network timeout")
            self.assertFalse(record["layout_written"])


if __name__ == "__main__":
    unittest.main()