"""第十三章：集中保存一次 Agent 运行的可变状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import TerminationReason
    from trace import StepRecord


@dataclass
class AgentState:
    """会影响当前运行和后续决策的可变状态。"""

    messages: list[dict[str, str]] = field(
        default_factory=list
    )
    step: int = 0
    finished: bool = False
    records: list[StepRecord] = field(
        default_factory=list
    )
    llm_calls: int = 0
    tool_calls: int = 0
    request_failures: int = 0
    parse_failures: int = 0
    tool_failures: int = 0
    termination_reason: TerminationReason | None = None


def create_initial_state(
    system_prompt: str,
    user_task: str,
) -> AgentState:
    """为一次新任务创建独立状态。"""
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise ValueError("system_prompt 不能为空。")

    if not isinstance(user_task, str) or not user_task.strip():
        raise ValueError("user_task 不能为空。")

    return AgentState(
        messages=[
            {
                "role": "system",
                "content": system_prompt.strip(),
            },
            {
                "role": "user",
                "content": user_task.strip(),
            },
        ]
    )
