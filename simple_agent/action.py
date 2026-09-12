"""Action 数据结构与稳定序列化。"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class AgentAction:
    """已经通过 Parser 校验的内部行动对象。"""

    name: str
    arguments: dict[str, object]
    reason: str | None = None


def snapshot_action(action: AgentAction) -> AgentAction:
    """保存 Action 当时的深拷贝快照。"""
    return AgentAction(
        name=action.name,
        arguments=deepcopy(action.arguments),
        reason=action.reason,
    )


def action_to_json(action: AgentAction) -> str:
    """按照 Action Protocol 生成稳定 JSON。"""
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
        separators=(",", ":"),
    )


def action_fingerprint(action: AgentAction) -> str:
    """生成重复行动检测指纹，故意忽略 Reason 文本。"""
    return action_to_json(
        AgentAction(
            name=action.name,
            arguments=action.arguments,
        )
    )
