"""运行不访问网络的固定案例并展示基础 Metrics。"""

from __future__ import annotations

import json

from metrics import AgentMetrics, collect_metrics, summarize_metrics
from mock_llm import MockLLM
from simple_agent import Agent, TerminationReason, Tool, ToolRegistry
from simple_agent.action import AgentAction, snapshot_action
from simple_agent.parser import (
    ActionParseError,
    parse_action as _parse_action,
)
from simple_agent.state import create_initial_state as _create_initial_state
from simple_agent.tools import ToolInputError


def validate_weather(arguments: dict[str, object]) -> None:
    if set(arguments) != {"city"}:
        raise ValueError("get_weather 参数必须且只能包含 city。")
    city = arguments["city"]
    if not isinstance(city, str) or not city.strip():
        raise ValueError("city 必须是非空字符串。")


def get_weather(city: str) -> str:
    data = {
        "北京": "晴，30℃",
        "上海": "多云，27℃",
        "广州": "阵雨，32℃",
    }
    if city not in data:
        raise ToolInputError(
            f"没有城市“{city}”的本地模拟天气。",
            error_type="not_found",
        )
    return f"{city}模拟天气：{data[city]}。"


def create_tools() -> ToolRegistry:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="get_weather",
            description="查询北京、上海或广州的本地模拟天气。",
            parameters={"city": "城市名称"},
            function=get_weather,
            validator=validate_weather,
        )
    )
    return tools


def create_initial_state(
    *,
    system_prompt: str,
    user_task: str,
):
    """保持正文使用的参数名称，同时调用本章状态构造函数。"""
    return _create_initial_state(system_prompt, user_task)


def parse_action(model_output: str) -> AgentAction:
    """为本章正文示例提供使用默认旅行工具的 Parser 入口。"""
    return _parse_action(model_output, create_tools())


def execute_tool(
    tool_name: str,
    arguments: dict[str, object],
):
    """为工具单元测试提供稳定的教学入口。"""
    return create_tools().execute(
        AgentAction(name=tool_name, arguments=arguments)
    )


def run_agent(
    *,
    user_task: str,
    llm: MockLLM,
    max_steps: int = 8,
    max_format_retries: int = 2,
    max_same_action: int = 2,
):
    """用本章默认工具运行一次确定性 Agent。"""
    agent = Agent(
        llm=llm,
        tools=create_tools(),
        max_steps=max_steps,
        max_format_retries=max_format_retries,
        max_same_action=max_same_action,
    )
    return agent.run(user_task)


def run_case(outputs: list[str]) -> AgentMetrics:
    agent = Agent(
        llm=MockLLM(outputs),
        tools=create_tools(),
        max_steps=4,
        max_format_retries=1,
    )
    execution = agent.run("请查询北京的模拟天气。")
    return collect_metrics(execution)


def main() -> None:
    cases = [
        run_case(
            [
                '{"action":"get_weather","arguments":{"city":"北京"}}',
                '{"action":"finish","arguments":{"answer":"查询完成。"}}',
            ]
        ),
        run_case(
            [
                '{"action":"get_weather","arguments":{"city":"北京",}}',
                '{"action":"get_weather","arguments":{"city":"北京"}}',
                '{"action":"finish","arguments":{"answer":"查询完成。"}}',
            ]
        ),
    ]
    print(json.dumps(summarize_metrics(cases), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
