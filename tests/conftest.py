from __future__ import annotations

from collections.abc import Callable

import pytest

from simple_agent import Tool, ToolExecutionResult, ToolRegistry


SYSTEM_PROMPT = """
你是一个测试 Agent。每次只输出一个 JSON Action。
可用工具由测试注册表决定；任务完成时使用 finish。
""".strip()


def validate_echo(arguments: dict[str, object]) -> None:
    if set(arguments) != {"text"}:
        raise ValueError("echo 只接受 text 参数。")
    if not isinstance(arguments["text"], str):
        raise ValueError("text 必须是字符串。")


def validate_number(arguments: dict[str, object]) -> None:
    if set(arguments) != {"value"}:
        raise ValueError("number 只接受 value 参数。")
    value = arguments["value"]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("value 必须是数字。")


@pytest.fixture
def echo_registry() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="echo",
            description="原样返回文本。",
            parameters={"text": "需要返回的文本"},
            function=lambda text: text,
            validator=validate_echo,
        )
    )
    return tools


@pytest.fixture
def counter_registry() -> tuple[ToolRegistry, dict[str, int]]:
    counter = {"calls": 0}

    def count(value: float) -> str:
        counter["calls"] += 1
        return str(value)

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="number",
            description="返回数字并记录调用次数。",
            parameters={"value": "数字"},
            function=count,
            validator=validate_number,
        )
    )
    return tools, counter


@pytest.fixture
def temporary_registry() -> tuple[ToolRegistry, dict[str, int]]:
    counter = {"calls": 0}

    def unstable(text: str) -> ToolExecutionResult:
        counter["calls"] += 1
        if counter["calls"] == 1:
            return ToolExecutionResult(
                success=False,
                content="临时不可用。",
                error_type="temporary_unavailable",
                retryable=True,
            )
        return ToolExecutionResult(success=True, content=text)

    tools = ToolRegistry()
    tools.register(
        Tool(
            name="unstable",
            description="第一次临时失败，第二次成功。",
            parameters={"text": "文本"},
            function=unstable,
            validator=validate_echo,
            retryable=True,
        )
    )
    return tools, counter
