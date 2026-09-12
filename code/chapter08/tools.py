"""第八章沿用的本地模拟旅行工具。"""

from collections.abc import Callable


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


def get_weather(city: str) -> str:
    """根据城市名称读取本地模拟天气。"""
    data = WEATHER_DATA.get(city)

    if data is None:
        return f"没有找到城市“{city}”的模拟天气数据。"

    return (
        f"{city}当前模拟天气为{data['condition']}，"
        f"温度{data['temperature']}℃，"
        f"湿度{data['humidity']}%，"
        f"{data['wind']}。"
    )


def get_attraction_info(name: str) -> str:
    """根据景点名称读取本地模拟景点信息。"""
    data = ATTRACTION_DATA.get(name)

    if data is None:
        return f"没有找到景点“{name}”的模拟信息。"

    open_status = "开放" if data["open"] else "闭馆"

    return (
        f"{name}位于{data['city']}，"
        f"在当前模拟数据中处于{open_status}状态，"
        f"成人票价{data['adult_ticket']}元，"
        f"活动类型为{data['activity_type']}。"
        f"{data['description']}"
    )


def calculator(
    operation: str,
    a: float,
    b: float,
) -> str:
    """执行受限的加、减、乘、除运算。"""
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

    if float(result).is_integer():
        return str(int(result))

    return str(result)


ToolFunction = Callable[..., str]


TOOL_REGISTRY: dict[str, ToolFunction] = {
    "get_weather": get_weather,
    "get_attraction_info": get_attraction_info,
    "calculator": calculator,
}


def execute_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> str:
    """通过注册名称执行工具并返回 Tool Result。"""
    tool_function = TOOL_REGISTRY.get(tool_name)

    if tool_function is None:
        available_tools = ", ".join(TOOL_REGISTRY)
        raise ValueError(
            f"未知工具：{tool_name}。"
            f"可用工具：{available_tools}"
        )

    try:
        result = tool_function(**arguments)
    except TypeError as error:
        raise ValueError(
            f"工具“{tool_name}”的参数不正确：{error}"
        ) from error

    if not isinstance(result, str):
        raise TypeError(
            f"工具“{tool_name}”必须返回字符串。"
        )

    return result
