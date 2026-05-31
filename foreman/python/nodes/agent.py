from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


def _normalize_name(name: str) -> str:
	return re.sub(r"[^a-z0-9]", "", name.lower())


def _resolve_team_folder(agent_name: str) -> str | None:
	normalized = _normalize_name(agent_name)

	direct_match = re.match(r"team0*([1-6])$", normalized)
	if direct_match:
		return f"team_{int(direct_match.group(1)):02d}"

	aliases: dict[str, str] = {
		"permanenceos": "team_01",
		"sensi": "team_02",
		"spatialflow": "team_03",
		"spatialflowagent": "team_03",
		"siteagent": "team_04",
		"terapilot": "team_04",
		"costagent": "team_05",
		"regulationcostagent": "team_05",
		"inhabit": "team_06",
		"inhabitagent": "team_06",
	}
	return aliases.get(normalized)


def _extract_prompt(arguments: dict[str, Any]) -> str:
	for key in ("prompt", "request", "instruction", "query", "message", "task"):
		value = arguments.get(key)
		if isinstance(value, str) and value.strip():
			return value.strip()

	if arguments:
		return "Subtask details: " + json.dumps(arguments, ensure_ascii=False)
	return "Complete the delegated subtask and return concise results."


def _parse_team_cli_output(stdout: str) -> tuple[str, str | None]:
	"""Parse README-style team output.

	Returns (final_response_text, edited_layout_json_text_or_none).
	"""
	text = stdout.strip()
	if not text:
		return "", None

	final_match = re.search(r"(?im)^\s*Final Response\s*:\s*", text)
	layout_match = re.search(r"(?im)^\s*Edited Layout JSON\s*:\s*", text)

	if final_match and layout_match and final_match.start() < layout_match.start():
		final_text = text[final_match.end():layout_match.start()].strip()
		layout_text = text[layout_match.end():].strip()
		if layout_text.lower() == "no layout changes":
			layout_text = None
		return final_text, layout_text

	# Compatibility fallback for teams still printing the old format.
	legacy_match = re.search(r"(?im)^\s*Agent response\s*:\s*", text)
	if legacy_match:
		return text[legacy_match.end():].strip(), None

	return text, None


def _truncate(text: str, max_len: int = 1200) -> str:
	if len(text) <= max_len:
		return text
	return text[: max_len - 3] + "..."


def build_agent_node(ctx: Any):
	"""Return a graph node that executes delegated team-agent CLI calls."""

	repo_root = Path(__file__).resolve().parents[3] # adjust as needed if repo structure changes
	python_executable = sys.executable or "python" # use the same Python interpreter running the foreman

	def agent_node(state: dict[str, Any]) -> dict[str, Any]:
		pending_calls = state.get("pending_agent_calls")
		if not isinstance(pending_calls, list) or not pending_calls:
			state["pending_agent_calls"] = None
			return state

		for call in pending_calls:
			call_name = str(call.get("name", "")).strip()
			arguments = call.get("arguments")
			if not isinstance(arguments, dict):
				arguments = {}

			team_folder = _resolve_team_folder(call_name)
			prompt = _extract_prompt(arguments)
			layout_json = state.get("layout_json_string")
			if not isinstance(layout_json, str) or not layout_json.strip():
				layout_json = "{}"

			if not team_folder:
				state["messages"].append(
					{
						"role": "assistant",
						"content": (
							f"Agent delegation skipped: unknown agent '{call_name}'. "
							"Expected team_01..team_06 or a known alias."
						),
					}
				)
				continue

			team_main = repo_root / team_folder / "python" / "main.py"
			if not team_main.exists():
				state["messages"].append(
					{
						"role": "assistant",
						"content": (
							f"Agent delegation failed: CLI entrypoint not found for {team_folder} "
							f"at {team_main}."
						),
					}
				)
				continue

			command = [
				python_executable,
				str(team_main),
				"--prompt",
				prompt,
				"--layout_json",
				layout_json,
			]

			try:
				completed = subprocess.run(
					command,
					cwd=str(repo_root),
					capture_output=True,
					text=True,
					encoding="utf-8",
					timeout=180,
					check=False,
				)
			except subprocess.TimeoutExpired as exc:
				state["messages"].append(
					{
						"role": "assistant",
						"content": (
							f"Agent delegation timed out for {team_folder}. "
							f"Prompt: {_truncate(prompt)}"
						),
					}
				)
				continue
			except Exception as exc:  # keep orchestration running
				state["messages"].append(
					{
						"role": "assistant",
						"content": (
							f"Agent delegation crashed for {team_folder}: {exc}"
						),
					}
				)
				continue

			stdout = completed.stdout or ""
			stderr = completed.stderr or ""
			parsed_response, parsed_layout = _parse_team_cli_output(stdout)

			layout_status = "No layout changes"
			if parsed_layout:
				try:
					parsed_layout_data = json.loads(parsed_layout)
				except json.JSONDecodeError:
					layout_status = "Invalid Edited Layout JSON returned"
				else:
					state["layout_json_string"] = json.dumps(
						parsed_layout_data, ensure_ascii=False
					)
					layout_status = "Layout updated"

			summary = (
				f"Delegated to {team_folder} (agent name: {call_name}).\n"
				f"Exit code: {completed.returncode}\n"
				f"Final response:\n{_truncate(parsed_response)}\n"
				f"Edited layout status: {layout_status}"
			)

			if completed.returncode != 0:
				summary += f"\nStderr:\n{_truncate(stderr)}"

			state["messages"].append({"role": "assistant", "content": summary})

		state["pending_agent_calls"] = None
		return state

	return agent_node