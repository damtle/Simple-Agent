"""Simple Travel Assistant v0.6：工具结果与 Observation。

固定流程：

用户任务
→ 第一次模型调用生成 Action
→ Parser
→ 最多执行一次工具
→ 构造 Tool Observation
→ 第二次模型调用生成最终回答

本章不实现不确定次数的循环、连续多工具调用或自动重试。
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from parser import (
    ActionParseError,
    AgentAction,
    parse_action,
)
from prompts import (
    ACTION_SYSTEM_PROMPT,
    FINAL_ANSWER_SYSTEM_PROMPT,
)
from tools import execute_tool


Message = dict[str, str]


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
    """发送一次模型请求并提取非空文本。"""
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    text = response.choices[0].message.content

    if not text:
        raise RuntimeError(
            "模型返回了响应，但没有可用文本。"
        )

    return text


def request_action(
    client: OpenAI,
    model_id: str,
    user_task: str,
) -> str:
    """第一次调用：让模型选择一个 Action。"""
    return request_text(
        client=client,
        model_id=model_id,
        messages=[
            {
                "role": "system",
                "content": ACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_task,
            },
        ],
    )


def action_to_json(action: AgentAction) -> str:
    """把经过校验的 AgentAction 序列化为规范 JSON。"""
    return json.dumps(
        {
            "action": action.name,
            "arguments": action.arguments,
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
    """根据 Action、执行状态和 Tool Result 构造反馈。"""
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


def execute_action_once(action: AgentAction) -> str:
    """执行一次工具 Action，并返回成功或失败 Observation。"""
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


def build_final_answer_messages(
    user_task: str,
    action: AgentAction,
    observation: str,
) -> list[Message]:
    """构造包含 Action-Observation Pair 的第二次请求。"""
    return [
        {
            "role": "system",
            "content": FINAL_ANSWER_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_task,
        },
        {
            "role": "assistant",
            "content": action_to_json(action),
        },
        {
            "role": "user",
            "content": observation,
        },
    ]


def request_final_answer(
    client: OpenAI,
    model_id: str,
    user_task: str,
    action: AgentAction,
    observation: str,
) -> str:
    """第二次调用：根据任务和 Observation 生成最终回答。"""
    return request_text(
        client=client,
        model_id=model_id,
        messages=build_final_answer_messages(
            user_task=user_task,
            action=action,
            observation=observation,
        ),
    )


def run_task(
    client: OpenAI,
    model_id: str,
    user_task: str,
) -> str:
    """按照固定两阶段流程处理一次旅行任务。"""
    model_output = request_action(
        client=client,
        model_id=model_id,
        user_task=user_task,
    )

    print("\n第一次模型输出：")
    print(model_output)

    action = parse_action(model_output)

    print("\n程序接受的 AgentAction：")
    print(action)

    if action.name == "finish":
        answer = action.arguments["answer"]

        if not isinstance(answer, str):
            raise RuntimeError(
                "Parser 已接受 finish，"
                "但 answer 不是字符串。"
            )

        return answer

    observation = execute_action_once(action)

    print("\n构造的 Observation：")
    print(observation)

    return request_final_answer(
        client=client,
        model_id=model_id,
        user_task=user_task,
        action=action,
        observation=observation,
    )


def main() -> None:
    """读取配置和用户任务，运行固定 Observation 流程。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    user_task = input("请输入旅行任务：").strip()

    if not user_task:
        raise ValueError("用户任务不能为空。")

    try:
        answer = run_task(
            client=client,
            model_id=model_id,
            user_task=user_task,
        )
    except ActionParseError as error:
        print(f"\nAction 解析失败：{error}")
        return

    print("\n最终回答：")
    print(answer)


if __name__ == "__main__":
    main()
