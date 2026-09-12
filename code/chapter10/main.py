"""Simple Travel Assistant v1.2：Plan-and-Solve。

完整流程：

用户目标
→ Planner 生成并校验 Plan
→ Executor 按 PlanStep 顺序生成并执行 Action
→ 保存全部 StepResult
→ Finalize 生成最终回答

本章实现静态线性计划，不进行动态重规划、并行执行、
步骤重试、条件分支或 Reflection。
"""

import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

from executor import (
    ALLOWED_TOOL_NAMES,
    execute_plan,
    finalize_answer,
)
from models import Plan, PlanExecutionError, PlanParseError, StepResult
from planner import create_plan, format_plan


DEFAULT_MAX_PLAN_STEPS = 6


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
    """加载模型配置并创建客户端。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    return client, model_id


def get_user_goal() -> str:
    """读取用户目标。"""
    user_goal = input("请输入旅行任务：").strip()

    if not user_goal:
        raise ValueError("用户目标不能为空。")

    return user_goal


def show_plan(plan: Plan) -> None:
    """在真正执行工具前展示完整计划。"""
    print("\n=== Planning Result ===")
    print(format_plan(plan))
    print("\n此时所有工具均尚未执行。")


def show_completed_results(
    step_results: list[StepResult],
) -> None:
    """展示全部步骤执行结果。"""
    print("\n=== Completed StepResults ===")

    for result in step_results:
        print(
            f"Step {result.step_id} | "
            f"Tool={result.tool_name} | "
            f"Arguments={result.arguments} | "
            f"Output={result.output}"
        )


def run_plan_and_solve(
    client: OpenAI,
    model_id: str,
    user_goal: str,
    max_plan_steps: int = DEFAULT_MAX_PLAN_STEPS,
) -> str:
    """连接 Planning、Solving 和 Finalize 三个阶段。"""
    plan = create_plan(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
        allowed_tools=set(ALLOWED_TOOL_NAMES),
        max_plan_steps=max_plan_steps,
    )

    show_plan(plan)

    step_results = execute_plan(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
        plan=plan,
    )

    show_completed_results(step_results)

    print("\n=== Finalize ===")

    return finalize_answer(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
        plan=plan,
        step_results=step_results,
    )


def main() -> None:
    """程序入口。"""
    client, model_id = load_client()
    user_goal = get_user_goal()

    answer = run_plan_and_solve(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
        max_plan_steps=DEFAULT_MAX_PLAN_STEPS,
    )

    print("\nPlan-and-Solve 正常结束。")
    print("最终回答：")
    print(answer)


if __name__ == "__main__":
    try:
        main()
    except PlanParseError as error:
        print("\n终止阶段：Planning")
        print(f"计划解析失败：{error}")
        print("没有执行任何未经校验的计划步骤。")
        sys.exit(1)
    except PlanExecutionError as error:
        print("\n终止阶段：Solving")
        print(f"计划执行失败：{error}")
        print("当前静态计划已停止，不会进入 Finalize。")
        sys.exit(1)
    except (RuntimeError, ValueError) as error:
        print(f"\n程序异常终止：{error}")
        sys.exit(1)
