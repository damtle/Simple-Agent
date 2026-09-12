"""可靠的同步 Agent Loop 编排。"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass, replace
import json
from time import monotonic

from .action import (
    AgentAction,
    action_fingerprint,
    action_to_json,
    snapshot_action,
)
from .llm import LLM, LLMRequestError, Message
from .parser import ActionParseError, parse_action
from .state import (
    AgentExecution,
    AgentRunResult,
    AgentState,
    ExecutionTrace,
    ModelAttemptRecord,
    StepRecord,
    TerminationReason,
)
from .tools import ToolExecutionResult, ToolRegistry


ConfirmationCallback = Callable[[AgentAction], bool]


@dataclass(frozen=True)
class RetryPolicy:
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

        if min(
            self.max_network_retries,
            self.max_format_retries,
            self.max_tool_retries,
        ) < 0:
            raise ValueError("重试次数不能小于 0。")
        if self.max_steps <= 0:
            raise ValueError("max_steps 必须大于 0。")
        if self.repeated_action_limit < 2:
            raise ValueError("repeated_action_limit 至少为 2。")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds 必须大于 0。")


class Agent:
    """连接 LLM、Parser、ToolRegistry、State 与终止策略。"""

    def __init__(
        self,
        *,
        llm: LLM,
        tools: ToolRegistry,
        system_prompt: str,
        policy: RetryPolicy | None = None,
        require_reason: bool = False,
    ) -> None:
        if not isinstance(system_prompt, str) or not system_prompt.strip():
            raise ValueError("system_prompt 不能为空。")
        if not isinstance(tools, ToolRegistry):
            raise TypeError("tools 必须是 ToolRegistry。")

        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt.strip()
        self.policy = policy or RetryPolicy()
        self.require_reason = require_reason

    def run(
        self,
        user_task: str,
        *,
        confirmation_callback: ConfirmationCallback | None = None,
    ) -> AgentExecution:
        """使用全新 AgentState 运行一次任务。"""
        if not isinstance(user_task, str) or not user_task.strip():
            state = AgentState(
                finished=True,
                termination_reason=TerminationReason.INVALID_INPUT,
            )
            return self._execution(
                state=state,
                success=False,
                message="用户任务不能为空。",
                reason=TerminationReason.INVALID_INPUT,
            )

        state = AgentState(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_task.strip()},
            ]
        )
        started_at = monotonic()
        previous_fingerprint: str | None = None
        repeated_count = 0

        for step in range(1, self.policy.max_steps + 1):
            if monotonic() - started_at > self.policy.timeout_seconds:
                self._mark_last_record(
                    state,
                    reason=TerminationReason.TIMEOUT,
                    error="超过 Agent 总时间限制。",
                )
                return self._execution(
                    state=state,
                    success=False,
                    message="Agent 运行超过总时间限制。",
                    reason=TerminationReason.TIMEOUT,
                    error="超过 Agent 总时间限制。",
                )

            state.step = step
            action, attempts, terminal_reason, terminal_error = (
                self._request_valid_action(state)
            )

            if terminal_reason is not None:
                state.records.append(
                    StepRecord(
                        step=step,
                        model_attempts=tuple(attempts),
                        action=None,
                        tool_results=(),
                        observation=None,
                        termination_reason=terminal_reason,
                        error=terminal_error,
                    )
                )
                return self._execution(
                    state=state,
                    success=False,
                    message=(
                        "模型服务当前不可用。"
                        if terminal_reason is TerminationReason.LLM_ERROR
                        else "模型输出未通过 Action 协议校验。"
                    ),
                    reason=terminal_reason,
                    error=terminal_error,
                )

            if action is None:
                raise RuntimeError("没有得到 Action 或终止原因。")

            fingerprint = action_fingerprint(action)
            repeated_count = (
                repeated_count + 1
                if fingerprint == previous_fingerprint
                else 1
            )
            previous_fingerprint = fingerprint

            if repeated_count >= self.policy.repeated_action_limit:
                state.records.append(
                    StepRecord(
                        step=step,
                        model_attempts=tuple(attempts),
                        action=snapshot_action(action),
                        tool_results=(),
                        observation=None,
                        termination_reason=TerminationReason.REPEATED_ACTION,
                        error=fingerprint,
                    )
                )
                return self._execution(
                    state=state,
                    success=False,
                    message="Agent 连续生成了相同 Action。",
                    reason=TerminationReason.REPEATED_ACTION,
                    error=fingerprint,
                )

            if action.name == "finish":
                state.records.append(
                    StepRecord(
                        step=step,
                        model_attempts=tuple(attempts),
                        action=snapshot_action(action),
                        tool_results=(),
                        observation=None,
                        termination_reason=TerminationReason.SUCCESS,
                    )
                )
                return self._execution(
                    state=state,
                    success=True,
                    message=str(action.arguments["answer"]).strip(),
                    reason=TerminationReason.SUCCESS,
                )

            if self.tools.requires_confirmation(action):
                if confirmation_callback is None:
                    state.records.append(
                        StepRecord(
                            step=step,
                            model_attempts=tuple(attempts),
                            action=snapshot_action(action),
                            tool_results=(),
                            observation=None,
                            termination_reason=(
                                TerminationReason.CONFIRMATION_REQUIRED
                            ),
                            error=f"等待确认：{action.name}",
                        )
                    )
                    return self._execution(
                        state=state,
                        success=False,
                        message="当前 Action 需要用户明确确认后才能执行。",
                        reason=TerminationReason.CONFIRMATION_REQUIRED,
                        error=f"等待确认：{action.name}",
                    )

                if not confirmation_callback(action):
                    state.records.append(
                        StepRecord(
                            step=step,
                            model_attempts=tuple(attempts),
                            action=snapshot_action(action),
                            tool_results=(),
                            observation=None,
                            termination_reason=TerminationReason.USER_REJECTED,
                            error=f"用户拒绝：{action.name}",
                        )
                    )
                    return self._execution(
                        state=state,
                        success=False,
                        message="用户拒绝执行当前 Action。",
                        reason=TerminationReason.USER_REJECTED,
                        error=f"用户拒绝：{action.name}",
                    )

            tool_results = self._execute_tool_with_retry(state, action)
            if not tool_results:
                state.records.append(
                    StepRecord(
                        step=step,
                        model_attempts=tuple(attempts),
                        action=snapshot_action(action),
                        tool_results=(),
                        observation=None,
                        termination_reason=TerminationReason.TOOL_ERROR,
                        error="工具没有返回结果。",
                    )
                )
                return self._execution(
                    state=state,
                    success=False,
                    message="工具没有返回结果。",
                    reason=TerminationReason.TOOL_ERROR,
                    error="工具没有返回结果。",
                )

            final_tool_result = tool_results[-1]
            observation = self._build_observation(action, final_tool_result)
            state.messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": action_to_json(action),
                    },
                    {"role": "user", "content": observation},
                ]
            )
            state.records.append(
                StepRecord(
                    step=step,
                    model_attempts=tuple(attempts),
                    action=snapshot_action(action),
                    tool_results=tuple(tool_results),
                    observation=observation,
                )
            )

        self._mark_last_record(
            state,
            reason=TerminationReason.MAX_STEPS,
            error="超过最大 Agent 决策步数。",
        )
        return self._execution(
            state=state,
            success=False,
            message="Agent 已达到最大执行步数。",
            reason=TerminationReason.MAX_STEPS,
            error="超过最大 Agent 决策步数。",
        )

    def _request_valid_action(
        self,
        state: AgentState,
    ) -> tuple[
        AgentAction | None,
        list[ModelAttemptRecord],
        TerminationReason | None,
        str | None,
    ]:
        retry_messages = deepcopy(state.messages)
        attempts: list[ModelAttemptRecord] = []
        attempt_number = 0

        for format_index in range(self.policy.max_format_retries + 1):
            model_output: str | None = None

            for network_index in range(
                self.policy.max_network_retries + 1
            ):
                attempt_number += 1
                state.llm_calls += 1

                try:
                    model_output = self.llm.generate(retry_messages)
                except LLMRequestError as error:
                    state.request_failures += 1
                    attempts.append(
                        ModelAttemptRecord(
                            attempt=attempt_number,
                            model_output=None,
                            request_error=str(error),
                        )
                    )
                    can_retry = (
                        error.retryable
                        and network_index < self.policy.max_network_retries
                    )
                    if can_retry:
                        continue
                    return (
                        None,
                        attempts,
                        TerminationReason.LLM_ERROR,
                        str(error),
                    )
                else:
                    break

            if model_output is None:
                raise RuntimeError("模型没有输出，也没有报告请求错误。")

            try:
                action = parse_action(
                    model_output,
                    self.tools,
                    require_reason=self.require_reason,
                )
            except ActionParseError as error:
                state.parse_failures += 1
                attempts.append(
                    ModelAttemptRecord(
                        attempt=attempt_number,
                        model_output=model_output,
                        parse_error=str(error),
                    )
                )
                if format_index >= self.policy.max_format_retries:
                    return (
                        None,
                        attempts,
                        TerminationReason.PARSE_ERROR,
                        str(error),
                    )

                retry_messages.extend(
                    [
                        {"role": "assistant", "content": model_output},
                        {
                            "role": "user",
                            "content": (
                                "ProtocolError：上一轮输出未通过 "
                                "Action 协议校验。\n"
                                f"错误原因：{error}\n"
                                "请只重新输出一个合法 JSON 对象。"
                            ),
                        },
                    ]
                )
                continue

            attempts.append(
                ModelAttemptRecord(
                    attempt=attempt_number,
                    model_output=model_output,
                )
            )
            return action, attempts, None, None

        raise RuntimeError("不可达代码。")

    def _execute_tool_with_retry(
        self,
        state: AgentState,
        action: AgentAction,
    ) -> list[ToolExecutionResult]:
        results: list[ToolExecutionResult] = []

        for retry_index in range(self.policy.max_tool_retries + 1):
            state.tool_calls += 1
            result = self.tools.execute(action)
            results.append(result)

            if result.success:
                break

            state.tool_failures += 1
            if not result.retryable or retry_index >= self.policy.max_tool_retries:
                break

        return results

    @staticmethod
    def _build_observation(
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
            "执行状态：" + ("成功" if result.success else "失败"),
        ]

        if not result.success:
            lines.append(f"错误类型：{result.error_type or 'unknown'}")
            lines.append(
                "建议原样重试：" + ("是" if result.retryable else "否")
            )

        lines.append(f"工具结果：{result.content}")
        return "\n".join(lines)

    @staticmethod
    def _mark_last_record(
        state: AgentState,
        *,
        reason: TerminationReason,
        error: str,
    ) -> None:
        if state.records:
            state.records[-1] = replace(
                state.records[-1],
                termination_reason=reason,
                error=error,
            )

    @staticmethod
    def _execution(
        *,
        state: AgentState,
        success: bool,
        message: str,
        reason: TerminationReason,
        error: str | None = None,
    ) -> AgentExecution:
        state.finished = True
        state.termination_reason = reason
        result = AgentRunResult(
            success=success,
            message=message,
            termination_reason=reason,
            steps=state.step,
            error=error,
        )
        trace = ExecutionTrace(
            records=tuple(deepcopy(state.records)),
            steps=state.step,
            termination_reason=reason,
        )
        return AgentExecution(
            result=result,
            state=state,
            trace=trace,
        )
