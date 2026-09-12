"""使用同一核心包构建 ReAct 风格的本地模拟旅行 Agent。"""

from __future__ import annotations

import os
import sys
from numbers import Real

from dotenv import load_dotenv
from openai import OpenAI

from simple_agent import Agent, OpenAIChatLLM, Tool, ToolRegistry
from simple_agent.tools import ToolInputError


WEATHER_DATA: dict[str, dict[str, object]] = {
    "北京": {"condition": "晴", "temperature": 30},
    "上海": {"condition": "多云", "temperature": 27},
    "广州": {"condition": "阵雨", "temperature": 32},
}


def get_weather(city: str) -> str:
    weather = WEATHER_DATA.get(city)
    if weather is None:
        raise ToolInputError(
            f"没有找到城市“{city}”的模拟天气。",
            error_type="not_found",
        )
    return (
        f"城市={city}；天气={weather['condition']}；"
        f"温度={weather['temperature']}℃。"
    )


def recommend_activity(condition: str, temperature: float) -> str:
    if "雨" in condition:
        activity, category, price = "博物馆参观", "室内", 80
    elif temperature >= 30:
        activity, category, price = "傍晚城市公园散步", "户外", 30
    else:
        activity, category, price = "城市骑行", "户外", 60
    return (
        f"推荐活动={activity}；活动类型={category}；"
        f"单人模拟费用={price}元。"
    )


def calculator(operation: str, a: float, b: float) -> str:
    if operation != "multiply":
        raise ValueError("旅行示例中的计算器只开放 multiply。")
    return str(a * b)


def validate_weather(arguments: dict[str, object]) -> None:
    if set(arguments) != {"city"}:
        raise ValueError("get_weather 参数必须且只能包含 city。")
    city = arguments["city"]
    if not isinstance(city, str) or not city.strip():
        raise ValueError("city 必须是非空字符串。")


def validate_activity(arguments: dict[str, object]) -> None:
    if set(arguments) != {"condition", "temperature"}:
        raise ValueError("recommend_activity 需要 condition 和 temperature。")
    if not isinstance(arguments["condition"], str):
        raise ValueError("condition 必须是字符串。")
    value = arguments["temperature"]
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError("temperature 必须是数字。")


def validate_calculator(arguments: dict[str, object]) -> None:
    if set(arguments) != {"operation", "a", "b"}:
        raise ValueError("calculator 需要 operation、a 和 b。")
    if arguments["operation"] != "multiply":
        raise ValueError("operation 必须是 multiply。")
    for name in ("a", "b"):
        value = arguments[name]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} 必须是数字。")


def create_llm() -> OpenAIChatLLM:
    load_dotenv()
    required = ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"缺少环境变量：{', '.join(missing)}")
    client = OpenAI(
        api_key=os.environ["LLM_API_KEY"],
        base_url=os.environ["LLM_BASE_URL"],
        timeout=30.0,
        max_retries=2,
    )
    return OpenAIChatLLM(client=client, model_id=os.environ["LLM_MODEL_ID"])


def create_tools() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="get_weather",
            description="查询北京、上海或广州的本地模拟天气。",
            parameters={"city": "城市名称"},
            function=get_weather,
            validator=validate_weather,
            retryable=False,
        )
    )
    tools.register(
        Tool(
            name="recommend_activity",
            description="根据天气状况和温度推荐活动，并返回单人模拟费用。",
            parameters={
                "condition": "天气工具返回的天气状况",
                "temperature": "天气工具返回的温度数字",
            },
            function=recommend_activity,
            validator=validate_activity,
        )
    )
    tools.register(
        Tool(
            name="calculator",
            description="把单人费用乘以人数，计算模拟总费用。",
            parameters={
                "operation": "固定为 multiply",
                "a": "单人费用",
                "b": "人数",
            },
            function=calculator,
            validator=validate_calculator,
        )
    )
    return tools


def main() -> None:
    task = (
        " ".join(sys.argv[1:]).strip()
        or "查询北京的模拟天气，推荐一个适合两人的活动，并计算预计总费用。"
    )
    agent = Agent(
        llm=create_llm(),
        tools=create_tools(),
        max_steps=8,
        require_reason=True,
    )
    execution = agent.run(task)
    print(execution.message)
    print(
        f"步骤={execution.state.step}，模型调用={execution.state.llm_calls}，"
        f"工具调用={execution.state.tool_calls}，"
        f"终止原因={execution.termination_reason.value}"
    )


if __name__ == "__main__":
    main()
