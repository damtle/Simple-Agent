"""第八章：程序内部的行动对象与解析异常。"""

from dataclasses import dataclass


@dataclass
class AgentAction:
    """表示已经通过 Parser 解析和协议校验的行动。"""

    name: str
    arguments: dict[str, object]


class ActionParseError(ValueError):
    """模型输出无法被解析，或未通过 Action Protocol 校验。"""
