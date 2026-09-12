"""第二章：第一次调用大语言模型。

该示例实现 Simple Travel Assistant v0.1：
读取一条旅行问题，构造 system 与 user 消息，调用一次兼容
OpenAI Chat Completions 的模型服务，并打印模型回答。

本章不保存多轮历史，也不包含工具、Action 或 Agent Loop。
"""

import os

from dotenv import load_dotenv
from openai import OpenAI


SYSTEM_MESSAGE = (
    "你是一名城市旅行助手。"
    "请使用简洁、清晰的中文回答。"
    "当问题涉及实时天气、票价或开放状态时，"
    "请明确提醒用户进一步核实。"
)


def require_env(name: str) -> str:
    """读取必需环境变量；缺失时在发送请求前终止程序。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请检查项目根目录下的 .env 文件。"
        )

    return value


def main() -> None:
    """完成一次独立的旅行问题模型调用。"""
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model_id = require_env("LLM_MODEL_ID")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    user_message = input("请输入旅行问题：").strip()

    if not user_message:
        raise ValueError("用户问题不能为空。")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    if not response.choices:
        raise RuntimeError("模型返回了响应，但 choices 列表为空。")

    answer = response.choices[0].message.content

    if answer is None or not answer.strip():
        raise RuntimeError("模型返回了响应，但没有可用的文本回答。")

    print("\n旅行助手：")
    print(answer.strip())


if __name__ == "__main__":
    main()
