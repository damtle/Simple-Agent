# 第十三章 状态、轨迹与日志

第十二章让城市旅行助手能够区分模型请求失败、Action 格式错误、工具错误、重复行动和权限边界，并根据不同情况进行有限重试或明确终止。无论任务正常完成还是中途停止，程序都会返回一个 `AgentRunResult`：

```python
AgentRunResult(
    success=False,
    message="Agent 连续生成了相同 Action。",
    termination_reason=TerminationReason.REPEATED_ACTION,
    steps=2,
    error='get_weather:{"city":"北京"}',
)
```

这份结果能够说明任务是否成功、程序为什么停止，以及应当向调用方展示什么。但它不能还原运行过程：模型在前两步分别输出了什么、是否发生过格式重试、工具实际执行了几次、哪一项 Observation 没有改变模型的下一步决策，以及终止前 `messages` 中已经保存了哪些信息。

如果这些内容只通过临时 `print()` 输出，程序结束后便很难再次检查；若日志级别发生变化，关键细节也可能不再显示。要让 Agent 的运行过程可被诊断，程序需要在执行时维护明确状态，并把发生过的步骤保存为结构化记录。

本章将把第十二章中分散的消息、计数器、模型尝试、Action、Tool Result、Observation 和终止事件整理起来，让一次运行不再只留下最终答案。

## 13.1 最终结果为什么不能代替运行过程

假设 Agent 正常返回：

```text
北京当前模拟天气为晴，温度30℃；
故宫在模拟数据中处于开放状态，
两张成人票共120元。
```

仅看这段回答，无法判断它是怎样产生的。模型可能依次查询天气、景点信息和票价，也可能没有执行某个必要工具，直接根据上下文补全了结果。即使最终文字恰好正确，执行过程仍可能存在重复调用、无效重试或未经工具验证的事实。

失败结果同样如此。`TerminationReason.MAX_STEPS` 只表示最大步数已经耗尽，却不能说明 Agent 是在两个工具之间来回切换，还是每一步都获得了新信息但始终没有生成 `finish`。

一次 Agent 运行至少需要保存三个层次的信息：

| 层次 | 需要回答的问题 |
|---|---|
| 最终结果 | 任务是否成功，为什么终止，应向调用方返回什么 |
| 当前状态 | 程序运行到第几步，当前上下文和计数器是什么 |
| 执行过程 | 每一步模型尝试、Action、工具结果和 Observation 分别是什么 |

第十二章的 `AgentRunResult` 解决第一层。本章通过 `AgentState`、`StepRecord` 和 Execution Trace 解决后两层。

> 最终结果描述运行的结局，状态描述程序当前在哪里，轨迹描述程序怎样到达这个结局。

## 13.2 State、Trace、Log 与 User Output

状态、轨迹、日志和用户输出都可能包含运行信息，但它们服务于不同对象。

| 对象 | 主要内容 | 主要使用者 | 是否影响后续决策 |
|---|---|---|---:|
| `AgentState` | `messages`、当前步骤、计数器、终止状态和记录列表 | Controller | 是 |
| Execution Trace | 按顺序冻结的 `StepRecord` | 开发者、调试工具 | 通常否 |
| Log | 带有时间、级别和模块名的运行事件 | 开发者、运维系统 | 否 |
| User Output | 最终答案或用户可以理解的失败说明 | 用户或调用方 | 否 |

**AgentState** 是一次运行中的可变状态。`messages` 属于 State，因为模型下一轮会读取它；当前步骤和终止状态也会影响 Controller 是否继续运行。

**Execution Trace** 是已经发生的步骤历史。它保存模型尝试、Action、Tool Result、Observation 和错误，用于解释程序为什么得到当前结果。轨迹不应直接作为下一轮 Prompt，否则开发日志、错误细节和无关字段会污染模型上下文。

**Log** 是程序运行时发出的事件。例如：

```text
2026-07-22 10:18:03 WARNING action_parse_failed step=1 attempt=1
```

日志便于实时观察，但可能被过滤、轮转或发送到不同位置，因此不能成为唯一的结构化运行记录。

**User Output** 是最终面向用户展示的内容。在本书中，它通常来自 `AgentRunResult.message`。用户输出不应包含完整模型原文、异常堆栈、API Key、本机路径或内部 Prompt。

这四者之间没有互相替代关系：

```text
AgentState 负责控制当前运行
Execution Trace 负责保存结构化历史
Log 负责传播运行事件
User Output 负责向用户表达结果
```

## 13.3 Step 与 Attempt

第八章把一次模型决策记为一个 Step。模型生成一个合法 Tool Action，程序执行工具并构造 Observation，这是一项 Step；模型生成合法 `finish`，Controller 返回回答，这同样是一项 Step。

第十二章加入格式重试和网络重试后，一个 Step 可能包含多次模型请求：

```text
Step 1 / Attempt 1：模型请求超时
Step 1 / Attempt 2：返回非法 JSON
Step 1 / Attempt 3：返回合法 get_weather Action
Step 1：执行天气工具并生成 Observation

Step 2 / Attempt 1：返回 finish
```

在本书中：

> **Step 是 Agent 当前的一次决策位置。它最终得到一项通过校验的 Action，或者因为当前决策无法恢复而终止。**

> **Attempt 是同一个 Step 内的一次模型请求尝试。网络失败、格式错误和最终被接受的输出，都分别占用一次 Attempt。**

因此：

```text
Step 数量 ≠ 模型调用次数
```

上面的过程包含两个 Step，却发生了四次模型请求。若把每次格式重试都算成新 Step，`max_steps` 的含义就会改变；若只保存最终一次模型输出，前面的失败又会从轨迹中消失。

Step 用于表示 Agent 做了多少次决策，Attempt 用于表示完成某次决策实际尝试了多少次模型调用。

## 13.4 用 ModelAttemptRecord 和 StepRecord 保存事实

模型每次请求都需要留下一个 `ModelAttemptRecord`：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelAttemptRecord:
    attempt: int
    model_output: str | None
    request_error: str | None = None
    parse_error: str | None = None

    @property
    def accepted(self) -> bool:
        return (
            self.model_output is not None
            and self.request_error is None
            and self.parse_error is None
        )
```

三个典型记录分别为：

```python
ModelAttemptRecord(
    attempt=1,
    model_output=None,
    request_error="模型服务连接超时。",
)
```

```python
ModelAttemptRecord(
    attempt=2,
    model_output='{"action": "get_weather"}',
    parse_error="Action 缺少字段：arguments。",
)
```

```python
ModelAttemptRecord(
    attempt=3,
    model_output=(
        '{"action": "get_weather", '
        '"arguments": {"city": "北京"}}'
    ),
)
```

第一项记录模型请求失败，没有取得输出；第二项取得了文本，但 Parser 拒绝；第三项没有请求错误或解析错误，因此代表被接受的模型输出。

一个 Step 需要保存本步骤的全部模型尝试，以及最终发生的 Action 和工具反馈：

```python
@dataclass(frozen=True)
class StepRecord:
    step: int
    model_attempts: tuple[ModelAttemptRecord, ...]
    action: AgentAction | None
    tool_results: tuple[ToolExecutionResult, ...]
    observation: str | None
    termination_reason: TerminationReason | None = None
    error: str | None = None
```

各字段含义如下：

| 字段 | 含义 |
|---|---|
| `step` | Agent 决策步骤编号 |
| `model_attempts` | 当前 Step 中发生的全部模型请求 |
| `action` | 最终通过校验的 `AgentAction`；未得到合法 Action 时为 `None` |
| `tool_results` | 当前 Action 的全部工具执行结果，包括允许的 Tool Retry |
| `observation` | 最终加入模型上下文的 Observation |
| `termination_reason` | 当前 Step 是否直接导致运行终止 |
| `error` | 当前 Step 最终无法继续时的简洁错误原因 |

`tool_results` 使用元组保存同一 Action 的工具执行过程。例如天气工具第一次临时失败、第二次成功时，可以记录：

```python
tool_results=(
    ToolExecutionResult(
        success=False,
        content="模拟天气服务暂时不可用。",
        error_type="temporary_unavailable",
        retryable=True,
    ),
    ToolExecutionResult(
        success=True,
        content=(
            "北京当前模拟天气为晴，"
            "温度30℃，湿度45%，微风。"
        ),
    ),
)
```

Observation 只使用程序最终决定反馈给模型的结果，但轨迹保留本步骤发生过的全部工具结果。这样可以区分“第一次就成功”和“经过一次安全重试后成功”。

### 为什么记录使用不可变数据

`ModelAttemptRecord` 和 `StepRecord` 表示已经发生的历史，因此使用 `frozen=True`。记录加入轨迹后，后续代码不应把“第 1 步当时发生了什么”改写成另一种结果。

不过，`frozen=True` 只能防止字段被重新赋值，不能自动冻结 `AgentAction.arguments` 中的字典。写入轨迹前应复制可变数据：

```python
from copy import deepcopy


def snapshot_action(
    action: AgentAction,
) -> AgentAction:
    return AgentAction(
        name=action.name,
        arguments=deepcopy(action.arguments),
    )
```

这样，即使后续代码修改原始 `arguments`，已经保存的历史也不会发生变化。

## 13.5 用 AgentState 集中保存当前运行

前面的 Agent Loop 使用多个局部变量保存运行信息：

```python
messages = [...]
step = 0
finished = False
llm_calls = 0
tool_calls = 0
```

随着重试、终止和轨迹记录加入，这些变量会分散在不同函数中。程序可能更新了工具调用次数，却忘记更新终止状态；也可能返回了结果，却没有把最后一条步骤记录写入列表。

可以把当前运行信息集中到 `AgentState`：

```python
from dataclasses import dataclass, field


@dataclass
class AgentState:
    messages: list[dict[str, str]]
    step: int = 0
    finished: bool = False
    records: list[StepRecord] = field(
        default_factory=list
    )
    llm_calls: int = 0
    tool_calls: int = 0
    request_failures: int = 0
    parse_failures: int = 0
    tool_failures: int = 0
    termination_reason: TerminationReason | None = None
```

字段职责如下：

| 字段 | 记录内容 |
|---|---|
| `messages` | 当前模型上下文 |
| `step` | 已经进入的最新决策步骤 |
| `finished` | Controller 是否已经停止 |
| `records` | 已完成的 `StepRecord` |
| `llm_calls` | 实际模型请求次数，包括网络与格式重试 |
| `tool_calls` | 实际工具执行次数，包括 Tool Retry |
| `request_failures` | 模型请求层失败次数 |
| `parse_failures` | Parser 拒绝模型输出的次数 |
| `tool_failures` | 工具返回失败结果的次数 |
| `termination_reason` | 当前运行的最终终止原因 |

`finished=True` 只表示 Controller 已经停止，不表示任务成功。因为用户拒绝、最大步数和格式重试耗尽而结束时，`finished` 同样应为 `True`。运行是否成功仍由第十二章的 `AgentRunResult.success` 表达。

`AgentState` 在执行期间需要不断更新，因此不使用 `frozen=True`。不过，状态应由 Controller 统一维护。Parser 只返回解析结果，工具只返回 `ToolExecutionResult`，日志函数只读取并报告事件，不应随意修改状态。

### 为什么要使用 default_factory

下面的写法不能用于可变默认值：

```python
@dataclass
class AgentState:
    messages: list[dict[str, str]] = []
    records: list[StepRecord] = []
```

多个实例可能意外共享同一个列表。正确做法是：

```python
messages: list[dict[str, str]] = field(
    default_factory=list
)
records: list[StepRecord] = field(
    default_factory=list
)
```

创建初始状态时，再加入本次任务的消息：

```python
def create_initial_state(
    system_prompt: str,
    user_task: str,
) -> AgentState:
    return AgentState(
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_task,
            },
        ]
    )
```

每次运行都创建新的 `AgentState`。不同任务之间不应因为复用列表而共享消息和轨迹。

## 13.6 Execution Trace：从可变状态得到历史快照

运行过程中，`state.records` 会不断增长；程序结束后，我们需要一份可以稳定读取的执行历史。这份按顺序保存的步骤记录称为 **Execution Trace（执行轨迹）**。

在本书中：

> **Execution Trace 是一次 Agent 运行中按决策顺序排列的 `StepRecord` 集合，用于还原运行过程怎样到达最终结局。**

可以定义一个独立快照：

```python
@dataclass(frozen=True)
class ExecutionTrace:
    records: tuple[StepRecord, ...]
    steps: int
    termination_reason: TerminationReason | None
```

从 State 创建 Trace：

```python
def build_execution_trace(
    state: AgentState,
) -> ExecutionTrace:
    return ExecutionTrace(
        records=tuple(state.records),
        steps=state.step,
        termination_reason=state.termination_reason,
    )
```

State 与 Trace 的关系是：

```text
运行中：Controller 持续修改 AgentState
运行后：程序从 AgentState 创建 Execution Trace
```

二者保存的内容存在重叠，但用途不同。State 服务于当前运行，Trace 服务于运行后的检查。

### Trace 与 messages 的区别

`messages` 和 Trace 都按照顺序增长，但它们不是同一种历史。

| 对比维度 | `messages` | Execution Trace |
|---|---|---|
| 主要目的 | 为下一次模型调用提供上下文 | 调试和还原程序过程 |
| 数据形式 | `system`、`user`、`assistant` 消息 | `StepRecord` |
| 网络失败 | 通常不会进入正式上下文 | 应当记录 |
| Parser 失败 | 只在格式修复上下文中临时出现 | 应完整保存 |
| Tool Retry | 不一定逐次进入上下文 | 每次结果都可保存 |
| 是否发送给模型 | 是 | 否 |

不能用 Trace 直接替换 `messages`，因为模型需要的是经过选择的对话上下文；也不能只保存 `messages`，因为它无法完整表达底层请求失败、解析失败和工具重试。

## 13.7 在 Agent Loop 中写入状态和轨迹

加入 `AgentState` 后，Controller 不再只依赖局部变量。一个 Step 的记录过程可以分为四个阶段。

**第一阶段：进入新的 Step。**

```python
state.step = step
model_attempts: list[ModelAttemptRecord] = []
tool_results: list[ToolExecutionResult] = []
```

**第二阶段：记录每一次模型请求。**

模型请求失败时：

```python
state.llm_calls += 1
state.request_failures += 1

model_attempts.append(
    ModelAttemptRecord(
        attempt=attempt,
        model_output=None,
        request_error=str(error),
    )
)
```

模型返回文本但 Parser 拒绝时：

```python
state.llm_calls += 1
state.parse_failures += 1

model_attempts.append(
    ModelAttemptRecord(
        attempt=attempt,
        model_output=model_output,
        parse_error=str(error),
    )
)
```

得到合法 Action 时：

```python
state.llm_calls += 1

model_attempts.append(
    ModelAttemptRecord(
        attempt=attempt,
        model_output=model_output,
    )
)
```

**第三阶段：记录工具执行与 Observation。**

每次执行工具都更新计数并保存结果：

```python
state.tool_calls += 1
tool_result = execute_tool(...)

if not tool_result.success:
    state.tool_failures += 1

tool_results.append(tool_result)
```

工具过程结束后，程序根据最终结果构造 Observation，并把规范 Action 与 Observation 加入 `state.messages`。

**第四阶段：完成当前 StepRecord。**

```python
record = StepRecord(
    step=step,
    model_attempts=tuple(model_attempts),
    action=snapshot_action(action),
    tool_results=tuple(tool_results),
    observation=observation,
)

state.records.append(record)
```

推荐先使用局部列表收集当前 Step 的数据，等步骤到达明确边界后，再一次性创建不可变 `StepRecord`。不要把一个半完成的可变对象提前放进 `state.records`，再让多个函数不断修改它。

### 记录失败步骤

格式重试全部耗尽时，当前 Step 仍然必须进入轨迹：

```python
state.records.append(
    StepRecord(
        step=step,
        model_attempts=tuple(model_attempts),
        action=None,
        tool_results=(),
        observation=None,
        termination_reason=(
            TerminationReason.PARSE_ERROR
        ),
        error=str(error),
    )
)
```

若只记录成功步骤，Trace 会显示程序在上一步之后突然终止，却无法解释模型究竟返回了哪些非法内容。

重复 Action 在工具执行前触发时，也应保存当前合法 Action：

```python
state.records.append(
    StepRecord(
        step=step,
        model_attempts=tuple(model_attempts),
        action=snapshot_action(action),
        tool_results=(),
        observation=None,
        termination_reason=(
            TerminationReason.REPEATED_ACTION
        ),
        error="连续生成相同 Action。",
    )
)
```

这能清楚证明：当前失败发生在决策控制层，而不是工具执行层。

## 13.8 终止事件怎样进入状态与轨迹

第十二章已经定义多个 `TerminationReason`。本章需要保证所有返回路径都先更新状态，再构造最终结果。

可以集中处理：

```python
def finish_state(
    state: AgentState,
    reason: TerminationReason,
) -> None:
    state.finished = True
    state.termination_reason = reason
```

正常 `finish`：

```python
finish_state(
    state,
    TerminationReason.SUCCESS,
)
```

达到最大步数：

```python
finish_state(
    state,
    TerminationReason.MAX_STEPS,
)
```

用户拒绝高风险工具：

```python
finish_state(
    state,
    TerminationReason.USER_REJECTED,
)
```

不是所有终止原因都一定对应新的 StepRecord。模型生成合法 `finish` 或重复 Action 时，终止发生在某个 Step 内，可以写入该步骤；Step 边界软时间预算可能在新 Step 开始前触发，最大步数则发生在循环结束后。无论是否产生新的步骤记录，最终原因都必须写入 `AgentState.termination_reason`，并进入 Execution Trace 的顶层字段。

推荐的返回顺序是：

```text
完成当前 StepRecord
→ 更新 AgentState 终止字段
→ 创建 AgentRunResult
→ 创建 Execution Trace
→ 返回
```

这样最终结果、状态和轨迹不会出现互相矛盾的结局。

## 13.9 使用 logging 传播运行事件

结构化状态能够保存运行事实，但开发者还需要在程序运行时看到关键事件。Python 标准库提供了 `logging`。

每个模块只创建自己的 logger：

```python
import logging


logger = logging.getLogger(__name__)
```

日志配置由程序入口统一完成。`logging_config.py` 可以写成：

```python
import logging


def configure_logging(
    level: str = "INFO",
) -> None:
    numeric_level = getattr(
        logging,
        level.upper(),
        None,
    )

    if not isinstance(numeric_level, int):
        raise ValueError(
            f"未知日志级别：{level!r}。"
        )

    logging.basicConfig(
        level=numeric_level,
        format=(
            "%(asctime)s "
            "%(levelname)s "
            "%(name)s "
            "%(message)s"
        ),
    )
```

Controller 中记录事件：

```python
logger.info(
    "agent_started task_length=%s",
    len(user_task),
)

logger.info(
    "agent_step_started step=%s",
    step,
)

logger.warning(
    "action_parse_failed "
    "step=%s attempt=%s error=%s",
    step,
    attempt,
    error,
)

logger.info(
    "tool_completed "
    "step=%s tool=%s success=%s",
    step,
    action.name,
    tool_result.success,
)

logger.info(
    "agent_finished "
    "success=%s reason=%s steps=%s",
    result.success,
    result.termination_reason.value,
    result.steps,
)
```

日志调用使用占位符，而不是提前拼接完整字符串。这样只有当对应日志级别启用时，日志系统才需要完成最终格式化。

### 日志级别

| 级别 | 本章中的典型用途 |
|---|---|
| `DEBUG` | Attempt 编号、Action 指纹、计数器变化 |
| `INFO` | Agent 开始、步骤完成、工具成功、正常终止 |
| `WARNING` | 可恢复的请求失败、Parser 失败、工具临时失败 |
| `ERROR` | 重试耗尽或不可恢复的预期运行失败 |
| `EXCEPTION` | 捕获到意外程序异常并需要记录堆栈 |

第一次格式错误仍有重试机会，因此属于 `WARNING`；格式重试全部耗尽并导致终止时，才记录为 `ERROR`。

日志只能观察行为，不能改变行为。下面的写法是错误的：

```python
if logger.isEnabledFor(logging.DEBUG):
    state.tool_calls += 1
```

关闭 DEBUG 后，工具调用计数不应改变。状态更新必须独立于日志级别。

## 13.10 日志、轨迹和用户输出不能混在一起

同一次工具失败可以有三种表达。

**User Output**

```text
当前模拟数据中没有成都天气，因此无法完成查询。
```

**Log**

```text
WARNING tool_failed step=2 tool=get_weather error_type=not_found
```

**StepRecord**

```python
StepRecord(
    step=2,
    model_attempts=(...),
    action=AgentAction(
        name="get_weather",
        arguments={"city": "成都"},
    ),
    tool_results=(
        ToolExecutionResult(
            success=False,
            content=(
                "没有找到城市“成都”的"
                "模拟天气数据。"
            ),
            error_type="not_found",
            retryable=False,
        ),
    ),
    observation=(
        "Observation:\n"
        "工具名称：get_weather\n"
        "执行状态：失败\n"
        "错误类型：not_found\n"
        "工具结果：没有找到城市“成都”的"
        "模拟天气数据。"
    ),
)
```

三者描述的是同一事件，却不能共用同一份文本。

用户输出应避免暴露技术实现；日志需要紧凑字段，便于定位事件；StepRecord 则要保存程序可以再次读取的结构化事实。日志可能因级别被过滤，不能作为唯一轨迹；Trace 也不应直接打印给普通用户。

在本书中：

> **User Output 是 Agent 面向用户或调用方返回的最终答案或可理解失败说明。**

它与开发者调试信息之间应保持明确边界。

## 13.11 展示并保存 Execution Trace

开发阶段可以把 Trace 以紧凑形式打印出来：

```python
def print_trace(
    trace: ExecutionTrace,
) -> None:
    for record in trace.records:
        print(f"Step {record.step}")

        for attempt in record.model_attempts:
            if attempt.request_error is not None:
                status = "request_error"
            elif attempt.parse_error is not None:
                status = "parse_error"
            else:
                status = "accepted"

            print(
                "  "
                f"Attempt {attempt.attempt}: "
                f"{status}"
            )

        if record.action is not None:
            print(
                f"  Action: {record.action.name}"
            )
            print(
                "  Arguments: "
                f"{record.action.arguments}"
            )

        for index, result in enumerate(
            record.tool_results,
            start=1,
        ):
            print(
                "  "
                f"Tool Result {index}: "
                f"success={result.success}"
            )

        if record.observation is not None:
            print(
                "  Observation: "
                f"{record.observation}"
            )

        if record.error is not None:
            print(f"  Error: {record.error}")

    reason = trace.termination_reason
    print(
        "Termination: "
        + (
            reason.value
            if reason is not None
            else "running"
        )
    )
```

若需要在程序结束后检查轨迹，可以保存为 JSON。不要直接使用 `str(record)`，因为字符串格式不稳定，也不便于程序读取。

```python
from dataclasses import asdict
import json
from pathlib import Path


def step_record_to_dict(
    record: StepRecord,
) -> dict[str, object]:
    return {
        "step": record.step,
        "model_attempts": [
            asdict(attempt)
            for attempt in record.model_attempts
        ],
        "action": (
            asdict(record.action)
            if record.action is not None
            else None
        ),
        "tool_results": [
            asdict(result)
            for result in record.tool_results
        ],
        "observation": record.observation,
        "termination_reason": (
            record.termination_reason.value
            if record.termination_reason is not None
            else None
        ),
        "error": record.error,
    }


def save_trace(
    trace: ExecutionTrace,
    path: Path,
) -> None:
    payload = {
        "steps": trace.steps,
        "termination_reason": (
            trace.termination_reason.value
            if trace.termination_reason is not None
            else None
        ),
        "records": [
            step_record_to_dict(record)
            for record in trace.records
        ],
    }

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
```

调用：

```python
save_trace(
    trace=trace,
    path=Path("trace.json"),
)
```

轨迹可能包含用户输入、工具参数、模型原始输出和错误信息。真实系统保存前必须建立字段白名单、脱敏规则、访问权限和保留周期。API Key、访问令牌、密码、完整认证请求头和不必要的个人信息不得写入日志或 Trace。

## 13.12 运行主线案例

本章代码目录为：

```text
code/chapter13/
├── state.py
├── trace.py
├── logging_config.py
├── agent.py
└── README.md
```

各文件职责如下：

| 文件 | 职责 |
|---|---|
| `state.py` | 定义 `AgentState` 并创建初始状态 |
| `trace.py` | 定义模型尝试、步骤记录和 Execution Trace，负责展示与保存 |
| `logging_config.py` | 统一配置 Python logging |
| `agent.py` | 在第十二章可靠 Agent Loop 中更新状态并写入轨迹 |
| `README.md` | 说明运行方式、日志级别和轨迹保存位置 |

从项目根目录运行：

```bash
python code/chapter13/agent.py
```

使用任务：

```text
请查询北京的模拟天气和故宫的模拟开放信息，
计算两张成人票的总价，并给出出行建议。
```

为了展示 Attempt，假设第一步第一次输出缺少 `arguments`，第二次才生成合法 Action。一次运行结束后，用户只看到最终回答：

```text
北京当前模拟天气为晴，温度30℃；
故宫在模拟数据中处于开放状态，
成人票价60元，两张票共120元。
建议注意防晒补水。
以上信息来自本地模拟数据。
```

开发者可以查看状态摘要：

```text
finished = True
termination_reason = success
step = 4
llm_calls = 5
tool_calls = 3
request_failures = 0
parse_failures = 1
tool_failures = 0
```

Execution Trace 则显示：

```text
Step 1
  Attempt 1: parse_error
  Attempt 2: accepted
  Action: get_weather
  Tool Result 1: success=True

Step 2
  Attempt 1: accepted
  Action: get_attraction_info
  Tool Result 1: success=True

Step 3
  Attempt 1: accepted
  Action: calculator
  Tool Result 1: success=True

Step 4
  Attempt 1: accepted
  Action: finish

Termination: success
```

这组信息解释了为什么：

```text
steps = 4
llm_calls = 5
```

格式修复增加了模型请求次数，却没有增加 Agent 决策步骤。

## 13.13 失败实验：重复 Action 在哪里终止

让模型连续两次输出：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

设定：

```text
repeated_action_limit = 2
```

第一步会正常执行天气工具并产生 Observation。第二步的 Action 可以通过 Parser，但 Controller 在执行工具前发现它与上一项 Action 完全相同，于是终止运行。

最终结果只能告诉我们：

```text
termination_reason = repeated_action
steps = 2
```

Trace 则能进一步说明：

```text
Step 1
  Attempt 1: accepted
  Action: get_weather({"city": "北京"})
  Tool Result 1: success=True
  Observation: 北京当前模拟天气为晴……

Step 2
  Attempt 1: accepted
  Action: get_weather({"city": "北京"})
  Tool Results: 0
  Observation: None
  Termination: repeated_action
```

从这份记录可以确认：

```text
第二步模型输出格式合法
Parser 没有失败
重复检测发生在工具执行之前
天气工具实际只调用了一次
```

若没有 `StepRecord`，开发者很容易误以为第二次天气查询已经执行，或者把问题归咎于工具层。

还可以制造格式重试耗尽：当前 Step 的所有 `ModelAttemptRecord` 都带有 `parse_error`，`action=None`，`tool_results=()`，并以 `PARSE_ERROR` 终止。两类失败虽然都没有完成任务，但在 Trace 中具有完全不同的结构。

## 13.14 当前系统快照

完成这一章后，城市旅行助手不再只返回一个最终结果。一次运行同时拥有：

```text
AgentRunResult：说明最终结局
AgentState：保存当前消息、步骤和计数器
Execution Trace：保存每一步发生的结构化事实
Log：实时传播运行事件
User Output：向用户展示答案或失败说明
```

当前系统可以回答：

```text
一次任务实际调用了多少次模型
格式重试发生在哪个 Step
工具执行了多少次
某个 Action 是否真正被执行
哪项 Observation 进入了后续上下文
重复行动、解析失败或正常 finish 在哪里发生
最终终止原因是否与过程一致
```

这些信息已经能够帮助开发者还原一次运行，但当前程序仍主要依赖真实模型或人工制造故障。要稳定验证正常路径和每一种失败路径，还需要一种不依赖网络和模型随机性的输入方式，并用自动化测试检查状态与轨迹是否符合预期。

## 13.15 本章小结

这一章为可靠 Agent 加入了状态、轨迹和日志。

`AgentState` 集中保存当前 `messages`、步骤编号、调用计数器、终止状态和步骤记录。Step 表示一次 Agent 决策位置，Attempt 表示同一个 Step 内的一次模型请求。`ModelAttemptRecord` 保存请求错误、模型原始输出和解析错误；`StepRecord` 则把一项决策中的全部模型尝试、Action、工具结果、Observation 和终止信息组织在一起。

多个 `StepRecord` 按顺序组成 Execution Trace。State 在运行过程中可变，Trace 是运行结束后的历史快照；Trace 不等于模型消息，也不等于日志。Log 用于实时传播事件，User Output 用于向用户表达最终结果，两者都不能替代结构化轨迹。

完成本章后，应当能够回答：

1. 为什么 `AgentRunResult` 不能还原完整执行过程？
2. Agent Step 与模型 Attempt 有什么区别？
3. `messages`、`AgentState` 和 Execution Trace 分别服务于谁？
4. 为什么失败步骤也必须写入 `StepRecord`？
5. 为什么日志不能替代 Trace，Trace 也不能直接作为 User Output？

## 习题

**1. 记录模型请求失败**

构造一个 Step：第一次模型请求超时，第二次返回合法 `get_weather` Action。检查两个 `ModelAttemptRecord` 的字段，并确认 `step=1`、`llm_calls=2`。

**2. 记录工具重试**

让天气工具第一次返回 `temporary_unavailable`，第二次成功。确认同一个 `StepRecord.tool_results` 中保存两个结果，而 Agent Step 只增加一次。

**3. 检查状态隔离**

连续创建两个 `AgentState`，只向第一个状态追加消息和记录。确认第二个状态保持不变，并解释 `default_factory` 的作用。

**4. 检查轨迹快照**

将 Action 写入 `StepRecord` 后修改原始 `arguments` 字典，观察轨迹是否变化，再使用 `snapshot_action()` 修复。

**5. 保存并读取 JSON**

把一次正常运行的 Execution Trace 保存为 `trace.json`，重新读取后检查步骤数量、Action 名称、工具执行次数和终止原因。

## 参考资料

1. [dataclasses — Data Classes](https://docs.python.org/3/library/dataclasses.html).
2. [logging — Logging facility for Python](https://docs.python.org/3/library/logging.html).
3. [Logging HOWTO](https://docs.python.org/3/howto/logging.html).
