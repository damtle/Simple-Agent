"""第十二章：重试策略、网络重试与工具重试。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tools import ToolExecutionResult, ToolSpec


@dataclass(frozen=True)
class RetryPolicy:
    """Agent 的有限重试与硬终止预算。"""

    max_network_retries: int = 2
    max_format_retries: int = 2
    max_tool_retries: int = 1
    max_steps: int = 8
    repeated_action_limit: int = 2
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        integer_fields = {
            "max_network_retries": self.max_network_retries,
            "max_format_retries": self.max_format_retries,
            "max_tool_retries": self.max_tool_retries,
            "max_steps": self.max_steps,
            "repeated_action_limit": self.repeated_action_limit,
        }

        for field_name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{field_name} 必须是整数。")

        for field_name in (
            "max_network_retries",
            "max_format_retries",
            "max_tool_retries",
        ):
            if integer_fields[field_name] < 0:
                raise ValueError(f"{field_name} 不能小于 0。")

        if self.max_steps <= 0:
            raise ValueError("max_steps 必须大于 0。")

        if self.repeated_action_limit < 2:
            raise ValueError(
                "repeated_action_limit 至少为 2。"
            )

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or self.timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds 必须是大于 0 的数字。"
            )


class LLMRequestError(RuntimeError):
    """模型请求失败，并携带是否适合原样重试的信息。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable


RequestFunction = Callable[[], str]


def call_with_network_retry(
    request_fn: RequestFunction,
    max_retries: int,
) -> str:
    """在不改变请求语义的情况下有限重复同一次模型请求。"""
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries 必须是整数。")

    if max_retries < 0:
        raise ValueError("max_retries 不能小于 0。")

    for attempt in range(max_retries + 1):
        try:
            return request_fn()
        except LLMRequestError as error:
            can_retry = (
                error.retryable
                and attempt < max_retries
            )

            if not can_retry:
                raise

    raise RuntimeError("不可达代码：网络重试循环未结束。")


def execute_with_tool_retry(
    spec: ToolSpec,
    arguments: dict[str, object],
    max_retries: int,
) -> ToolExecutionResult:
    """只重试可恢复且幂等的同一工具 Action。"""
    if isinstance(max_retries, bool) or not isinstance(max_retries, int):
        raise TypeError("max_retries 必须是整数。")

    if max_retries < 0:
        raise ValueError("max_retries 不能小于 0。")

    for attempt in range(max_retries + 1):
        result = spec.function(**arguments)

        if not isinstance(result, ToolExecutionResult):
            raise TypeError(
                f"工具 {spec.name!r} 必须返回 "
                "ToolExecutionResult。"
            )

        if result.success:
            return result

        can_retry = (
            result.retryable
            and spec.idempotent
            and attempt < max_retries
        )

        if not can_retry:
            return result

    raise RuntimeError("不可达代码：工具重试循环未结束。")
