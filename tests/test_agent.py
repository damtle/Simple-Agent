from __future__ import annotations

import pytest

from simple_agent import (
    Agent,
    LLMRequestError,
    RetryPolicy,
    TerminationReason,
    Tool,
    ToolExecutionResult,
    ToolRegistry,
)
from tests.conftest import SYSTEM_PROMPT, validate_echo
from tests.fakes import MockLLM


def test_public_api_echo_loop(echo_registry) -> None:
    llm = MockLLM(
        [
            '{"action":"echo","arguments":{"text":"hello"}}',
            '{"action":"finish","arguments":{"answer":"hello"}}',
        ]
    )
    agent = Agent(
        llm=llm,
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_steps=4),
    )

    execution = agent.run("请返回 hello。")

    assert execution.result.success is True
    assert execution.message == "hello"
    assert execution.state.llm_calls == 2
    assert execution.state.tool_calls == 1
    assert len(execution.trace.records) == 2


def test_observation_enters_next_request(echo_registry) -> None:
    llm = MockLLM(
        [
            '{"action":"echo","arguments":{"text":"hello"}}',
            '{"action":"finish","arguments":{"answer":"hello"}}',
        ]
    )
    Agent(
        llm=llm,
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。")

    assert len(llm.calls[0]) == 2
    assert len(llm.calls[1]) == 4
    assert any(
        message["content"].startswith("Observation:")
        for message in llm.calls[1]
    )


def test_format_retry_stays_in_same_step(echo_registry) -> None:
    llm = MockLLM(
        [
            '{"action":"echo","arguments":{"text":"hello",}}',
            '{"action":"echo","arguments":{"text":"hello"}}',
            '{"action":"finish","arguments":{"answer":"hello"}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_format_retries=1),
    ).run("任务。")

    assert execution.success is True
    assert execution.result.steps == 2
    assert execution.state.llm_calls == 3
    assert execution.state.parse_failures == 1
    assert len(execution.records[0].model_attempts) == 2


def test_parse_retry_exhaustion_does_not_execute_tool(counter_registry) -> None:
    tools, counter = counter_registry
    execution = Agent(
        llm=MockLLM(["bad", "still bad"]),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_format_retries=1),
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.PARSE_ERROR
    assert execution.state.llm_calls == 2
    assert execution.state.parse_failures == 2
    assert execution.state.tool_calls == 0
    assert counter["calls"] == 0
    assert execution.records[0].action is None


def test_repeated_action_stops_before_second_tool(counter_registry) -> None:
    tools, counter = counter_registry
    repeated = (
        '{"action":"number","arguments":{"value":1}}'
    )
    execution = Agent(
        llm=MockLLM([repeated, repeated]),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(repeated_action_limit=2),
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.REPEATED_ACTION
    assert execution.state.tool_calls == 1
    assert counter["calls"] == 1
    assert execution.records[1].tool_results == ()


def test_reason_text_does_not_hide_repeated_action(counter_registry) -> None:
    tools, counter = counter_registry
    execution = Agent(
        llm=MockLLM(
            [
                '{"reason":"第一次。","action":"number",'
                '"arguments":{"value":1}}',
                '{"reason":"换一种说法。","action":"number",'
                '"arguments":{"value":1}}',
            ]
        ),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(repeated_action_limit=2),
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.REPEATED_ACTION
    assert counter["calls"] == 1


def test_max_steps(counter_registry) -> None:
    tools, counter = counter_registry
    execution = Agent(
        llm=MockLLM(
            [
                '{"action":"number","arguments":{"value":1}}',
                '{"action":"number","arguments":{"value":2}}',
            ]
        ),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_steps=2, repeated_action_limit=3),
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.MAX_STEPS
    assert counter["calls"] == 2
    assert execution.records[-1].termination_reason is TerminationReason.MAX_STEPS


def test_network_retry_is_same_step(echo_registry) -> None:
    execution = Agent(
        llm=MockLLM(
            [
                LLMRequestError("模拟超时。", retryable=True),
                '{"action":"finish","arguments":{"answer":"完成。"}}',
            ]
        ),
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_network_retries=1),
    ).run("任务。")

    assert execution.success is True
    assert execution.result.steps == 1
    assert execution.state.llm_calls == 2
    assert execution.state.request_failures == 1
    assert len(execution.records[0].model_attempts) == 2


def test_tool_retry_is_same_step(temporary_registry) -> None:
    tools, counter = temporary_registry
    execution = Agent(
        llm=MockLLM(
            [
                '{"action":"unstable","arguments":{"text":"ok"}}',
                '{"action":"finish","arguments":{"answer":"ok"}}',
            ]
        ),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        policy=RetryPolicy(max_tool_retries=1),
    ).run("任务。")

    assert execution.success is True
    assert counter["calls"] == 2
    assert execution.state.tool_calls == 2
    assert execution.state.tool_failures == 1
    assert len(execution.records[0].tool_results) == 2


def test_business_failure_becomes_observation() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="lookup",
            description="始终返回未找到。",
            parameters={},
            function=lambda: ToolExecutionResult(
                success=False,
                content="没有找到数据。",
                error_type="not_found",
                retryable=False,
            ),
        )
    )
    llm = MockLLM(
        [
            '{"action":"lookup","arguments":{}}',
            '{"action":"finish","arguments":{"answer":"未找到。"}}',
        ]
    )
    execution = Agent(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。")

    assert execution.success is True
    assert execution.state.tool_failures == 1
    assert "not_found" in llm.calls[1][-1]["content"]


def test_confirmation_required_before_side_effect() -> None:
    counter = {"calls": 0}

    def submit(text: str) -> str:
        counter["calls"] += 1
        return text

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="submit",
            description="模拟提交。",
            parameters={"text": "内容"},
            function=submit,
            validator=validate_echo,
            requires_confirmation=True,
        )
    )
    output = '{"action":"submit","arguments":{"text":"hello"}}'

    execution = Agent(
        llm=MockLLM([output]),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。")

    assert execution.termination_reason is TerminationReason.CONFIRMATION_REQUIRED
    assert execution.state.tool_calls == 0
    assert counter["calls"] == 0


def test_user_rejection_prevents_execution() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="submit",
            description="模拟提交。",
            parameters={"text": "内容"},
            function=lambda text: text,
            validator=validate_echo,
            requires_confirmation=True,
        )
    )
    execution = Agent(
        llm=MockLLM(
            ['{"action":"submit","arguments":{"text":"hello"}}']
        ),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。", confirmation_callback=lambda action: False)

    assert execution.termination_reason is TerminationReason.USER_REJECTED
    assert execution.state.tool_calls == 0


def test_confirmation_allows_execution() -> None:
    counter = {"calls": 0}

    def submit(text: str) -> str:
        counter["calls"] += 1
        return text

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="submit",
            description="模拟提交。",
            parameters={"text": "内容"},
            function=submit,
            validator=validate_echo,
            requires_confirmation=True,
        )
    )
    execution = Agent(
        llm=MockLLM(
            [
                '{"action":"submit","arguments":{"text":"hello"}}',
                '{"action":"finish","arguments":{"answer":"done"}}',
            ]
        ),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    ).run("任务。", confirmation_callback=lambda action: True)

    assert execution.success is True
    assert counter["calls"] == 1


def test_require_reason_mode(echo_registry) -> None:
    execution = Agent(
        llm=MockLLM(
            [
                '{"reason":"任务可以完成。","action":"finish",'
                '"arguments":{"answer":"完成。"}}'
            ]
        ),
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
        require_reason=True,
    ).run("任务。")

    assert execution.success is True
    assert execution.records[0].action is not None
    assert execution.records[0].action.reason == "任务可以完成。"


def test_two_runs_use_fresh_state(echo_registry) -> None:
    agent = Agent(
        llm=MockLLM(
            [
                '{"action":"finish","arguments":{"answer":"一。"}}',
                '{"action":"finish","arguments":{"answer":"二。"}}',
            ]
        ),
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
    )

    first = agent.run("任务一")
    second = agent.run("任务二")

    assert first.state is not second.state
    assert first.state.messages is not second.state.messages
    assert first.state.records is not second.state.records


def test_empty_task_returns_invalid_input(echo_registry) -> None:
    execution = Agent(
        llm=MockLLM([]),
        tools=echo_registry,
        system_prompt=SYSTEM_PROMPT,
    ).run("   ")

    assert execution.success is False
    assert execution.termination_reason is TerminationReason.INVALID_INPUT
    assert execution.result.steps == 0


def test_mock_exhaustion_fails_loudly(echo_registry) -> None:
    with pytest.raises(AssertionError, match="没有更多预设输出"):
        Agent(
            llm=MockLLM([]),
            tools=echo_registry,
            system_prompt=SYSTEM_PROMPT,
        ).run("任务。")
