from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

TEAM_ROOT = Path(__file__).resolve().parents[1]
if str(TEAM_ROOT) not in sys.path:
    sys.path.insert(0, str(TEAM_ROOT))

from agent.decision_engine import OpenAIDecisionEngine


class FakeLlm:
    def __init__(self, content: str = '{"action": "generate_shape", "reasoning": "ok", "user_question": "", "tool_calls": []}') -> None:
        self.timeout = 12
        self.model_kwargs = {"seed": 7}
        self.invocations: list[list[dict[str, str]]] = []
        self.content = content

    def invoke(self, messages: list[dict[str, str]]):
        self.invocations.append(messages)
        return type("Result", (), {"content": self.content})()


class BenchmarkingOverrideTests(unittest.TestCase):
    def test_decide_uses_override_llm_when_requested(self) -> None:
        base_llm = FakeLlm()
        override_llm = FakeLlm()
        engine = OpenAIDecisionEngine(
            llm=base_llm,
            decision_provider="cloudflare",
            decision_model="@cf/meta/llama-3.1-8b-instruct",
        )

        with patch("agent.decision_engine.resolve_active_llm", return_value=override_llm) as mocked_resolve:
            result = engine._invoke_json(system_prompt="system", user_prompt="user")

        self.assertEqual(result["action"], "generate_shape")
        self.assertEqual(len(base_llm.invocations), 0)
        self.assertEqual(len(override_llm.invocations), 1)
        mocked_resolve.assert_called_once_with(
            base_llm,
            provider="cloudflare",
            model="@cf/meta/llama-3.1-8b-instruct",
        )

    def test_report_uses_report_override_llm_when_requested(self) -> None:
        base_llm = FakeLlm(content="base")
        override_llm = FakeLlm(content="benchmark report")
        engine = OpenAIDecisionEngine(
            llm=base_llm,
            report_provider="openai",
            report_model="gpt-4.1-mini",
        )

        with patch("agent.decision_engine.resolve_active_llm", return_value=override_llm) as mocked_resolve:
            report = engine.build_report({"user_prompt": "Summarize"})

        self.assertEqual(report, "benchmark report")
        self.assertEqual(len(base_llm.invocations), 0)
        self.assertEqual(len(override_llm.invocations), 1)
        mocked_resolve.assert_called_once_with(
            base_llm,
            provider="openai",
            model="gpt-4.1-mini",
        )

    def test_resolve_active_llm_requires_provider_context_for_model_only_override(self) -> None:
        from agent.llm import resolve_active_llm

        base_llm = FakeLlm()
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                resolve_active_llm(base_llm, model="gpt-4.1-mini")


if __name__ == "__main__":
    unittest.main()