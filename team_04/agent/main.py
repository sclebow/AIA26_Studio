from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from langchain_openai import ChatOpenAI

from .benchmark_logger import write_benchmark_logs
from .config import load_settings
from .decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
from .graph import run_agent
from .mcp_client import CompositeToolClient, HttpMcpClient, build_default_local_tool_client
from .tool_catalog import ToolCatalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Team 04 TerraPilot agent.")
    parser.add_argument("--prompt", required=True, help="User prompt for the site-design workflow")
    parser.add_argument("--layout_json", default=None, help="Optional JSON string representing the input layout")
    parser.add_argument("--layout_file", default=None, help="Optional path to a JSON file representing the input layout (use instead of --layout_json to avoid shell quoting issues)")
    parser.add_argument("--decision-provider", help="Optional provider override for supervisor/tool-routing calls")
    parser.add_argument("--decision-model", help="Optional model override for supervisor/tool-routing calls")
    parser.add_argument("--report-provider", help="Optional provider override for final report generation")
    parser.add_argument("--report-model", help="Optional model override for final report generation")
    return parser.parse_args()


def _build_output_payload(final_state: dict[str, object], final_response: str) -> dict[str, object]:
    return {
        "final_response": final_response,
        "geometry_id": final_state.get("geometry_id"),
        "site_boundary": final_state.get("site_boundary", []),
        "site_context": final_state.get("site_context", {}),
        "shape_context": final_state.get("shape_context", {}),
        "placed_buildings": final_state.get("placed_buildings", []),
        "violations": final_state.get("violations", []),
        "evaluation_results": final_state.get("evaluation_results", {}),
        "placement_fit_summary": final_state.get("placement_fit_summary", {}),
        "tool_history": final_state.get("tool_history", []),
    }


def main() -> None:
    args = parse_args()
    started_at = datetime.now(timezone.utc)
    settings = None
    client = None
    final_state: dict[str, object] = {}
    final_response = ""
    error_message = ""
    active_decision_provider = args.decision_provider
    active_decision_model = args.decision_model
    active_report_provider = args.report_provider
    active_report_model = args.report_model

    input_layout: dict[str, object] = {}
    if args.layout_file is not None and args.layout_json is not None:
        print("Error: --layout_json and --layout_file cannot be used together.", file=sys.stderr)
        sys.exit(1)
    if args.layout_file is not None:
        try:
            input_layout = json.loads(Path(args.layout_file).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Error: --layout_file could not be read as JSON: {exc}", file=sys.stderr)
            sys.exit(1)
    elif args.layout_json is not None:
        try:
            input_layout = json.loads(args.layout_json)
        except json.JSONDecodeError as exc:
            print(f"Error: --layout_json is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(1)

    try:
        settings = load_settings()
        active_decision_provider = active_decision_provider or settings.decision_llm_provider or settings.llm_provider
        active_decision_model = active_decision_model or settings.decision_llm_model or settings.llm_model
        active_report_provider = active_report_provider or settings.report_llm_provider or settings.llm_provider
        active_report_model = active_report_model or settings.report_llm_model or settings.llm_model

        local_client = build_default_local_tool_client()
        mcp_client = HttpMcpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
        try:
            mcp_client.initialize()
            client = CompositeToolClient([local_client, mcp_client])
        except Exception as mcp_exc:
            print(f"[warning] MCP server unreachable ({mcp_exc}); running with local tools only.", file=sys.stderr)
            mcp_client.close()
            client = local_client
        discovered_tools = client.list_tools()
        catalog = ToolCatalog.from_discovered_tools(discovered_tools)
        llm = ChatOpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            model=settings.llm_model,
            timeout=settings.request_timeout_seconds,
            temperature=0,
        )
        engine = OpenAIDecisionEngine(
            llm=llm,
            decision_provider=args.decision_provider or settings.decision_llm_provider,
            decision_model=args.decision_model or settings.decision_llm_model,
            report_provider=args.report_provider or settings.report_llm_provider,
            report_model=args.report_model or settings.report_llm_model,
        )
        planner = RuleBasedPlanner()
        final_state = run_agent(
            user_prompt=args.prompt,
            decision_engine=engine,
            tool_client=client,
            catalog=catalog,
            initial_layout=input_layout,
            max_optimization_cycles=settings.max_optimization_cycles,
            planner=planner,
        )
        final_response = final_state.get("final_response") or "Workflow completed without a final response."
        output_payload = _build_output_payload(final_state, final_response)
        settings.output_result_path.write_text(
            json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        placed_buildings = final_state.get("placed_buildings") or []
        has_edits = bool(placed_buildings or final_state.get("geometry_id") or input_layout)
        edited_layout: dict[str, object] | None = None
        if has_edits:
            edited_layout = dict(input_layout)
            edited_layout.update(
                {
                    "placed_buildings": placed_buildings,
                    "site_boundary": final_state.get("site_boundary", []),
                    "site_context": final_state.get("site_context", {}),
                    "shape_context": final_state.get("shape_context", {}),
                    "violations": final_state.get("violations", []),
                    "placement_fit_summary": final_state.get("placement_fit_summary", {}),
                }
            )

        print("Final Response:")
        print(final_response)
        print("Edited Layout JSON:")
        if edited_layout is not None:
            print(json.dumps(edited_layout, indent=2, ensure_ascii=False))
        else:
            print("No layout changes")
    except Exception as exc:
        error_message = str(exc)
        raise
    finally:
        completed_at = datetime.now(timezone.utc)
        try:
            write_benchmark_logs(
                prompt=args.prompt,
                default_provider=settings.llm_provider if settings is not None else None,
                default_model=settings.llm_model if settings is not None else None,
                decision_provider=active_decision_provider,
                decision_model=active_decision_model,
                report_provider=active_report_provider,
                report_model=active_report_model,
                started_at=started_at,
                completed_at=completed_at,
                final_state=final_state,
                final_response=final_response,
                output_result_path=settings.output_result_path if settings is not None else None,
                error_message=error_message or None,
            )
        except Exception as logging_exc:
            print(f"[benchmark] Failed to write benchmark logs: {logging_exc}", file=sys.stderr)
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()