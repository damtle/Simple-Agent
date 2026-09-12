# 第十四章 Mock、测试与基础评估

第十三章已经让城市旅行助手保存 `AgentState`、`StepRecord` 和 Execution Trace。一次运行结束后，开发者可以知道模型请求了多少次、Parser 在哪一步失败、工具是否发生重试，以及程序最终为什么终止。

这些记录能够帮助我们复盘一次已经发生的运行，却还不能稳定回答另一个问题：

> 修改 Parser、工具或 Controller 之后，原有行为是否仍然正确？

最直接的方法是重新运行旅行助手并人工观察结果。但一旦测试依赖真实大语言模型，这种检查就很难重复。相同 Prompt 可能产生不同措辞和工具顺序；模型服务可能暂时不可用；每次运行还会消耗时间和调用额度。一次成功演示只能说明“这一次运行成功了”，不能证明某条控制路径在后续改动后仍然不被破坏。

要验证 Agent 的程序行为，需要把模型输出从不可控变量变成可控输入。程序先预先准备好模型将依次返回的内容，再检查 Parser、工具、Controller、State 和 Trace 是否产生预期结果。这样，同一个测试案例可以在没有网络和 API Key 的环境中反复运行。

本章将为当前教学实现建立一组确定性自动化测试，并从测试结果中提取最基础的运行指标。

## 14.1 为什么真实模型不适合作为基础自动化测试

假设我们要验证下面的行为：

```text
模型先选择 get_weather
→ 工具返回北京模拟天气
→ Observation 进入下一轮 messages
→ 模型输出 finish
→ Agent 正常结束
```

若测试直接调用真实模型，可能出现多种结果：

```text
模型直接输出 finish
模型先查询景点而不是天气
模型返回带代码围栏的 JSON
模型使用不同的最终回答措辞
模型服务请求超时
```

这些结果不一定表示程序出现 Bug。它们可能只是模型生成具有不确定性，或者模型服务当时不可用。

基础自动化测试需要满足三个条件：

| 条件 | 含义 |
|---|---|
| 可重复 | 相同代码和输入应得到相同测试结果 |
| 可定位 | 失败时能够指出哪个程序边界被破坏 |
| 可快速运行 | 不依赖网络、密钥和长时间模型生成 |

真实模型实验适合观察 Prompt 与具体模型的实际表现，却不适合作为每次修改代码都必须通过的基础测试。测试 Controller 时，我们真正关心的是：

```text
面对某段模型输出，程序怎样处理
```

而不是：

```text
真实模型这一次恰好会输出什么
```

因此，测试需要一个能够按照脚本返回预设文本的模型替代对象。

## 14.2 Unit Test、Integration Test 与 Regression Test

不同测试关注的范围不同。本章正式使用三类测试。

> **Unit Test（单元测试）是对一个边界清楚的组件进行独立验证，检查给定输入是否产生预期输出或错误。**

Parser 和旅行工具适合单元测试。Parser 测试不需要调用模型，也不需要执行工具；工具测试不需要进入 Agent Loop。

> **Integration Test（集成测试）是验证多个组件连接后能否按照约定共同工作。**

Controller 测试会同时经过 Mock LLM、Parser、工具执行、Observation、State 和终止逻辑。它不是只验证一个函数，而是检查完整控制链。

> **Regression Test（回归测试）是用于确认代码修改之后，已经存在的正确行为没有被意外破坏的测试。**

回归测试不是另一种特殊语法。一个单元测试或集成测试，在修复过某个 Bug 后被长期保留下来，就可以成为回归测试。

例如，若程序曾经忘记把 Observation 加入下一轮 `messages`，修复后应保留一个测试：

```text
第二次模型请求必须包含第一次工具执行产生的 Observation
```

以后无论怎样重构 Controller，这条测试都应继续通过。

三类测试在本章中的对应关系为：

| 测试文件 | 主要类型 | 主要验证 |
|---|---|---|
| `test_parser.py` | Unit Test | Action 文本是否被正确接受或拒绝 |
| `test_tools.py` | Unit Test | 工具结果、错误类型和可重试属性 |
| `test_agent.py` | Integration Test / Regression Test | Controller、Parser、Tool、Observation 和终止怎样协作 |
| `test_state.py` | Unit Test / Regression Test | 状态隔离、记录快照和计数器一致性 |

## 14.3 Mock LLM：把模型输出变成可控输入

在本书中：

> **Mock LLM 是测试中代替真实模型的对象。它按照预设顺序返回模型文本，并记录每次调用收到的 `messages`。**

本章使用的 Mock 不理解旅行任务，也不会根据关键词选择工具。测试用例负责提前写出模型应当返回的内容：

```python
outputs = [
    (
        '{"action":"get_weather",'
        '"arguments":{"city":"北京"}}'
    ),
    (
        '{"action":"finish",'
        '"arguments":{"answer":"查询完成。"}}'
    ),
]
```

第一次调用返回天气 Action，第二次调用返回 `finish`。

`mock_llm.py` 可以写成：

```python
from copy import deepcopy
from collections.abc import Sequence


MockOutput = str | Exception


class MockLLM:
    def __init__(
        self,
        outputs: Sequence[MockOutput],
    ) -> None:
        self._outputs = list(outputs)
        self._index = 0
        self.calls: list[
            list[dict[str, str]]
        ] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def remaining_outputs(self) -> int:
        return len(self._outputs) - self._index

    def generate(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        self.calls.append(deepcopy(messages))

        if self._index >= len(self._outputs):
            raise AssertionError(
                "MockLLM 没有更多预设输出。"
            )

        output = self._outputs[self._index]
        self._index += 1

        if isinstance(output, Exception):
            raise output

        return output
```

`deepcopy()` 十分重要。若 Mock 只保存原始 `messages` 列表的引用，Controller 后续继续追加消息时，第一次调用记录也会跟着变化。测试将无法还原模型在第一次请求时真正看到了什么。

`MockLLM` 还可以预设异常：

```python
llm = MockLLM(
    outputs=[
        LLMRequestError(
            "模型服务连接超时。",
            retryable=True,
        ),
        (
            '{"action":"finish",'
            '"arguments":{"answer":"完成。"}}'
        ),
    ]
)
```

这样可以稳定验证 Network Retry，而不需要真的制造网络故障。

从严格的测试术语看，一个只返回固定值的对象更接近 scripted stub。本章使用“Mock LLM”这一名称，是因为它不仅提供预设输出，还记录调用次数和每次收到的消息，能够支持后续断言。

## 14.4 Controller 必须允许替换模型对象

Mock 能否进入测试，取决于 Controller 是否把模型依赖写死在内部。

下面的结构很难测试：

```python
def run_agent(
    user_task: str,
) -> AgentExecution:
    client = OpenAI(
        api_key=...,
        base_url=...,
    )

    ...
```

每次调用 `run_agent()` 都会创建真实客户端，测试无法轻易阻止网络请求。

更合适的方式是让调用方传入一个提供 `generate()` 方法的对象：

```python
def run_agent(
    user_task: str,
    llm: object,
    max_steps: int = 6,
    max_format_retries: int = 2,
    max_tool_retries: int = 1,
    max_same_action: int = 2,
) -> AgentExecution:
    ...
```

Controller 只使用：

```python
model_output = llm.generate(
    state.messages
)
```

真实模型适配器和 Mock LLM 都可以提供相同方法：

```text
真实 LLM：
messages → 网络请求 → model_output

Mock LLM：
messages → 读取预设列表 → model_output
```

本章暂时依靠 Python 的鸭子类型，不建立最终的 LLM 抽象接口。当前目标只是让同一套 Agent 逻辑能够分别接收真实模型与测试替代对象。

为了避免在测试章节提前形成最终 Public API，`code/chapter14/` 保留一份可独立运行的教学快照。`main.py` 为正文中的固定案例提供少量兼容入口，完整测试则直接从本章本地 `simple_agent/` 导入职责明确的对象：

```python
from main import (
    create_initial_state,
    execute_tool,
    parse_action,
    run_agent,
)
from simple_agent import Agent, TerminationReason
from simple_agent.action import AgentAction, snapshot_action
```

这种导入方式不是最终公共 API。它只让重构前的现有行为拥有一组稳定断言。模块边界将在下一阶段单独整理。

## 14.5 使用 pytest 与 Test Fixture

本章使用 `pytest` 运行自动化测试：

```bash
python -m pip install pytest
```

进入章节代码目录：

```bash
cd code/chapter14
```

运行全部测试：

```bash
python -m pytest tests -q
```

运行单个文件：

```bash
python -m pytest tests/test_agent.py -q
```

其中，`-q` 表示使用较简洁的输出。

测试经常需要重复准备相同任务、Mock 输出或工具配置。若每个测试都重新复制这些内容，测试本身也会出现重复。pytest 使用 Fixture 解决这项问题。

> **Test Fixture（测试夹具）是为测试准备的可重复初始条件，例如输入数据、对象、配置或临时资源。**

例如：

```python
import pytest

from mock_llm import MockLLM


@pytest.fixture
def travel_task() -> str:
    return "请查询北京的模拟天气。"


@pytest.fixture
def normal_llm() -> MockLLM:
    return MockLLM(
        outputs=[
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京"}}'
            ),
            (
                '{"action":"finish",'
                '"arguments":{'
                '"answer":"北京模拟天气查询完成。"}}'
            ),
        ]
    )
```

测试只需要在参数中声明 Fixture 名称：

```python
def test_agent_finishes(
    travel_task: str,
    normal_llm: MockLLM,
) -> None:
    execution = run_agent(
        user_task=travel_task,
        llm=normal_llm,
    )

    assert execution.result.success is True
```

每个测试都应获得新的 Mock LLM。若多个测试共享同一个已经消耗过输出的实例，测试执行顺序会影响结果，确定性测试反而会变得不稳定。

## 14.6 测试 Parser 的程序边界

Parser 测试不需要 Mock LLM。它直接把字符串交给 `parse_action()`，检查返回的 `AgentAction` 或 `ActionParseError`。

`tests/test_parser.py` 可以包含：

```python
import pytest

from main import (
    ActionParseError,
    parse_action,
)


def test_parse_valid_weather_action() -> None:
    action = parse_action(
        (
            '{"action":"get_weather",'
            '"arguments":{"city":"北京"}}'
        )
    )

    assert action.name == "get_weather"
    assert action.arguments == {
        "city": "北京",
    }


def test_reject_invalid_json() -> None:
    with pytest.raises(
        ActionParseError,
        match="JSON",
    ):
        parse_action(
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京",}}'
            )
        )


def test_reject_unknown_action() -> None:
    with pytest.raises(
        ActionParseError,
        match="未知",
    ):
        parse_action(
            (
                '{"action":"search_web",'
                '"arguments":{"query":"北京"}}'
            )
        )


def test_reject_wrong_argument_type() -> None:
    with pytest.raises(ActionParseError):
        parse_action(
            (
                '{"action":"calculator",'
                '"arguments":{'
                '"operation":"multiply",'
                '"a":"60","b":2}}'
            )
        )
```

这些测试关注的是边界，而不是实现细节。只要 Parser 仍然正确接受或拒绝输入，即使内部函数被拆分、变量名改变，测试也不应失败。

测试异常时，`match` 只匹配具有稳定意义的关键词。若断言完整错误句子，稍微调整提示文案就会导致测试失败，而程序行为其实没有变化。

## 14.7 测试旅行工具

工具单元测试直接检查输入、结构化结果和错误分类。

`tests/test_tools.py` 可以写成：

```python
from main import execute_tool


def test_get_weather_returns_simulated_data() -> None:
    result = execute_tool(
        tool_name="get_weather",
        arguments={"city": "北京"},
    )

    assert result.success is True
    assert "晴" in result.content
    assert "30℃" in result.content
    assert result.error_type is None
    assert result.retryable is False


def test_unknown_city_is_not_retryable() -> None:
    result = execute_tool(
        tool_name="get_weather",
        arguments={"city": "成都"},
    )

    assert result.success is False
    assert result.error_type == "not_found"
    assert result.retryable is False


def test_divide_by_zero_returns_business_error() -> None:
    result = execute_tool(
        tool_name="calculator",
        arguments={
            "operation": "divide",
            "a": 10,
            "b": 0,
        },
    )

    assert result.success is False
    assert result.error_type == "invalid_operation"
    assert result.retryable is False
```

这里不只检查 `content`。Controller 真正依赖的是：

```text
success
error_type
retryable
```

若工具把“城市不存在”错误地标记成 `retryable=True`，程序可能无意义地重复查询。即使错误文字完全相同，工具行为也已经被破坏。

工具测试至少应覆盖：

| 类型 | 示例 |
|---|---|
| 正常输入 | 查询北京模拟天气 |
| 缺失数据 | 查询未收录城市 |
| 边界值 | 成人票价为 0 |
| 非法业务值 | 除数为 0 |
| 临时失败 | `temporary_unavailable` |
| 安全属性 | 是否允许自动重试或需要确认 |

具有副作用的模拟工具只能测试调用边界和计数器，不应在测试中连接真实预订、发送或支付服务。

## 14.8 测试完整 Controller

Controller 集成测试使用 Mock LLM 驱动完整流程。

`tests/test_agent.py` 的成功路径可以写成：

```python
from main import TerminationReason, run_agent
from mock_llm import MockLLM


def test_agent_finishes_after_weather_tool() -> None:
    llm = MockLLM(
        outputs=[
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京"}}'
            ),
            (
                '{"action":"finish",'
                '"arguments":{'
                '"answer":"北京模拟天气查询完成。"}}'
            ),
        ]
    )

    execution = run_agent(
        user_task="请查询北京的模拟天气。",
        llm=llm,
        max_steps=4,
    )

    assert execution.result.success is True
    assert (
        execution.result.termination_reason
        is TerminationReason.SUCCESS
    )
    assert execution.result.steps == 2

    state = execution.state

    assert state.finished is True
    assert state.step == 2
    assert state.llm_calls == 2
    assert state.tool_calls == 1
    assert state.parse_failures == 0
    assert len(state.records) == 2
```

这项测试没有只断言最终回答。它同时检查运行结果、步骤数量、实际模型调用次数、工具调用次数和轨迹记录数量。

### 检查 Observation 是否进入下一次请求

Mock LLM 保存了每次调用收到的消息，因此测试可以查看第二次请求：

```python
def test_observation_enters_next_request() -> None:
    llm = MockLLM(
        outputs=[
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京"}}'
            ),
            (
                '{"action":"finish",'
                '"arguments":{"answer":"完成。"}}'
            ),
        ]
    )

    run_agent(
        user_task="查询北京天气。",
        llm=llm,
    )

    second_request = llm.calls[1]

    assert any(
        message["content"].startswith(
            "Observation:"
        )
        for message in second_request
    )
```

这条断言保护了第七章和第八章建立的核心行为：工具结果必须进入下一轮上下文。

### 检查格式重试仍属于同一个 Step

```python
def test_format_retry_stays_in_same_step() -> None:
    llm = MockLLM(
        outputs=[
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京",}}'
            ),
            (
                '{"action":"get_weather",'
                '"arguments":{"city":"北京"}}'
            ),
            (
                '{"action":"finish",'
                '"arguments":{"answer":"完成。"}}'
            ),
        ]
    )

    execution = run_agent(
        user_task="查询北京天气。",
        llm=llm,
        max_format_retries=1,
    )

    assert execution.result.success is True
    assert execution.result.steps == 2
    assert execution.state.llm_calls == 3
    assert execution.state.parse_failures == 1

    first_record = execution.state.records[0]

    assert len(
        first_record.model_attempts
    ) == 2
```

三次模型请求只形成两个 Agent Step。这个测试同时保护第十二章的格式重试语义和第十三章的 Step—Attempt 关系。

## 14.9 测试状态隔离与历史快照

状态错误往往不会立刻导致异常，却会让不同任务互相污染。`tests/test_state.py` 应明确检查每次运行都拥有独立列表。

```python
from main import (
    AgentAction,
    create_initial_state,
    snapshot_action,
)


def test_initial_states_do_not_share_lists() -> None:
    first = create_initial_state(
        system_prompt="system",
        user_task="任务一",
    )
    second = create_initial_state(
        system_prompt="system",
        user_task="任务二",
    )

    first.messages.append(
        {
            "role": "assistant",
            "content": "只属于第一次运行",
        }
    )

    assert len(first.messages) == 3
    assert len(second.messages) == 2
    assert first.messages is not second.messages
    assert first.records is not second.records


def test_action_snapshot_is_independent() -> None:
    arguments = {"city": "北京"}

    action = AgentAction(
        name="get_weather",
        arguments=arguments,
    )
    snapshot = snapshot_action(action)

    arguments["city"] = "上海"

    assert snapshot.arguments == {
        "city": "北京",
    }
```

第一项测试可以发现错误的可变默认值；第二项测试可以发现轨迹保存了 `arguments` 原始引用，而不是当时的快照。

还应检查最终结果与 State 的终止原因一致：

```python
def test_result_and_state_share_reason(
    normal_llm: MockLLM,
) -> None:
    execution = run_agent(
        user_task="查询北京天气。",
        llm=normal_llm,
    )

    assert (
        execution.state.termination_reason
        is execution.result.termination_reason
    )
```

状态、轨迹和最终结果描述同一次运行，不能分别保存互相冲突的结局。

## 14.10 为失败路径建立测试矩阵

只测试一次正常 `finish`，无法保护第十二章建立的可靠性逻辑。测试矩阵应覆盖每一种重要终止路径。

| 场景 | Mock 或输入安排 | 主要断言 |
|---|---|---|
| 正常结束 | Tool Action → `finish` | `SUCCESS`、步骤和工具次数正确 |
| 格式修复成功 | 非法 JSON → 合法 Action | `parse_failures=1`，仍在同一 Step |
| 格式重试耗尽 | 连续非法输出 | `PARSE_ERROR`，工具没有执行 |
| 重复 Action | 连续两次相同 Action | `REPEATED_ACTION`，第二次工具未执行 |
| 最大步数 | 持续生成不同 Tool Action | `MAX_STEPS` |
| LLM 请求失败 | Mock 抛出 `LLMRequestError` | `LLM_ERROR` |
| 工具临时失败 | 第一次失败、第二次成功 | Tool Retry 次数正确 |
| 工具业务失败 | `not_found` | Observation 进入下一轮 Decision Retry |
| 等待确认 | 高风险 Action，无确认回调 | `CONFIRMATION_REQUIRED` |
| 用户拒绝 | 确认回调返回 `False` | `USER_REJECTED` |

例如，重复 Action 测试可以写成：

```python
def test_repeated_action_stops_before_tool() -> None:
    repeated = (
        '{"action":"get_weather",'
        '"arguments":{"city":"北京"}}'
    )
    llm = MockLLM(
        outputs=[
            repeated,
            repeated,
        ]
    )

    execution = run_agent(
        user_task="查询北京天气。",
        llm=llm,
        max_same_action=2,
    )

    assert (
        execution.result.termination_reason
        is TerminationReason.REPEATED_ACTION
    )
    assert execution.state.tool_calls == 1

    second_record = execution.state.records[1]

    assert second_record.action is not None
    assert second_record.tool_result is None
    assert second_record.observation is None
```

这项测试证明重复检测发生在第二次工具执行之前。

回归测试的价值不在数量多，而在于每条测试都保护一项明确行为。测试名称应当描述行为，而不是内部函数名：

```text
test_observation_enters_next_request
test_format_retry_stays_in_same_step
test_repeated_action_stops_before_tool
```

这样的名称在失败时能够直接说明哪项系统约定被破坏。

## 14.11 Metrics：把运行过程汇总成数字

Execution Trace 可以解释每一步发生了什么。当测试案例增多后，还需要一组数字快速比较运行成本和控制结果。这些数字称为 Metrics。

在本书中：

> **Metrics 是从 AgentRunResult、AgentState 和 Execution Trace 中汇总得到的数值化运行信息。**

`metrics.py` 可以定义：

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from main import AgentExecution


@dataclass(frozen=True)
class AgentMetrics:
    normal_finish: bool
    llm_calls: int
    tool_calls: int
    parse_failures: int
    total_steps: int
    termination_reason: str


def collect_metrics(
    execution: AgentExecution,
) -> AgentMetrics:
    state = execution.state
    result = execution.result

    return AgentMetrics(
        normal_finish=result.success,
        llm_calls=state.llm_calls,
        tool_calls=state.tool_calls,
        parse_failures=state.parse_failures,
        total_steps=result.steps,
        termination_reason=(
            result.termination_reason.value
        ),
    )
```

当前教学快照记录 `llm_calls`、`tool_calls` 和 `parse_failures`。如果以后增加 `request_failures` 或 `tool_failures`，也应先把它们作为结构化状态字段保存，再生成 Metrics；Metrics 不应通过扫描日志文字猜测失败次数。

对固定案例集合，可以汇总：

```python
from collections import Counter


def summarize_metrics(
    items: list[AgentMetrics],
) -> dict[str, object]:
    if not items:
        return {
            "cases": 0,
            "normal_finish_rate": 0.0,
            "average_llm_calls": 0.0,
            "average_tool_calls": 0.0,
            "average_steps": 0.0,
            "termination_counts": {},
        }

    count = len(items)

    return {
        "cases": count,
        "normal_finish_rate": (
            sum(
                item.normal_finish
                for item in items
            )
            / count
        ),
        "average_llm_calls": (
            sum(item.llm_calls for item in items)
            / count
        ),
        "average_tool_calls": (
            sum(item.tool_calls for item in items)
            / count
        ),
        "average_steps": (
            sum(item.total_steps for item in items)
            / count
        ),
        "termination_counts": dict(
            Counter(
                item.termination_reason
                for item in items
            )
        ),
    }
```

这些指标主要观察：

```text
任务是否按当前协议正常结束
一次运行发生多少次模型请求
工具实际执行多少次
格式或工具失败出现多少次
运行在哪种原因下终止
```

它们不能证明最终答案符合现实事实，也不能证明模型在开放任务上的质量。`normal_finish=True` 只表示 Controller 通过合法的 `finish` 正常结束。它不表示用户目标已经客观完成，也不应直接命名为任务完成率。

同样地，调用次数越少不一定越好。模型可能因为执行高效而减少调用，也可能因为过早 `finish` 或绕过工具而减少调用。Metrics 必须结合测试任务、Trace 和断言一起解释。

## 14.12 使用固定案例进行基础评估

`main.py` 可以提供一组不访问真实模型的确定性案例：

```text
normal
format_retry
tool_retry
repeated_action
max_steps
```

每个案例包含：

```text
固定用户任务
预设模型输出
必要的故障配置
预期终止原因
```

最小组织方式如下：

```python
from mock_llm import MockLLM
from metrics import (
    collect_metrics,
    summarize_metrics,
)


def run_case(
    task: str,
    outputs: list[str | Exception],
    **settings: object,
) -> AgentMetrics:
    llm = MockLLM(outputs)

    execution = run_agent(
        user_task=task,
        llm=llm,
        **settings,
    )

    return collect_metrics(execution)


def main() -> None:
    metrics = [
        run_case(
            task="查询北京模拟天气。",
            outputs=[
                (
                    '{"action":"get_weather",'
                    '"arguments":{"city":"北京"}}'
                ),
                (
                    '{"action":"finish",'
                    '"arguments":{"answer":"完成。"}}'
                ),
            ],
        ),
        run_case(
            task="查询北京模拟天气。",
            outputs=[
                (
                    '{"action":"get_weather",'
                    '"arguments":{"city":"北京",}}'
                ),
                (
                    '{"action":"get_weather",'
                    '"arguments":{"city":"北京"}}'
                ),
                (
                    '{"action":"finish",'
                    '"arguments":{"answer":"完成。"}}'
                ),
            ],
            max_format_retries=1,
        ),
    ]

    print(summarize_metrics(metrics))


if __name__ == "__main__":
    main()
```

运行：

```bash
python main.py
```

可能得到：

```text
{
  "cases": 2,
  "normal_finish_rate": 1.0,
  "average_llm_calls": 2.5,
  "average_tool_calls": 1.0,
  "average_steps": 2.0,
  "termination_counts": {
    "success": 2
  }
}
```

固定案例必须保持输入和预设输出不变。若每次评估都更换任务，修改前后的数字就失去可比性。

`main.py` 只是展示基础 Metrics。判断代码是否正确仍应运行 pytest，并通过明确断言检查每条路径。

## 14.13 失败实验：删除 Observation 更新

为了验证测试是否真正保护了系统，可以故意破坏 Controller。暂时删除：

```python
state.messages.append(
    {
        "role": "user",
        "content": observation,
    }
)
```

然后运行：

```bash
python -m pytest \
    tests/test_agent.py::test_observation_enters_next_request \
    -q
```

测试应当失败：

```text
AssertionError:
第二次模型请求中没有 Observation
```

注意，使用简单 Mock LLM 时，Agent 仍可能继续输出预设的 `finish`，最终结果甚至可能显示成功。若测试只检查 `execution.result.success`，这个 Bug 不会被发现。

检查 `llm.calls[1]` 则能够验证真正需要保护的行为：第二次模型请求是否包含工具反馈。

恢复代码后重新运行全部测试：

```bash
python -m pytest tests -q
```

所有测试都应再次通过。

这个实验展示了自动化测试的基本价值：

```text
不是证明代码永远正确
而是在某项约定被破坏时立即给出可重复的失败信号
```

## 14.14 测试与评估的边界

本章建立的测试主要验证软件控制逻辑。

| 问题 | 本章测试能否回答 |
|---|---:|
| Parser 是否拒绝非法 JSON | 能 |
| 工具错误是否正确分类 | 能 |
| Observation 是否进入下一轮上下文 | 能 |
| 格式重试是否仍属于同一 Step | 能 |
| 重复 Action 是否在工具前被拦截 | 能 |
| 状态列表是否彼此隔离 | 能 |
| Metrics 是否与 State 一致 | 能 |
| 某个真实模型是否总会遵守 Prompt | 不能 |
| 最终旅行建议是否符合真实世界 | 不能 |
| 更换模型后开放任务质量是否下降 | 不能 |
| 哪个 Prompt 在大型任务集上表现最好 | 不能 |

真实模型质量评估需要固定任务集、模型与 Prompt 版本、语义评分规则、证据检查，必要时还需要人工评审或独立评估器。这些工作不属于本章的基础软件测试。

生产监控同样不同于本章 Metrics。生产系统还需要持续采集请求量、延迟、Token、费用、错误率和服务可用性，并处理隐私、权限和告警。当前 Metrics 只从本地测试运行中提取简单计数。

Mock LLM 也不能证明真实模型会生成预设输出。它证明的是：

> 当 Agent 收到这些输出时，程序是否按照既定规则处理。

因此，真实模型实验和 Mock 自动化测试应当并存，但不能互相替代。

## 14.15 当前系统快照

完成这一章后，城市旅行助手已经能够：

```text
使用 Mock LLM 提供确定性模型输出
→ 用 Unit Test 验证 Parser 和工具
→ 用 Integration Test 验证完整 Controller
→ 检查 State、Trace 和终止原因
→ 为已修复行为保留 Regression Test
→ 从固定案例中汇总基础 Metrics
```

本章代码目录为：

```text
code/chapter14/
├── simple_agent/
├── mock_llm.py
├── metrics.py
├── main.py
├── pyproject.toml
└── tests/
    ├── test_parser.py
    ├── test_tools.py
    ├── test_agent.py
    └── test_state.py
```

各文件职责如下：

| 文件 | 职责 |
|---|---|
| `simple_agent/` | 保存第十三章形成的本地教学实现，供本章测试使用 |
| `mock_llm.py` | 按顺序返回预设模型输出并记录请求 |
| `metrics.py` | 从运行结果和状态中提取基础指标 |
| `main.py` | 保存当前教学实现入口并运行确定性案例 |
| `test_parser.py` | 验证 Action 解析与协议边界 |
| `test_tools.py` | 验证工具结果、错误分类和安全属性 |
| `test_agent.py` | 验证 Controller 正常路径与失败路径 |
| `test_state.py` | 验证状态隔离、轨迹快照和计数一致性 |

此时，Parser、工具、Controller、State 与可靠性逻辑都拥有一组可以快速重复运行的测试。项目仍然保留教学脚本的组织方式，相同职责也仍可能散落在多个章节目录中。下一步进行结构调整时，这组测试将成为判断“外部行为是否保持不变”的保护网。

## 14.16 本章小结

这一章把 Agent 的运行过程变成了可以稳定验证的程序行为。

Mock LLM 按照预设顺序返回模型文本，并记录每次调用收到的消息，因此 Controller 测试不需要访问真实模型。Unit Test 独立检查 Parser、工具和状态；Integration Test 检查模型输出、Action、工具、Observation、State 和终止逻辑怎样共同工作；Regression Test 则长期保护已经确认的行为不被后续修改破坏。

Test Fixture 为每个测试准备全新的任务、Mock 和配置，避免测试之间共享可变状态。Metrics 从 `AgentRunResult` 和 `AgentState` 中汇总完成状态、调用次数、失败次数、步骤数和终止原因，但不等于真实模型质量或事实正确率。

完成本章后，应当能够回答：

1. 为什么真实模型实验不能替代基础自动化测试？
2. Mock LLM 为什么只返回预设输出，而不应重新实现模型决策？
3. Unit Test、Integration Test 与 Regression Test 分别保护什么？
4. 为什么测试不仅要检查最终回答，还要检查 State 和 Trace？
5. 基础 Metrics 能说明哪些运行现象，又不能证明什么？

## 习题

**1. 测试 Parser 的额外字段**

构造一个包含 `reason`、`action`、`arguments` 和未知字段 `debug` 的模型输出。根据当前 Action Protocol，确认 Parser 接受还是拒绝，并为预期行为编写测试。

**2. 测试 Tool Retry 次数**

让天气工具第一次返回 `temporary_unavailable`，第二次成功。断言 `state.tool_calls`、步骤中保存的工具结果和最终 `TerminationReason`。

**3. 测试格式重试耗尽**

让 Mock LLM 连续返回三次非法 JSON，并设置 `max_format_retries=2`。检查模型调用次数、Parser 失败次数、工具调用次数和最终结果。

**4. 建立一次 Bug 回归测试**

故意让 Controller 在检测重复 Action 后仍然执行工具，观察哪个断言失败。修复后保留该测试，防止以后再次出现相同行为。

**5. 比较两个固定案例集**

分别为“全部正常输出”和“包含格式错误、工具临时失败”的案例集汇总 Metrics。比较完成率、平均模型调用次数和平均工具调用次数，并结合 Trace 解释差异。

## 参考资料

1. [unittest.mock — mock object library](https://docs.python.org/3/library/unittest.mock.html).
2. [Fixtures reference](https://docs.pytest.org/en/stable/reference/fixtures.html).
3. [How to write and report assertions in tests](https://docs.pytest.org/en/stable/how-to/assert.html).
4. [Refactoring: Improving the Design of Existing Code](https://refactoring.com/). 2nd Edition. Addison-Wesley, 2018.
