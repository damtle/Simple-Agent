"""最终应用使用 Mock 完成四步旅行任务及答案检查，不访问网络。"""

import json
import sys
from types import SimpleNamespace

import pytest

from examples.travel_assistant.main import (
    CritiqueParseError, build_llm, build_travel_agent, collect_evidence,
    parse_critique, reflect_answer,
)
from examples.travel_assistant.tools import validate_calculator_arguments
from tests.fakes import MockLLM


def test_client_has_one_retry_owner_and_explicit_timeout(monkeypatch):
    captured = {}

    def client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=client))
    for name in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL_ID"):
        monkeypatch.setenv(name, "test-placeholder")
    build_llm()
    assert captured["max_retries"] == 0
    assert captured["timeout"] == 30.0


@pytest.mark.parametrize("value", [10**400, float("inf"), float("nan"), True])
def test_calculator_rejects_unsafe_numbers(value):
    with pytest.raises(ValueError, match="有限数字"):
        validate_calculator_arguments({"operation": "add", "a": value, "b": 1})


@pytest.mark.parametrize("output", [
    '{"passed":true,"summary":"ok","issues":[],"x":' + '9' * 5000 + '}',
    '[' * 5000 + ']' * 5000,
    '{"passed":true,"summary":"ok","issues":[{}]}',
    '{"passed":false,"summary":"failed","issues":[]}',
], ids=["huge-number", "deep-json", "passed-with-issues", "failed-without-issues"])
def test_critique_rejects_invalid_model_output(output):
    with pytest.raises(CritiqueParseError):
        parse_critique(output)


def test_complete_travel_task_and_reflection():
    def action(name, arguments):
        return json.dumps({"reason": "完成当前步骤", "action": name,
                           "arguments": arguments}, ensure_ascii=False)

    llm = MockLLM([
        action("get_weather", {"city": "北京"}),
        action("get_attraction_info", {"name": "故宫"}),
        action("calculator", {"operation": "multiply", "a": 60, "b": 2}),
        action("finish", {"answer": "两张票共120元，以上来自本地模拟数据。"}),
    ])
    execution = build_travel_agent(llm).run("查询天气、故宫信息和两张票总价")
    assert execution.success
    assert execution.state.tool_calls == 3
    assert execution.state.llm_calls == 4
    assert len(execution.state.messages) == 8
    for call in llm.calls[1:]:
        assert any("Observation:" in message["content"] for message in call)
    evidence = collect_evidence(execution)
    assert "get_weather" in evidence and "calculator" in evidence and "120" in evidence
    critic = MockLLM(['{"passed":true,"summary":"证据一致","issues":[]}'])
    assert reflect_answer(llm=critic, user_task="查询旅行信息", evidence=evidence,
                          draft=execution.message) == execution.message
