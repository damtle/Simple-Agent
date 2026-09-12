from __future__ import annotations

import pytest

from simple_agent import Tool, ToolExecutionResult, ToolRegistry
from simple_agent.action import AgentAction


def test_registry_registers_and_executes(echo_registry) -> None:
    action = AgentAction("echo", {"text": "hello"})
    result = echo_registry.execute(action)

    assert result.success is True
    assert result.content == "hello"
    assert echo_registry.names() == {"echo"}


def test_duplicate_registration_is_rejected(echo_registry) -> None:
    with pytest.raises(ValueError, match="已经注册"):
        echo_registry.register(
            Tool(
                name="echo",
                description="重复工具。",
                parameters={"text": "文本"},
                function=lambda text: text,
            )
        )


def test_registries_are_independent() -> None:
    first = ToolRegistry()
    second = ToolRegistry()
    first.register(
        Tool(
            name="one",
            description="第一个工具。",
            parameters={},
            function=lambda: "one",
        )
    )

    assert "one" in first.names()
    assert "one" not in second.names()


def test_finish_cannot_be_registered() -> None:
    with pytest.raises(ValueError, match="保留"):
        Tool(
            name="finish",
            description="错误示例。",
            parameters={},
            function=lambda: "done",
        )


def test_validator_is_used(echo_registry) -> None:
    with pytest.raises(ValueError, match="只接受 text"):
        echo_registry.validate(
            AgentAction("echo", {"value": "hello"})
        )


def test_retryable_result_requires_tool_permission() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="unsafe_retry",
            description="不允许自动重试。",
            parameters={},
            function=lambda: ToolExecutionResult(
                success=False,
                content="失败。",
                error_type="temporary",
                retryable=True,
            ),
            retryable=False,
        )
    )

    result = tools.execute(AgentAction("unsafe_retry", {}))
    assert result.retryable is False


def test_confirmation_metadata() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="submit",
            description="模拟提交。",
            parameters={},
            function=lambda: "submitted",
            requires_confirmation=True,
        )
    )

    assert tools.requires_confirmation(AgentAction("submit", {})) is True


def test_render_descriptions(echo_registry) -> None:
    rendered = echo_registry.render_descriptions()
    assert "echo" in rendered
    assert "原样返回文本" in rendered
    assert "text" in rendered
