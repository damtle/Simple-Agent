"""Simple Travel Assistant v0.4：让模型生成原始 Action 字符串。

本章只完成：

用户任务 → 工具说明与 Action Protocol → LLM → 原始字符串

程序不会调用 json.loads()，不会校验字段，也不会执行任何工具。
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

from prompts import build_action_system_prompt


def require_env(name: str) -> str:
    """读取必需环境变量；缺失时给出明确错误。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，"
            "请检查项目根目录下的 .env 文件。"
        )

    return value


def request_action(
    client: OpenAI,
    model_id: str,
    user_task: str,
) -> str:
    """请求模型根据用户任务生成一个原始 Action 字符串。"""
    messages = [
        {
            "role": "system",
            "content": build_action_system_prompt(),
        },
        {
            "role": "user",
            "content": user_task,
        },
    ]

    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    model_output = response.choices[0].message.content

    if not model_output:
        raise RuntimeError(
            "模型返回了响应，但没有可用的 Action 文本。"
        )

    return model_output


def main() -> None:
    """读取任务、调用模型并原样显示模型输出。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    user_task = input("请输入旅行任务：").strip()

    if not user_task:
        raise ValueError("用户任务不能为空。")

    model_output = request_action(
        client=client,
        model_id=model_id,
        user_task=user_task,
    )

    print("\n模型原始输出：")
    print(model_output)
    print(f"\nPython 类型：{type(model_output).__name__}")


if __name__ == "__main__":
    main()
