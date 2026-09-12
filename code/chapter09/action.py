"""第九章：ReAct 决策与程序行动的数据边界。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AgentAction:
    """表示已经通过 Parser 校验、可以交给 Controller 的行动。"""

    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ReActDecision:
    """保存一轮 ReAct 的决策摘要和对应行动。"""

    reason: str
    action: AgentAction


class ActionParseError(ValueError):
    """模型输出未通过 ReAct 决策协议校验。"""
