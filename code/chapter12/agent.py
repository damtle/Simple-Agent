"""Simple Travel Assistant v1.4：失败、重试与终止。

本章把可靠性控制接入最小 Agent Loop：

输入检查 → Network/Format Retry → Action 校验
→ 重复检测 → Confirmation → Tool Retry
→ Failure Observation / Decision Retry → 统一终止结果

运行确定性演示：

    python code/chapter12/agent.py
    python code/chapter12/agent.py --scenario format-retry
    python code/chapter12/agent.py --scenario tool-retry
    python code/chapter12/agent.py --scenario repeated-action

使用真实模型：

    python code/chapter12/agent.py --scenario real
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import math
import os
from time import monotonic
from typing import Protocol

from result import (
    AgentRunResult,
    TerminationReason,
    confirmation_required_result,
    invalid_input_result,
    llm_error_result,
    parse_error_result,
    repeated_action_result,
    timeout_result,
    tool_error_result,
    user_rejected_result,
)
from retry import (
    LLMRequestError,
    RetryPolicy,
    call_with_network_retry,
    execute_with_tool_retry,
)
from tools import (
    TOOL_SPECS,
    ToolExecutionResult,
    ToolSpec,
    create_flaky_tool,
)


@dataclass(frozen=True)
class AgentAction:
    """经过 Parser 校验、可以进入 Controller 的行动。"""

    name: str
    arguments: dict[str, object]


class ActionParseError(ValueError):
    """模型输出无法被解析或未通过 Action Protocol。"""


class ActionRequester(Protocol):
    def __call__(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """根据当前上下文返回一个原始 Action 字符串。"""


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
   该行动执行前必须由程序取得用户确认。

5. finish
   arguments: {"answer": "最终回答"}

规则：
1. 任务未完成时选择一个必要工具。
2. 工具失败后，根据 Observation 修改参数、
   选择其他行动或说明能力边界。
3. 不要重复已经成功且无需再次执行的 Action。
4. 所有天气、景点、票价和预订信息均为本地模拟数据。
5. 不要输出 Markdown 代码块或额外说明。
""".strip()



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


def create_initial_messages(
    user_task: str,
) -> list[dict[str, str]]:
    normalized_task = user_task.strip()

    if not normalized_task:
        raise ValueError("用户任务不能为空。")

    return [
        {
            "role": "system",
            "content": AGENT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": normalized_task,
        },
    ]


def normalize_model_output(model_output: str) -> str:
    """只去除首尾空白和完整 JSON 代码围栏。"""
    if not isinstance(model_output, str):
        raise ActionParseError("模型输出必须是字符串。")

    text = model_output.strip()

    if not text:
        raise ActionParseError("模型输出为空。")

    lines = text.splitlines()
    first_line = lines[0].strip()
    last_line = lines[-1].strip()

    if first_line.startswith("```"):
        if first_line not in {"```", "```json", "```JSON"}:
            raise ActionParseError(
                "只允许未标注语言或 json 的完整代码围栏。"
            )

        if last_line != "```":
            raise ActionParseError(
                "Markdown 代码围栏没有完整闭合。"
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
            "Markdown 代码围栏必须完整包裹整个输出。"
        )

    return text


def parse_action(
    model_output: str,
    allowed_tools: set[str] | None = None,
) -> AgentAction:
    """将不可信模型文本转换为经过严格校验的 AgentAction。"""
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

    action_name = data["action"]
    arguments = data["arguments"]

    if (
        not isinstance(action_name, str)
        or not action_name
        or action_name != action_name.strip()
    ):
        raise ActionParseError(
            "action 必须是前后无空白的非空字符串。"
        )

    if not isinstance(arguments, dict):
        raise ActionParseError(
            "arguments 必须是 JSON 对象。"
        )

    current_allowed_tools = (
        set(TOOL_SPECS)
        if allowed_tools is None
        else set(allowed_tools)
    )
    allowed_actions = current_allowed_tools | {"finish"}

    if action_name not in allowed_actions:
        allowed = "、".join(sorted(allowed_actions))
        raise ActionParseError(
            f"未知行动：{action_name!r}。允许值：{allowed}。"
        )

    _validate_arguments(action_name, arguments)

    return AgentAction(
        name=action_name,
        arguments=dict(arguments),
    )


def _validate_arguments(
    action_name: str,
    arguments: dict[str, object],
) -> None:
    if action_name == "get_weather":
        _validate_exact_fields(
            arguments,
            {"city"},
            "get_weather.arguments",
        )
        _require_text(arguments["city"], "city")
        return

    if action_name == "get_attraction_info":
        _validate_exact_fields(
            arguments,
            {"name"},
            "get_attraction_info.arguments",
        )
        _require_text(arguments["name"], "name")
        return

    if action_name == "calculator":
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

    if action_name == "submit_reservation":
        _validate_exact_fields(
            arguments,
            {"attraction", "visitor_count"},
            "submit_reservation.arguments",
        )
        _require_text(
            arguments["attraction"],
            "attraction",
        )
        visitor_count = arguments["visitor_count"]

        if (
            isinstance(visitor_count, bool)
            or not isinstance(visitor_count, int)
            or visitor_count <= 0
        ):
            raise ActionParseError(
                "visitor_count 必须是正整数。"
            )
        return

    if action_name == "finish":
        _validate_exact_fields(
            arguments,
            {"answer"},
            "finish.arguments",
        )
        _require_text(arguments["answer"], "answer")
        return

    raise ActionParseError(
        f"没有为行动 {action_name!r} 定义参数协议。"
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
        details.append("缺少 " + "、".join(sorted(missing)))

    if extra:
        details.append("多出 " + "、".join(sorted(extra)))

    if details:
        raise ActionParseError(
            f"{context} 字段不正确：" + "；".join(details) + "。"
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
    """生成与参数键顺序无关的稳定 Action 标识。"""
    arguments = json.dumps(
        action.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{action.name}:{arguments}"


def update_repeated_action_count(
    *,
    current_key: str,
    previous_key: str | None,
    previous_count: int,
) -> int:
    if current_key == previous_key:
        return previous_count + 1

    return 1


def request_valid_action(
    *,
    request_action: ActionRequester,
    messages: list[dict[str, str]],
    policy: RetryPolicy,
    allowed_tools: set[str],
) -> AgentAction:
    """在同一 Agent Step 内完成 Network Retry 与 Format Retry。"""
    retry_messages = [
        dict(message)
        for message in messages
    ]

    for format_attempt in range(
        policy.max_format_retries + 1
    ):
        model_output = call_with_network_retry(
            request_fn=lambda: request_action(
                retry_messages
            ),
            max_retries=policy.max_network_retries,
        )

        try:
            return parse_action(
                model_output,
                allowed_tools=allowed_tools,
            )
        except ActionParseError as error:
            if format_attempt >= policy.max_format_retries:
                raise

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
                            "请只重新输出一个符合协议的"
                            " JSON 对象。"
                        ),
                    },
                ]
            )

    raise RuntimeError(
        "不可达代码：格式重试循环未结束。"
    )


def confirm_action(
    *,
    action: AgentAction,
    spec: ToolSpec,
    confirmation_callback: ConfirmationCallback | None,
) -> bool | None:
    """True=已确认，False=拒绝，None=当前没有确认渠道。"""
    if not spec.requires_confirmation:
        return True

    if confirmation_callback is None:
        return None

    return confirmation_callback(action)


def build_observation(
    *,
    action: AgentAction,
    result: ToolExecutionResult,
) -> str:
    status = "成功" if result.success else "失败"
    lines = [
        "Observation:",
        f"工具名称：{action.name}",
        "工具参数："
        + json.dumps(
            action.arguments,
            ensure_ascii=False,
            sort_keys=True,
        ),
        f"执行状态：{status}",
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
    *,
    messages: list[dict[str, str]],
    action: AgentAction,
    observation: str,
) -> None:
    messages.extend(
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


def run_agent(
    *,
    user_task: str,
    request_action: ActionRequester,
    policy: RetryPolicy | None = None,
    confirmation_callback: ConfirmationCallback | None = None,
    tool_specs: Mapping[str, ToolSpec] | None = None,
    clock: Clock = monotonic,
) -> AgentRunResult:
    """驱动带有限重试、确认和受控终止的 Agent Loop。"""
    active_policy = policy or RetryPolicy()
    normalized_task = user_task.strip()

    if not normalized_task:
        return invalid_input_result("用户任务不能为空。")

    active_specs = dict(
        TOOL_SPECS if tool_specs is None else tool_specs
    )

    if not active_specs:
        return invalid_input_result("工具集合不能为空。")

    messages = create_initial_messages(normalized_task)
    started_at = clock()
    previous_action_key: str | None = None
    repeated_action_count = 0

    for step in range(1, active_policy.max_steps + 1):
        if clock() - started_at > active_policy.timeout_seconds:
            return timeout_result(steps=step - 1)

        try:
            action = request_valid_action(
                request_action=request_action,
                messages=messages,
                policy=active_policy,
                allowed_tools=set(active_specs),
            )
        except LLMRequestError as error:
            return llm_error_result(
                steps=step - 1,
                error=str(error),
            )
        except ActionParseError as error:
            return parse_error_result(
                steps=step,
                error=str(error),
            )

        current_key = action_key(action)
        repeated_action_count = update_repeated_action_count(
            current_key=current_key,
            previous_key=previous_action_key,
            previous_count=repeated_action_count,
        )
        previous_action_key = current_key

        if (
            repeated_action_count
            >= active_policy.repeated_action_limit
        ):
            return repeated_action_result(
                steps=step,
                action_key=current_key,
            )

        if action.name == "finish":
            return AgentRunResult(
                success=True,
                message=str(action.arguments["answer"]),
                termination_reason=TerminationReason.SUCCESS,
                steps=step,
            )

        spec = active_specs[action.name]
        confirmation = confirm_action(
            action=action,
            spec=spec,
            confirmation_callback=confirmation_callback,
        )

        if confirmation is None:
            return confirmation_required_result(
                steps=step,
                action_name=action.name,
            )

        if confirmation is False:
            return user_rejected_result(
                steps=step,
                action_name=action.name,
            )

        try:
            tool_result = execute_with_tool_retry(
                spec=spec,
                arguments=action.arguments,
                max_retries=active_policy.max_tool_retries,
            )
        except TypeError as error:
            return tool_error_result(
                steps=step,
                error=str(error),
            )

        observation = build_observation(
            action=action,
            result=tool_result,
        )
        append_action_observation(
            messages=messages,
            action=action,
            observation=observation,
        )

    return AgentRunResult(
        success=False,
        message="Agent 已达到最大执行步数。",
        termination_reason=TerminationReason.MAX_STEPS,
        steps=active_policy.max_steps,
        error="超过最大 Agent 决策步数。",
    )


class ScriptedRequester:
    """章节演示用的确定性输出序列，不属于正式 Mock LLM。"""

    def __init__(
        self,
        outputs: list[str | LLMRequestError],
    ) -> None:
        self._outputs = list(outputs)
        self.calls = 0
        self.received_messages: list[
            list[dict[str, str]]
        ] = []

    def __call__(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        self.calls += 1
        self.received_messages.append(
            [dict(message) for message in messages]
        )

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


def build_demo(
    scenario: str,
) -> tuple[
    str,
    ActionRequester,
    RetryPolicy,
    ConfirmationCallback | None,
    dict[str, ToolSpec],
]:
    """构造不依赖真实模型的确定性故障演示。"""
    task = (
        "请查询北京的模拟天气和故宫开放信息，"
        "计算两张成人票总价，并给出出行建议。"
    )
    policy = RetryPolicy()
    specs = dict(TOOL_SPECS)
    confirmation: ConfirmationCallback | None = None

    success_outputs = [
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
                    "故宫在模拟数据中开放，"
                    "两张成人票共120元。"
                    "建议注意防晒补水。"
                    "以上信息来自本地模拟数据。"
                )
            },
        ),
    ]

    if scenario == "success":
        requester = ScriptedRequester(success_outputs)

    elif scenario == "network-retry":
        requester = ScriptedRequester(
            [
                LLMRequestError(
                    "模拟模型请求超时。",
                    retryable=True,
                ),
                *success_outputs,
            ]
        )

    elif scenario == "format-retry":
        requester = ScriptedRequester(
            [
                '{"action": "get_weather"}',
                *success_outputs,
            ]
        )

    elif scenario == "tool-retry":
        requester = ScriptedRequester(success_outputs)
        weather_spec = specs["get_weather"]
        specs["get_weather"] = ToolSpec(
            name=weather_spec.name,
            function=create_flaky_tool(
                weather_spec.function,
                failures_before_success=1,
            ),
            idempotent=weather_spec.idempotent,
            requires_confirmation=(
                weather_spec.requires_confirmation
            ),
        )

    elif scenario == "repeated-action":
        requester = ScriptedRequester(
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
        requester = ScriptedRequester(
            [
                "天气工具",
                '{"action": "get_weather"}',
                '{"action": "weather", "arguments": {}}',
            ]
        )

    elif scenario == "confirmation-required":
        task = "请为两人提交故宫模拟预订。"
        requester = ScriptedRequester(
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

    elif scenario == "confirmation-approved":
        task = "请为两人提交故宫模拟预订。"
        requester = ScriptedRequester(
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

    elif scenario == "user-rejected":
        task = "请为两人提交故宫模拟预订。"
        requester = ScriptedRequester(
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

    elif scenario == "max-steps":
        requester = ScriptedRequester(
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
        policy = RetryPolicy(
            max_steps=2,
            repeated_action_limit=2,
        )

    else:
        raise ValueError(f"未知演示场景：{scenario}")

    return task, requester, policy, confirmation, specs


def create_openai_requester() -> ActionRequester:
    """读取 .env，并把 OpenAI SDK 错误转换为 LLMRequestError。"""
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
            "真实模型模式需要安装 openai 和 python-dotenv。"
        ) from error

    load_dotenv()

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
            "缺少环境变量：" + "、".join(missing) + "。"
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
            retryable = error.status_code >= 500
            raise LLMRequestError(
                f"HTTP {error.status_code}: {error}",
                retryable=retryable,
            ) from error
        except OpenAIError as error:
            raise LLMRequestError(
                f"{type(error).__name__}: {error}",
                retryable=False,
            ) from error

        if not response.choices:
            raise LLMRequestError(
                "模型响应的 choices 列表为空。",
                retryable=False,
            )

        content = response.choices[0].message.content

        if not content or not content.strip():
            raise LLMRequestError(
                "模型返回了响应，但没有文本内容。",
                retryable=False,
            )

        return content

    return requester


def print_run_result(result: AgentRunResult) -> None:
    print()
    print("=" * 72)
    print("AgentRunResult")
    print("=" * 72)
    print(f"success：{result.success}")
    print(
        "termination_reason："
        f"{result.termination_reason.value}"
    )
    print(f"steps：{result.steps}")
    print(f"message：{result.message}")
    print(f"error：{result.error or 'None'}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="第十二章：失败、重试与终止",
    )
    parser.add_argument(
        "--scenario",
        default="success",
        choices=[
            "success",
            "network-retry",
            "format-retry",
            "tool-retry",
            "repeated-action",
            "parse-error",
            "confirmation-required",
            "confirmation-approved",
            "user-rejected",
            "max-steps",
            "real",
        ],
        help="选择确定性演示或真实模型模式。",
    )
    parser.add_argument(
        "--task",
        default="",
        help="真实模型模式下的用户任务。",
    )
    args = parser.parse_args()

    if args.scenario == "real":
        requester = create_openai_requester()
        task = args.task.strip() or (
            "请查询北京的模拟天气和故宫的模拟开放信息，"
            "计算两张成人票的总价，并给出出行建议。"
        )
        result = run_agent(
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
        result = run_agent(
            user_task=task,
            request_action=requester,
            policy=policy,
            confirmation_callback=confirmation,
            tool_specs=specs,
        )

    print_run_result(result)


if __name__ == "__main__":
    main()
