"""第十一章：Critic 生成、解析并校验结构化 Critique。"""

import json
from dataclasses import dataclass

from openai import OpenAI


ALLOWED_DIMENSIONS = frozenset(
    {
        "completeness",
        "evidence_grounding",
        "consistency",
        "constraint_compliance",
    }
)


CRITIC_SYSTEM_PROMPT = """
你是城市旅行助手的答案评审者 Critic。

请根据用户任务、Evidence 和当前 Draft 进行检查。

只检查四个维度：
- completeness
- evidence_grounding
- consistency
- constraint_compliance

输出必须是一个 JSON 对象，只包含：
passed、summary、issues。

每个 issue 只能包含：
dimension、problem、suggestion。

规则：
1. 只依据用户任务和 Evidence 判断。
2. 不要使用外部常识补充事实。
3. 不要重新执行工具。
4. 不要直接输出修订后的完整答案。
5. 如果 Evidence 缺少完成任务所需的信息，
   应在 issue 中明确指出证据不足，不要要求编造。
6. passed=true 时 issues 必须为空。
7. passed=false 时 issues 至少包含一项。
8. dimension 只能使用规定的四个值。
9. 不要输出 Markdown 代码块或额外说明。

输出格式：
{
  "passed": true或false,
  "summary": "简短评审结论",
  "issues": [
    {
      "dimension": "检查维度",
      "problem": "具体问题",
      "suggestion": "具体修改建议"
    }
  ]
}
""".strip()


class CritiqueParseError(ValueError):
    """Critic 输出没有通过 Critique 协议校验。"""


@dataclass(frozen=True)
class CritiqueIssue:
    """Critic 指出的一个具体、可操作的问题。"""

    dimension: str
    problem: str
    suggestion: str


@dataclass(frozen=True)
class Critique:
    """经过解析和协议校验的评审结果。"""

    passed: bool
    summary: str
    issues: tuple[CritiqueIssue, ...]



def _load_bounded_json(text: str) -> object:
    """为教学快照限制不可信 JSON 的资源消耗。"""
    if len(text) > 65_536:
        raise json.JSONDecodeError("模型输出长度超过限制", text, 0)
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "{[":
            depth += 1
            if depth > 64:
                raise json.JSONDecodeError("JSON 嵌套层数超过限制", text, 0)
        elif character in "}]":
            depth -= 1

    def parse_integer(value: str) -> int:
        if len(value.lstrip("-")) > 128:
            raise ValueError("整数位数超过限制")
        return int(value)

    try:
        return json.loads(text, parse_int=parse_integer)
    except (ValueError, RecursionError) as error:
        raise json.JSONDecodeError("JSON 格式或数值超出允许范围", text, 0) from error


def _require_non_empty_text(
    value: object,
    field_name: str,
) -> str:
    """校验并返回去除首尾空白后的非空字符串。"""
    if not isinstance(value, str) or not value.strip():
        raise CritiqueParseError(
            f"{field_name} 必须是非空字符串。"
        )

    return value.strip()


def parse_issue(raw_issue: object) -> CritiqueIssue:
    """解析并校验一个 Critique Issue。"""
    if not isinstance(raw_issue, dict):
        raise CritiqueParseError(
            "每个 issue 都必须是 JSON 对象。"
        )

    expected_fields = {
        "dimension",
        "problem",
        "suggestion",
    }

    if set(raw_issue) != expected_fields:
        raise CritiqueParseError(
            "issue 必须且只能包含 "
            "dimension、problem 和 suggestion。"
        )

    dimension = _require_non_empty_text(
        raw_issue["dimension"],
        "dimension",
    )

    if dimension not in ALLOWED_DIMENSIONS:
        allowed = "、".join(sorted(ALLOWED_DIMENSIONS))
        raise CritiqueParseError(
            f"未知评审维度：{dimension!r}。"
            f"允许值：{allowed}。"
        )

    problem = _require_non_empty_text(
        raw_issue["problem"],
        "problem",
    )
    suggestion = _require_non_empty_text(
        raw_issue["suggestion"],
        "suggestion",
    )

    return CritiqueIssue(
        dimension=dimension,
        problem=problem,
        suggestion=suggestion,
    )


def parse_critique(model_output: str) -> Critique:
    """把不可信 Critic 文本转换为经过校验的 Critique。"""
    if not isinstance(model_output, str):
        raise CritiqueParseError(
            "Critique 模型输出必须是字符串。"
        )

    text = model_output.strip()

    if not text:
        raise CritiqueParseError("Critique 输出为空。")

    try:
        data = _load_bounded_json(text)
    except json.JSONDecodeError as error:
        raise CritiqueParseError(
            "Critique 不是合法 JSON："
            f"{error.msg}，第 {error.lineno} 行，"
            f"第 {error.colno} 列。"
        ) from error

    if not isinstance(data, dict):
        raise CritiqueParseError(
            "Critique 顶层必须是 JSON 对象。"
        )

    if set(data) != {"passed", "summary", "issues"}:
        raise CritiqueParseError(
            "Critique 必须且只能包含 "
            "passed、summary 和 issues。"
        )

    passed = data["passed"]

    if not isinstance(passed, bool):
        raise CritiqueParseError(
            "passed 必须是布尔值。"
        )

    summary = _require_non_empty_text(
        data["summary"],
        "summary",
    )
    raw_issues = data["issues"]

    if not isinstance(raw_issues, list):
        raise CritiqueParseError(
            "issues 必须是 JSON 数组。"
        )

    issues = tuple(
        parse_issue(raw_issue)
        for raw_issue in raw_issues
    )

    if passed and issues:
        raise CritiqueParseError(
            "passed 为 true 时，issues 必须为空。"
        )

    if not passed and not issues:
        raise CritiqueParseError(
            "passed 为 false 时，issues 不能为空。"
        )

    return Critique(
        passed=passed,
        summary=summary,
        issues=issues,
    )


def critique_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    draft: str,
) -> Critique:
    """让 Critic 检查 Draft，并返回结构化 Critique。"""
    if not user_task.strip():
        raise ValueError("用户任务不能为空。")

    if not evidence.strip():
        raise ValueError("Evidence 不能为空。")

    if not draft.strip():
        raise ValueError("待评审 Draft 不能为空。")

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": CRITIC_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task.strip()}\n\n"
                    f"Evidence：\n{evidence.strip()}\n\n"
                    f"当前 Draft：\n{draft.strip()}"
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError(
            "Critic 返回了响应，但 choices 列表为空。"
        )

    model_output = response.choices[0].message.content

    if not model_output or not model_output.strip():
        raise RuntimeError(
            "Critic 没有返回可用文本。"
        )

    return parse_critique(model_output)
