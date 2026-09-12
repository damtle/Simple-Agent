# 第九章 ReAct：边行动边观察

城市旅行助手已经能够围绕用户目标连续调用工具。面对下面的任务：

```text
请查询北京的模拟天气和故宫的模拟开放、票价信息，计算两张成人票的总价，并给出出行建议。
```

模型可以先查询天气，再读取景点信息，随后调用计算器，最后通过 `finish` 返回回答。每次工具执行产生的 Observation 都会进入下一轮上下文，因此模型能够根据已经获得的信息继续行动。

不过，现有运行过程主要说明了模型“选择了什么”：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

从这项 Action 可以看出模型准备计算 `60 × 2`，却看不出它如何判断已拿到单张票价、为什么此时需要计算器，以及用户目标中是否还有未完成的要求。任务较短时，人们可以根据上下文推测；但当步骤增多、工具返回失败或模型重复行动时，仅凭 Action 与 Observation 很难迅速定位问题。

ReAct 在每次行动前增加一段简洁的 Reason。它说明当前已经获得什么、还缺少什么，以及为什么选择下一项 Action：

```json
{
  "reason": "已经获得故宫成人票价60元，用户需要两张票的总价，因此调用计算器。",
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

工具执行之后，新的 Observation 再次改变下一轮判断。Agent 的运行过程由此变成：

```text
Reason + Action → Observation → Reason + Action → Observation → finish
```

## 9.1 只有 Action 时，哪些问题不容易看见

设想一次多工具任务出现了下面的执行过程：

```text
Step 1：get_weather(city="北京")
Step 2：get_weather(city="北京")
Step 3：calculator(operation="multiply", a=60, b=2)
Step 4：finish
```

第二步重复查询了同一个城市。仅看 Action，开发者无法立即确认模型为什么这样做。可能是第一轮 Observation 没有进入上下文，也可能是模型没有识别自己已经得到天气信息，还可能是用户确实要求再次确认。

再看另一种情况：

```text
Step 1：get_weather(city="北京")
Step 2：finish
```

如果原始任务还要求查询故宫开放状态并计算两张票的总价，那么第二步显然结束得过早。但从 `finish` 本身只能看到最终回答，不能直接看出模型是否遗漏了任务中的其他要求。

在行动前加入简短摘要后，这些问题更容易被看见：

```json
{
  "reason": "已经获得天气信息，用户要求已经全部满足，可以结束。",
  "action": "finish",
  "arguments": {
    "answer": "北京模拟天气为晴。"
  }
}
```

这段 Reason 记录了模型当前判断：它认为用户目标已经全部完成。程序仍然需要检查实际 Action 与最终回答，但开发者不必再完全依靠猜测还原模型的局部决策。

Reason 的作用不是证明模型一定正确，而是让错误更容易被观察到。

## 9.2 什么是 ReAct

ReAct 一词由 Reasoning 与 Acting 组合而来。它把语言形式的判断与面向环境的行动交替组织，使模型能够在采取行动后读取新的环境反馈，再更新下一步判断。原始 ReAct 工作强调的正是这种交替关系：推理帮助模型跟踪和调整行动，行动则让模型从外部环境取得新的信息。

在本书中，我们采用下面的工程化定义：

> **ReAct 是一种让模型交替生成简洁 Reason 与 Action，并在每次 Observation 到来后重新判断下一步的 Agent 控制方式。**

它的最小过程为：

```text
当前目标与已有反馈
→ Reason
→ Action
→ Tool
→ Observation
→ 更新后的 Reason
→ 下一项 Action
```

ReAct 并没有改变工具执行器，也没有取消 Parser。模型仍然只能提出 Action，程序仍然负责校验和执行。新增的部分是：模型在提出行动时，同时留下当前决策依据的简短摘要。

Agent Loop 与 ReAct 的关系可以写成：

```text
Agent Loop：负责让决策、执行和反馈持续运行
ReAct：规定每轮决策以 Reason + Action 的形式出现
```

因此，ReAct 不是另一套独立运行时，而是建立在已有 Agent Loop 之上的决策组织方式。

## 9.3 Reason：面向执行过程的决策摘要

在本书中：

> **Reason 是模型面向执行过程生成的简洁决策摘要，用于说明当前已知信息、缺失信息和下一步行动依据。**

一个有效 Reason 通常回答三个问题：

```text
当前已经获得了什么？
完成用户目标还缺少什么？
为什么选择当前 Action？
```

例如：

```text
已经获得北京的模拟天气，但还不知道故宫是否开放和成人票价，
因此下一步查询景点信息。
```

这段摘要清楚说明了现状、缺口和行动原因。

下面的 Reason 过于空泛：

```text
我需要调用一个工具。
```

它没有说明工具选择依据，也不能帮助检查模型是否真正理解了任务。

下面的 Reason 又过于冗长：

```text
首先我要分析用户句子的每一个词，然后枚举所有可能方案，
再考虑每一种方案的优缺点……
```

这种输出会增加上下文长度，使执行记录充满与当前行动无关的内容。它也没有必要成为程序接口的一部分。

因此，Reason 应保持一到两句话。它不是可执行代码，也不应被 `eval()`、`exec()` 或工具执行器处理。真正可以改变环境的仍然只有经过 Parser 校验的 Action。

还需要认识到，Reason 是模型生成的可读解释，不等于模型隐藏的完整内部思维过程，也不能保证精确反映模型生成 Action 时的全部内部计算。它更接近一段面向开发者的决策说明。

## 9.4 为什么 Reason、Action 和 Observation 要交替出现

工具型任务中的关键信息通常不会在开始时全部存在。模型只有先采取行动，才能获得新的事实。

仍以旅行任务为例。第一轮开始时，模型只知道用户目标，还不知道北京的模拟天气，因此可以生成：

```json
{
  "reason": "当前还没有北京的模拟天气信息，先查询天气才能继续给出建议。",
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

程序执行工具后返回：

```text
Observation:
工具名称：get_weather
工具参数：{"city": "北京"}
执行状态：成功
工具结果：北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

第二轮 Reason 必须根据这项新信息产生：

```json
{
  "reason": "天气信息已经获得，但故宫的开放状态和成人票价仍然未知，因此查询景点信息。",
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

景点工具返回成人票价 60 元后，模型才有依据构造计算 Action：

```json
{
  "reason": "故宫成人票价为60元，用户需要两张票的总价，因此计算60乘以2。",
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

得到 `120` 后，下一轮可以结束：

```json
{
  "reason": "天气、开放状态、单张票价和两张票总价都已获得，可以完整回答用户。",
  "action": "finish",
  "arguments": {
    "answer": "北京当前模拟天气为晴，温度30℃；故宫在模拟数据中处于开放状态，成人票价60元，两张票共120元。建议避开正午并注意防晒补水。以上信息来自本地模拟数据。"
  }
}
```

每轮 Reason 都依赖当前已经获得的 Observation。ReAct 不是在任务开始时写完所有判断，再一次性执行多个工具，而是不断进行局部更新：

```text
根据当前信息判断
→ 执行一个行动
→ 获得新信息
→ 重新判断
```

这使它适合工具结果可能改变后续路径的任务。

## 9.5 为 ReAct 增加输出协议

第八章的 Action JSON 包含两个顶层字段：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

ReAct 决策增加 `reason`：

```json
{
  "reason": "当前缺少北京天气信息，因此先查询模拟天气。",
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

顶层字段固定为：

```text
reason
action
arguments
```

三者职责不同：

| 字段 | 作用 |
|---|---|
| `reason` | 说明当前判断和行动依据 |
| `action` | 指定工具名称或 `finish` |
| `arguments` | 提供当前 Action 的参数 |

Tool Action 与原有协议保持一致，只是增加 Reason：

```json
{
  "reason": "还需要确认故宫的模拟开放状态和票价。",
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

Finish Action 同样需要 Reason：

```json
{
  "reason": "完成回答所需的信息已经全部获得。",
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
```

模型每轮仍然只能提出一个 Action。若一次输出多个工具调用，程序就无法在每项行动之间插入 Observation，也失去了 ReAct“行动后重新判断”的意义。

## 9.6 保持 AgentAction 边界不变

`AgentAction` 已经表示通过校验的程序行动：

```python
@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, object]
```

Reason 并不是工具参数，也不应改变 Action 的执行方式。为了保持这一数据边界，可以增加一个只用于表示 ReAct 决策的容器：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ReActDecision:
    reason: str
    action: AgentAction
```

例如：

```python
decision = ReActDecision(
    reason=(
        "已经获得票价60元，"
        "需要计算两张票的总价。"
    ),
    action=AgentAction(
        name="calculator",
        arguments={
            "operation": "multiply",
            "a": 60,
            "b": 2,
        },
    ),
)
```

这样，原有职责保持清楚：

```text
ReActDecision：保存本轮 Reason 与 Action
AgentAction：保存经过校验、可以交给 Controller 的行动
```

工具执行器只接收：

```python
decision.action
```

不会读取 `decision.reason`。

`code/chapter09/action.py` 可以保存这两个数据类，以及第六章已经使用的 `ActionParseError`：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class ReActDecision:
    reason: str
    action: AgentAction


class ActionParseError(ValueError):
    """模型输出未通过 ReAct 决策协议校验。"""
```

这里新增的是 ReAct 决策的组合方式，而不是重新改变 Tool Executor 对 `AgentAction` 的理解。

## 9.7 Parser 怎样校验 ReAct 决策

Parser 仍然承担第六章建立的边界。它需要先完成原有 JSON 和 Action 校验，再额外检查 `reason`。

核心步骤为：

```text
model_output: str
→ JSON 对象
→ 检查 reason、action、arguments
→ 校验 Reason
→ 校验 AgentAction
→ ReActDecision
```

可以在 `parser.py` 中实现：

```python
import json

from action import (
    ActionParseError,
    AgentAction,
    ReActDecision,
)


def parse_react_decision(
    model_output: str,
) -> ReActDecision:
    try:
        data = json.loads(model_output)
    except json.JSONDecodeError as error:
        raise ActionParseError(
            f"模型输出不是合法 JSON：{error.msg}。"
        ) from error

    if not isinstance(data, dict):
        raise ActionParseError(
            "ReAct 决策顶层必须是 JSON 对象。"
        )

    expected_fields = {
        "reason",
        "action",
        "arguments",
    }

    if set(data) != expected_fields:
        raise ActionParseError(
            "ReAct 决策必须且只能包含 "
            "reason、action 和 arguments。"
        )

    reason = data["reason"]

    if not isinstance(reason, str):
        raise ActionParseError(
            "reason 必须是字符串。"
        )

    reason = reason.strip()

    if not reason:
        raise ActionParseError(
            "reason 不能为空。"
        )

    action = validate_action(
        action_name=data["action"],
        arguments=data["arguments"],
    )

    return ReActDecision(
        reason=reason,
        action=action,
    )
```

其中，`validate_action()` 继续使用第六章已经建立的规则，检查允许的行动名称、字段集合和参数类型。正文不再重复展开所有工具参数校验。

Parser 可以确认 Reason 是非空字符串，却不能自动证明它与 Action 在语义上完全一致。例如：

```json
{
  "reason": "需要查询北京天气。",
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

这段输出在结构上可能合法，但 Reason 与 Action 并不一致。结构校验能够建立明确的数据边界，无法替代对决策内容的判断。

因此：

> Reason 看起来合理，不能让程序跳过 Action 校验；Action 通过结构校验，也不表示 Reason 一定准确。

## 9.8 Prompt 怎样引导局部判断

ReAct Prompt 不只是要求模型多输出一个字段，还要明确告诉模型如何利用 Observation 更新判断。

`code/chapter09/prompts.py` 可以定义：

```python
REACT_SYSTEM_PROMPT = """
你是一个使用本地模拟工具完成旅行任务的城市旅行助手。

每一轮都要根据用户目标、此前经过校验的 Action
以及全部 Observation，生成一个 ReAct 决策。

输出必须是一个 JSON 对象，并且只能包含：
reason、action、arguments。

reason 使用一到两句话说明：
1. 当前已经获得什么；
2. 完成用户目标还缺少什么；
3. 为什么选择当前 Action。

不要输出冗长的内部思维过程。

可用行动：

1. get_weather
   arguments: {"city": "城市名称"}

2. get_attraction_info
   arguments: {"name": "景点名称"}

3. calculator
   arguments: {
     "operation": "add|subtract|multiply|divide",
     "a": 数字,
     "b": 数字
   }

4. finish
   arguments: {"answer": "最终回答"}

规则：
1. 每轮只能选择一个 Action。
2. 需要模拟天气时使用 get_weather。
3. 需要模拟景点状态或票价时使用
   get_attraction_info。
4. 需要精确计算时使用 calculator。
5. 获得 Observation 后重新检查尚未完成的要求。
6. 不要重复已经成功且无需再次执行的 Action。
7. 工具失败后，根据失败信息修改下一步判断，
   或使用 finish 如实说明限制。
8. 只有用户目标已经完整满足时才使用 finish。
9. 最终事实必须来自 Observation。
10. 不要输出 Markdown 代码块或额外说明文字。
""".strip()
```

Prompt 中有三项关键要求。

第一，Reason 只描述当前局部判断，不要求一次生成完整任务计划。

第二，每轮只能选择一个 Action。程序必须先执行并返回 Observation，模型才能决定下一步。

第三，工具失败同样要进入下一轮判断。模型不能忽略失败结果，也不应在没有新依据时反复执行完全相同的失败 Action。

Prompt 只能引导模型遵循这些规则。输出是否满足 JSON 和参数协议，仍然由 Parser 判断。

## 9.9 在已有 Agent Loop 中接入 ReAct

循环骨架不需要重新设计。主要变化发生在模型输出解析和终端展示位置。

第八章中：

```python
action = parse_action(model_output)
```

现在改为：

```python
decision = parse_react_decision(model_output)
action = decision.action
```

进入消息历史的内容同时包含 Reason 和 Action：

```python
def decision_to_json(
    decision: ReActDecision,
) -> str:
    return json.dumps(
        {
            "reason": decision.reason,
            "action": decision.action.name,
            "arguments": decision.action.arguments,
        },
        ensure_ascii=False,
        indent=2,
    )
```

循环核心可以写成：

```python
for step in range(1, max_steps + 1):
    model_output = request_text(
        client=client,
        model_id=model_id,
        messages=messages,
    )

    decision = parse_react_decision(
        model_output
    )
    action = decision.action

    print(f"\n=== Step {step} ===")
    print(f"Reason：{decision.reason}")
    print(f"Action：{action.name}")
    print(f"Arguments：{action.arguments}")

    messages.append(
        {
            "role": "assistant",
            "content": decision_to_json(decision),
        }
    )

    if action.name == "finish":
        answer = action.arguments["answer"]
        assert isinstance(answer, str)
        return answer

    observation = execute_action_once(action)

    print("Observation：")
    print(observation)

    messages.append(
        {
            "role": "user",
            "content": observation,
        }
    )
```

与第八章相比，Controller 的执行职责没有变化：

```text
调用模型
→ 解析决策
→ 执行 AgentAction
→ 构造 Observation
→ 更新 messages
→ 继续或结束
```

新增的是每轮可见的 Reason，以及 Parser 对 `reason` 字段的检查。Reason 不会被传给工具，也不会改变 Tool Observation 的产生方式。

本章代码目录如下：

```text
code/chapter09/
├── main.py
├── action.py
├── parser.py
├── prompts.py
└── README.md
```

其中，`main.py` 继续使用前面已经建立的旅行工具与 Observation 构造逻辑，正文只展示 ReAct 带来的增量变化。

## 9.10 运行完整 ReAct 任务

从项目根目录执行：

```bash
python code/chapter09/main.py
```

输入：

```text
请查询北京的模拟天气和故宫的模拟开放、票价信息，计算两张成人票的总价，并给出出行建议。
```

一次可能的运行过程如下。

**Step 1**

```text
Reason：
当前还没有北京的模拟天气信息，需要先查询天气。

Action：
get_weather

Arguments：
{"city": "北京"}
```

Observation：

```text
Observation:
工具名称：get_weather
工具参数：{"city": "北京"}
执行状态：成功
工具结果：北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

**Step 2**

```text
Reason：
天气信息已经获得，但故宫的模拟开放状态和成人票价仍然未知，因此查询景点信息。

Action：
get_attraction_info

Arguments：
{"name": "故宫"}
```

Observation：

```text
Observation:
工具名称：get_attraction_info
工具参数：{"name": "故宫"}
执行状态：成功
工具结果：故宫位于北京，在当前模拟数据中处于开放状态，成人票价60元，活动类型为室内外步行。
```

**Step 3**

```text
Reason：
故宫成人票价为60元，用户需要两张票的总价，因此调用计算器。

Action：
calculator

Arguments：
{"operation": "multiply", "a": 60, "b": 2}
```

Observation：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "multiply", "a": 60, "b": 2}
执行状态：成功
工具结果：120
```

**Step 4**

```text
Reason：
天气、开放状态、单张票价和两张票总价都已经获得，可以完整回答用户。

Action：
finish
```

最终回答可能为：

```text
北京当前模拟天气为晴，温度30℃；故宫在模拟数据中处于开放状态，成人票价60元，两张票共120元。天气较热，建议避开正午并注意防晒补水。以上信息来自本地模拟数据。
```

不同模型可能采用不同的工具顺序和表达方式。判断运行是否合理时，应检查 Reason 是否使用了已有 Observation、Action 是否与当前缺失信息对应，以及 `finish` 是否覆盖用户目标。

## 9.11 失败实验：根据错误 Observation 调整判断

使用下面的任务：

```text
请计算10除以0，并根据实际执行结果回答，不要猜测。
```

第一轮可能生成：

```json
{
  "reason": "用户要求得到精确计算结果，因此先调用计算器。",
  "action": "calculator",
  "arguments": {
    "operation": "divide",
    "a": 10,
    "b": 0
  }
}
```

Parser 可以接受这项 Action，因为参数名称和类型都符合协议。计算器真正执行时返回失败 Observation：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "divide", "a": 10, "b": 0}
执行状态：失败
错误类型：ValueError
工具结果：除数不能为 0。
```

下一轮合理的决策是：

```json
{
  "reason": "计算器已经明确返回除数不能为0，无法得到有效数值，因此应结束并说明失败原因。",
  "action": "finish",
  "arguments": {
    "answer": "本次计算无法完成，因为除数不能为0。"
  }
}
```

这次运行展示了 Observation 对下一步判断的直接影响。模型没有继续声称得到了计算结果，也没有在没有新信息时重复相同 Action，而是根据工具失败改变了结束内容。

若下一轮 Reason 写成：

```text
计算应该已经成功，可以返回结果。
```

就说明模型没有正确使用失败 Observation。若它再次以相同参数调用计算器，也说明当前局部判断没有有效更新。

当前程序可以把这些现象展示出来，但不会仅凭 Reason 自动阻止重复 Action。Reason 提高了可观察性，不等于已经建立完整的错误恢复机制。

## 9.12 Reason-Action-Observation Trace

连续保存每轮 Reason、Action 和 Observation，就形成 **Reason-Action-Observation Trace**。

在本书中：

> **Reason-Action-Observation Trace 是按执行顺序展示每轮决策摘要、实际行动和环境反馈的可读记录。**

例如：

```text
Step 1
Reason: 当前缺少北京天气信息。
Action: get_weather({"city": "北京"})
Observation: 北京模拟天气为晴，温度30℃。

Step 2
Reason: 天气已获得，但故宫状态和票价仍未知。
Action: get_attraction_info({"name": "故宫"})
Observation: 故宫开放，成人票价60元。

Step 3
Reason: 单张票价已获得，需要计算两张票总价。
Action: calculator({"operation": "multiply", "a": 60, "b": 2})
Observation: 120
```

这类记录可以帮助检查：

| 运行现象 | Trace 中应重点观察什么 |
|---|---|
| 重复查询同一工具 | Reason 是否忽略已有 Observation |
| 调用错误工具 | Reason 中识别的缺失信息是否正确 |
| 参数不符合任务 | Reason 与 Arguments 是否指向同一对象 |
| 工具失败后继续编造 | 下一轮 Reason 是否读取失败状态 |
| 过早 `finish` | Reason 是否遗漏用户目标中的要求 |
| 获得全部信息后仍不结束 | Reason 是否能识别完成条件 |

这仍然是一份面向阅读的运行记录。它可以显示在终端，也可以暂时保存在 `messages` 中，但尚未形成专门的步骤数据结构、持久化日志或自动化评估结果。

Reason 也不能替代执行事实。真正发生过的操作仍然由经过校验的 AgentAction 和工具返回的 Observation 证明。即使 Reason 声称“天气查询成功”，只要没有对应成功 Observation，程序就不能把这句话视为天气数据。

## 9.13 ReAct 的适用范围与边界

ReAct 的主要优势在于动态性。每一轮都可以根据最新 Observation 重新选择行动，因此它适合下面的任务：

```text
工具结果可能改变下一步
执行路径无法提前完全确定
某项工具可能失败
需要逐步探索外部信息
需要观察模型的局部判断
```

它也存在明显边界。

**局部判断不等于完整计划。** Reason 通常解释当前一步，并不保证模型在任务开始时已经形成覆盖全部目标的全局步骤。任务结构较长时，模型仍可能只关注眼前信息。

**可读解释不等于正确决策。** Reason 可能表述得很合理，但 Action 仍可能选择错误工具或填写错误参数。程序必须继续校验和执行 Action。

**Reason 不负责修订最终答案。** 即使工具过程正确，`finish.answer` 仍可能遗漏信息或违反用户要求。检查与修订结果属于答案生成之后的另一项职责。

因此，ReAct 与“先形成完整计划再执行”是两种并列的控制思路，而不是前者必然取代后者。ReAct 关注每次获得反馈后下一步怎样调整；完整计划更关注执行开始前怎样覆盖整个目标。最终答案生成后，还可以再接入独立的结果检查过程。

理解这些边界后，才能根据任务特点选择控制方式，而不是把所有多步任务都强行写成同一种 Prompt。

## 9.14 当前系统快照

完成这一章后，城市旅行助手的每轮决策都包含：

```text
简洁 Reason
经过校验的 AgentAction
工具执行产生的 Observation
```

当前流程为：

```text
用户目标与已有反馈
→ ReActDecision
→ Reason + AgentAction
→ Tool
→ Observation
→ 下一轮 ReActDecision
→ finish
```

与普通 Agent Loop 相比，工具、Parser、Controller 和终止方式没有被替换。新增的是一条可读的局部判断记录，使开发者更容易观察模型是否使用了已有信息、为什么选择当前工具，以及失败 Observation 是否改变了下一步行动。

不过，当前 Reason 主要解释局部决策。面对步骤较多而依赖关系清晰的任务，仅靠每轮局部判断仍可能遗漏整体要求。由此可以继续追问：

> 在真正执行工具之前，程序能否先得到一份覆盖完整目标、可以检查步骤顺序的计划？

## 9.15 本章小结

这一章在已有 Agent Loop 上实现了 ReAct。

ReAct 让模型在每一轮交替生成 Reason 与 Action，并在工具产生 Observation 后重新判断。Reason 是面向执行过程的简洁决策摘要，用于说明当前已知信息、缺失信息和行动依据；它不是可执行代码，也不是模型完整内部思维过程。

为避免改变原有 `AgentAction` 的职责，本章使用 `ReActDecision` 组合 Reason 与经过校验的 Action。连续的 Reason、Action 和 Observation 构成可读的 Reason-Action-Observation Trace，帮助开发者观察工具选择、任务遗漏和失败调整。

完成本章后，应当能够回答：

1. ReAct 与第八章 Agent Loop 的关系是什么？
2. Reason 应当包含哪些信息，为什么不应写成冗长思维过程？
3. 为什么 Reason 不能替代 Parser 对 Action 的校验？
4. Observation 怎样改变下一轮 Reason 与 Action？
5. Reason-Action-Observation Trace 能帮助发现哪些问题，又不能证明什么？

## 习题

**1. 为现有任务补充 Reason**

观察一个第八章 Action：

```json
{
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

假设天气已经查询完成、景点信息仍然缺失，为它补充一个一到两句话的 `reason`。

**2. 检查空 Reason**

让模型输出：

```json
{
  "reason": "",
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

确认 Parser 拒绝该输出，并说明错误发生在 Reason 校验还是工具执行阶段。

**3. 制造 Reason 与 Action 不一致**

测试：

```json
{
  "reason": "当前缺少北京天气，因此需要查询天气。",
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

说明为什么基础 Parser 可能接受它，以及结构正确与语义一致之间有什么区别。

**4. 观察失败后的局部调整**

运行：

```text
请计算10除以0，并根据实际执行结果回答。
```

记录失败 Observation 后的下一轮 Reason，检查模型是否使用 `finish` 如实说明限制，还是重复完全相同的计算 Action。

**5. 删除 Reason 历史**

保存 Action 和 Observation，但不把前几轮 Reason 放入下一次 `messages`。比较运行是否仍能完成，并思考 Reason 对模型后续判断与开发者调试分别有什么价值。

## 参考资料

1. [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629). ICLR, 2023. arXiv:2210.03629.
2. [Artificial Intelligence: A Modern Approach](https://aima.cs.berkeley.edu/). 4th Edition. Pearson, 2020.
