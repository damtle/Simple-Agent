from __future__ import annotations

import importlib

from simple_agent import Agent, TerminationReason
from simple_agent.action import (
    AgentAction,
    action_fingerprint,
    snapshot_action,
)
from tests.conftest import SYSTEM_PROMPT
from tests.fakes import MockLLM


def test_action_snapshot_is_independent() -> None:
    arguments: dict[str, object] = {
        "city": "北京",
        "nested": {"value": 1},
    }
    snapshot = snapshot_action(
        AgentAction("weather", arguments, reason="查询天气。")
    )

    arguments["city"] = "上海"
    nested = arguments["nested"]
    assert isinstance(nested, dict)
    nested["value"] = 2

    assert snapshot.arguments == {
        "city": "北京",
        "nested": {"value": 1},
    }
    assert snapshot.reason == "查询天气。"


def test_fingerprint_ignores_reason() -> None:
    first = AgentAction("echo", {"text": "hello"}, reason="第一次。")
    second = AgentAction("echo", {"text": "hello"}, reason="第二次。")

    assert action_fingerprint(first) == action_fingerprint(second)


def test_result_state_and_trace_share_reason(echo_registry) -> None:
    execution = Agent(
        llm=MockLLM(
            ['{"action":"finish","arguments":{"answer":"完成。"}}']
        ),
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.SUCCESS
    assert execution.state.termination_reason is TerminationReason.SUCCESS
    assert execution.trace.termination_reason is TerminationReason.SUCCESS
    assert execution.trace.records == tuple(execution.state.records)
    assert execution.message == "完成。"


def test_public_import_has_no_environment_side_effect(monkeypatch) -> None:
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID"):
        monkeypatch.delenv(key, raising=False)

    module = importlib.import_module("simple_agent")
    assert module.__version__ == "1.0.0"
    assert module.Agent is Agent


def test_public_api_is_small() -> None:
    module = importlib.import_module("simple_agent")
    assert set(module.__all__) == {
        "Agent",
        "AgentExecution",
        "AgentRunResult",
        "LLM",
        "LLMRequestError",
        "OpenAIChatLLM",
        "RetryPolicy",
        "TerminationReason",
        "Tool",
        "ToolExecutionResult",
        "ToolRegistry",
    }
