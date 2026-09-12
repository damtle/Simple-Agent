"""第三章：上下文与对话状态。

该示例实现 Simple Travel Assistant v0.2：
在命令行中持续接收用户输入，按照发生顺序保存 system、user 和
assistant 消息，并在每次模型调用时重新发送完整 messages。

本章只实现当前进程中的多轮会话状态，不包含长期记忆、工具、
结构化 Action、Observation 或 Agent Loop。
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


def create_initial_messages() -> list[dict[str, str]]:
    """创建新的会话状态，并保留固定的 system 消息。"""
    return [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
        }
    ]


def request_answer(
    client: OpenAI,
    model_id: str,
    messages: list[dict[str, str]],
) -> str:
    """将当前完整 messages 发送给模型并提取文本回答。"""
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    if not response.choices:
        raise RuntimeError("模型返回了响应，但 choices 列表为空。")

    answer = response.choices[0].message.content

    if answer is None or not answer.strip():
        raise RuntimeError("模型返回了响应，但没有可用的文本回答。")

    return answer.strip()


def main() -> None:
    """运行具有当前会话历史的多轮城市旅行助手。"""
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model_id = require_env("LLM_MODEL_ID")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    # messages 位于 while 循环外，因此历史能够跨轮次保留。
    messages = create_initial_messages()

    print("城市旅行助手已启动。")
    print("输入 /clear 清空当前对话，输入 /exit 结束程序。")

    while True:
        user_input = input("\n你：").strip()

        if not user_input:
            print("请输入有效内容。")
            continue

        if user_input == "/exit":
            print("对话结束。")
            break

        if user_input == "/clear":
            # 重新创建列表，而不是 messages.clear()，以保留 system 消息。
            messages = create_initial_messages()
            print("当前对话已清空。")
            continue

        messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        answer = request_answer(
            client=client,
            model_id=model_id,
            messages=messages,
        )

        messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        print(f"\n旅行助手：{answer}")


if __name__ == "__main__":
    main()
