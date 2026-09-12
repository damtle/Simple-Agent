"""第十一章：Generator 根据用户任务和 Evidence 生成 Draft。"""

from openai import OpenAI


GENERATOR_SYSTEM_PROMPT = """
你是城市旅行助手的答案生成器 Generator。

请根据用户任务和 Evidence 生成一段完整的中文候选答案。

规则：
1. 只能使用 Evidence 中已有的事实和数字。
2. 不要声称执行了新的工具。
3. 满足用户明确提出的长度、格式和内容要求。
4. 涉及天气、开放状态和票价时，
   明确说明它们来自本地模拟数据。
5. 只输出候选答案，不要输出分析、JSON 或代码块。
""".strip()


def generate_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
) -> str:
    """根据用户任务和 Evidence 生成第一版候选答案。"""
    if not user_task.strip():
        raise ValueError("用户任务不能为空。")

    if not evidence.strip():
        raise ValueError("Evidence 不能为空。")

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": GENERATOR_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task.strip()}\n\n"
                    f"Evidence：\n{evidence.strip()}"
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError(
            "Generator 返回了响应，但 choices 列表为空。"
        )

    draft = response.choices[0].message.content

    if not draft or not draft.strip():
        raise RuntimeError(
            "Generator 没有返回可用 Draft。"
        )

    return draft.strip()
