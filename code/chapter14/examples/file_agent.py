"""只允许读取 workspace/ 内 UTF-8 文本文件的安全示例。"""

from __future__ import annotations

import os
from pathlib import Path
import sys

from dotenv import load_dotenv
from openai import OpenAI

from simple_agent import Agent, OpenAIChatLLM, Tool, ToolRegistry
from simple_agent.tools import ToolInputError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOT = (PROJECT_ROOT / "workspace").resolve()


def read_text_file(path: str) -> str:
    candidate = (ALLOWED_ROOT / path).resolve()

    if candidate != ALLOWED_ROOT and ALLOWED_ROOT not in candidate.parents:
        raise ToolInputError("文件路径超出允许目录。", error_type="path_denied")
    if not candidate.is_file():
        raise ToolInputError(f"文件不存在：{path}", error_type="not_found")

    try:
        return candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ToolInputError(
            "文件不是可读取的 UTF-8 文本。",
            error_type="invalid_encoding",
        ) from error


def validate_read_file(arguments: dict[str, object]) -> None:
    if set(arguments) != {"path"}:
        raise ValueError("read_text_file 参数必须且只能包含 path。")
    path = arguments["path"]
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path 必须是非空字符串。")


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
            name="read_text_file",
            description="读取 workspace 目录内的 UTF-8 文本文件。",
            parameters={"path": "相对于 workspace 的文件路径"},
            function=read_text_file,
            validator=validate_read_file,
        )
    )

    task = (
        " ".join(sys.argv[1:]).strip()
        or "请读取 example.txt，并用一句话概括文件内容。"
    )
    execution = Agent(llm=create_llm(), tools=tools, max_steps=4).run(task)
    print(execution.message)
    print(f"终止原因：{execution.termination_reason.value}")


if __name__ == "__main__":
    main()
