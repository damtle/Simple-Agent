"""旅行场景工具及其 ToolRegistry。"""

from __future__ import annotations

import math

from simple_agent import Tool, ToolRegistry

if __package__:
    from .data import ATTRACTION_DATA, WEATHER_DATA
else:
    from data import ATTRACTION_DATA, WEATHER_DATA


_CALCULATOR_OPERATIONS = {
    "add",
    "subtract",
    "multiply",
    "divide",
}


def get_weather(city: str) -> str:
    """读取指定城市的本地模拟天气。"""
    normalized_city = city.strip()
    data = WEATHER_DATA.get(normalized_city)

    if data is None:
        raise ValueError(
            f"没有找到城市“{normalized_city}”的模拟天气数据。"
        )

    return (
        f"{normalized_city}当前模拟天气为"
        f"{data['condition']}，"
        f"温度{data['temperature']}℃，"
        f"湿度{data['humidity']}%，"
        f"{data['wind']}。"
    )


def get_attraction_info(name: str) -> str:
    """读取指定景点的本地模拟信息。"""
    normalized_name = name.strip()
    data = ATTRACTION_DATA.get(normalized_name)

    if data is None:
        raise ValueError(
            f"没有找到景点“{normalized_name}”的模拟信息。"
        )

    status = "开放" if data["open"] else "闭馆"

    return (
        f"{normalized_name}位于{data['city']}，"
        f"在当前模拟数据中处于{status}状态，"
        f"成人票价{data['adult_ticket']}元，"
        f"活动类型为{data['activity_type']}。"
        f"{data['description']}"
    )


def calculator(
    operation: str,
    a: float,
    b: float,
) -> str:
    """执行有限集合中的确定性四则运算。"""
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("除数不能为 0。")
        result = a / b
    else:
        raise ValueError(
            f"不支持的计算操作：{operation}"
        )

    if not math.isfinite(float(result)):
        raise ValueError("计算结果不是有限数字。")

    if float(result).is_integer():
        return str(int(result))

    return str(result)


def validate_weather_arguments(
    arguments: dict[str, object],
) -> None:
    """校验天气工具的参数结构，不检查数据是否存在。"""
    _validate_exact_arguments(
        arguments,
        expected={"city"},
        tool_name="get_weather",
    )
    _require_non_empty_text(
        arguments["city"],
        field_name="city",
    )


def validate_attraction_arguments(
    arguments: dict[str, object],
) -> None:
    """校验景点工具的参数结构，不检查数据是否存在。"""
    _validate_exact_arguments(
        arguments,
        expected={"name"},
        tool_name="get_attraction_info",
    )
    _require_non_empty_text(
        arguments["name"],
        field_name="name",
    )


def validate_calculator_arguments(
    arguments: dict[str, object],
) -> None:
    """校验计算器操作、字段和数字类型。"""
    _validate_exact_arguments(
        arguments,
        expected={"operation", "a", "b"},
        tool_name="calculator",
    )

    operation = _require_non_empty_text(
        arguments["operation"],
        field_name="operation",
    )

    if operation not in _CALCULATOR_OPERATIONS:
        allowed = "、".join(sorted(_CALCULATOR_OPERATIONS))
        raise ValueError(
            f"operation 必须是：{allowed}。"
        )

    for field_name in ("a", "b"):
        value = arguments[field_name]

        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not -1e100 <= value <= 1e100
        ):
            raise ValueError(
                f"{field_name} 必须是 -1e100 至 1e100 之间的有限数字。"
            )


def build_travel_tools() -> ToolRegistry:
    """创建本次应用独立持有的旅行工具注册表。"""
    tools = ToolRegistry()

    tools.register(
        Tool(
            name="get_weather",
            description=(
                "查询一个城市的本地模拟天气；"
                "当前数据范围为北京、上海、广州。"
            ),
            parameters={
                "city": "城市名称字符串",
            },
            function=get_weather,
            validator=validate_weather_arguments,
        )
    )

    tools.register(
        Tool(
            name="get_attraction_info",
            description=(
                "查询一个景点的本地模拟开放状态、"
                "成人票价和活动类型；当前数据范围为"
                "故宫、上海博物馆、广东省博物馆。"
            ),
            parameters={
                "name": "景点名称字符串",
            },
            function=get_attraction_info,
            validator=validate_attraction_arguments,
        )
    )

    tools.register(
        Tool(
            name="calculator",
            description=(
                "执行两个有限数字之间的加、减、乘、除。"
            ),
            parameters={
                "operation": (
                    "add|subtract|multiply|divide"
                ),
                "a": "第一个数字",
                "b": "第二个数字",
            },
            function=calculator,
            validator=validate_calculator_arguments,
        )
    )

    return tools


def _validate_exact_arguments(
    arguments: dict[str, object],
    *,
    expected: set[str],
    tool_name: str,
) -> None:
    actual = set(arguments)
    missing = expected - actual
    extra = actual - expected
    problems: list[str] = []

    if missing:
        problems.append(
            "缺少 " + "、".join(sorted(missing))
        )

    if extra:
        problems.append(
            "多出 " + "、".join(sorted(extra))
        )

    if problems:
        raise ValueError(
            f"{tool_name} 参数不正确："
            + "；".join(problems)
            + "。"
        )


def _require_non_empty_text(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} 必须是非空字符串。"
        )

    return value.strip()
