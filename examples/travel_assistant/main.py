"""第十六章：使用 simple_agent 构建完整旅行助手。

运行：

    python -m examples.travel_assistant.main

显示完整执行轨迹：

    python -m examples.travel_assistant.main --show-trace
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from typing import Sequence

from simple_agent import (
    Agent,
    AgentExecution,
    LLM,
    LLMRequestError,
    OpenAIChatLLM,
    RetryPolicy,
)
from simple_agent.parser import ActionParseError, load_json_object

if __package__:
    from .prompts import (
        REFLECTION_CRITIC_PROMPT,
        REFLECTION_REFINER_PROMPT,
        build_travel_agent_prompt,
    )
    from .tools import build_travel_tools
else:
    from prompts import (
        REFLECTION_CRITIC_PROMPT,
        REFLECTION_REFINER_PROMPT,
        build_travel_agent_prompt,
    )
    from tools import build_travel_tools


DEFAULT_TASK = """
请查询北京的模拟天气和故宫的模拟开放、票价信息，
计算两张成人票的总价，并给出一段不超过120字的出行建议。
回答必须明确说明数据来自本地模拟信息。
""".strip()


ALLOWED_CRITIQUE_DIMENSIONS = frozenset(
    {
        "completeness",
        "evidence_grounding",
        "consistency",
        "constraint_compliance",
    }
)


class ReflectionError(RuntimeError):
    """应用层答案检查或修订无法继续。"""


class CritiqueParseError(ValueError):
    """Critic 输出没有通过 Critique 协议校验。"""


@dataclass(frozen=True)
class CritiqueIssue:
    dimension: str
    problem: str
    suggestion: str


@dataclass(frozen=True)
class Critique:
    passed: bool
    summary: str
    issues: tuple[CritiqueIssue, ...]


def require_env(name: str) -> str:
    """读取一项必需配置，避免在更深层才出现含糊错误。"""
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"缺少环境变量：{name}"
        )

    return value.strip()


def build_llm() -> OpenAIChatLLM:
    """在应用入口创建真实模型适配器。"""
    try:
        from openai import OpenAI
    except ImportError as error:
        raise RuntimeError(
            "缺少 openai，请先安装项目依赖。"
        ) from error

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
        timeout=30.0,
        max_retries=0,
    )

    return OpenAIChatLLM(
        client=client,
        model_id=require_env("LLM_MODEL_ID"),
        temperature=0.0,
    )


def build_travel_agent(llm: LLM) -> Agent:
    """把模型、真实工具说明、Prompt 和运行边界连接起来。"""
    tools = build_travel_tools()
    system_prompt = build_travel_agent_prompt(
        tools.render_descriptions()
    )

    return Agent(
        llm=llm,
        tools=tools,
        system_prompt=system_prompt,
        policy=RetryPolicy(
            max_network_retries=2,
            max_format_retries=2,
            max_tool_retries=1,
            max_steps=8,
            repeated_action_limit=2,
            timeout_seconds=30.0,
        ),
        require_reason=True,
    )


def collect_evidence(
    execution: AgentExecution,
) -> str:
    """只从 Trace 中收集成功工具结果，不混入 Reason 或 Critique。"""
    evidence: list[str] = []

    for record in execution.trace.records:
        action = record.action

        if action is None or action.name == "finish":
            continue

        successful_results = [
            result
            for result in record.tool_results
            if result.success
        ]

        if not successful_results:
            continue

        result = successful_results[-1]
        arguments = json.dumps(
            action.arguments,
            ensure_ascii=False,
            sort_keys=True,
        )
        evidence.append(
            (
                f"{len(evidence) + 1}. "
                f"{action.name}({arguments})\n"
                f"   {result.content}"
            )
        )

    return "\n\n".join(evidence)


def parse_critique(model_output: str) -> Critique:
    """把不可信 Critic 文本转换为经过校验的结构化结果。"""
    try:
        data = load_json_object(model_output)
    except ActionParseError as error:
        raise CritiqueParseError(f"Critique 解析失败：{error}") from error

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
            "passed 必须是 JSON 布尔值。"
        )

    summary = _require_non_empty_text(
        data["summary"],
        field_name="summary",
    )
    raw_issues = data["issues"]

    if not isinstance(raw_issues, list):
        raise CritiqueParseError(
            "issues 必须是 JSON 数组。"
        )

    issues = tuple(
        _parse_critique_issue(raw_issue, index)
        for index, raw_issue in enumerate(raw_issues)
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


def reflect_answer(
    *,
    llm: LLM,
    user_task: str,
    evidence: str,
    draft: str,
    max_revisions: int = 1,
) -> str:
    """检查 Draft；必要时有限修订，并检查修订后的版本。"""
    if isinstance(max_revisions, bool) or not isinstance(
        max_revisions,
        int,
    ):
        raise TypeError("max_revisions 必须是整数。")

    if max_revisions < 0:
        raise ValueError("max_revisions 不能小于 0。")

    normalized_task = _require_non_empty_text(
        user_task,
        field_name="user_task",
    )
    normalized_evidence = _require_non_empty_text(
        evidence,
        field_name="evidence",
    )
    current_answer = _require_non_empty_text(
        draft,
        field_name="draft",
    )

    for review_index in range(max_revisions + 1):
        critique = _request_critique(
            llm=llm,
            user_task=normalized_task,
            evidence=normalized_evidence,
            draft=current_answer,
        )

        if critique.passed:
            return current_answer

        if review_index >= max_revisions:
            # 返回最后一个已经接受 Critic 检查的版本，
            # 不把答案层失败改写成 Agent 执行失败。
            return current_answer

        current_answer = _request_revision(
            llm=llm,
            user_task=normalized_task,
            evidence=normalized_evidence,
            draft=current_answer,
            critique=critique,
        )

    raise RuntimeError("不可达代码。")


def print_run_summary(
    execution: AgentExecution,
) -> None:
    state = execution.state

    print("\n运行摘要：")
    print(
        "终止原因："
        f"{execution.result.termination_reason.value}"
    )
    print(f"Agent Steps：{execution.result.steps}")
    print(f"LLM Calls：{state.llm_calls}")
    print(f"Tool Calls：{state.tool_calls}")
    print(f"Request Failures：{state.request_failures}")
    print(f"Parse Failures：{state.parse_failures}")
    print(f"Tool Failures：{state.tool_failures}")


def print_trace(
    execution: AgentExecution,
) -> None:
    """读取结构化 StepRecord，不重新推断模型内部过程。"""
    print("\n执行轨迹：")

    if not execution.trace.records:
        print("（没有步骤记录）")
        return

    for record in execution.trace.records:
        print(f"\nStep {record.step}")

        for attempt in record.model_attempts:
            if attempt.request_error:
                status = (
                    "request_error: "
                    f"{attempt.request_error}"
                )
            elif attempt.parse_error:
                status = (
                    "parse_error: "
                    f"{attempt.parse_error}"
                )
            else:
                status = "accepted"

            print(
                f"Model Attempt {attempt.attempt}: "
                f"{status}"
            )

        if record.action is not None:
            print(
                "Action: "
                f"{record.action.name}"
                f"{record.action.arguments}"
            )

            if record.action.reason:
                print(
                    f"Reason: {record.action.reason}"
                )

        for index, result in enumerate(
            record.tool_results,
            start=1,
        ):
            status = (
                "成功" if result.success else "失败"
            )
            print(
                f"Tool Attempt {index}: "
                f"{status} - {result.content}"
            )

        if record.observation:
            print(record.observation)

        if record.termination_reason:
            print(
                "Termination: "
                f"{record.termination_reason.value}"
            )

        if record.error:
            print(f"Error: {record.error}")


def print_failure(
    execution: AgentExecution,
) -> None:
    result = execution.result

    print("\n旅行助手未完成任务：")
    print(result.message)
    print(
        "终止原因："
        f"{result.termination_reason.value}"
    )

    if result.error:
        print(f"错误摘要：{result.error}")

    print_run_summary(execution)
    print_trace(execution)


def run_travel_task(
    user_task: str,
    *,
    show_trace: bool = False,
) -> int:
    """运行应用主线；Agent 失败时不进入 Reflection。"""
    try:
        from dotenv import load_dotenv
    except ImportError as error:
        print("启动失败：缺少 python-dotenv，请安装开发依赖。")
        return 2

    load_dotenv()

    try:
        llm = build_llm()
        agent = build_travel_agent(llm)
        execution = agent.run(user_task)
    except RuntimeError as error:
        print(f"启动失败：{error}")
        return 2

    if not execution.result.success:
        print_failure(execution)
        return 1

    draft = execution.message
    evidence = collect_evidence(execution)
    final_answer = draft

    if evidence:
        try:
            final_answer = reflect_answer(
                llm=llm,
                user_task=user_task,
                evidence=evidence,
                draft=draft,
                max_revisions=1,
            )
        except ReflectionError as error:
            print(
                "\n答案检查未完成，"
                "将保留 Agent 原始回答："
            )
            print(error)
    else:
        print(
            "\n本次运行没有成功工具结果，"
            "因此跳过 Evidence Reflection。"
        )

    print("\n最终回答：")
    print(final_answer)
    print_run_summary(execution)

    if show_trace:
        print_trace(execution)

    return 0


def _request_critique(
    *,
    llm: LLM,
    user_task: str,
    evidence: str,
    draft: str,
) -> Critique:
    messages = [
        {
            "role": "system",
            "content": REFLECTION_CRITIC_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"用户任务：\n{user_task}\n\n"
                f"Evidence：\n{evidence}\n\n"
                f"当前 Draft：\n{draft}"
            ),
        },
    ]

    try:
        output = llm.generate(messages)
        return parse_critique(output)
    except (LLMRequestError, CritiqueParseError) as error:
        raise ReflectionError(
            f"Critic 检查失败：{error}"
        ) from error


def _request_revision(
    *,
    llm: LLM,
    user_task: str,
    evidence: str,
    draft: str,
    critique: Critique,
) -> str:
    messages = [
        {
            "role": "system",
            "content": REFLECTION_REFINER_PROMPT,
        },
        {
            "role": "user",
            "content": (
                f"用户任务：\n{user_task}\n\n"
                f"Evidence：\n{evidence}\n\n"
                f"当前 Draft：\n{draft}\n\n"
                "Critique：\n"
                f"{_format_critique(critique)}"
            ),
        },
    ]

    try:
        output = llm.generate(messages)
    except LLMRequestError as error:
        raise ReflectionError(
            f"Refiner 请求失败：{error}"
        ) from error

    try:
        return _require_non_empty_text(
            output,
            field_name="revised_answer",
        )
    except CritiqueParseError as error:
        raise ReflectionError(
            f"Refiner 输出不可用：{error}"
        ) from error


def _parse_critique_issue(
    raw_issue: object,
    index: int,
) -> CritiqueIssue:
    if not isinstance(raw_issue, dict):
        raise CritiqueParseError(
            f"issues[{index}] 必须是 JSON 对象。"
        )

    if set(raw_issue) != {
        "dimension",
        "problem",
        "suggestion",
    }:
        raise CritiqueParseError(
            f"issues[{index}] 必须且只能包含 "
            "dimension、problem 和 suggestion。"
        )

    dimension = _require_non_empty_text(
        raw_issue["dimension"],
        field_name=f"issues[{index}].dimension",
    )

    if dimension not in ALLOWED_CRITIQUE_DIMENSIONS:
        allowed = "、".join(
            sorted(ALLOWED_CRITIQUE_DIMENSIONS)
        )
        raise CritiqueParseError(
            f"不支持的评审维度：{dimension!r}。"
            f"允许值：{allowed}。"
        )

    return CritiqueIssue(
        dimension=dimension,
        problem=_require_non_empty_text(
            raw_issue["problem"],
            field_name=f"issues[{index}].problem",
        ),
        suggestion=_require_non_empty_text(
            raw_issue["suggestion"],
            field_name=f"issues[{index}].suggestion",
        ),
    )


def _require_non_empty_text(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CritiqueParseError(
            f"{field_name} 必须是非空字符串。"
        )

    return value.strip()


def _format_critique(
    critique: Critique,
) -> str:
    lines = [
        f"是否通过：{'是' if critique.passed else '否'}",
        f"评审摘要：{critique.summary}",
    ]

    if not critique.issues:
        lines.append("具体问题：无")
        return "\n".join(lines)

    lines.append("具体问题：")

    for index, issue in enumerate(
        critique.issues,
        start=1,
    ):
        lines.append(
            f"{index}. [{issue.dimension}] "
            f"{issue.problem}"
        )
        lines.append(
            f"   建议：{issue.suggestion}"
        )

    return "\n".join(lines)


def _parse_args(
    argv: Sequence[str] | None = None,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "运行使用本地模拟数据的 Simple Travel Assistant。"
        )
    )
    parser.add_argument(
        "task",
        nargs="?",
        help=(
            "旅行任务；省略时从终端读取，"
            "直接回车使用默认任务。"
        ),
    )
    parser.add_argument(
        "--show-trace",
        action="store_true",
        help="显示完整 Agent Execution Trace。",
    )
    return parser.parse_args(argv)


def _resolve_task(task_argument: str | None) -> str:
    if task_argument is not None:
        return task_argument.strip()

    print("请输入旅行任务；直接回车使用默认任务：")
    try:
        user_input = input().strip()
    except EOFError:
        user_input = ""

    return user_input or DEFAULT_TASK


def main(
    argv: Sequence[str] | None = None,
) -> int:
    args = _parse_args(argv)
    user_task = _resolve_task(args.task)

    return run_travel_task(
        user_task,
        show_trace=args.show_trace,
    )


if __name__ == "__main__":
    raise SystemExit(main())
