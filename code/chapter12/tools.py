"""第十二章：结构化工具结果、工具元数据与模拟旅行工具。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ToolExecutionResult:
    """一次工具执行的结构化结果。"""

    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False


ToolFunction = Callable[..., ToolExecutionResult]


@dataclass(frozen=True)
class ToolSpec:
    """Controller 判断工具能否重试、是否需确认的元数据。"""

    name: str
    function: ToolFunction
    idempotent: bool
    requires_confirmation: bool = False


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


def get_weather(city: str) -> ToolExecutionResult:
    """读取本地模拟天气。"""
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


def get_attraction_info(name: str) -> ToolExecutionResult:
    """读取本地模拟景点信息。"""
    data = ATTRACTION_DATA.get(name)

    if data is None:
        return ToolExecutionResult(
            success=False,
            content=f"没有找到景点“{name}”的模拟信息。",
            error_type="not_found",
            retryable=False,
        )

    open_status = "开放" if data["open"] else "闭馆"

    return ToolExecutionResult(
        success=True,
        content=(
            f"{name}位于{data['city']}，"
            f"在当前模拟数据中处于{open_status}状态，"
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
    """执行确定性的四则运算。"""
    if not _is_finite_number(a) or not _is_finite_number(b):
        return ToolExecutionResult(
            success=False,
            content="计算器参数必须是有限数字。",
            error_type="invalid_arguments",
            retryable=False,
        )

    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            return ToolExecutionResult(
                success=False,
                content="除数不能为 0。",
                error_type="invalid_arguments",
                retryable=False,
            )
        result = a / b
    else:
        return ToolExecutionResult(
            success=False,
            content=f"不支持的计算操作：{operation}",
            error_type="invalid_arguments",
            retryable=False,
        )

    if float(result).is_integer():
        output = str(int(result))
    else:
        output = str(result)

    return ToolExecutionResult(
        success=True,
        content=output,
    )


def submit_reservation(
    attraction: str,
    visitor_count: int,
) -> ToolExecutionResult:
    """创建模拟预订；不访问真实账号、支付或预订服务。"""
    return ToolExecutionResult(
        success=True,
        content=(
            f"已创建{attraction}的模拟预订，"
            f"人数为{visitor_count}。"
            "本操作不连接真实预订或支付服务。"
        ),
    )


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False

    if isinstance(value, int):
        return True

    return isinstance(value, float) and math.isfinite(value)


TOOL_SPECS: dict[str, ToolSpec] = {
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


def create_flaky_tool(
    base_function: ToolFunction,
    *,
    failures_before_success: int = 1,
    error_message: str = "模拟服务暂时不可用。",
) -> ToolFunction:
    """为教学演示创建先临时失败、后恢复的工具包装器。"""
    if (
        isinstance(failures_before_success, bool)
        or not isinstance(failures_before_success, int)
        or failures_before_success < 0
    ):
        raise ValueError(
            "failures_before_success 必须是非负整数。"
        )

    remaining = failures_before_success

    def flaky_tool(**arguments: object) -> ToolExecutionResult:
        nonlocal remaining

        if remaining > 0:
            remaining -= 1
            return ToolExecutionResult(
                success=False,
                content=error_message,
                error_type="temporary_unavailable",
                retryable=True,
            )

        return base_function(**arguments)

    return flaky_tool
