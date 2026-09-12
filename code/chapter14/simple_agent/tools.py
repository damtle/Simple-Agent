"""工具定义、独立注册表、参数校验与统一执行结果。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .action import AgentAction


ToolFunction = Callable[..., object]
ArgumentValidator = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class ToolExecutionResult:
    """一次工具执行的结构化结果。"""

    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False


class ToolError(RuntimeError):
    """工具能够预期并结构化报告的运行失败。"""

    def __init__(
        self,
        message: str,
        *,
        error_type: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.retryable = retryable


class ToolInputError(ToolError):
    """参数或业务条件不满足，原样重试通常没有意义。"""

    def __init__(self, message: str, *, error_type: str = "invalid_arguments") -> None:
        super().__init__(message, error_type=error_type, retryable=False)


class TemporaryToolError(ToolError):
    """明确的临时错误，可在工具策略允许时有限重试。"""

    def __init__(
        self,
        message: str,
        *,
        error_type: str = "temporary_unavailable",
    ) -> None:
        super().__init__(message, error_type=error_type, retryable=True)


@dataclass(frozen=True)
class Tool:
    """一个被显式开放给 Agent 的工具。"""

    name: str
    description: str
    parameters: dict[str, str]
    function: ToolFunction
    validator: ArgumentValidator | None = None
    retryable: bool = False
    requires_confirmation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("工具名称必须是非空字符串。")
        if self.name == "finish":
            raise ValueError("finish 是 Agent 终止 Action，不能注册为工具。")
        if not isinstance(self.description, str) or not self.description.strip():
            raise ValueError("工具描述必须是非空字符串。")
        if not isinstance(self.parameters, dict):
            raise TypeError("parameters 必须是字典。")
        if not callable(self.function):
            raise TypeError("工具 function 必须可调用。")
        if self.validator is not None and not callable(self.validator):
            raise TypeError("工具 validator 必须可调用或为 None。")


@dataclass
class ToolRegistry:
    """每个 Agent 独立拥有的工具集合。"""

    _tools: dict[str, Tool] = field(default_factory=dict, init=False, repr=False)

    def register(self, tool: Tool) -> None:
        if not isinstance(tool, Tool):
            raise TypeError("只能注册 Tool 实例。")
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

    def render_descriptions(self) -> str:
        if not self._tools:
            return "（当前没有注册工具，只能使用 finish。）"

        blocks: list[str] = []
        for index, tool in enumerate(self._tools.values(), start=1):
            if tool.parameters:
                parameter_lines = "\n".join(
                    f"      - {name}: {description}"
                    for name, description in tool.parameters.items()
                )
            else:
                parameter_lines = "      - 无"

            confirmation_text = (
                "需要用户确认" if tool.requires_confirmation else "无需额外确认"
            )
            retry_text = (
                "允许对明确临时错误自动重试"
                if tool.retryable
                else "不允许自动原样重试"
            )
            blocks.append(
                f"{index}. {tool.name}\n"
                f"   说明：{tool.description}\n"
                f"   参数：\n{parameter_lines}\n"
                f"   控制：{confirmation_text}；{retry_text}。"
            )

        return "\n\n".join(blocks)

    def validate(self, action: AgentAction) -> None:
        tool = self.get(action.name)
        if tool.validator is not None:
            tool.validator(action.arguments)

    def requires_confirmation(self, action: AgentAction) -> bool:
        return self.get(action.name).requires_confirmation

    def allows_retry(self, action: AgentAction) -> bool:
        return self.get(action.name).retryable

    def execute(self, action: AgentAction) -> ToolExecutionResult:
        """执行一次工具；未知程序缺陷不会被宽泛异常静默吞掉。"""
        tool = self.get(action.name)

        try:
            if tool.validator is not None:
                tool.validator(action.arguments)
            value = tool.function(**action.arguments)
        except ToolError as error:
            return ToolExecutionResult(
                success=False,
                content=str(error),
                error_type=error.error_type,
                retryable=error.retryable,
            )
        except (TypeError, ValueError) as error:
            return ToolExecutionResult(
                success=False,
                content=str(error),
                error_type="invalid_operation",
                retryable=False,
            )

        if isinstance(value, ToolExecutionResult):
            return value

        if value is None:
            return ToolExecutionResult(
                success=False,
                content="工具没有返回结果。",
                error_type="empty_result",
                retryable=False,
            )

        content = str(value).strip()
        if not content:
            return ToolExecutionResult(
                success=False,
                content="工具没有返回可用文本结果。",
                error_type="empty_result",
                retryable=False,
            )

        return ToolExecutionResult(success=True, content=content)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: Any) -> bool:
        return name in self._tools
