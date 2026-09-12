"""第十章：Plan-and-Solve 使用的数据结构与异常。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentAction:
    """经过校验、可以交给工具执行器的具体行动。"""

    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class PlanStep:
    """静态计划中的一个顺序步骤。"""

    id: int
    description: str
    tool_name: str
    expected_output: str


@dataclass(frozen=True)
class Plan:
    """Planner 生成并通过校验的静态线性计划。"""

    goal: str
    steps: tuple[PlanStep, ...]


@dataclass(frozen=True)
class StepResult:
    """Executor 完成一个 PlanStep 后保存的结构化结果。"""

    step_id: int
    description: str
    tool_name: str
    arguments: dict[str, object]
    output: str


class PlanParseError(ValueError):
    """Planner 输出没有通过 Plan 协议校验。"""


class PlanExecutionError(RuntimeError):
    """某个计划步骤无法继续执行。"""
