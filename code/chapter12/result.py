"""第十二章：统一终止原因与 Agent 运行结果。"""

from dataclasses import dataclass
from enum import Enum


class TerminationReason(str, Enum):
    """一次 Agent 运行停止的明确控制层原因。"""

    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    LLM_ERROR = "llm_error"
    PARSE_ERROR = "parse_error"
    TOOL_ERROR = "tool_error"
    REPEATED_ACTION = "repeated_action"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    CONFIRMATION_REQUIRED = "confirmation_required"
    USER_REJECTED = "user_rejected"


@dataclass(frozen=True)
class AgentRunResult:
    """无论成功还是预期失败，Agent 都返回同一种结果。"""

    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None


def invalid_input_result(message: str) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message=message,
        termination_reason=TerminationReason.INVALID_INPUT,
        steps=0,
    )


def llm_error_result(
    *,
    steps: int,
    error: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="模型服务当前不可用。",
        termination_reason=TerminationReason.LLM_ERROR,
        steps=steps,
        error=error,
    )


def parse_error_result(
    *,
    steps: int,
    error: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="模型输出未通过 Action 协议校验。",
        termination_reason=TerminationReason.PARSE_ERROR,
        steps=steps,
        error=error,
    )


def tool_error_result(
    *,
    steps: int,
    error: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="工具发生无法继续处理的受控错误。",
        termination_reason=TerminationReason.TOOL_ERROR,
        steps=steps,
        error=error,
    )


def repeated_action_result(
    *,
    steps: int,
    action_key: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="Agent 连续生成了相同 Action。",
        termination_reason=TerminationReason.REPEATED_ACTION,
        steps=steps,
        error=action_key,
    )


def timeout_result(*, steps: int) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="Agent 运行超过总时间限制。",
        termination_reason=TerminationReason.TIMEOUT,
        steps=steps,
        error="超过 Agent 总超时。",
    )


def confirmation_required_result(
    *,
    steps: int,
    action_name: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="当前 Action 需要用户明确确认后才能执行。",
        termination_reason=(
            TerminationReason.CONFIRMATION_REQUIRED
        ),
        steps=steps,
        error=f"等待确认：{action_name}",
    )


def user_rejected_result(
    *,
    steps: int,
    action_name: str,
) -> AgentRunResult:
    return AgentRunResult(
        success=False,
        message="用户拒绝执行当前 Action。",
        termination_reason=TerminationReason.USER_REJECTED,
        steps=steps,
        error=f"用户拒绝：{action_name}",
    )
