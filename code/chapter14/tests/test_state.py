from __future__ import annotations

from simple_agent.action import AgentAction, snapshot_action
from simple_agent.state import create_initial_state


def test_initial_states_do_not_share_lists() -> None:
    first = create_initial_state("system", "任务一")
    second = create_initial_state("system", "任务二")

    first.messages.append(
        {"role": "assistant", "content": "只属于第一次运行"}
    )

    assert len(first.messages) == 3
    assert len(second.messages) == 2
    assert first.messages is not second.messages
    assert first.records is not second.records


def test_action_snapshot_is_independent() -> None:
    arguments = {"city": "北京"}
    action = AgentAction(name="get_weather", arguments=arguments)

    saved = snapshot_action(action)
    arguments["city"] = "上海"

    assert saved.arguments == {"city": "北京"}
