"""使用 simple_agent 包构建计算器 Agent。"""

from __future__ import annotations

import os
import sys
from numbers import Real

from dotenv import load_dotenv
from openai import OpenAI

from simple_agent import Agent, OpenAIChatLLM, Tool, ToolRegistry


OPERATIONS = {"add", "subtract", "multiply", "divide"}


def calculator(operation: str, a: float, b: float) -> str:
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
        raise ValueError(f"不支持的操作：{operation}")
    return str(result)


def validate_calculator(arguments: dict[str, object]) -> None:
    required = {"operation", "a", "b"}
    if set(arguments) != required:
        raise ValueError("计算器参数必须包含 operation、a 和 b。")

    operation = arguments["operation"]
    if not isinstance(operation, str) or operation not in OPERATIONS:
        raise ValueError("operation 必须是 add、subtract、multiply 或 divide。")

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


def main() -> None:
    tools = ToolRegistry()
    tools.register(
        Tool(
            name="calculator",
            description="执行两个数字的基础算术运算。",
            parameters={
                "operation": "add、subtract、multiply 或 divide",
                "a": "第一个数字",
                "b": "第二个数字",
            },
            function=calculator,
            validator=validate_calculator,
        )
    )

    task = " ".join(sys.argv[1:]).strip() or "请计算 125 × 48。"
    execution = Agent(llm=create_llm(), tools=tools, max_steps=4).run(task)
    print(execution.message)
    print(f"终止原因：{execution.termination_reason.value}")


if __name__ == "__main__":
    main()
