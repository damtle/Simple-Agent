"""Simple Travel Assistant v1.3：Reflection 检查与修正。

本章输入已经执行完成的 Evidence，不重新调用旅行工具。
核心过程：

Generator → Draft → Critic → Critique
                       ↓ 未通过
                    Refiner → Revision → Critic

程序在 Critic 判断通过时返回当前答案；达到最大修订次数后，
以最小 RuntimeError 结束。正式终止结果将在下一章实现。
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from critic import (
    Critique,
    CritiqueParseError,
    critique_draft,
)
from generator import generate_draft
from refiner import revise_draft


DEFAULT_USER_TASK = """
请根据已经获得的结果，为两人写一段不超过120字的出行建议。
回答必须包含北京天气、故宫开放状态、两张成人票总价，
并明确说明数据为本地模拟信息。
""".strip()


DEFAULT_EVIDENCE = """
1. get_weather({"city": "北京"})
   北京当前模拟天气为晴，温度30℃，湿度45%，微风。

2. get_attraction_info({"name": "故宫"})
   故宫位于北京，在当前模拟数据中处于开放状态，
   成人票价60元，活动类型为室内外步行。

3. calculator({"operation": "multiply", "a": 60, "b": 2})
   120
""".strip()


DEFAULT_MAX_REVISIONS = 2


def require_env(name: str) -> str:
    """读取必需环境变量。"""
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，"
            "请检查项目根目录下的 .env 文件。"
        )

    return value


def load_client() -> tuple[OpenAI, str]:
    """读取配置并创建模型客户端。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    return client, model_id


def show_candidate(
    version: int,
    answer: str,
) -> None:
    """展示当前 Draft 或 Revision。"""
    title = "Draft 0" if version == 0 else f"Revision {version}"

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(answer)


def show_critique(
    review_round: int,
    critique: Critique,
) -> None:
    """展示一轮结构化 Critique。"""
    print()
    print(f"Critique {review_round}")
    print(f"passed：{critique.passed}")
    print(f"summary：{critique.summary}")

    if not critique.issues:
        print("issues：无")
        return

    print("issues：")

    for index, issue in enumerate(
        critique.issues,
        start=1,
    ):
        print(
            f"  {index}. [{issue.dimension}] "
            f"{issue.problem}"
        )
        print(f"     建议：{issue.suggestion}")


def run_reflection(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    max_revisions: int = DEFAULT_MAX_REVISIONS,
) -> str:
    """运行有限的答案层 Reflection Loop。"""
    if isinstance(max_revisions, bool) or not isinstance(
        max_revisions,
        int,
    ):
        raise TypeError("max_revisions 必须是整数。")

    if max_revisions < 0:
        raise ValueError(
            "max_revisions 不能小于 0。"
        )

    current_answer = generate_draft(
        client=client,
        model_id=model_id,
        user_task=user_task,
        evidence=evidence,
    )

    revisions = 0
    review_round = 0

    while True:
        show_candidate(
            version=revisions,
            answer=current_answer,
        )

        critique = critique_draft(
            client=client,
            model_id=model_id,
            user_task=user_task,
            evidence=evidence,
            draft=current_answer,
        )
        review_round += 1

        show_critique(
            review_round=review_round,
            critique=critique,
        )

        if critique.passed:
            print()
            print("停止原因：当前答案已经通过 Critic 检查。")
            return current_answer

        if revisions >= max_revisions:
            raise RuntimeError(
                "已达到最大修订次数，"
                "当前答案仍未通过 Critic。"
            )

        current_answer = revise_draft(
            client=client,
            model_id=model_id,
            user_task=user_task,
            evidence=evidence,
            draft=current_answer,
            critique=critique,
        )
        revisions += 1


def main() -> None:
    """程序入口。"""
    client, model_id = load_client()

    final_answer = run_reflection(
        client=client,
        model_id=model_id,
        user_task=DEFAULT_USER_TASK,
        evidence=DEFAULT_EVIDENCE,
        max_revisions=DEFAULT_MAX_REVISIONS,
    )

    print()
    print("=" * 72)
    print("最终回答")
    print("=" * 72)
    print(final_answer)


if __name__ == "__main__":
    try:
        main()
    except CritiqueParseError as error:
        print(f"\nReflection 未完成：Critique 解析失败：{error}")
        sys.exit(1)
    except (RuntimeError, TypeError, ValueError) as error:
        print(f"\nReflection 未完成：{error}")
        sys.exit(1)
