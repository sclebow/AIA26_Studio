from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from langchain_openai import ChatOpenAI

from .benchmark_logger import write_benchmark_logs
from .config import load_initial_layout, load_settings
from .decision_engine import OpenAIDecisionEngine, RuleBasedPlanner
from .graph import run_agent
from .mcp_client import CompositeToolClient, HttpMcpClient, build_default_local_tool_client
from .tool_catalog import ToolCatalog


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Team 04 TerraPilot agent.")
    parser.add_argument("prompt", help="User prompt for the site-design workflow")
    parser.add_argument("--decision-provider", help="Optional provider override for supervisor/tool-routing calls")
    parser.add_argument("--decision-model", help="Optional model override for supervisor/tool-routing calls")
    parser.add_argument("--report-provider", help="Optional provider override for final report generation")
    parser.add_argument("--report-model", help="Optional model override for final report generation")
    return parser.parse_args()


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
    try:
        settings = load_settings()
        initial_layout = load_initial_layout(settings.initial_layout_path)
        active_decision_provider = active_decision_provider or settings.decision_llm_provider or settings.llm_provider
        active_decision_model = active_decision_model or settings.decision_llm_model or settings.llm_model
        active_report_provider = active_report_provider or settings.report_llm_provider or settings.llm_provider
        active_report_model = active_report_model or settings.report_llm_model or settings.llm_model

        local_client = build_default_local_tool_client()
        mcp_client = HttpMcpClient(settings.mcp_endpoint, settings.request_timeout_seconds)
        mcp_client.initialize()
        client = CompositeToolClient([local_client, mcp_client])
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
            initial_layout=initial_layout,
            max_optimization_cycles=settings.max_optimization_cycles,
            planner=planner,
        )
        final_layout = final_state.get("layout_json")
        if isinstance(final_layout, str) and final_layout.strip():
            settings.output_layout_path.write_text(final_layout, encoding="utf-8")
        final_response = final_state.get("final_response") or "Workflow completed without a final response."
        print(final_response)
    except Exception as exc:
        error_message = str(exc)
        raise
    finally:
        completed_at = datetime.now(timezone.utc)
        try:
            write_benchmark_logs(
                prompt=args.prompt,
                default_provider=settings.llm_provider,
                default_model=settings.llm_model,
                decision_provider=active_decision_provider,
                decision_model=active_decision_model,
                report_provider=active_report_provider,
                report_model=active_report_model,
                started_at=started_at,
                completed_at=completed_at,
                final_state=final_state,
                final_response=final_response,
                output_layout_path=settings.output_layout_path,
                error_message=error_message or None,
            )
        except Exception as logging_exc:
            print(f"[benchmark] Failed to write benchmark logs: {logging_exc}", file=sys.stderr)
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()