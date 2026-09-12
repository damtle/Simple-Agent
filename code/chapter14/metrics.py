"""从固定 Agent 运行中提取基础 Metrics。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from simple_agent import AgentExecution


@dataclass(frozen=True)
class AgentMetrics:
    task_completed: bool
    llm_calls: int
    tool_calls: int
    parse_failures: int
    total_steps: int
    termination_reason: str


def collect_metrics(execution: AgentExecution) -> AgentMetrics:
    """把一次结构化运行结果转换成便于比较的数字。"""
    return AgentMetrics(
        task_completed=execution.result.success,
        llm_calls=execution.state.llm_calls,
        tool_calls=execution.state.tool_calls,
        parse_failures=execution.state.parse_failures,
        total_steps=execution.result.steps,
        termination_reason=execution.result.termination_reason.value,
    )


def summarize_metrics(
    metrics: Sequence[AgentMetrics],
) -> dict[str, object]:
    """汇总一组固定案例；空案例集返回零值。"""
    cases = len(metrics)
    if cases == 0:
        return {
            "cases": 0,
            "completion_rate": 0.0,
            "average_llm_calls": 0.0,
            "average_tool_calls": 0.0,
            "average_steps": 0.0,
            "termination_counts": {},
        }

    return {
        "cases": cases,
        "completion_rate": sum(item.task_completed for item in metrics) / cases,
        "average_llm_calls": sum(item.llm_calls for item in metrics) / cases,
        "average_tool_calls": sum(item.tool_calls for item in metrics) / cases,
        "average_steps": sum(item.total_steps for item in metrics) / cases,
        "termination_counts": dict(
            sorted(Counter(item.termination_reason for item in metrics).items())
        ),
    }
