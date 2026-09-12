"""Simple Travel Assistant v1.1：ReAct Agent。

运行关系：

用户目标与已有反馈
→ ReActDecision
→ Reason + AgentAction
→ Tool
→ Observation
→ 下一轮 ReActDecision
→ finish 或 max_steps

本章在第八章 Agent Loop 上增加 Reason 决策摘要。
它不实现格式重试、工具自动重试、重复 Action 检测、
结构化轨迹或最终答案反思。
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from action import (
    ActionParseError,
    AgentAction,
    ReActDecision,
)
from parser import parse_react_decision
from prompts import REACT_SYSTEM_PROMPT


Message = dict[str, str]
DEFAULT_MAX_STEPS = 6


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


def require_env(name: str) -> str:
    """读取必需环境变量。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，"
            "请检查项目根目录下的 .env 文件。"
        )

    return value


def request_text(
    client: OpenAI,
    model_id: str,
    messages: list[Message],
) -> str:
    """根据当前完整上下文请求下一项 ReAct 决策。"""
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    if not response.choices:
        raise RuntimeError(
            "模型返回了响应，但 choices 列表为空。"
        )

    text = response.choices[0].message.content

    if not text or not text.strip():
        raise RuntimeError(
            "模型返回了响应，但没有可用文本。"
        )

    return text


def get_weather(city: str) -> str:
    """根据城市名称读取本地模拟天气。"""
    data = WEATHER_DATA.get(city)

    if data is None:
        raise ValueError(
            f"没有找到城市“{city}”的模拟天气数据。"
        )

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
        raise ValueError(
            f"没有找到景点“{name}”的模拟信息。"
        )

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


TOOL_REGISTRY = {
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


def decision_to_json(
    decision: ReActDecision,
) -> str:
    """把经过校验的 ReActDecision 序列化为规范 JSON。"""
    return json.dumps(
        {
            "reason": decision.reason,
            "action": decision.action.name,
            "arguments": decision.action.arguments,
        },
        ensure_ascii=False,
        indent=2,
    )


def build_observation(
    action: AgentAction,
    tool_result: str,
    success: bool,
    error_type: str | None = None,
) -> str:
    """根据实际工具执行构造成功或失败 Observation。"""
    arguments_text = json.dumps(
        action.arguments,
        ensure_ascii=False,
    )

    lines = [
        "Observation:",
        f"工具名称：{action.name}",
        f"工具参数：{arguments_text}",
        f"执行状态：{'成功' if success else '失败'}",
    ]

    if error_type is not None:
        lines.append(f"错误类型：{error_type}")

    lines.append(f"工具结果：{tool_result}")
    return "\n".join(lines)


def execute_action_once(
    action: AgentAction,
) -> str:
    """执行一次工具 Action，并返回对应 Observation。"""
    try:
        tool_result = execute_tool(
            tool_name=action.name,
            arguments=action.arguments,
        )
    except (TypeError, ValueError) as error:
        return build_observation(
            action=action,
            tool_result=str(error),
            success=False,
            error_type=type(error).__name__,
        )

    return build_observation(
        action=action,
        tool_result=tool_result,
        success=True,
    )


def show_decision(
    step: int,
    decision: ReActDecision,
) -> None:
    """以可读形式展示一轮 Reason 和 Action。"""
    action = decision.action

    print(f"\n=== Step {step} ===")
    print("Reason：")
    print(decision.reason)
    print("\nAction：")
    print(action.name)
    print("\nArguments：")
    print(
        json.dumps(
            action.arguments,
            ensure_ascii=False,
        )
    )


def run_react_agent(
    client: OpenAI,
    model_id: str,
    user_task: str,
    max_steps: int = DEFAULT_MAX_STEPS,
) -> str:
    """运行 ReAct Agent，直到 finish 或达到最大步数。"""
    if not user_task.strip():
        raise ValueError("用户任务不能为空。")

    if max_steps <= 0:
        raise ValueError("max_steps 必须大于 0。")

    messages: list[Message] = [
        {
            "role": "system",
            "content": REACT_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_task,
        },
    ]

    for step in range(1, max_steps + 1):
        model_output = request_text(
            client=client,
            model_id=model_id,
            messages=messages,
        )
        decision = parse_react_decision(model_output)
        action = decision.action

        show_decision(
            step=step,
            decision=decision,
        )

        messages.append(
            {
                "role": "assistant",
                "content": decision_to_json(decision),
            }
        )

        if action.name == "finish":
            answer = action.arguments["answer"]

            if not isinstance(answer, str):
                raise RuntimeError(
                    "Parser 已接受 finish，"
                    "但 answer 不是字符串。"
                )

            return answer

        observation = execute_action_once(action)

        print("\nObservation：")
        print(observation)

        messages.append(
            {
                "role": "user",
                "content": observation,
            }
        )

    raise RuntimeError(
        f"ReAct Agent 在 {max_steps} 个步骤内"
        "没有生成 finish。"
    )


def main() -> None:
    """读取配置和任务，运行第九章 ReAct Agent。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    user_task = input("请输入旅行任务：").strip()

    try:
        answer = run_react_agent(
            client=client,
            model_id=model_id,
            user_task=user_task,
            max_steps=DEFAULT_MAX_STEPS,
        )
    except ActionParseError as error:
        print(
            "\nReAct Agent 异常终止："
            f"模型决策未通过校验：{error}"
        )
        return
    except (RuntimeError, ValueError) as error:
        print(f"\nReAct Agent 异常终止：{error}")
        return

    print("\nReAct Agent 正常终止。")
    print("最终回答：")
    print(answer)


if __name__ == "__main__":
    main()
