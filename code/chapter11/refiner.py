"""第十一章：Refiner 根据 Critique 生成 Revision。"""

from openai import OpenAI

from critic import Critique


REFINER_SYSTEM_PROMPT = """
你是城市旅行助手的答案修订者 Refiner。

请根据用户任务、Evidence、当前 Draft 和 Critique，
生成一版修订后的完整答案。

规则：
1. 修复 Critique 中指出的有效问题。
2. Evidence 的优先级高于 Critique。
3. 只能使用 Evidence 中已有的事实和数字。
4. 保留 Draft 中已经正确且符合要求的内容。
5. 不要提及评审、修改、旧答案或修订过程。
6. 继续满足用户的长度、格式和表达约束。
7. 只输出修订后的答案，不要输出 JSON 或代码块。
""".strip()


def format_critique(critique: Critique) -> str:
    """把结构化 Critique 转换为 Refiner 可读文本。"""
    lines = [
        f"是否通过：{critique.passed}",
        f"评审结论：{critique.summary}",
    ]

    if not critique.issues:
        lines.append("具体问题：无")
        return "\n".join(lines)

    for index, issue in enumerate(
        critique.issues,
        start=1,
    ):
        lines.extend(
            [
                f"问题 {index}",
                f"维度：{issue.dimension}",
                f"问题：{issue.problem}",
                f"建议：{issue.suggestion}",
            ]
        )

    return "\n".join(lines)


def revise_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    draft: str,
    critique: Critique,
) -> str:
    """根据任务、Evidence、Draft 和 Critique 生成 Revision。"""
    if not user_task.strip():
        raise ValueError("用户任务不能为空。")

    if not evidence.strip():
        raise ValueError("Evidence 不能为空。")

    if not draft.strip():
        raise ValueError("待修订 Draft 不能为空。")

    if critique.passed:
        raise ValueError(
            "当前 Critique 已通过，不应调用 Refiner。"
        )

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": REFINER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task.strip()}\n\n"
                    f"Evidence：\n{evidence.strip()}\n\n"
                    f"当前 Draft：\n{draft.strip()}\n\n"
                    f"Critique：\n{format_critique(critique)}"
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError(
            "Refiner 返回了响应，但 choices 列表为空。"
        )

    revised_answer = response.choices[0].message.content

    if not revised_answer or not revised_answer.strip():
        raise RuntimeError(
            "Refiner 没有返回可用 Revision。"
        )

    return revised_answer.strip()
