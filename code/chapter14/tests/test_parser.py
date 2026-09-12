from __future__ import annotations

import pytest

from simple_agent.action import action_fingerprint, action_to_json, snapshot_action
from simple_agent.parser import ActionParseError, parse_action
from simple_agent.tools import Tool, ToolRegistry


@pytest.mark.parametrize("output", [
    "x" * 65_537,
    "[" * 5_000 + "]" * 5_000,
    '{"action":"finish","arguments":{"answer":"ok"},"number":' + "9" * 5000 + "}",
    '说明：{"action":"finish","arguments":{"answer":"ok"},"number":' + "9" * 5000 + "}",
], ids=["oversize", "deep-json", "huge-integer", "prefixed-huge-integer"])
def test_resource_limits_reject_untrusted_output(output, tools):
    with pytest.raises(ActionParseError):
        parse_action(output, tools)


def validate_weather(arguments: dict[str, object]) -> None:
    if set(arguments) != {"city"}:
        raise ValueError("天气工具只接受 city。")
    if not isinstance(arguments["city"], str):
        raise ValueError("city 必须是字符串。")


@pytest.fixture
def tools() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        Tool(
            name="get_weather",
            description="查询模拟天气。",
            parameters={"city": "城市"},
            function=lambda city: city,
            validator=validate_weather,
        )
    )
    return registry


def test_parse_tool_action(tools: ToolRegistry) -> None:
    action = parse_action(
        '{"action":"get_weather","arguments":{"city":"北京"}}', tools
    )
    assert action.name == "get_weather"
    assert action.arguments == {"city": "北京"}
    assert action.reason is None


def test_parse_finish_action(tools: ToolRegistry) -> None:
    action = parse_action(
        '{"action":"finish","arguments":{"answer":"完成。"}}', tools
    )
    assert action.arguments["answer"] == "完成。"


def test_parse_markdown_fence(tools: ToolRegistry) -> None:
    action = parse_action(
        '```json\n{"action":"finish","arguments":{"answer":"完成。"}}\n```',
        tools,
    )
    assert action.name == "finish"


def test_parse_single_json_with_prefix(tools: ToolRegistry) -> None:
    action = parse_action(
        '模型决定如下：\n{"action":"finish","arguments":{"answer":"完成。"}}',
        tools,
    )
    assert action.name == "finish"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        '{"action":"finish","arguments":{"answer":"x",}}',
        "[]",
        '{"action":"finish","arguments":{"answer":"a"}} '
        '{"action":"finish","arguments":{"answer":"b"}}',
    ],
)
def test_reject_invalid_model_output(text: str, tools: ToolRegistry) -> None:
    with pytest.raises(ActionParseError):
        parse_action(text, tools)


@pytest.mark.parametrize(
    "text",
    [
        '{"arguments":{}}',
        '{"action":"finish"}',
        '{"action":"finish","arguments":{"answer":"ok"},"extra":1}',
        '{"action":"finish","arguments":[]}',
        '{"action":"finish","arguments":{"answer":""}}',
        '{"action":"unknown","arguments":{}}',
        '{"action":"get_weather","arguments":{"location":"北京"}}',
        '{"action":"get_weather","arguments":{"city":123}}',
    ],
)
def test_reject_protocol_violations(text: str, tools: ToolRegistry) -> None:
    with pytest.raises(ActionParseError):
        parse_action(text, tools)


def test_require_reason_accepts_react_action(tools: ToolRegistry) -> None:
    action = parse_action(
        '{"reason":"缺少天气信息。","action":"get_weather",'
        '"arguments":{"city":"北京"}}',
        tools,
        require_reason=True,
    )
    assert action.reason == "缺少天气信息。"


def test_require_reason_rejects_missing_reason(tools: ToolRegistry) -> None:
    with pytest.raises(ActionParseError, match="缺少字段"):
        parse_action(
            '{"action":"get_weather","arguments":{"city":"北京"}}',
            tools,
            require_reason=True,
        )


def test_normal_mode_rejects_unexpected_reason(tools: ToolRegistry) -> None:
    with pytest.raises(ActionParseError, match="额外字段"):
        parse_action(
            '{"reason":"x","action":"finish","arguments":{"answer":"ok"}}',
            tools,
        )


def test_action_fingerprint_ignores_reason_and_key_order() -> None:
    first = parse_action_for_fingerprint(
        reason="第一种解释", arguments={"b": 2, "a": 1}
    )
    second = parse_action_for_fingerprint(
        reason="第二种解释", arguments={"a": 1, "b": 2}
    )
    assert action_fingerprint(first) == action_fingerprint(second)


def parse_action_for_fingerprint(reason: str, arguments: dict[str, object]):
    from simple_agent.action import AgentAction

    return AgentAction("calculator", arguments, reason)


def test_snapshot_action_is_independent() -> None:
    from simple_agent.action import AgentAction

    arguments: dict[str, object] = {"city": "北京"}
    snapshot = snapshot_action(AgentAction("get_weather", arguments))
    arguments["city"] = "上海"
    assert snapshot.arguments == {"city": "北京"}
    assert '"action": "get_weather"' in action_to_json(snapshot)
