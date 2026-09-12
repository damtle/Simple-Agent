"""第九章：解析并校验 ReAct 决策。

处理顺序：

model_output
→ Text Normalization
→ JSON Parsing
→ ReAct Protocol Validation
→ AgentAction Validation
→ ReActDecision

Parser 只能检查结构、字段和参数类型，不能证明 Reason 与
Action 在语义上完全一致。
"""

import json
import math
from collections.abc import Callable

from action import (
    ActionParseError,
    AgentAction,
    ReActDecision,
)


ArgumentValidator = Callable[[dict[str, object]], None]



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


def normalize_model_output(model_output: str) -> str:
    """去除首尾空白，并有限处理完整 Markdown 代码围栏。"""
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
                "只允许使用未标注语言或 json 标记的代码围栏。"
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
            "Markdown 代码围栏必须完整包裹整个模型输出。"
        )

    return text


def parse_json_object(text: str) -> dict[str, object]:
    """把规范化文本解析为顶层 JSON 对象。"""
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
            "ReAct 决策顶层必须是 JSON 对象。"
        )

    return data


def validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    """要求对象字段与协议完全一致。"""
    actual = set(data)
    missing = expected - actual
    extra = actual - expected
    details: list[str] = []

    if missing:
        details.append(
            "缺少 " + ", ".join(sorted(missing))
        )

    if extra:
        details.append(
            "多出 " + ", ".join(sorted(extra))
        )

    if details:
        raise ActionParseError(
            f"{context}字段不正确："
            + "；".join(details)
            + "。"
        )


def validate_non_empty_string(
    value: object,
    field_name: str,
) -> str:
    """校验并返回去除首尾空白后的非空字符串。"""
    if not isinstance(value, str):
        raise ActionParseError(
            f"{field_name} 必须是字符串。"
        )

    normalized = value.strip()

    if not normalized:
        raise ActionParseError(
            f"{field_name} 不能为空。"
        )

    return normalized


def validate_weather_arguments(
    arguments: dict[str, object],
) -> None:
    """校验 get_weather 参数。"""
    validate_exact_fields(
        data=arguments,
        expected={"city"},
        context="get_weather.arguments",
    )
    validate_non_empty_string(
        arguments["city"],
        "get_weather.city",
    )


def validate_attraction_arguments(
    arguments: dict[str, object],
) -> None:
    """校验 get_attraction_info 参数。"""
    validate_exact_fields(
        data=arguments,
        expected={"name"},
        context="get_attraction_info.arguments",
    )
    validate_non_empty_string(
        arguments["name"],
        "get_attraction_info.name",
    )


def is_finite_number(value: object) -> bool:
    """判断值是否为有限数字，并明确排除 bool。"""
    if isinstance(value, bool):
        return False

    if isinstance(value, int):
        return True

    if isinstance(value, float):
        return math.isfinite(value)

    return False


def validate_calculator_arguments(
    arguments: dict[str, object],
) -> None:
    """校验 calculator 参数。"""
    validate_exact_fields(
        data=arguments,
        expected={"operation", "a", "b"},
        context="calculator.arguments",
    )

    operation = arguments["operation"]

    if not isinstance(operation, str):
        raise ActionParseError(
            "calculator.operation 必须是字符串。"
        )

    allowed_operations = {
        "add",
        "subtract",
        "multiply",
        "divide",
    }

    if operation not in allowed_operations:
        raise ActionParseError(
            f"不支持的计算操作：{operation!r}。"
        )

    if not is_finite_number(arguments["a"]):
        raise ActionParseError(
            "calculator.a 必须是有限数字。"
        )

    if not is_finite_number(arguments["b"]):
        raise ActionParseError(
            "calculator.b 必须是有限数字。"
        )


def validate_finish_arguments(
    arguments: dict[str, object],
) -> None:
    """校验 finish 参数。"""
    validate_exact_fields(
        data=arguments,
        expected={"answer"},
        context="finish.arguments",
    )
    validate_non_empty_string(
        arguments["answer"],
        "finish.answer",
    )


ARGUMENT_VALIDATORS: dict[str, ArgumentValidator] = {
    "get_weather": validate_weather_arguments,
    "get_attraction_info": validate_attraction_arguments,
    "calculator": validate_calculator_arguments,
    "finish": validate_finish_arguments,
}


def validate_action(
    action_name: object,
    arguments: object,
) -> AgentAction:
    """校验 Action 名称和参数，并构造 AgentAction。"""
    if not isinstance(action_name, str):
        raise ActionParseError(
            "action 必须是字符串。"
        )

    if not action_name:
        raise ActionParseError(
            "action 不能为空。"
        )

    if action_name != action_name.strip():
        raise ActionParseError(
            "action 前后不能包含空白字符。"
        )

    if not isinstance(arguments, dict):
        raise ActionParseError(
            "arguments 必须是 JSON 对象。"
        )

    validator = ARGUMENT_VALIDATORS.get(action_name)

    if validator is None:
        allowed = ", ".join(ARGUMENT_VALIDATORS)
        raise ActionParseError(
            f"未知行动：{action_name!r}。"
            f"允许的行动：{allowed}。"
        )

    validator(arguments)

    return AgentAction(
        name=action_name,
        arguments=dict(arguments),
    )


def parse_react_decision(
    model_output: str,
) -> ReActDecision:
    """把模型原始文本转换为经过校验的 ReActDecision。"""
    text = normalize_model_output(model_output)
    data = parse_json_object(text)

    validate_exact_fields(
        data=data,
        expected={"reason", "action", "arguments"},
        context="ReAct 决策顶层",
    )

    reason = validate_non_empty_string(
        data["reason"],
        "reason",
    )
    action = validate_action(
        action_name=data["action"],
        arguments=data["arguments"],
    )

    return ReActDecision(
        reason=reason,
        action=action,
    )
