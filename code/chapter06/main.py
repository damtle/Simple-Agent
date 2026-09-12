"""Simple Travel Assistant v0.5：解析与校验模型行动。

本章程序只完成：

用户任务 → LLM → model_output: str → Parser
→ AgentAction 或 ActionParseError

即使解析成功，程序也不会执行天气、景点或计算器工具。
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from action import ActionParseError
from parser import parse_action


ACTION_SYSTEM_PROMPT = """
你是城市旅行助手中的行动选择模块。

可用行动：

1. get_weather
   arguments: {"city": "城市名称"}

2. get_attraction_info
   arguments: {"name": "景点名称"}

3. calculator
   arguments: {
     "operation": "add|subtract|multiply|divide",
     "a": 数字,
     "b": 数字
   }

4. finish
   arguments: {"answer": "最终回答"}

每次只输出一个 JSON 对象。
不要输出解释文字。
不要输出不存在的行动。
""".strip()


def require_env(name: str) -> str:
    """读取必需环境变量，缺失时给出明确错误。"""
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
    """请求模型生成一个原始 Action 字符串。"""
    response = client.chat.completions.create(
        model=model_id,
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

    model_output = response.choices[0].message.content

    if not model_output:
        raise RuntimeError(
            "模型返回了响应，但没有可用文本。"
        )

    return model_output


def main() -> None:
    """请求模型行动，并将其交给 Parser 检查。"""
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

    try:
        action = parse_action(model_output)
    except ActionParseError as error:
        print(f"\nAction 解析失败：{error}")
        return

    print("\n程序接受的 AgentAction：")
    print(f"name = {action.name}")
    print(
        "arguments = "
        + json.dumps(
            action.arguments,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
