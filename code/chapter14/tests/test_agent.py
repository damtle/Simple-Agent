from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
import os
import subprocess
import sys

import pytest

from simple_agent import Agent, LLMRequestError, TerminationReason, Tool, ToolRegistry
from simple_agent.llm import Message
from simple_agent.tools import TemporaryToolError, ToolInputError


class MockLLM:
    def __init__(self, outputs: list[str | Exception]) -> None:
        self._outputs = iter(outputs)
        self.call_count = 0
        self.calls: list[list[Message]] = []

    def generate(self, messages: Sequence[Message]) -> str:
        self.call_count += 1
        self.calls.append(deepcopy(list(messages)))
        try:
            output = next(self._outputs)
        except StopIteration as error:
            raise AssertionError("MockLLM 没有更多预设输出。") from error
        if isinstance(output, Exception):
            raise output
        return output


def validate_weather(arguments: dict[str, object]) -> None:
    if set(arguments) != {"city"} or not isinstance(arguments["city"], str):
        raise ValueError("get_weather 只接受字符串 city。")


def validate_calculator(arguments: dict[str, object]) -> None:
    if set(arguments) != {"operation", "a", "b"}:
        raise ValueError("calculator 参数错误。")


def create_tools() -> ToolRegistry:
    registry = ToolRegistry()

    def weather(city: str) -> str:
        if city == "成都":
            raise ToolInputError("没有成都数据。", error_type="not_found")
        return f"{city}晴，30℃。"

    registry.register(
        Tool(
            "get_weather",
            "查询模拟天气。",
            {"city": "城市"},
            weather,
            validator=validate_weather,
        )
    )
    registry.register(
        Tool(
            "calculator",
            "计算。",
            {"operation": "操作", "a": "数字", "b": "数字"},
            lambda operation, a, b: str(a + b),
            validator=validate_calculator,
        )
    )
    return registry


def test_agent_finishes_after_tool_result() -> None:
    llm = MockLLM(
        [
            '{"action":"get_weather","arguments":{"city":"北京"}}',
            '{"action":"finish","arguments":{"answer":"查询完成。"}}',
        ]
    )
    execution = Agent(llm=llm, tools=create_tools()).run("查询北京天气。")

    assert execution.success is True
    assert execution.termination_reason is TerminationReason.FINISHED
    assert execution.state.step == 2
    assert execution.state.llm_calls == 2
    assert execution.state.tool_calls == 1
    assert len(execution.records) == 2


def test_observation_enters_next_model_call() -> None:
    llm = MockLLM(
        [
            '{"action":"get_weather","arguments":{"city":"北京"}}',
            '{"action":"finish","arguments":{"answer":"完成。"}}',
        ]
    )
    Agent(llm=llm, tools=create_tools()).run("查询天气。")

    assert any(
        message["role"] == "user"
        and message["content"].startswith("Observation:")
        and "get_weather" in message["content"]
        for message in llm.calls[1]
    )


def test_format_retry_stays_in_same_step() -> None:
    llm = MockLLM(
        [
            '{"action":"get_weather","arguments":{"city":"北京",}}',
            '{"action":"get_weather","arguments":{"city":"北京"}}',
            '{"action":"finish","arguments":{"answer":"完成。"}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=create_tools(),
        max_format_retries=1,
    ).run("查询天气。")

    assert execution.state.step == 2
    assert execution.state.llm_calls == 3
    assert execution.state.parse_failures == 1
    assert len(execution.records[0].model_attempts) == 2


def test_parse_retries_exhausted() -> None:
    execution = Agent(
        llm=MockLLM(["bad", "still bad", "again bad"]),
        tools=create_tools(),
        max_format_retries=2,
    ).run("查询天气。")

    assert execution.success is False
    assert execution.termination_reason is TerminationReason.PARSE_ERROR
    assert execution.state.tool_calls == 0
    assert len(execution.records[0].model_attempts) == 3


def test_max_steps_terminates_loop() -> None:
    llm = MockLLM(
        [
            '{"action":"calculator","arguments":{"operation":"add","a":1,"b":1}}',
            '{"action":"calculator","arguments":{"operation":"add","a":2,"b":2}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=create_tools(),
        max_steps=2,
        max_same_action=10,
    ).run("持续计算。")

    assert execution.termination_reason is TerminationReason.MAX_STEPS
    assert execution.state.tool_calls == 2
    assert len(execution.records) == 2


def test_repeated_action_stops_before_third_execution() -> None:
    output = '{"action":"get_weather","arguments":{"city":"北京"}}'
    execution = Agent(
        llm=MockLLM([output, output, output]),
        tools=create_tools(),
        max_same_action=2,
    ).run("重复测试。")

    assert execution.termination_reason is TerminationReason.REPEATED_ACTION
    assert execution.state.tool_calls == 2
    assert execution.state.step == 3
    assert execution.records[-1].tool_result is None


def test_tool_error_followed_by_finish_is_failure() -> None:
    llm = MockLLM(
        [
            '{"action":"get_weather","arguments":{"city":"成都"}}',
            '{"action":"finish","arguments":{"answer":"当前没有数据。"}}',
        ]
    )
    execution = Agent(llm=llm, tools=create_tools()).run("查询成都天气。")

    assert execution.termination_reason is TerminationReason.TOOL_ERROR
    assert execution.message == "当前没有数据。"
    assert execution.records[0].tool_result is not None
    assert execution.records[0].tool_result.error_type == "not_found"


def test_safe_tool_retry_updates_actual_call_count() -> None:
    remaining = {"count": 1}

    def flaky() -> str:
        if remaining["count"]:
            remaining["count"] -= 1
            raise TemporaryToolError("临时失败。")
        return "恢复成功。"

    tools = ToolRegistry()
    tools.register(Tool("flaky", "临时工具。", {}, flaky, retryable=True))
    llm = MockLLM(
        [
            '{"action":"flaky","arguments":{}}',
            '{"action":"finish","arguments":{"answer":"完成。"}}',
        ]
    )
    execution = Agent(llm=llm, tools=tools, max_tool_retries=1).run("测试。")

    assert execution.success is True
    assert execution.state.tool_calls == 2
    assert execution.records[0].tool_result is not None
    assert execution.records[0].tool_result.success is True


def test_llm_error_is_recorded() -> None:
    execution = Agent(
        llm=MockLLM([LLMRequestError("模拟超时。")]),
        tools=create_tools(),
    ).run("查询天气。")

    assert execution.termination_reason is TerminationReason.LLM_ERROR
    assert execution.result.steps == 0
    assert execution.state.step == 1
    assert execution.state.llm_calls == 1
    assert "模拟超时" in (execution.records[0].error or "")


def test_timeout_can_use_fake_clock() -> None:
    values = iter([0.0, 1.0])
    execution = Agent(
        llm=MockLLM([]),
        tools=create_tools(),
        max_run_seconds=0.5,
        time_fn=lambda: next(values),
    ).run("测试超时。")

    assert execution.termination_reason is TerminationReason.TIMEOUT
    assert execution.state.step == 0
    assert execution.state.llm_calls == 0
    assert execution.records == ()


def test_user_rejection_prevents_execution() -> None:
    counter = {"calls": 0}

    def send() -> str:
        counter["calls"] += 1
        return "sent"

    tools = ToolRegistry()
    tools.register(
        Tool("send", "发送。", {}, send, requires_confirmation=True)
    )
    execution = Agent(
        llm=MockLLM(['{"action":"send","arguments":{}}']),
        tools=tools,
        confirmation_callback=lambda action: False,
    ).run("发送。")

    assert execution.termination_reason is TerminationReason.USER_REJECTED
    assert counter["calls"] == 0
    assert execution.state.tool_calls == 0


def test_confirmed_high_risk_tool_executes() -> None:
    counter = {"calls": 0}

    def send() -> str:
        counter["calls"] += 1
        return "sent"

    tools = ToolRegistry()
    tools.register(Tool("send", "发送。", {}, send, requires_confirmation=True))
    llm = MockLLM(
        [
            '{"action":"send","arguments":{}}',
            '{"action":"finish","arguments":{"answer":"已发送。"}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=tools,
        confirmation_callback=lambda action: True,
    ).run("发送。")

    assert execution.success is True
    assert counter["calls"] == 1


def test_require_reason_mode() -> None:
    llm = MockLLM(
        [
            '{"reason":"任务可以直接完成。","action":"finish",'
            '"arguments":{"answer":"完成。"}}'
        ]
    )
    execution = Agent(llm=llm, tools=create_tools(), require_reason=True).run("任务。")
    assert execution.success is True
    assert execution.records[0].action is not None
    assert execution.records[0].action.reason == "任务可以直接完成。"


def test_require_reason_retries_missing_reason() -> None:
    llm = MockLLM(
        [
            '{"action":"finish","arguments":{"answer":"错误。"}}',
            '{"reason":"已完成。","action":"finish","arguments":{"answer":"正确。"}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=create_tools(),
        require_reason=True,
        max_format_retries=1,
    ).run("任务。")
    assert execution.message == "正确。"
    assert execution.state.parse_failures == 1


def test_two_runs_use_fresh_state() -> None:
    llm = MockLLM(
        [
            '{"action":"finish","arguments":{"answer":"一。"}}',
            '{"action":"finish","arguments":{"answer":"二。"}}',
        ]
    )
    agent = Agent(llm=llm, tools=create_tools())
    first = agent.run("任务一")
    second = agent.run("任务二")

    assert first.state is not second.state
    assert first.state.messages is not second.state.messages
    assert first.state.records is not second.state.records


def test_mock_exhaustion_fails_loudly() -> None:
    with pytest.raises(AssertionError, match="没有更多预设输出"):
        Agent(llm=MockLLM([]), tools=create_tools()).run("测试。")


def test_empty_task_is_rejected() -> None:
    with pytest.raises(ValueError, match="不能为空"):
        Agent(llm=MockLLM([]), tools=create_tools()).run("   ")


def test_public_import_has_no_configuration_side_effect() -> None:
    env = dict(os.environ)
    for key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID"):
        env.pop(key, None)
    completed = subprocess.run(
        [sys.executable, "-c", "import simple_agent; print(simple_agent.__version__)"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert completed.stdout.strip() == "0.1.0"


def test_execution_convenience_properties() -> None:
    execution = Agent(
        llm=MockLLM(['{"action":"finish","arguments":{"answer":"完成。"}}']),
        tools=create_tools(),
    ).run("任务。")
    assert execution.message == "完成。"
    assert execution.success is True
    assert execution.termination_reason is TerminationReason.FINISHED
    assert isinstance(execution.records, tuple)
