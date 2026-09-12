"""一次模型输出的解析与 Action Protocol 校验。"""

from __future__ import annotations

import json
import math

from .action import AgentAction
from .tools import ToolRegistry


class ActionParseError(ValueError):
    """模型输出无法解析，或没有通过当前 Action Protocol。"""


MAX_OUTPUT_CHARS = 65_536
MAX_JSON_DEPTH = 64
MAX_INTEGER_DIGITS = 128


def _check_json_depth(text: str) -> None:
    """只统计字符串以外的括号，避免把回答中的括号误当成结构。"""
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
            if depth > MAX_JSON_DEPTH:
                raise ActionParseError("JSON 嵌套层数超过限制。")
        elif character in "}]":
            depth -= 1


def _parse_integer(text: str) -> int:
    if len(text.lstrip("-")) > MAX_INTEGER_DIGITS:
        raise ValueError("JSON 整数位数超过限制。")
    return int(text)


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("JSON 数字必须是有限值。")
    return value


def _reject_constant(text: str) -> None:
    raise ValueError("JSON 不允许 NaN 或 Infinity。")


def normalize_model_output(model_output: str) -> str:
    if not isinstance(model_output, str):
        raise ActionParseError("模型输出必须是字符串。")

    if len(model_output) > MAX_OUTPUT_CHARS:
        raise ActionParseError("模型输出长度超过限制。")

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
            raise ActionParseError("Markdown 代码围栏没有闭合。")

        text = "\n".join(lines[1:-1]).strip()
        if not text:
            raise ActionParseError("Markdown 代码围栏中没有内容。")
    elif any(line.strip().startswith("```") for line in lines):
        raise ActionParseError("代码围栏必须完整包裹整个输出。")

    return text


def load_json_object(model_output: str) -> dict[str, object]:
    """有限解析模型 JSON；应用层可复用，再校验自己的字段协议。"""
    text = normalize_model_output(model_output)
    _check_json_depth(text)
    try:
        data = json.loads(
            text,
            parse_int=_parse_integer,
            parse_float=_parse_float,
            parse_constant=_reject_constant,
        )
    except (ValueError, RecursionError) as error:
        raise ActionParseError("模型输出不是合法或可接受规模的 JSON。") from error
    if not isinstance(data, dict):
        raise ActionParseError("JSON 顶层必须是 JSON 对象。")
    return data


def parse_action(
    model_output: str,
    tools: ToolRegistry,
    *,
    require_reason: bool = False,
) -> AgentAction:
    """解析一次输出；是否重试由 Agent 负责。"""
    data = load_json_object(model_output)

    allowed_fields = {"action", "arguments", "reason"}
    required_fields = {"action", "arguments"}
    if require_reason:
        required_fields.add("reason")

    _validate_fields(
        data,
        required=required_fields,
        allowed=allowed_fields,
        context="Action",
    )

    reason_value = data.get("reason")
    reason: str | None
    if reason_value is None:
        reason = None
    elif not isinstance(reason_value, str) or not reason_value.strip():
        raise ActionParseError("reason 必须是非空字符串。")
    else:
        reason = reason_value.strip()

    if require_reason and reason is None:
        raise ActionParseError("当前模式要求提供 reason。")

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
        raise ActionParseError("arguments 必须是 JSON 对象。")

    action = AgentAction(
        name=name,
        arguments=dict(arguments),
        reason=reason,
    )

    if action.name == "finish":
        _validate_finish(action)
    else:
        try:
            tools.validate(action)
        except (TypeError, ValueError) as error:
            raise ActionParseError(str(error)) from error

    return action


def _validate_finish(action: AgentAction) -> None:
    _validate_fields(
        action.arguments,
        required={"answer"},
        allowed={"answer"},
        context="finish.arguments",
    )
    answer = action.arguments["answer"]
    if not isinstance(answer, str) or not answer.strip():
        raise ActionParseError("finish.answer 必须是非空字符串。")


def _validate_fields(
    data: dict[str, object],
    *,
    required: set[str],
    allowed: set[str],
    context: str,
) -> None:
    actual = set(data)
    missing = required - actual
    extra = actual - allowed
    problems: list[str] = []

    if missing:
        problems.append("缺少 " + "、".join(sorted(missing)))
    if extra:
        problems.append("多出 " + "、".join(sorted(extra)))

    if problems:
        raise ActionParseError(
            f"{context} 字段不正确：" + "；".join(problems) + "。"
        )
