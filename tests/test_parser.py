from __future__ import annotations

import pytest

from simple_agent.parser import ActionParseError, parse_action


def test_parse_valid_tool_action(echo_registry) -> None:
    action = parse_action(
        '{"action":"echo","arguments":{"text":"hello"}}',
        echo_registry,
    )

    assert action.name == "echo"
    assert action.arguments == {"text": "hello"}
    assert action.reason is None


def test_parse_optional_reason(echo_registry) -> None:
    action = parse_action(
        '{"reason":"需要回显。","action":"echo",'
        '"arguments":{"text":"hello"}}',
        echo_registry,
    )

    assert action.reason == "需要回显。"


def test_require_reason_rejects_missing_reason(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="reason"):
        parse_action(
            '{"action":"finish","arguments":{"answer":"完成。"}}',
            echo_registry,
            require_reason=True,
        )


def test_parse_complete_json_fence(echo_registry) -> None:
    action = parse_action(
        """```json
{"action":"finish","arguments":{"answer":"完成。"}}
```""",
        echo_registry,
    )

    assert action.name == "finish"


def test_reject_invalid_json(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="JSON"):
        parse_action(
            '{"action":"echo","arguments":{"text":"hello",}}',
            echo_registry,
        )


def test_reject_unknown_tool(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="工具不存在"):
        parse_action(
            '{"action":"search_web","arguments":{}}',
            echo_registry,
        )


def test_reject_tool_arguments(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="只接受 text"):
        parse_action(
            '{"action":"echo","arguments":{"value":"hello"}}',
            echo_registry,
        )


def test_reject_empty_finish_answer(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="answer"):
        parse_action(
            '{"action":"finish","arguments":{"answer":"  "}}',
            echo_registry,
        )


def test_reject_extra_top_level_field(echo_registry) -> None:
    with pytest.raises(ActionParseError, match="debug"):
        parse_action(
            '{"action":"finish","arguments":{"answer":"完成。"},'
            '"debug":true}',
            echo_registry,
        )
