"""第十三章：模型尝试、步骤记录和 Execution Trace。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent import (
        AgentAction,
        TerminationReason,
        ToolExecutionResult,
    )
    from state import AgentState


@dataclass(frozen=True)
class ModelAttemptRecord:
    """同一个 Agent Step 内的一次模型请求尝试。"""

    attempt: int
    model_output: str | None
    request_error: str | None = None
    parse_error: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt <= 0
        ):
            raise ValueError("attempt 必须是正整数。")

        error_count = sum(
            value is not None
            for value in (
                self.request_error,
                self.parse_error,
            )
        )

        if error_count > 1:
            raise ValueError(
                "一次模型尝试不能同时包含请求错误和解析错误。"
            )

        if self.request_error is not None and self.model_output is not None:
            raise ValueError(
                "模型请求失败时不应存在 model_output。"
            )

    @property
    def accepted(self) -> bool:
        """当前输出是否已经被 Parser 接受。"""
        return (
            self.model_output is not None
            and self.request_error is None
            and self.parse_error is None
        )


@dataclass(frozen=True)
class StepRecord:
    """一个 Agent 决策位置中已经发生的结构化事实。"""

    step: int
    model_attempts: tuple[ModelAttemptRecord, ...]
    action: AgentAction | None
    tool_results: tuple[ToolExecutionResult, ...]
    observation: str | None
    termination_reason: TerminationReason | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.step, bool)
            or not isinstance(self.step, int)
            or self.step <= 0
        ):
            raise ValueError("step 必须是正整数。")

        expected_attempts = tuple(
            range(1, len(self.model_attempts) + 1)
        )
        actual_attempts = tuple(
            item.attempt
            for item in self.model_attempts
        )

        if actual_attempts != expected_attempts:
            raise ValueError(
                "model_attempts 必须从 1 开始连续编号。"
            )


@dataclass(frozen=True)
class ExecutionTrace:
    """一次运行结束后得到的不可变步骤快照。"""

    records: tuple[StepRecord, ...]
    steps: int
    termination_reason: TerminationReason | None


def snapshot_action(
    action: AgentAction,
) -> AgentAction:
    """复制嵌套参数，避免后续修改污染已保存历史。"""
    from agent import AgentAction

    return AgentAction(
        name=action.name,
        arguments=deepcopy(action.arguments),
    )


def build_execution_trace(
    state: AgentState,
) -> ExecutionTrace:
    """从当前 State 创建不可变 Execution Trace。"""
    return ExecutionTrace(
        records=tuple(state.records),
        steps=state.step,
        termination_reason=state.termination_reason,
    )


def _reason_value(reason: object | None) -> str | None:
    if reason is None:
        return None

    value = getattr(reason, "value", None)
    return str(value) if value is not None else str(reason)


def step_record_to_dict(
    record: StepRecord,
) -> dict[str, object]:
    """将 StepRecord 转换为稳定、可写入 JSON 的结构。"""
    return {
        "step": record.step,
        "model_attempts": [
            asdict(attempt)
            for attempt in record.model_attempts
        ],
        "action": (
            asdict(record.action)
            if record.action is not None
            else None
        ),
        "tool_results": [
            asdict(result)
            for result in record.tool_results
        ],
        "observation": record.observation,
        "termination_reason": _reason_value(
            record.termination_reason
        ),
        "error": record.error,
    }


def trace_to_dict(
    trace: ExecutionTrace,
) -> dict[str, object]:
    """将完整轨迹转换为 JSON 兼容对象。"""
    return {
        "steps": trace.steps,
        "termination_reason": _reason_value(
            trace.termination_reason
        ),
        "records": [
            step_record_to_dict(record)
            for record in trace.records
        ],
    }


def save_trace(
    trace: ExecutionTrace,
    path: Path,
) -> None:
    """以 UTF-8 JSON 保存开发者轨迹。"""
    if not isinstance(path, Path):
        raise TypeError("path 必须是 pathlib.Path。")

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            trace_to_dict(trace),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def print_trace(
    trace: ExecutionTrace,
) -> None:
    """以紧凑形式显示开发者执行轨迹。"""
    for record in trace.records:
        print(f"Step {record.step}")

        for attempt in record.model_attempts:
            if attempt.request_error is not None:
                status = "request_error"
            elif attempt.parse_error is not None:
                status = "parse_error"
            else:
                status = "accepted"

            print(
                f"  Attempt {attempt.attempt}: "
                f"{status}"
            )

        if record.action is not None:
            print(f"  Action: {record.action.name}")
            print(
                "  Arguments: "
                + json.dumps(
                    record.action.arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )

        for index, result in enumerate(
            record.tool_results,
            start=1,
        ):
            print(
                f"  Tool Result {index}: "
                f"success={result.success}"
            )

        if record.observation is not None:
            one_line = record.observation.replace(
                "\n",
                " | ",
            )
            print(f"  Observation: {one_line}")

        if record.termination_reason is not None:
            print(
                "  Termination: "
                f"{_reason_value(record.termination_reason)}"
            )

        if record.error is not None:
            print(f"  Error: {record.error}")

    print(
        "Termination: "
        + (
            _reason_value(trace.termination_reason)
            or "running"
        )
    )
