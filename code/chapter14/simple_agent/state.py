"""Agent 状态、执行轨迹、最终结果和终止原因。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .action import AgentAction
from .llm import Message
from .tools import ToolExecutionResult


class TerminationReason(str, Enum):
    FINISHED = "finished"
    MAX_STEPS = "max_steps"
    PARSE_ERROR = "parse_error"
    TOOL_ERROR = "tool_error"
    LLM_ERROR = "llm_error"
    REPEATED_ACTION = "repeated_action"
    TIMEOUT = "timeout"
    USER_REJECTED = "user_rejected"


@dataclass(frozen=True)
class ModelAttemptRecord:
    attempt: int
    model_output: str
    parse_error: str | None = None


@dataclass(frozen=True)
class StepRecord:
    step: int
    model_attempts: tuple[ModelAttemptRecord, ...]
    action: AgentAction | None
    observation: str | None
    tool_result: ToolExecutionResult | None
    error: str | None


@dataclass
class AgentState:
    messages: list[Message] = field(default_factory=list)
    step: int = 0
    finished: bool = False
    records: list[StepRecord] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    parse_failures: int = 0
    termination_reason: TerminationReason | None = None


@dataclass(frozen=True)
class AgentRunResult:
    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None


@dataclass(frozen=True)
class AgentExecution:
    result: AgentRunResult
    state: AgentState

    @property
    def message(self) -> str:
        return self.result.message

    @property
    def success(self) -> bool:
        return self.result.success

    @property
    def termination_reason(self) -> TerminationReason:
        return self.result.termination_reason

    @property
    def records(self) -> tuple[StepRecord, ...]:
        return tuple(self.state.records)


def create_initial_state(system_prompt: str, task: str) -> AgentState:
    normalized_task = task.strip()
    if not normalized_task:
        raise ValueError("用户任务不能为空。")

    return AgentState(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": normalized_task},
        ]
    )
