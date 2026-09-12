"""不可信模型输入、工具空结果和历史快照的回归测试。"""

import json

import pytest

from simple_agent import Agent, TerminationReason, Tool, ToolRegistry
from simple_agent.action import AgentAction
from simple_agent.parser import ActionParseError, load_json_object, parse_action
from tests.fakes import MockLLM


@pytest.mark.parametrize("output", [
    " " * 65_537,
    "[" * 5_000 + "]" * 5_000,
    '{"number":' + "9" * 5_000 + "}",
    '{"number":1e999}',
    '{"number":NaN}',
    '{"number":Infinity}',
], ids=["oversize", "deep-json", "huge-integer", "overflow-float", "nan", "infinity"])
def test_untrusted_output_returns_controlled_failure(output):
    execution = Agent(
        llm=MockLLM([output, output, output]),
        tools=ToolRegistry(),
        system_prompt="只输出 JSON。",
    ).run("测试边界")
    assert execution.termination_reason is TerminationReason.PARSE_ERROR
    assert execution.state.tool_calls == 0
    assert execution.state.parse_failures == 3


def test_brackets_and_escaped_quotes_inside_answer_are_not_nesting():
    answer = '括号与引号：' + '[\\"' * 100
    output = json.dumps({"action": "finish", "arguments": {"answer": answer}})
    assert parse_action(output, ToolRegistry()).arguments["answer"] == answer


def test_actual_nesting_limit():
    with pytest.raises(ActionParseError, match="嵌套"):
        load_json_object('{"x":' + '[' * 64 + '0' + ']' * 64 + '}')


@pytest.mark.parametrize("value", [None, "", "  \n"])
def test_empty_tool_output_is_failure(value):
    tools = ToolRegistry()
    tools.register(Tool("empty", "没有有效结果", {}, lambda: value))
    result = tools.execute(AgentAction("empty", {}))
    assert not result.success
    assert result.error_type == "empty_result"


def test_zero_is_a_valid_tool_result():
    tools = ToolRegistry()
    tools.register(Tool("zero", "数值零", {}, lambda: 0))
    result = tools.execute(AgentAction("zero", {}))
    assert result.success and result.content == "0"


def test_state_and_trace_do_not_share_nested_arguments(echo_registry):
    execution = Agent(
        llm=MockLLM([
            '{"action":"echo","arguments":{"text":"original"}}',
            '{"action":"finish","arguments":{"answer":"done"}}',
        ]),
        tools=echo_registry,
        system_prompt="只输出 JSON。",
    ).run("回显")
    execution.state.records[0].action.arguments["text"] = "changed"
    assert execution.trace.records[0].action.arguments["text"] == "original"
    execution.trace.records[0].action.arguments["text"] = "trace-only"
    assert execution.state.records[0].action.arguments["text"] == "changed"
