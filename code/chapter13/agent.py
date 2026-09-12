"""Simple Travel Assistant v1.5：状态、轨迹与日志。

本章沿用第十二章的可靠 Agent Loop，并把运行过程写入：

    AgentState
    ModelAttemptRecord
    StepRecord
    ExecutionTrace
    logging

默认离线演示：

    python code/chapter13/agent.py

保存轨迹：

    python code/chapter13/agent.py \
        --scenario main \
        --save-trace artifacts/traces/trace.json

真实模型：

    python code/chapter13/agent.py --real
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
import json
import logging
import math
import os
from pathlib import Path
from time import monotonic
from typing import Protocol

from logging_config import configure_logging
from state import AgentState, create_initial_state
from trace import (
    ExecutionTrace,
    ModelAttemptRecord,
    StepRecord,
    build_execution_trace,
    print_trace,
    save_trace,
    snapshot_action,
)


logger = logging.getLogger(__name__)


class TerminationReason(str, Enum):
    """一次 Agent 运行停止的明确原因。"""

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
    """面向调用方的一次运行最终结局。"""

    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None


@dataclass(frozen=True)
class AgentExecution:
    """同时返回结局、最终状态和不可变轨迹。"""

    result: AgentRunResult
    state: AgentState
    trace: ExecutionTrace


@dataclass(frozen=True)
class AgentAction:
    """已经通过 Parser 校验的行动。"""

    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ToolExecutionResult:
    """一次真实工具执行的结构化结果。"""

    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False


ToolFunction = Callable[..., ToolExecutionResult]


@dataclass(frozen=True)
class ToolSpec:
    """工具执行元数据。"""

    name: str
    function: ToolFunction
    idempotent: bool
    requires_confirmation: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    """有限重试与硬终止预算。"""

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

        for name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} 必须是整数。")

        for name in (
            "max_network_retries",
            "max_format_retries",
            "max_tool_retries",
        ):
            if integer_fields[name] < 0:
                raise ValueError(f"{name} 不能小于 0。")

        if self.max_steps <= 0:
            raise ValueError("max_steps 必须大于 0。")

        if self.repeated_action_limit < 2:
            raise ValueError(
                "repeated_action_limit 至少为 2。"
            )

        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(
                self.timeout_seconds,
                (int, float),
            )
            or self.timeout_seconds <= 0
        ):
            raise ValueError(
                "timeout_seconds 必须是大于 0 的数字。"
            )


class LLMRequestError(RuntimeError):
    """模型请求失败，并标记是否适合原样重试。"""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable


class ActionParseError(ValueError):
    """模型文本没有通过 Action Protocol。"""


class ActionRequester(Protocol):
    def __call__(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """根据当前消息返回原始模型文本。"""


ConfirmationCallback = Callable[[AgentAction], bool]
Clock = Callable[[], float]


AGENT_SYSTEM_PROMPT = """
你是一个使用本地模拟工具完成任务的城市旅行助手。

每次只能输出一个 JSON 对象：
{
  "action": "行动名称",
  "arguments": {}
}

可用行动：

1. get_weather
   arguments: {"city": "城市名称"}

2. get_attraction_info
   arguments: {"name": "景点名称"}

3. calculator
   arguments: {
     "operation": "add|subtract|multiply|divide",
     "a": 数字,
     "b": 数字
   }

4. submit_reservation
   arguments: {
     "attraction": "景点名称",
     "visitor_count": 正整数
   }
   该工具执行前必须取得用户确认。

5. finish
   arguments: {"answer": "最终回答"}

规则：
1. 每轮只选择一个行动。
2. 工具失败后，根据 Observation 重新决策。
3. 不要重复已经成功且无需再次执行的 Action。
4. 天气、景点、票价和预订均为本地模拟信息。
5. 不要输出 Markdown 代码块或额外说明。
""".strip()


WEATHER_DATA = {
    "北京": {
        "condition": "晴",
        "temperature": 30,
        "humidity": 45,
        "wind": "微风",
    },
    "上海": {
        "condition": "多云",
        "temperature": 27,
        "humidity": 70,
        "wind": "东南风",
    },
    "广州": {
        "condition": "阵雨",
        "temperature": 32,
        "humidity": 82,
        "wind": "南风",
    },
}

ATTRACTION_DATA = {
    "故宫": {
        "city": "北京",
        "open": True,
        "adult_ticket": 60,
        "activity_type": "室内外步行",
        "description": "以宫殿建筑、历史展陈和步行参观为主。",
    },
    "上海博物馆": {
        "city": "上海",
        "open": True,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "以历史文物和艺术展陈为主。",
    },
    "广东省博物馆": {
        "city": "广州",
        "open": False,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "当前模拟数据中处于闭馆状态。",
    },
}



def _load_bounded_json(text: str) -> object:
    """为教学快照限制不可信 JSON 的资源消耗。"""
    if len(text) > 65_536:
        raise json.JSONDecodeError("模型输出长度超过限制", text, 0)
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "{[":
            depth += 1
            if depth > 64:
                raise json.JSONDecodeError("JSON 嵌套层数超过限制", text, 0)
        elif character in "}]":
            depth -= 1

    def parse_integer(value: str) -> int:
        if len(value.lstrip("-")) > 128:
            raise ValueError("整数位数超过限制")
        return int(value)

    try:
        return json.loads(text, parse_int=parse_integer)
    except (ValueError, RecursionError) as error:
        raise json.JSONDecodeError("JSON 格式或数值超出允许范围", text, 0) from error


def get_weather(city: str) -> ToolExecutionResult:
    data = WEATHER_DATA.get(city)

    if data is None:
        return ToolExecutionResult(
            success=False,
            content=f"没有找到城市“{city}”的模拟天气数据。",
            error_type="not_found",
            retryable=False,
        )

    return ToolExecutionResult(
        success=True,
        content=(
            f"{city}当前模拟天气为{data['condition']}，"
            f"温度{data['temperature']}℃，"
            f"湿度{data['humidity']}%，"
            f"{data['wind']}。"
        ),
    )


def get_attraction_info(
    name: str,
) -> ToolExecutionResult:
    data = ATTRACTION_DATA.get(name)

    if data is None:
        return ToolExecutionResult(
            success=False,
            content=f"没有找到景点“{name}”的模拟信息。",
            error_type="not_found",
            retryable=False,
        )

    status = "开放" if data["open"] else "闭馆"

    return ToolExecutionResult(
        success=True,
        content=(
            f"{name}位于{data['city']}，"
            f"在当前模拟数据中处于{status}状态，"
            f"成人票价{data['adult_ticket']}元，"
            f"活动类型为{data['activity_type']}。"
            f"{data['description']}"
        ),
    )


def calculator(
    operation: str,
    a: float,
    b: float,
) -> ToolExecutionResult:
    if not _is_finite_number(a) or not _is_finite_number(b):
        return ToolExecutionResult(
            success=False,
            content="计算器参数必须是有限数字。",
            error_type="invalid_arguments",
        )

    if operation == "add":
        value = a + b
    elif operation == "subtract":
        value = a - b
    elif operation == "multiply":
        value = a * b
    elif operation == "divide":
        if b == 0:
            return ToolExecutionResult(
                success=False,
                content="除数不能为 0。",
                error_type="invalid_arguments",
            )
        value = a / b
    else:
        return ToolExecutionResult(
            success=False,
            content=f"不支持的计算操作：{operation}",
            error_type="invalid_arguments",
        )

    content = (
        str(int(value))
        if float(value).is_integer()
        else str(value)
    )

    return ToolExecutionResult(
        success=True,
        content=content,
    )


def submit_reservation(
    attraction: str,
    visitor_count: int,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        success=True,
        content=(
            f"已创建{attraction}的模拟预订，"
            f"人数为{visitor_count}。"
            "本操作不连接真实预订或支付服务。"
        ),
    )


DEFAULT_TOOL_SPECS: dict[str, ToolSpec] = {
    "get_weather": ToolSpec(
        name="get_weather",
        function=get_weather,
        idempotent=True,
    ),
    "get_attraction_info": ToolSpec(
        name="get_attraction_info",
        function=get_attraction_info,
        idempotent=True,
    ),
    "calculator": ToolSpec(
        name="calculator",
        function=calculator,
        idempotent=True,
    ),
    "submit_reservation": ToolSpec(
        name="submit_reservation",
        function=submit_reservation,
        idempotent=False,
        requires_confirmation=True,
    ),
}


def normalize_model_output(
    model_output: str,
) -> str:
    """只移除首尾空白和完整 JSON 代码围栏。"""
    if not isinstance(model_output, str):
        raise ActionParseError("模型输出必须是字符串。")

    text = model_output.strip()

    if not text:
        raise ActionParseError("模型输出为空。")

    lines = text.splitlines()
    first = lines[0].strip()
    last = lines[-1].strip()

    if first.startswith("```"):
        if first not in {"```", "```json", "```JSON"}:
            raise ActionParseError(
                "只允许未标注语言或 json 的代码围栏。"
            )

        if last != "```":
            raise ActionParseError(
                "Markdown 代码围栏没有闭合。"
            )

        text = "\n".join(lines[1:-1]).strip()

        if not text:
            raise ActionParseError(
                "Markdown 代码围栏中没有内容。"
            )

    elif any(
        line.strip().startswith("```")
        for line in lines
    ):
        raise ActionParseError(
            "代码围栏必须完整包裹整个输出。"
        )

    return text


def parse_action(
    model_output: str,
    *,
    allowed_tools: set[str],
) -> AgentAction:
    """把不可信文本转换为经过严格校验的 Action。"""
    text = normalize_model_output(model_output)

    try:
        data = _load_bounded_json(text)
    except json.JSONDecodeError as error:
        raise ActionParseError(
            "模型输出不是合法 JSON："
            f"{error.msg}，第 {error.lineno} 行，"
            f"第 {error.colno} 列。"
        ) from error

    if not isinstance(data, dict):
        raise ActionParseError(
            "Action 顶层必须是 JSON 对象。"
        )

    _validate_exact_fields(
        data,
        {"action", "arguments"},
        "Action",
    )

    name = data["action"]
    arguments = data["arguments"]

    if (
        not isinstance(name, str)
        or not name
        or name != name.strip()
    ):
        raise ActionParseError(
            "action 必须是前后无空白的非空字符串。"
        )

    if not isinstance(arguments, dict):
        raise ActionParseError(
            "arguments 必须是 JSON 对象。"
        )

    if name not in allowed_tools | {"finish"}:
        allowed = "、".join(
            sorted(allowed_tools | {"finish"})
        )
        raise ActionParseError(
            f"未知行动：{name!r}。允许值：{allowed}。"
        )

    _validate_action_arguments(
        name,
        arguments,
    )

    return AgentAction(
        name=name,
        arguments=dict(arguments),
    )


def _validate_action_arguments(
    name: str,
    arguments: dict[str, object],
) -> None:
    if name == "get_weather":
        _validate_exact_fields(
            arguments,
            {"city"},
            "get_weather.arguments",
        )
        _require_text(arguments["city"], "city")
        return

    if name == "get_attraction_info":
        _validate_exact_fields(
            arguments,
            {"name"},
            "get_attraction_info.arguments",
        )
        _require_text(arguments["name"], "name")
        return

    if name == "calculator":
        _validate_exact_fields(
            arguments,
            {"operation", "a", "b"},
            "calculator.arguments",
        )
        operation = _require_text(
            arguments["operation"],
            "operation",
        )

        if operation not in {
            "add",
            "subtract",
            "multiply",
            "divide",
        }:
            raise ActionParseError(
                f"不支持的计算操作：{operation!r}。"
            )

        for field_name in ("a", "b"):
            if not _is_finite_number(arguments[field_name]):
                raise ActionParseError(
                    f"{field_name} 必须是有限数字。"
                )
        return

    if name == "submit_reservation":
        _validate_exact_fields(
            arguments,
            {"attraction", "visitor_count"},
            "submit_reservation.arguments",
        )
        _require_text(
            arguments["attraction"],
            "attraction",
        )
        count = arguments["visitor_count"]

        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count <= 0
        ):
            raise ActionParseError(
                "visitor_count 必须是正整数。"
            )
        return

    if name == "finish":
        _validate_exact_fields(
            arguments,
            {"answer"},
            "finish.arguments",
        )
        _require_text(arguments["answer"], "answer")
        return

    raise ActionParseError(
        f"没有为行动 {name!r} 定义参数协议。"
    )


def _validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    actual = set(data)
    missing = expected - actual
    extra = actual - expected
    details: list[str] = []

    if missing:
        details.append(
            "缺少 " + "、".join(sorted(missing))
        )

    if extra:
        details.append(
            "多出 " + "、".join(sorted(extra))
        )

    if details:
        raise ActionParseError(
            f"{context} 字段不正确："
            + "；".join(details)
            + "。"
        )


def _require_text(
    value: object,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ActionParseError(
            f"{field_name} 必须是非空字符串。"
        )

    return value.strip()


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False

    if isinstance(value, int):
        return True

    return isinstance(value, float) and math.isfinite(value)


def action_to_json(action: AgentAction) -> str:
    return json.dumps(
        {
            "action": action.name,
            "arguments": action.arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def action_key(action: AgentAction) -> str:
    arguments = json.dumps(
        action.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{action.name}:{arguments}"


def build_observation(
    action: AgentAction,
    result: ToolExecutionResult,
) -> str:
    lines = [
        "Observation:",
        f"工具名称：{action.name}",
        "工具参数："
        + json.dumps(
            action.arguments,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "执行状态："
        + ("成功" if result.success else "失败"),
    ]

    if not result.success:
        lines.append(
            f"错误类型：{result.error_type or 'unknown'}"
        )
        lines.append(
            "建议原样重试："
            + ("是" if result.retryable else "否")
        )

    lines.append(f"工具结果：{result.content}")
    return "\n".join(lines)


def append_action_observation(
    state: AgentState,
    action: AgentAction,
    observation: str,
) -> None:
    state.messages.extend(
        [
            {
                "role": "assistant",
                "content": action_to_json(action),
            },
            {
                "role": "user",
                "content": observation,
            },
        ]
    )


def _make_result(
    *,
    success: bool,
    message: str,
    reason: TerminationReason,
    state: AgentState,
    error: str | None = None,
) -> AgentRunResult:
    return AgentRunResult(
        success=success,
        message=message,
        termination_reason=reason,
        steps=state.step,
        error=error,
    )


def _finish_execution(
    *,
    state: AgentState,
    result: AgentRunResult,
) -> AgentExecution:
    """按 Record → State → Result → Trace 的顺序收口。"""
    state.finished = True
    state.termination_reason = result.termination_reason
    trace = build_execution_trace(state)

    log_method = (
        logger.info
        if result.success
        else logger.error
    )
    log_method(
        "agent_finished success=%s reason=%s steps=%s",
        result.success,
        result.termination_reason.value,
        result.steps,
    )

    return AgentExecution(
        result=result,
        state=state,
        trace=trace,
    )


def _append_terminal_record(
    *,
    state: AgentState,
    step: int,
    model_attempts: list[ModelAttemptRecord],
    action: AgentAction | None,
    tool_results: list[ToolExecutionResult],
    observation: str | None,
    reason: TerminationReason,
    error: str | None,
) -> None:
    state.records.append(
        StepRecord(
            step=step,
            model_attempts=tuple(model_attempts),
            action=(
                snapshot_action(action)
                if action is not None
                else None
            ),
            tool_results=tuple(tool_results),
            observation=observation,
            termination_reason=reason,
            error=error,
        )
    )


def _replace_last_record_termination(
    state: AgentState,
    reason: TerminationReason,
    error: str,
) -> None:
    if not state.records:
        return

    state.records[-1] = replace(
        state.records[-1],
        termination_reason=reason,
        error=error,
    )


def _request_action_for_step(
    *,
    request_action: ActionRequester,
    state: AgentState,
    policy: RetryPolicy,
    allowed_tools: set[str],
) -> tuple[
    AgentAction | None,
    list[ModelAttemptRecord],
    TerminationReason | None,
    str | None,
]:
    """在同一 Step 内记录 Network Retry 与 Format Retry。"""
    retry_messages = [
        dict(message)
        for message in state.messages
    ]
    records: list[ModelAttemptRecord] = []
    attempt_number = 0

    for format_index in range(
        policy.max_format_retries + 1
    ):
        model_output: str | None = None
        request_error: LLMRequestError | None = None

        for network_index in range(
            policy.max_network_retries + 1
        ):
            attempt_number += 1
            state.llm_calls += 1

            logger.debug(
                "model_attempt_started step=%s attempt=%s",
                state.step,
                attempt_number,
            )

            try:
                model_output = request_action(
                    retry_messages
                )
            except LLMRequestError as error:
                request_error = error
                state.request_failures += 1
                records.append(
                    ModelAttemptRecord(
                        attempt=attempt_number,
                        model_output=None,
                        request_error=str(error),
                    )
                )
                logger.warning(
                    "llm_request_failed "
                    "step=%s attempt=%s retryable=%s error=%s",
                    state.step,
                    attempt_number,
                    error.retryable,
                    error,
                )

                can_retry = (
                    error.retryable
                    and network_index
                    < policy.max_network_retries
                )

                if can_retry:
                    continue

                return (
                    None,
                    records,
                    TerminationReason.LLM_ERROR,
                    str(error),
                )
            else:
                request_error = None
                break

        if request_error is not None:
            raise RuntimeError(
                "不可达代码：请求错误未被处理。"
            )

        if model_output is None:
            raise RuntimeError(
                "不可达代码：模型没有输出也没有错误。"
            )

        try:
            action = parse_action(
                model_output,
                allowed_tools=allowed_tools,
            )
        except ActionParseError as error:
            state.parse_failures += 1
            records.append(
                ModelAttemptRecord(
                    attempt=attempt_number,
                    model_output=model_output,
                    parse_error=str(error),
                )
            )
            logger.warning(
                "action_parse_failed "
                "step=%s attempt=%s error=%s",
                state.step,
                attempt_number,
                error,
            )

            if format_index >= policy.max_format_retries:
                return (
                    None,
                    records,
                    TerminationReason.PARSE_ERROR,
                    str(error),
                )

            retry_messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": model_output,
                    },
                    {
                        "role": "user",
                        "content": (
                            "ProtocolError：上一轮输出"
                            "未通过 Action 协议校验。\n"
                            f"错误原因：{error}\n"
                            "请只重新输出一个合法 JSON 对象。"
                        ),
                    },
                ]
            )
            continue

        records.append(
            ModelAttemptRecord(
                attempt=attempt_number,
                model_output=model_output,
            )
        )
        return action, records, None, None

    raise RuntimeError(
        "不可达代码：格式重试循环未返回。"
    )


def _execute_tool_for_step(
    *,
    state: AgentState,
    action: AgentAction,
    spec: ToolSpec,
    policy: RetryPolicy,
) -> tuple[list[ToolExecutionResult], ToolExecutionResult]:
    """执行同一个 Action，并保存每一次 Tool Retry 结果。"""
    results: list[ToolExecutionResult] = []

    for tool_index in range(
        policy.max_tool_retries + 1
    ):
        state.tool_calls += 1
        result = spec.function(**action.arguments)

        if not isinstance(result, ToolExecutionResult):
            raise TypeError(
                f"工具 {spec.name!r} 必须返回 "
                "ToolExecutionResult。"
            )

        results.append(result)

        if not result.success:
            state.tool_failures += 1
            logger.warning(
                "tool_failed "
                "step=%s tool=%s retryable=%s error_type=%s",
                state.step,
                action.name,
                result.retryable,
                result.error_type,
            )

        logger.info(
            "tool_completed "
            "step=%s tool=%s success=%s",
            state.step,
            action.name,
            result.success,
        )

        if result.success:
            return results, result

        can_retry = (
            result.retryable
            and spec.idempotent
            and tool_index < policy.max_tool_retries
        )

        if not can_retry:
            return results, result

    raise RuntimeError(
        "不可达代码：工具重试循环未返回。"
    )


def run_agent(
    *,
    user_task: str,
    request_action: ActionRequester,
    policy: RetryPolicy | None = None,
    confirmation_callback: ConfirmationCallback | None = None,
    tool_specs: Mapping[str, ToolSpec] | None = None,
    clock: Clock = monotonic,
) -> AgentExecution:
    """运行带状态、轨迹和日志的可靠 Agent Loop。"""
    active_policy = policy or RetryPolicy()
    normalized_task = (
        user_task.strip()
        if isinstance(user_task, str)
        else ""
    )

    if not normalized_task:
        state = AgentState()
        state.finished = True
        state.termination_reason = (
            TerminationReason.INVALID_INPUT
        )
        result = AgentRunResult(
            success=False,
            message="用户任务不能为空。",
            termination_reason=(
                TerminationReason.INVALID_INPUT
            ),
            steps=0,
        )
        return AgentExecution(
            result=result,
            state=state,
            trace=build_execution_trace(state),
        )

    active_specs = dict(
        DEFAULT_TOOL_SPECS
        if tool_specs is None
        else tool_specs
    )

    if not active_specs:
        state = AgentState()
        state.finished = True
        state.termination_reason = (
            TerminationReason.INVALID_INPUT
        )
        result = AgentRunResult(
            success=False,
            message="工具集合不能为空。",
            termination_reason=(
                TerminationReason.INVALID_INPUT
            ),
            steps=0,
        )
        return AgentExecution(
            result=result,
            state=state,
            trace=build_execution_trace(state),
        )

    state = create_initial_state(
        AGENT_SYSTEM_PROMPT,
        normalized_task,
    )
    started_at = clock()
    previous_key: str | None = None
    repeated_count = 0

    logger.info(
        "agent_started task_length=%s",
        len(normalized_task),
    )

    for step in range(1, active_policy.max_steps + 1):
        if clock() - started_at > active_policy.timeout_seconds:
            _replace_last_record_termination(
                state,
                TerminationReason.TIMEOUT,
                "超过 Agent 总超时。",
            )
            result = _make_result(
                success=False,
                message="Agent 运行超过总时间限制。",
                reason=TerminationReason.TIMEOUT,
                state=state,
                error="超过 Agent 总超时。",
            )
            return _finish_execution(
                state=state,
                result=result,
            )

        state.step = step
        logger.info(
            "agent_step_started step=%s",
            step,
        )

        (
            action,
            model_attempts,
            request_reason,
            request_error,
        ) = _request_action_for_step(
            request_action=request_action,
            state=state,
            policy=active_policy,
            allowed_tools=set(active_specs),
        )

        if request_reason is not None:
            _append_terminal_record(
                state=state,
                step=step,
                model_attempts=model_attempts,
                action=None,
                tool_results=[],
                observation=None,
                reason=request_reason,
                error=request_error,
            )
            result = _make_result(
                success=False,
                message=(
                    "模型服务当前不可用。"
                    if request_reason
                    is TerminationReason.LLM_ERROR
                    else "模型输出未通过 Action 协议校验。"
                ),
                reason=request_reason,
                state=state,
                error=request_error,
            )
            return _finish_execution(
                state=state,
                result=result,
            )

        if action is None:
            raise RuntimeError(
                "不可达代码：没有 Action 或终止原因。"
            )

        key = action_key(action)
        repeated_count = (
            repeated_count + 1
            if key == previous_key
            else 1
        )
        previous_key = key

        logger.debug(
            "action_accepted "
            "step=%s key=%s repeated_count=%s",
            step,
            key,
            repeated_count,
        )

        if repeated_count >= active_policy.repeated_action_limit:
            _append_terminal_record(
                state=state,
                step=step,
                model_attempts=model_attempts,
                action=action,
                tool_results=[],
                observation=None,
                reason=TerminationReason.REPEATED_ACTION,
                error=key,
            )
            result = _make_result(
                success=False,
                message="Agent 连续生成了相同 Action。",
                reason=TerminationReason.REPEATED_ACTION,
                state=state,
                error=key,
            )
            return _finish_execution(
                state=state,
                result=result,
            )

        if action.name == "finish":
            _append_terminal_record(
                state=state,
                step=step,
                model_attempts=model_attempts,
                action=action,
                tool_results=[],
                observation=None,
                reason=TerminationReason.SUCCESS,
                error=None,
            )
            result = _make_result(
                success=True,
                message=str(action.arguments["answer"]),
                reason=TerminationReason.SUCCESS,
                state=state,
            )
            return _finish_execution(
                state=state,
                result=result,
            )

        spec = active_specs[action.name]

        if spec.requires_confirmation:
            if confirmation_callback is None:
                _append_terminal_record(
                    state=state,
                    step=step,
                    model_attempts=model_attempts,
                    action=action,
                    tool_results=[],
                    observation=None,
                    reason=(
                        TerminationReason.CONFIRMATION_REQUIRED
                    ),
                    error=f"等待确认：{action.name}",
                )
                result = _make_result(
                    success=False,
                    message=(
                        "当前 Action 需要用户明确确认后"
                        "才能执行。"
                    ),
                    reason=(
                        TerminationReason.CONFIRMATION_REQUIRED
                    ),
                    state=state,
                    error=f"等待确认：{action.name}",
                )
                return _finish_execution(
                    state=state,
                    result=result,
                )

            if not confirmation_callback(action):
                _append_terminal_record(
                    state=state,
                    step=step,
                    model_attempts=model_attempts,
                    action=action,
                    tool_results=[],
                    observation=None,
                    reason=TerminationReason.USER_REJECTED,
                    error=f"用户拒绝：{action.name}",
                )
                result = _make_result(
                    success=False,
                    message="用户拒绝执行当前 Action。",
                    reason=TerminationReason.USER_REJECTED,
                    state=state,
                    error=f"用户拒绝：{action.name}",
                )
                return _finish_execution(
                    state=state,
                    result=result,
                )

        try:
            tool_results, final_tool_result = (
                _execute_tool_for_step(
                    state=state,
                    action=action,
                    spec=spec,
                    policy=active_policy,
                )
            )
        except TypeError as error:
            _append_terminal_record(
                state=state,
                step=step,
                model_attempts=model_attempts,
                action=action,
                tool_results=[],
                observation=None,
                reason=TerminationReason.TOOL_ERROR,
                error=str(error),
            )
            result = _make_result(
                success=False,
                message="工具发生无法继续处理的受控错误。",
                reason=TerminationReason.TOOL_ERROR,
                state=state,
                error=str(error),
            )
            return _finish_execution(
                state=state,
                result=result,
            )

        observation = build_observation(
            action,
            final_tool_result,
        )
        append_action_observation(
            state,
            action,
            observation,
        )
        state.records.append(
            StepRecord(
                step=step,
                model_attempts=tuple(model_attempts),
                action=snapshot_action(action),
                tool_results=tuple(tool_results),
                observation=observation,
            )
        )

    _replace_last_record_termination(
        state,
        TerminationReason.MAX_STEPS,
        "超过最大 Agent 决策步数。",
    )
    result = _make_result(
        success=False,
        message="Agent 已达到最大执行步数。",
        reason=TerminationReason.MAX_STEPS,
        state=state,
        error="超过最大 Agent 决策步数。",
    )
    return _finish_execution(
        state=state,
        result=result,
    )


class DemoSequenceRequester:
    """手工故障演示器；正式 Mock LLM 留到下一章。"""

    def __init__(
        self,
        outputs: list[str | LLMRequestError],
    ) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def __call__(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        self.calls += 1

        if not self._outputs:
            raise LLMRequestError(
                "演示输出已经耗尽。",
                retryable=False,
            )

        output = self._outputs.pop(0)

        if isinstance(output, LLMRequestError):
            raise output

        return output


def _json_action(
    name: str,
    arguments: dict[str, object],
) -> str:
    return json.dumps(
        {
            "action": name,
            "arguments": arguments,
        },
        ensure_ascii=False,
    )


def _main_outputs(
    *,
    include_format_error: bool,
) -> list[str]:
    outputs: list[str] = []

    if include_format_error:
        outputs.append(
            '{"action": "get_weather"}'
        )

    outputs.extend(
        [
            _json_action(
                "get_weather",
                {"city": "北京"},
            ),
            _json_action(
                "get_attraction_info",
                {"name": "故宫"},
            ),
            _json_action(
                "calculator",
                {
                    "operation": "multiply",
                    "a": 60,
                    "b": 2,
                },
            ),
            _json_action(
                "finish",
                {
                    "answer": (
                        "北京当前模拟天气为晴，温度30℃；"
                        "故宫在模拟数据中处于开放状态，"
                        "成人票价60元，两张票共120元。"
                        "建议注意防晒补水。"
                        "以上信息来自本地模拟数据。"
                    )
                },
            ),
        ]
    )
    return outputs


def _flaky_weather_spec() -> ToolSpec:
    remaining_failures = 1

    def flaky_weather(
        city: str,
    ) -> ToolExecutionResult:
        nonlocal remaining_failures

        if remaining_failures > 0:
            remaining_failures -= 1
            return ToolExecutionResult(
                success=False,
                content="模拟天气服务暂时不可用。",
                error_type="temporary_unavailable",
                retryable=True,
            )

        return get_weather(city)

    return ToolSpec(
        name="get_weather",
        function=flaky_weather,
        idempotent=True,
    )


def build_demo(
    scenario: str,
) -> tuple[
    str,
    ActionRequester,
    RetryPolicy,
    ConfirmationCallback | None,
    dict[str, ToolSpec],
]:
    task = (
        "请查询北京的模拟天气和故宫的模拟开放信息，"
        "计算两张成人票的总价，并给出出行建议。"
    )
    policy = RetryPolicy()
    confirmation: ConfirmationCallback | None = None
    specs = dict(DEFAULT_TOOL_SPECS)

    if scenario == "main":
        requester = DemoSequenceRequester(
            _main_outputs(
                include_format_error=True,
            )
        )

    elif scenario == "normal":
        requester = DemoSequenceRequester(
            _main_outputs(
                include_format_error=False,
            )
        )

    elif scenario == "network-retry":
        requester = DemoSequenceRequester(
            [
                LLMRequestError(
                    "模拟模型请求超时。",
                    retryable=True,
                ),
                *_main_outputs(
                    include_format_error=False,
                ),
            ]
        )

    elif scenario == "tool-retry":
        requester = DemoSequenceRequester(
            _main_outputs(
                include_format_error=False,
            )
        )
        specs["get_weather"] = _flaky_weather_spec()

    elif scenario == "repeated-action":
        requester = DemoSequenceRequester(
            [
                _json_action(
                    "get_weather",
                    {"city": "北京"},
                ),
                _json_action(
                    "get_weather",
                    {"city": "北京"},
                ),
            ]
        )

    elif scenario == "parse-error":
        requester = DemoSequenceRequester(
            [
                "不是 JSON",
                '{"action": "get_weather"}',
                '{"action": "weather", "arguments": {}}',
            ]
        )

    elif scenario == "confirmation-required":
        task = "请为两人提交故宫模拟预订。"
        requester = DemoSequenceRequester(
            [
                _json_action(
                    "submit_reservation",
                    {
                        "attraction": "故宫",
                        "visitor_count": 2,
                    },
                )
            ]
        )

    elif scenario == "user-rejected":
        task = "请为两人提交故宫模拟预订。"
        requester = DemoSequenceRequester(
            [
                _json_action(
                    "submit_reservation",
                    {
                        "attraction": "故宫",
                        "visitor_count": 2,
                    },
                )
            ]
        )
        confirmation = lambda action: False

    elif scenario == "confirmation-approved":
        task = "请为两人提交故宫模拟预订。"
        requester = DemoSequenceRequester(
            [
                _json_action(
                    "submit_reservation",
                    {
                        "attraction": "故宫",
                        "visitor_count": 2,
                    },
                ),
                _json_action(
                    "finish",
                    {
                        "answer": (
                            "已完成两人的故宫模拟预订。"
                            "本操作不连接真实预订或支付服务。"
                        )
                    },
                ),
            ]
        )
        confirmation = lambda action: True

    elif scenario == "max-steps":
        requester = DemoSequenceRequester(
            [
                _json_action(
                    "get_weather",
                    {"city": "北京"},
                ),
                _json_action(
                    "get_weather",
                    {"city": "上海"},
                ),
            ]
        )
        policy = RetryPolicy(max_steps=2)

    else:
        raise ValueError(f"未知演示场景：{scenario}")

    return task, requester, policy, confirmation, specs


def create_openai_requester() -> ActionRequester:
    """读取项目根目录 .env 并创建真实模型请求函数。"""
    try:
        from dotenv import load_dotenv
        from openai import (
            APIConnectionError,
            APIStatusError,
            APITimeoutError,
            AuthenticationError,
            OpenAI,
            OpenAIError,
            RateLimitError,
        )
    except ImportError as error:
        raise RuntimeError(
            "真实模式需要安装 openai 和 python-dotenv。"
        ) from error

    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model_id = os.getenv("LLM_MODEL_ID")

    missing = [
        name
        for name, value in {
            "LLM_API_KEY": api_key,
            "LLM_BASE_URL": base_url,
            "LLM_MODEL_ID": model_id,
        }.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "缺少环境变量："
            + "、".join(missing)
            + "。"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=30.0,
        max_retries=0,
    )

    def requester(
        messages: list[dict[str, str]],
    ) -> str:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages,
                temperature=0,
            )
        except AuthenticationError as error:
            raise LLMRequestError(
                "模型服务拒绝访问，请检查 API Key。",
                retryable=False,
            ) from error
        except (
            APIConnectionError,
            APITimeoutError,
            RateLimitError,
        ) as error:
            raise LLMRequestError(
                f"{type(error).__name__}: {error}",
                retryable=True,
            ) from error
        except APIStatusError as error:
            raise LLMRequestError(
                f"HTTP {error.status_code}: {error}",
                retryable=error.status_code >= 500,
            ) from error
        except OpenAIError as error:
            raise LLMRequestError(
                f"{type(error).__name__}: {error}",
                retryable=False,
            ) from error

        if not response.choices:
            raise LLMRequestError(
                "模型响应 choices 列表为空。",
                retryable=False,
            )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise LLMRequestError(
                "模型没有返回可用文本。",
                retryable=False,
            )

        return content

    return requester


def print_execution(
    execution: AgentExecution,
) -> None:
    """分别展示 User Output、State 摘要和开发者 Trace。"""
    result = execution.result
    state = execution.state

    print()
    print("=" * 72)
    print("User Output")
    print("=" * 72)
    print(result.message)

    print()
    print("=" * 72)
    print("AgentState")
    print("=" * 72)
    print(f"finished = {state.finished}")
    print(
        "termination_reason = "
        f"{state.termination_reason.value}"
    )
    print(f"step = {state.step}")
    print(f"llm_calls = {state.llm_calls}")
    print(f"tool_calls = {state.tool_calls}")
    print(
        f"request_failures = {state.request_failures}"
    )
    print(f"parse_failures = {state.parse_failures}")
    print(f"tool_failures = {state.tool_failures}")

    print()
    print("=" * 72)
    print("Execution Trace")
    print("=" * 72)
    print_trace(execution.trace)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="第十三章：状态、轨迹与日志",
    )
    parser.add_argument(
        "task",
        nargs="?",
        default="",
        help="真实模型模式下的用户任务。",
    )
    parser.add_argument(
        "--scenario",
        default="main",
        choices=[
            "main",
            "normal",
            "network-retry",
            "tool-retry",
            "repeated-action",
            "parse-error",
            "confirmation-required",
            "confirmation-approved",
            "user-rejected",
            "max-steps",
        ],
        help="选择无需 API 的手工故障演示。",
    )
    parser.add_argument(
        "--real",
        action="store_true",
        help="使用 .env 中配置的真实模型。",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="DEBUG、INFO、WARNING、ERROR 或 CRITICAL。",
    )
    parser.add_argument(
        "--save-trace",
        default="",
        help="将 Execution Trace 保存到指定 JSON 路径。",
    )
    args = parser.parse_args()

    configure_logging(args.log_level)

    if args.real:
        requester = create_openai_requester()
        task = args.task.strip() or (
            "请查询北京的模拟天气，并根据工具结果"
            "给出简洁说明。"
        )
        execution = run_agent(
            user_task=task,
            request_action=requester,
        )
    else:
        (
            task,
            requester,
            policy,
            confirmation,
            specs,
        ) = build_demo(args.scenario)
        execution = run_agent(
            user_task=task,
            request_action=requester,
            policy=policy,
            confirmation_callback=confirmation,
            tool_specs=specs,
        )

    print_execution(execution)

    if args.save_trace:
        trace_path = Path(args.save_trace)
        save_trace(
            execution.trace,
            trace_path,
        )
        print()
        print(f"Trace 已保存：{trace_path}")


if __name__ == "__main__":
    main()
