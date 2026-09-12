"""Agent Action 数据结构与规范序列化。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class AgentAction:
    """经过 Parser 校验、可以交给 Controller 使用的行动。"""

    name: str
    arguments: dict[str, object]
    reason: str | None = None


def action_to_json(action: AgentAction) -> str:
    """把 AgentAction 序列化为写入消息历史的规范 JSON。"""
    payload: dict[str, object] = {
        "action": action.name,
        "arguments": action.arguments,
    }

    if action.reason is not None:
        payload["reason"] = action.reason

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )


def action_fingerprint(action: AgentAction) -> str:
    """生成忽略 reason、与参数键顺序无关的稳定行动指纹。"""
    return json.dumps(
        {
            "action": action.name,
            "arguments": action.arguments,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def snapshot_action(action: AgentAction) -> AgentAction:
    """复制嵌套参数，避免后续修改污染已保存的历史轨迹。"""
    return AgentAction(
        name=action.name,
        arguments=deepcopy(action.arguments),
        reason=action.reason,
    )
