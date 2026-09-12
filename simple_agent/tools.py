"""工具定义、实例级注册表、参数验证与执行。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import json

from .action import AgentAction


ToolFunction = Callable[..., object]
ArgumentValidator = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class ToolExecutionResult:
    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, str]
    function: ToolFunction
    validator: ArgumentValidator | None = None
    retryable: bool = False
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("工具名称不能为空。")
        if self.name != self.name.strip():
            raise ValueError("工具名称前后不能包含空白。")
        if self.name == "finish":
            raise ValueError("finish 是保留行动，不能注册为工具。")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("工具描述不能为空。")
        if not callable(self.function):
            raise TypeError("工具 function 必须可调用。")
        if self.validator is not None and not callable(self.validator):
            raise TypeError("工具 validator 必须可调用。")
        if not isinstance(self.parameters, dict):
            raise TypeError("工具 parameters 必须是字典。")

        # 与调用方传入的可变字典解除引用关系。
        object.__setattr__(self, "parameters", dict(self.parameters))


class ToolRegistry:
    """由每个 Agent 实例独立持有的工具集合。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("只能注册 Tool 对象。")

        if tool.name in self._tools:
            raise ValueError(f"工具已经注册：{tool.name}")

        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ValueError(f"工具不存在：{name}") from error

    def names(self) -> set[str]:
        return set(self._tools)

    def validate(self, action: AgentAction) -> None:
        tool = self.get(action.name)

        if tool.validator is not None:
            tool.validator(action.arguments)

    def execute(self, action: AgentAction) -> ToolExecutionResult:
        """执行已通过协议校验的 Action。"""
        tool = self.get(action.name)
        self.validate(action)

        try:
            output = tool.function(**action.arguments)
        except TypeError as error:
            return ToolExecutionResult(
                success=False,
                content=f"工具参数错误：{error}",
                error_type="invalid_arguments",
                retryable=False,
            )
        except (ValueError, OverflowError) as error:
            return ToolExecutionResult(
                success=False,
                content=str(error),
                error_type="tool_error",
                retryable=False,
            )

        if isinstance(output, ToolExecutionResult):
            # 工具结果声明可重试，还必须同时满足工具元数据允许重试。
            if output.retryable and not tool.retryable:
                return replace(output, retryable=False)
            return output

        if output is None or not str(output).strip():
            return ToolExecutionResult(
                success=False,
                content="工具没有返回可用结果。",
                error_type="empty_result",
            )

        return ToolExecutionResult(
            success=True,
            content=str(output),
        )

    def requires_confirmation(self, action: AgentAction) -> bool:
        return self.get(action.name).requires_confirmation

    def render_descriptions(self) -> str:
        """为应用 Prompt 生成稳定、紧凑的工具说明。"""
        blocks: list[str] = []

        for name in sorted(self._tools):
            tool = self._tools[name]
            parameters = json.dumps(
                tool.parameters,
                ensure_ascii=False,
                sort_keys=True,
            )
            blocks.append(
                f"- {tool.name}: {tool.description}\n"
                f"  parameters: {parameters}"
            )

        return "\n".join(blocks)
