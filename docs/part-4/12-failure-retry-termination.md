# 第十二章 失败、重试与终止

前面的城市旅行助手已经能够连续调用工具，也能够采用 ReAct、Plan-and-Solve 或 Reflection 改进任务执行与答案生成。只要模型按要求返回、工具正常运行、程序最终得到 `finish`，整个过程就会顺利结束。

但真实运行不会始终沿着这条路径前进。

一次模型请求可能因为网络波动而超时；模型可能返回不完整的 JSON；工具可能因为临时故障无法提供结果；同一个 Action 也可能被连续执行多次。更危险的是，程序可能把所有错误都当成“再试一次”，最终陷入无限循环，或者在一个具有副作用的工具上重复执行同一操作。

因此，可靠的 Agent 不能只会继续行动，还要能够回答：

```text
错误发生在哪一层？
当前问题是否可以恢复？
应当重试哪个操作？
重试是否安全？
最多允许重试多少次？
程序最终为什么停止？
```

这一章将为城市旅行助手加入失败分类、有限重试、重复行动检测、Step 边界软时间预算、工具确认和统一运行结果。无论任务正常完成还是中途失败，调用方都将得到一个明确的 `AgentRunResult`，而不是依赖零散的 `print()` 或混在一起的异常。

## 12.1 “Agent 失败”不是一种错误

假设用户输入：

```text
请查询北京的模拟天气，并给出出行建议。
```

运行过程中可能出现下面几种情况。

**模型请求失败**

```text
调用模型服务时连接超时。
```

此时模型尚未产生输出，Parser 和工具都没有运行。

**模型输出格式错误**

```text
我建议查询天气：
{"action": "get_weather", "arguments": {"city": "北京",}}
```

模型已经返回文本，但文本没有通过 Action Protocol。工具仍然没有执行。

**工具执行失败**

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

Action 已经通过 Parser，但天气工具返回：

```text
天气服务暂时不可用。
```

**Agent 决策异常**

```text
Step 1：get_weather(city="北京")
Step 2：get_weather(city="北京")
Step 3：get_weather(city="北京")
```

每一次 Action 都可能合法，工具也可能成功，但 Agent 没有利用已经获得的信息继续完成任务。

**权限边界未满足**

```json
{
  "action": "submit_reservation",
  "arguments": {
    "attraction": "故宫",
    "visitor_count": 2
  }
}
```

Action 结构正确，工具也存在，但预订会产生外部影响，程序不能仅凭模型决定直接执行。

这些失败发生在不同位置，恢复方式也不同。网络超时可以重复同一次请求；非法 JSON 应当让模型重新生成；工具临时故障可以在满足条件时重新执行；工具参数错误则应作为 Observation 返回，让 Agent 重新决策；需要确认的操作必须等待用户授权。

在本书中：

> **Failure Classification 是根据错误发生的位置、性质和可恢复性，对一次 Agent 失败进行分层。**

本章采用下面的分类：

| 层级 | 典型问题 | 合适处理 |
|---|---|---|
| 输入与配置 | 用户任务为空、必要配置缺失 | 立即终止 |
| LLM 请求 | 临时超时、连接中断、服务限流 | Network Retry |
| 模型协议 | 空输出、非法 JSON、字段或参数错误 | Format Retry |
| Tool 执行 | 临时服务错误、数据不存在、业务错误 | Tool Retry 或 Decision Retry |
| Agent 决策 | 重复 Action、始终不结束 | 重复检测或硬终止 |
| 权限边界 | 有副作用的 Action 未确认 | Confirmation |
| Controller | 最大步数、Step 边界软时间预算达到上限 | 强制终止或阻止下一步 |
| 程序缺陷 | `NameError`、错误的数据结构访问 | 暴露并修复代码 |

最后一类不应被普通重试吞掉。若工具代码因为开发错误抛出 `NameError`，盲目再执行三次不会让程序变正确，只会掩盖真正的缺陷。

## 12.2 Retry Policy：先决定什么可以重试

重试并不等于在每个 `except` 分支都重新调用函数。一个可靠的重试过程至少需要明确四件事：

```text
重试对象
允许条件
最大次数
达到上限后的终止方式
```

在本书中：

> **Retry Policy 是程序针对不同失败类型规定重试对象、触发条件、次数上限和停止方式的规则集合。**

本章使用四类重试：

| 类型 | 实际重复什么 | 是否产生新决策 | 典型场景 |
|---|---|---:|---|
| Network Retry | 同一次模型请求 | 否 | 临时连接错误、超时 |
| Format Retry | 再次让模型生成当前 Action | 否 | 非法 JSON、协议校验失败 |
| Tool Retry | 重新执行同一个 AgentAction | 否 | 可安全重复的临时工具故障 |
| Decision Retry | 把失败作为 Observation 后重新选择 Action | 是 | 参数错误、数据不存在、当前工具不适用 |

前三种重试都在尝试完成当前操作。Decision Retry 则承认当前 Action 没有解决问题，让 Agent 进入下一轮决策。

可以用一个数据类集中保存本章的最小限制：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_network_retries: int = 2
    max_format_retries: int = 2
    max_tool_retries: int = 1
    max_steps: int = 8
    repeated_action_limit: int = 2
    timeout_seconds: float = 30.0
```

这些数值表示“最多额外重试多少次”。例如：

```text
max_network_retries = 2
```

表示一次初始请求失败后，最多再发送两次相同请求，总调用次数最多为三次。

所有限制都必须是明确的有限值。即使错误看起来可以恢复，程序也不能无限消耗模型调用、时间和工具资源。

`timeout_seconds` 是在 Agent Step 边界检查的软时间预算。它可以阻止超预算后的下一步开始，但不能中断正在进行的同步模型请求或工具调用。

## 12.3 Network Retry 与 Format Retry

Network Retry 和 Format Retry 都发生在工具执行之前，但它们解决的是两种完全不同的问题。

### Network Retry：重复同一次请求

Network Retry 适用于模型服务暂时无法返回结果的情况。请求内容没有问题，模型也尚未生成错误 Action，因此程序只需要在有限次数内重复同一次请求。

为了让核心逻辑不依赖某个 SDK 的具体异常名称，本章先使用统一错误类型：

```python
class LLMRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
```

模型适配代码负责把底层 SDK 异常转换为 `LLMRequestError`。例如，临时连接失败可以设置：

```python
raise LLMRequestError(
    "模型服务连接超时。",
    retryable=True,
)
```

认证失败则不可重试：

```python
raise LLMRequestError(
    "模型服务拒绝访问，请检查 API Key。",
    retryable=False,
)
```

有限网络重试可以写成：

```python
from collections.abc import Callable


def call_with_network_retry(
    request_fn: Callable[[], str],
    max_retries: int,
) -> str:
    for attempt in range(max_retries + 1):
        try:
            return request_fn()
        except LLMRequestError as error:
            if not error.retryable:
                raise

            if attempt >= max_retries:
                raise

    raise RuntimeError("不可达代码。")
```

这里不会修改 `messages`，因为每次发送的都是同一份模型请求。为了避免服务故障时立即连续轰击接口，完整实现还可以加入短暂等待和退避，但本章先保留最小结构。

### Format Retry：重新生成当前 Action

Format Retry 发生在模型已经返回文本之后。假设第一次输出：

```json
{
  "action": "get_weather"
}
```

缺少 `arguments`，Parser 会抛出 `ActionParseError`。程序不能自动猜测：

```python
arguments = {"city": "北京"}
```

而应把协议错误反馈给模型，请它重新生成当前 Action。

```python
def request_valid_action(
    request_action,
    messages: list[dict[str, str]],
    policy: RetryPolicy,
) -> AgentAction:
    retry_messages = list(messages)

    for attempt in range(
        policy.max_format_retries + 1
    ):
        model_output = call_with_network_retry(
            request_fn=lambda: request_action(
                retry_messages
            ),
            max_retries=policy.max_network_retries,
        )

        try:
            return parse_action(model_output)
        except ActionParseError as error:
            if attempt >= policy.max_format_retries:
                raise

            retry_messages.extend(
                [
                    {
                        "role": "assistant",
                        "content": model_output,
                    },
                    {
                        "role": "user",
                        "content": (
                            "ProtocolError：上一轮输出"
                            "未通过 Action 协议校验。\n"
                            f"错误原因：{error}\n"
                            "请只重新输出一个符合协议的"
                            " JSON 对象。"
                        ),
                    },
                ]
            )

    raise RuntimeError("不可达代码。")
```

这里使用临时的 `retry_messages`。未通过校验的输出只用于当前修复过程，不会直接成为正式 Action-Observation 历史。

两者的区别可以概括为：

```text
Network Retry：
没有取得模型输出 → 重复同一次请求

Format Retry：
已经取得非法输出 → 提供错误原因并重新生成
```

无论发生多少次网络或格式重试，只要最终得到的是同一个决策位置上的 Action，Agent 都还没有进入新的工具步骤。

## 12.4 Tool Retry 与 Idempotency

Action 通过 Parser 后，工具仍然可能失败。为了让 Controller 判断失败是否值得重试，工具不再只返回任意字符串，而是返回一个最小结构化结果：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolExecutionResult:
    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False
```

成功结果：

```python
ToolExecutionResult(
    success=True,
    content=(
        "北京当前模拟天气为晴，"
        "温度30℃，湿度45%，微风。"
    ),
)
```

临时失败：

```python
ToolExecutionResult(
    success=False,
    content="模拟天气服务暂时不可用。",
    error_type="temporary_unavailable",
    retryable=True,
)
```

确定性业务失败：

```python
ToolExecutionResult(
    success=False,
    content="没有找到城市“成都”的模拟天气数据。",
    error_type="not_found",
    retryable=False,
)
```

`retryable=True` 只表示错误本身可能通过再次执行恢复，还不能证明重复执行一定安全。程序还要检查工具是否具有幂等性。

在本书中：

> **Idempotency 是同一操作被重复执行多次时，其外部效果与执行一次保持一致的性质。**

查询天气通常可以被视为幂等操作。连续查询两次不会创建两个订单，也不会重复扣款。预订、发送和支付则可能产生副作用，不能因为网络异常就直接重复执行。

工具元数据可以写成：

```python
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    name: str
    function: Callable[..., ToolExecutionResult]
    idempotent: bool
    requires_confirmation: bool = False
```

三个基础旅行工具都是本地只读或确定性计算：

```python
TOOL_SPECS = {
    "get_weather": ToolSpec(
        name="get_weather",
        function=get_weather,
        idempotent=True,
    ),
    "get_attraction_info": ToolSpec(
        name="get_attraction_info",
        function=get_attraction_info,
        idempotent=True,
    ),
    "calculator": ToolSpec(
        name="calculator",
        function=calculator,
        idempotent=True,
    ),
}
```

Tool Retry 只有在两个条件同时成立时才执行：

```text
工具结果标记 retryable=True
并且 ToolSpec.idempotent=True
```

```python
def execute_with_tool_retry(
    spec: ToolSpec,
    arguments: dict[str, object],
    max_retries: int,
) -> ToolExecutionResult:
    for attempt in range(max_retries + 1):
        result = spec.function(**arguments)

        if result.success:
            return result

        can_retry = (
            result.retryable
            and spec.idempotent
            and attempt < max_retries
        )

        if not can_retry:
            return result

    raise RuntimeError("不可达代码。")
```

若天气数据中没有成都，结果会标记为 `retryable=False`，程序不会再次执行相同查询。若模拟天气服务第一次返回临时不可用，并且天气工具是幂等的，程序可以进行一次有限 Tool Retry。

> 可重试描述错误是否可能恢复，幂等性描述重复执行是否安全。两者不能互相替代。

## 12.5 Decision Retry 与重复行动

工具失败后，并不一定要立即结束整个任务。对于不可原样重试的失败，程序可以把结果构造成失败 Observation，交给模型重新选择下一步。

例如：

```text
Observation:
工具名称：get_weather
工具参数：{"city": "成都"}
执行状态：失败
错误类型：not_found
工具结果：没有找到城市“成都”的模拟天气数据。
```

模型看到这项反馈后，可以：

```text
询问用户是否要更换城市
选择当前已有数据支持的城市
说明能力边界并 finish
```

这种过程称为 Decision Retry。

> **Decision Retry 是把当前 Action 的失败结果作为 Observation 加入上下文，使 Agent 在新的决策轮次中选择其他行动。**

它与 Tool Retry 的区别是：

```text
Tool Retry：
同一个 Action → 再次执行同一个工具

Decision Retry：
失败 Observation → 模型重新选择 Action
```

Decision Retry 会推进 Agent Loop，因此仍然受到最大步数和 Step 边界软时间预算限制。

### 重复 Action 为什么需要额外检测

Agent 可能忽略已经获得的 Observation，连续产生相同 Action：

```text
get_weather(city="北京")
get_weather(city="北京")
get_weather(city="北京")
```

每项 Action 都能通过 Parser，工具也可能成功。如果 Controller 只检查格式和工具错误，这种循环会一直持续到 `max_steps`。

本章使用规范化字符串标识 Action：

```python
import json


def action_key(action: AgentAction) -> str:
    arguments = json.dumps(
        action.arguments,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{action.name}:{arguments}"
```

为了减少误判，最小实现只统计连续出现、工具和参数完全相同的 Action。达到限制时终止：

```python
def update_repeated_action_count(
    current_key: str,
    previous_key: str | None,
    previous_count: int,
) -> int:
    if current_key == previous_key:
        return previous_count + 1

    return 1
```

当：

```text
repeated_action_limit = 2
```

时，同一 Action 连续出现两次就会触发 `REPEATED_ACTION`。在更复杂的系统中，重复查询可能有合理理由，因此判断还可以结合时间、Observation 是否变化和工具类型。本章只建立最小保护，避免明显死循环。

## 12.6 Confirmation：模型不能独自授权高风险操作

前三个旅行工具只读取本地数据或完成计算，不会修改外部世界。为了说明权限边界，本章增加一个模拟预订工具：

```python
def submit_reservation(
    attraction: str,
    visitor_count: int,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        success=True,
        content=(
            f"已创建{attraction}的模拟预订，"
            f"人数为{visitor_count}。"
        ),
    )
```

它不会访问真实预订、账号或支付服务，但它代表了一类具有副作用的工具。注册时设置：

```python
TOOL_SPECS["submit_reservation"] = ToolSpec(
    name="submit_reservation",
    function=submit_reservation,
    idempotent=False,
    requires_confirmation=True,
)
```

在本书中：

> **Confirmation 是在执行需要授权或具有明显副作用的 Action 前，由程序取得用户明确同意的控制步骤。**

Confirmation 发生在 Action 已经通过 Parser 之后、工具真正执行之前：

```text
模型提出 Action
→ Parser 校验
→ 检查 requires_confirmation
→ 用户确认
→ 执行或拒绝
```

它不是让模型再说一句“我确认”。模型不能替用户授权自己的行动。

可以定义确认回调：

```python
from collections.abc import Callable


ConfirmationCallback = Callable[[AgentAction], bool]
```

执行前检查：

```python
def confirm_action(
    action: AgentAction,
    spec: ToolSpec,
    confirmation_callback: ConfirmationCallback | None,
) -> bool | None:
    if not spec.requires_confirmation:
        return True

    if confirmation_callback is None:
        return None

    return confirmation_callback(action)
```

返回值含义为：

```text
True：用户确认，可以执行
False：用户拒绝，停止执行
None：当前没有确认渠道，等待确认
```

本章不会自动暂停并恢复长期任务，只通过结构化终止结果说明当前 Action 需要确认。

## 12.7 TerminationReason 与 AgentRunResult

第八章已经具有 `finish` 和最大步数，但返回值主要是一段文本。进入失败恢复后，调用方还需要知道程序为什么结束。

在本书中：

> **Termination Reason 是一次 Agent 运行停止的明确原因。**

`result.py` 中定义：

```python
from dataclasses import dataclass
from enum import Enum


class TerminationReason(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    LLM_ERROR = "llm_error"
    PARSE_ERROR = "parse_error"
    TOOL_ERROR = "tool_error"
    REPEATED_ACTION = "repeated_action"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    CONFIRMATION_REQUIRED = "confirmation_required"
    USER_REJECTED = "user_rejected"
```

这些值描述控制层结局，而不是答案质量。例如，`SUCCESS` 表示 Agent 正常输出 `finish`，不表示该答案已经通过 Reflection，也不证明 Evidence 本身正确。

最终结果使用：

```python
@dataclass(frozen=True)
class AgentRunResult:
    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None
```

成功：

```python
AgentRunResult(
    success=True,
    message="北京模拟天气为晴，建议注意防晒。",
    termination_reason=TerminationReason.SUCCESS,
    steps=2,
)
```

格式重试耗尽：

```python
AgentRunResult(
    success=False,
    message="模型输出未通过 Action 协议校验。",
    termination_reason=TerminationReason.PARSE_ERROR,
    steps=1,
    error="Action 缺少 arguments 字段。",
)
```

等待确认：

```python
AgentRunResult(
    success=False,
    message="模拟预订需要用户明确确认。",
    termination_reason=(
        TerminationReason.CONFIRMATION_REQUIRED
    ),
    steps=2,
)
```

`message` 面向调用方或用户，`termination_reason` 供程序分支处理，`error` 保存简洁技术原因。这里不保存每一步的模型输出、Action 和 Observation；完整过程将在状态与轨迹结构中单独记录。

## 12.8 把可靠性控制接入 Agent Loop

本章代码目录为：

```text
code/chapter12/
├── result.py
├── retry.py
├── agent.py
├── tools.py
└── README.md
```

文件职责如下：

| 文件 | 职责 |
|---|---|
| `result.py` | 定义 `TerminationReason` 和 `AgentRunResult` |
| `retry.py` | 定义 `RetryPolicy`、Network Retry 与 Tool Retry |
| `tools.py` | 定义 `ToolExecutionResult`、`ToolSpec` 与旅行工具 |
| `agent.py` | 处理格式重试、决策重试、确认和终止 |
| `README.md` | 说明运行方式、故障开关和边界 |

可靠 Agent Loop 的主要顺序是：

```text
检查输入与总时间
→ 请求并校验 Action
→ 检查重复行动
→ finish 或执行工具
→ 检查 Confirmation
→ 有限 Tool Retry
→ 构造 Observation
→ 成功继续或 Decision Retry
→ 达到终止条件时返回 AgentRunResult
```

核心结构如下：

```python
from time import monotonic


def run_agent(
    user_task: str,
    request_action,
    policy: RetryPolicy,
    confirmation_callback=None,
) -> AgentRunResult:
    if not user_task.strip():
        return AgentRunResult(
            success=False,
            message="用户任务不能为空。",
            termination_reason=(
                TerminationReason.INVALID_INPUT
            ),
            steps=0,
        )

    messages = create_initial_messages(user_task)
    started_at = monotonic()
    previous_action_key: str | None = None
    repeated_action_count = 0

    for step in range(1, policy.max_steps + 1):
        if monotonic() - started_at > policy.timeout_seconds:
            return timeout_result(step - 1)

        try:
            action = request_valid_action(
                request_action=request_action,
                messages=messages,
                policy=policy,
            )
        except LLMRequestError as error:
            return llm_error_result(
                steps=step,
                error=str(error),
            )
        except ActionParseError as error:
            return parse_error_result(
                steps=step,
                error=str(error),
            )

        current_key = action_key(action)
        repeated_action_count = (
            update_repeated_action_count(
                current_key=current_key,
                previous_key=previous_action_key,
                previous_count=repeated_action_count,
            )
        )
        previous_action_key = current_key

        if (
            repeated_action_count
            >= policy.repeated_action_limit
        ):
            return repeated_action_result(
                steps=step,
                action=action,
            )

        if action.name == "finish":
            return AgentRunResult(
                success=True,
                message=action.arguments["answer"],
                termination_reason=(
                    TerminationReason.SUCCESS
                ),
                steps=step,
            )

        spec = TOOL_SPECS[action.name]

        confirmation = confirm_action(
            action=action,
            spec=spec,
            confirmation_callback=confirmation_callback,
        )

        if confirmation is None:
            return confirmation_required_result(
                steps=step,
                action=action,
            )

        if confirmation is False:
            return user_rejected_result(
                steps=step,
                action=action,
            )

        tool_result = execute_with_tool_retry(
            spec=spec,
            arguments=action.arguments,
            max_retries=policy.max_tool_retries,
        )

        observation = build_observation(
            action=action,
            result=tool_result,
        )
        append_action_observation(
            messages=messages,
            action=action,
            observation=observation,
        )

    return AgentRunResult(
        success=False,
        message="Agent 已达到最大执行步数。",
        termination_reason=TerminationReason.MAX_STEPS,
        steps=policy.max_steps,
    )
```

工具失败时没有立即统一返回 `TOOL_ERROR`，因为失败 Observation 仍可能使模型在下一轮改变参数或说明能力边界。只有当 Controller 判断任务无法继续，或者所有允许恢复的机会都已耗尽时，才返回失败结果。

本章把 `NameError`、错误的数据结构访问等程序缺陷视为应当暴露的问题。但当前 `ToolRegistry.execute()` 仍会把工具函数抛出的 `TypeError` 和 `ValueError` 统一转换为工具失败结果，因此可能混淆业务错误和程序缺陷。更严格的实现应使用专门的业务异常。

这段代码仍然省略了逐步轨迹和调用计数。当前目标是先让每一种运行结局都有明确控制语义。

## 12.9 运行主线案例

从项目根目录执行：

```bash
python code/chapter12/agent.py
```

主线任务仍然使用：

```text
请查询北京的模拟天气和故宫的模拟开放信息，
计算两张成人票的总价，并给出出行建议。
```

为了展示恢复过程，示例程序可以通过故障开关模拟：

```text
第一次模型请求：临时超时
第一次 Action 输出：缺少 arguments
第一次天气工具执行：temporary_unavailable
后续请求与工具执行：正常
```

一次可能的过程为：

```text
Step 1
Network Retry 1：模型请求超时
Network Retry 2：请求成功

Format Retry 1：
{"action": "get_weather"}

ProtocolError：
缺少 arguments 字段

Format Retry 2：
{"action": "get_weather",
 "arguments": {"city": "北京"}}

Tool Retry 1：
模拟天气服务暂时不可用

Tool Retry 2：
北京当前模拟天气为晴，温度30℃，湿度45%，微风。

Step 2
get_attraction_info(name="故宫")
→ 故宫开放，成人票价60元

Step 3
calculator(operation="multiply", a=60, b=2)
→ 120

Step 4
finish
```

最终结果：

```python
AgentRunResult(
    success=True,
    message=(
        "北京当前模拟天气为晴，温度30℃；"
        "故宫在模拟数据中处于开放状态，"
        "两张成人票共120元。"
        "建议注意防晒补水。"
        "以上信息来自本地模拟数据。"
    ),
    termination_reason=TerminationReason.SUCCESS,
    steps=4,
)
```

这里的 `steps=4` 表示 Agent 作出了四次决策。Network Retry、Format Retry 和 Tool Retry 都没有被计算为新的 Agent 决策步骤。

## 12.10 失败实验

### 实验一：格式重试耗尽

让模型连续返回：

```text
第一次：天气工具
第二次：{"action": "get_weather"}
第三次：{"action": "weather", "arguments": {}}
```

三次输出都无法成为合法 `AgentAction`。当 `max_format_retries=2` 时，程序返回：

```python
AgentRunResult(
    success=False,
    message="模型输出未通过 Action 协议校验。",
    termination_reason=TerminationReason.PARSE_ERROR,
    steps=1,
    error="未知行动：weather。",
)
```

程序不会猜测 `weather` 等于 `get_weather`，也不会继续执行任何工具。

### 实验二：连续重复 Action

让模型始终输出：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

第一次查询可以成功。第二次仍然产生完全相同的 Action 时，若 `repeated_action_limit=2`，Controller 返回：

```python
AgentRunResult(
    success=False,
    message="Agent 连续生成了相同 Action。",
    termination_reason=(
        TerminationReason.REPEATED_ACTION
    ),
    steps=2,
    error="get_weather:{\"city\":\"北京\"}",
)
```

这说明格式正确和工具成功并不足以证明 Agent 正在取得进展。

### 实验三：模拟预订需要确认

用户要求：

```text
请为两人提交故宫模拟预订。
```

模型生成合法 `submit_reservation` Action，但程序没有提供确认回调。结果为：

```python
AgentRunResult(
    success=False,
    message="模拟预订需要用户明确确认。",
    termination_reason=(
        TerminationReason.CONFIRMATION_REQUIRED
    ),
    steps=1,
)
```

工具不会执行。即使模型在 Reason 中写“用户一定会同意”，也不能越过程序的确认边界。

## 12.11 当前系统快照

完成这一章后，城市旅行助手已经能够：

```text
识别错误发生的大致层级
→ 对模型请求进行有限 Network Retry
→ 对非法 Action 进行有限 Format Retry
→ 对安全且可恢复的工具失败进行 Tool Retry
→ 将其他工具失败作为 Observation 触发 Decision Retry
→ 检测连续重复 Action
→ 限制最大步骤，并在 Step 边界检查软时间预算
→ 在高风险 Action 前要求 Confirmation
→ 统一返回 AgentRunResult
```

当前运行结果能够明确说明：

```text
是否成功
向调用方展示什么
为什么终止
经过了多少个 Agent 决策步骤
最后的简洁错误原因
```

但它仍然不能回答：

```text
每一步模型原始输出是什么
一次决策中发生了几次格式重试
工具实际调用了多少次
哪一项 Observation 导致了下一步 Action
运行结束后怎样完整还原过程
```

这些问题需要把运行中的消息、Action、Observation 和错误保存为结构化状态与轨迹。

## 12.12 本章小结

这一章把城市旅行助手从“能够运行”推进到“能够受控地失败”。

Failure Classification 用于定位错误所在层级；Retry Policy 规定不同失败应当重试什么、最多重试多少次。Network Retry 重复同一次模型请求，Format Retry 让模型重新生成当前 Action，Tool Retry 只重复安全且可能恢复的工具执行，Decision Retry 则把失败作为 Observation 交给 Agent 重新决策。

工具重试必须同时考虑错误的可恢复性和操作的 Idempotency。具有副作用或权限要求的工具还要经过 Confirmation，模型不能自行授权真实执行。无论最终成功、超时、格式失败、重复行动还是等待确认，Controller 都会返回包含 `TerminationReason` 的 `AgentRunResult`。

完成本章后，应当能够回答：

1. 为什么不能为所有异常使用同一种重试？
2. Network Retry、Format Retry、Tool Retry 和 Decision Retry 分别重复什么？
3. `retryable=True` 为什么不能单独证明工具可以安全重试？
4. Confirmation 为什么必须位于 Parser 之后、工具执行之前？
5. `AgentRunResult.success=True` 为什么不等于答案一定正确？

## 习题

**1. 区分四类重试**

分别构造模型超时、非法 JSON、天气工具临时失败和城市不存在四个案例，说明程序应进入哪一种重试路径。

**2. 修改重试上限**

把 `max_network_retries`、`max_format_retries` 和 `max_tool_retries` 都设为 `0`。观察相同故障下模型调用次数、工具调用次数和最终 `TerminationReason` 怎样变化。

**3. 检查幂等性**

新增一个模拟 `send_message` 工具，并设置 `idempotent=False`。让它返回 `retryable=True`，确认程序仍然不会自动重复执行。

**4. 测试重复 Action**

让模型依次输出北京天气、上海天气、北京天气，再与连续两次北京天气进行比较。说明为什么当前实现只检测连续相同 Action。

**5. 测试确认边界**

分别让确认回调返回 `True`、`False` 和不提供回调，观察模拟预订工具是否执行，以及最终返回哪一种 `TerminationReason`。

## 参考资料

1. [Release It! Design and Deploy Production-Ready Software](https://pragprog.com/titles/mnee2/release-it-second-edition/). 2nd Edition. Pragmatic Bookshelf, 2018.
2. [Site Reliability Engineering: How Google Runs Production Systems](https://sre.google/books/). O’Reilly Media, 2016.
3. [Designing Data-Intensive Applications](https://dataintensive.net/). O’Reilly Media, 2017.
4. [HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110). 2022.
