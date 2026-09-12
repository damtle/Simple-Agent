"""Agent 最终结果、运行状态与 Execution Trace。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .action import AgentAction
from .llm import Message
from .tools import ToolExecutionResult


class TerminationReason(str, Enum):
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
class ModelAttemptRecord:
    attempt: int
    model_output: str | None
    request_error: str | None = None
    parse_error: str | None = None

    @property
    def accepted(self) -> bool:
        return (
            self.model_output is not None
            and self.request_error is None
            and self.parse_error is None
        )


@dataclass(frozen=True)
class StepRecord:
    step: int
    model_attempts: tuple[ModelAttemptRecord, ...]
    action: AgentAction | None
    tool_results: tuple[ToolExecutionResult, ...]
    observation: str | None
    termination_reason: TerminationReason | None = None
    error: str | None = None


@dataclass
class AgentState:
    messages: list[Message] = field(default_factory=list)
    step: int = 0
    finished: bool = False
    records: list[StepRecord] = field(default_factory=list)
    llm_calls: int = 0
    tool_calls: int = 0
    request_failures: int = 0
    parse_failures: int = 0
    tool_failures: int = 0
    termination_reason: TerminationReason | None = None


@dataclass(frozen=True)
class AgentRunResult:
    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None


@dataclass(frozen=True)
class ExecutionTrace:
    records: tuple[StepRecord, ...]
    steps: int
    termination_reason: TerminationReason | None


@dataclass(frozen=True)
class AgentExecution:
    result: AgentRunResult
    state: AgentState
    trace: ExecutionTrace

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
        return self.trace.records
