"""把不可信模型字符串解析并校验为 AgentAction。"""

from __future__ import annotations

import json
import math

from .action import AgentAction
from .tools import ToolRegistry


class ActionParseError(ValueError):
    """模型 Action 无法解析，或没有通过当前协议校验。"""


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

    if len(model_output) > 65_536:
        raise ActionParseError("模型输出长度超过限制。")
    text = model_output.strip()
    if not text:
        raise ActionParseError("模型输出为空。")
    return text


def strip_markdown_fence(text: str) -> str:
    lines = text.splitlines()
    if len(lines) < 3:
        return text

    first = lines[0].strip()
    last = lines[-1].strip()
    if not first.startswith("```") or last != "```":
        return text

    inner = "\n".join(lines[1:-1]).strip()
    if not inner:
        raise ActionParseError("Markdown 代码块中没有 Action 内容。")
    return inner


def _find_json_values(text: str) -> list[object]:
    _check_json_depth(text)
    if len(text) > 65_536:
        raise ActionParseError("模型输出长度超过限制。")
    decoder = json.JSONDecoder(
        parse_int=_parse_integer,
        parse_float=_parse_float,
        parse_constant=_reject_constant,
    )
    values: list[object] = []
    index = 0

    while index < len(text):
        if text[index] not in "{[":
            index += 1
            continue
        try:
            value, consumed = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            index += 1
            continue
        except (ValueError, RecursionError) as error:
            raise ActionParseError("JSON 数值或嵌套超出允许范围。") from error
        values.append(value)
        index += consumed

    return values


def _format_json_error(error: json.JSONDecodeError) -> str:
    return (
        "JSON 语法错误："
        f"第 {error.lineno} 行，第 {error.colno} 列，{error.msg}。"
    )


def extract_json_object(text: str) -> dict[str, object]:
    """接受纯 JSON、整段 Markdown 围栏或前后有少量说明的唯一对象。"""
    _check_json_depth(text)
    if len(text) > 65_536:
        raise ActionParseError("模型输出长度超过限制。")
    decoder = json.JSONDecoder(
        parse_int=_parse_integer,
        parse_float=_parse_float,
        parse_constant=_reject_constant,
    )
    stripped = text.lstrip()

    if not stripped:
        raise ActionParseError("模型输出为空。")

    if stripped[0] in "{[":
        try:
            value, consumed = decoder.raw_decode(stripped)
        except json.JSONDecodeError as error:
            raise ActionParseError(_format_json_error(error)) from error
        except (ValueError, RecursionError) as error:
            raise ActionParseError("JSON 数值或嵌套超出允许范围。") from error

        if stripped[consumed:].strip():
            values = _find_json_values(stripped)
            if len(values) != 1:
                raise ActionParseError("模型输出中必须且只能包含一个 JSON 值。")
        if not isinstance(value, dict):
            raise ActionParseError("Action 顶层必须是 JSON 对象。")
        return value

    values = _find_json_values(stripped)
    if not values:
        raise ActionParseError("没有找到可解析的 JSON 对象。")
    if len(values) != 1:
        raise ActionParseError("模型输出中必须且只能包含一个 JSON 值。")

    value = values[0]
    if not isinstance(value, dict):
        raise ActionParseError("Action 顶层必须是 JSON 对象。")
    return value


def _validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    label: str,
) -> None:
    actual = set(data)
    if actual == expected:
        return

    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    details: list[str] = []
    if missing:
        details.append(f"缺少字段：{'、'.join(missing)}")
    if extra:
        details.append(f"存在额外字段：{'、'.join(extra)}")
    raise ActionParseError(f"{label} 顶层字段不符合协议（{'；'.join(details)}）。")


def _non_empty_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ActionParseError(f"{field_name} 必须是字符串。")
    normalized = value.strip()
    if not normalized:
        raise ActionParseError(f"{field_name} 不能为空。")
    return normalized


def _validate_finish(arguments: dict[str, object]) -> dict[str, object]:
    if set(arguments) != {"answer"}:
        raise ActionParseError("finish.arguments 必须且只能包含 answer。")
    return {"answer": _non_empty_text(arguments.get("answer"), "finish.answer")}


def parse_action(
    model_output: str,
    tools: ToolRegistry,
    require_reason: bool = False,
) -> AgentAction:
    """完成一次文本整理、JSON 解析和 Action 协议校验。"""
    text = strip_markdown_fence(normalize_model_output(model_output))
    data = extract_json_object(text)

    expected = {"action", "arguments"}
    if require_reason:
        expected.add("reason")
    _validate_exact_fields(data, expected, "Action")

    name = _non_empty_text(data.get("action"), "action")
    arguments = data.get("arguments")
    if not isinstance(arguments, dict):
        raise ActionParseError("arguments 必须是 JSON 对象。")

    reason: str | None = None
    if require_reason:
        reason = _non_empty_text(data.get("reason"), "reason")

    if name == "finish":
        validated_arguments = _validate_finish(arguments)
    else:
        action = AgentAction(name=name, arguments=dict(arguments), reason=reason)
        try:
            tools.validate(action)
        except (TypeError, ValueError) as error:
            raise ActionParseError(str(error)) from error
        validated_arguments = dict(arguments)

    return AgentAction(
        name=name,
        arguments=validated_arguments,
        reason=reason,
    )
