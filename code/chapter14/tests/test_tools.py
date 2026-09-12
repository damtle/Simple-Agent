from __future__ import annotations

import pytest

from simple_agent.action import AgentAction
from simple_agent.tools import (
    TemporaryToolError,
    Tool,
    ToolExecutionResult,
    ToolInputError,
    ToolRegistry,
)


def make_echo_tool(name: str = "echo") -> Tool:
    def validate(arguments: dict[str, object]) -> None:
        if set(arguments) != {"text"} or not isinstance(arguments["text"], str):
            raise ValueError("text 必须是字符串。")

    return Tool(
        name=name,
        description="返回输入文本。",
        parameters={"text": "文本"},
        function=lambda text: text,
        validator=validate,
    )


def test_register_get_and_names() -> None:
    registry = ToolRegistry()
    tool = make_echo_tool()
    registry.register(tool)
    assert registry.get("echo") is tool
    assert registry.names() == {"echo"}
    assert len(registry) == 1


def test_duplicate_registration_is_rejected() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_tool())
    with pytest.raises(ValueError, match="已经注册"):
        registry.register(make_echo_tool())


def test_unknown_tool_is_rejected() -> None:
    with pytest.raises(ValueError, match="不存在"):
        ToolRegistry().get("missing")


def test_registries_are_independent() -> None:
    first = ToolRegistry()
    second = ToolRegistry()
    first.register(make_echo_tool())
    assert "echo" in first.names()
    assert "echo" not in second.names()


def test_render_descriptions_contains_metadata() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_tool())
    text = registry.render_descriptions()
    assert "echo" in text
    assert "text" in text
    assert "无需额外确认" in text


def test_execute_success() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_tool())
    result = registry.execute(AgentAction("echo", {"text": "hello"}))
    assert result == ToolExecutionResult(success=True, content="hello")


def test_execute_validator_failure_becomes_structured_result() -> None:
    registry = ToolRegistry()
    registry.register(make_echo_tool())
    result = registry.execute(AgentAction("echo", {"text": 1}))
    assert result.success is False
    assert result.error_type == "invalid_operation"


def test_tool_input_error_keeps_error_type() -> None:
    registry = ToolRegistry()

    def fail() -> str:
        raise ToolInputError("没有数据。", error_type="not_found")

    registry.register(
        Tool("lookup", "查询数据。", {}, fail)
    )
    result = registry.execute(AgentAction("lookup", {}))
    assert result.success is False
    assert result.error_type == "not_found"
    assert result.retryable is False


def test_temporary_error_is_retryable() -> None:
    registry = ToolRegistry()

    def fail() -> str:
        raise TemporaryToolError("暂时不可用。")

    registry.register(
        Tool("temporary", "临时工具。", {}, fail, retryable=True)
    )
    result = registry.execute(AgentAction("temporary", {}))
    assert result.success is False
    assert result.retryable is True


def test_function_can_return_structured_result() -> None:
    registry = ToolRegistry()
    expected = ToolExecutionResult(False, "业务失败", "business", False)
    registry.register(Tool("structured", "返回结构结果。", {}, lambda: expected))
    assert registry.execute(AgentAction("structured", {})) is expected


def test_confirmation_metadata() -> None:
    registry = ToolRegistry()
    registry.register(
        Tool(
            "send",
            "模拟发送。",
            {},
            lambda: "sent",
            requires_confirmation=True,
        )
    )
    assert registry.requires_confirmation(AgentAction("send", {})) is True


def test_unexpected_program_error_is_not_hidden() -> None:
    registry = ToolRegistry()

    def broken() -> str:
        raise RuntimeError("program bug")

    registry.register(Tool("broken", "故障工具。", {}, broken))
    with pytest.raises(RuntimeError, match="program bug"):
        registry.execute(AgentAction("broken", {}))


def test_finish_cannot_be_registered() -> None:
    with pytest.raises(ValueError, match="不能注册"):
        Tool("finish", "错误。", {}, lambda: "x")
