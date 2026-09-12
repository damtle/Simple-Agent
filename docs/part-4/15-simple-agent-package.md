# 第十五章 从教学脚本到 `simple_agent` 包

第十四章已经为 Parser、工具、Controller、状态隔离和主要失败路径建立了确定性测试。模型输出由 Mock LLM 预先给定，因此修改代码之后，可以快速确认原有行为是否仍然成立。

测试帮助确认“程序是否还保持原有行为”，但并不直接解决代码怎么长期维护的问题。为了让每一章能够独立阅读，前面的 `code/chapter01/` 至 `code/chapter14/` 都保存了一份当时可以运行的教学快照。随着能力逐步增加，`AgentAction`、Parser、工具注册、Observation、重试、状态和 Agent Loop 也在多个目录中重复出现。

这种重复在学习阶段有明确价值。读者打开第六章就能看到 Parser 怎样形成，不需要先理解一个完整框架；打开第八章也能直接观察 Agent Loop 怎样连接已有组件。但当这些职责已经反复出现，并且由第十四章的测试确认了行为边界，继续复制就会带来新的问题：一次 Parser 修复需要同步多个目录，新案例必须重新复制整套循环，不同文件中的状态结构也可能逐渐产生差异。

现在可以进行一次结构调整：保留各章代码作为学习过程的历史快照，同时把已经稳定的公共职责提取到根目录中的 `simple_agent` 包。

## 15.1 从教学重复到工程重复

教学代码与公共代码追求的目标不同。

| 代码位置 | 主要目标 | 是否允许重复 |
|---|---|---:|
| `code/chapter01/`—`code/chapter14/` | 展示一个概念第一次怎样进入系统 | 允许适度重复 |
| `simple_agent/` | 保存当前唯一的公共实现 | 不应存在同一职责的多个版本 |
| `tests/` | 保护公共行为和模块边界 | 测试场景可以重复使用 Fixture |
| `examples/` | 使用公共包构建具体应用 | 不应重新实现核心 Agent Loop |

例如，第六章中的 `parse_action()` 是 Parser 的教学快照。它应继续保留，因为读者需要看到 Parser 当时怎样从简单函数逐步形成。根目录中的 `simple_agent/parser.py` 则是包化后的当前实现；后续应用和根目录测试只依赖这一份公共代码。

这意味着包化不是把所有章节目录改成：

```python
from simple_agent import ...
```

若这样处理，早期章节会失去当时的代码样貌，读者也无法观察结构是怎样逐步形成的。正确关系是：

```text
code/chapter01/ ... code/chapter14/  保存学习快照
simple_agent/       保存公共实现
tests/              验证公共实现
examples/           使用公共实现
```

章节快照与公共包可以暂时包含相似代码，但它们不承担同一种维护承诺。旧章节只在修正文档错误或严重 Bug 时更新；公共包则代表项目当前版本。

## 15.2 Refactoring 与 Package

把代码移动到新目录，并不一定构成有效重构。若移动过程中同时改变 Action Protocol、重试次数、工具错误分类和终止语义，即使新代码更整齐，也无法确认行为变化来自哪一项修改。

在本书中：

> **Refactoring（重构）是在保持外部可观察行为基本不变的前提下，调整代码内部结构、职责和依赖关系。**

这里的“外部可观察行为”包括：

```text
合法 Action 仍然可以被解析
非法 Action 仍然被 Parser 拒绝
Parser 失败不会执行工具
Observation 仍然进入下一轮 messages
格式重试仍然属于同一个 Step
重复 Action 仍然在再次执行工具前终止
成功和失败仍然返回 AgentRunResult
AgentState 与 Execution Trace 仍然记录真实过程
```

第十四章的自动化测试就是判断这些行为是否保持不变的依据。重构时应先移动一个职责，修改相应导入，运行测试，再继续下一项。测试失败时，当前改动范围越小，问题越容易定位。

重构完成后，公共代码将形成一个 Python Package。

> **Package（包）是按照明确目录和模块关系组织、可以被 Python 导入并由安装工具管理的一组代码。**

本章使用的导入包为：

```text
simple_agent
```

### 15.2.1 包化前的接口统一

在正式移动模块之前，本章先统一了若干前期教学快照中尚未完全一致的名称和返回结构。这些调整不是纯粹的文件移动：

| 教学快照 | 公共包 | 原因 |
|---|---|---|
| `FINISHED` | `SUCCESS` | 统一正常终止命名 |
| 单个 `tool_result` | `tool_results` | 保存 Tool Retry 的全部结果 |
| State 中直接读取记录 | 独立 `ExecutionTrace` | 区分当前状态与独立历史快照 |
| 缺少输入终止类型 | `INVALID_INPUT` | 统一所有返回路径 |

统一这些接口后，剩余模块移动才属于行为保持重构。第十四章的测试仍然提供保护网，但它保护的是已经统一后的公共契约，而不是证明所有字段和枚举名称从教学快照到公共包都完全没有变化。

`simple_agent` 包由一个目录和其中的多个模块组成：

```text
simple_agent/
├── __init__.py
├── llm.py
├── action.py
├── parser.py
├── tools.py
├── state.py
└── agent.py
```

包的价值不只是缩短导入路径。它还要求我们明确：哪些职责属于核心运行时，模块之间可以怎样依赖，哪些名称对使用者公开，以及项目怎样被安装到 Python 环境中。

## 15.3 Module Boundary 与 Dependency Direction

把一个长脚本拆成七个文件，只完成了物理分割。若 `parser.py` 可以直接修改 Agent 状态，`tools.py` 又创建模型客户端，所有文件仍然互相了解内部细节，代码只是从一个混乱脚本变成多个混乱模块。

在本书中：

> **Module Boundary（模块边界）是一个模块明确负责的职责，以及它允许其他模块通过哪些数据和函数与自己交互。**

最终模块的边界如下：

| 模块 | 负责 | 不负责 |
|---|---|---|
| `action.py` | 表示、复制和序列化 `AgentAction` | 调用模型、执行工具 |
| `llm.py` | 定义最小模型接口与真实模型适配器 | 读取业务工具、推进 Agent Loop |
| `tools.py` | 定义工具、注册表、参数验证和执行结果 | 决定下一步使用哪个工具 |
| `parser.py` | 解析一次模型输出并校验 Action Protocol | 格式重试、工具执行 |
| `state.py` | 保存结果、状态、步骤记录和轨迹 | 调用模型、修改外部环境 |
| `agent.py` | 编排模型、Parser、工具、状态和终止 | 实现天气、景点或计算器业务 |
| `__init__.py` | 暴露稳定 Public API | 承担实际运行逻辑 |

边界清楚之后，还要规定依赖方向。

> **Dependency Direction（依赖方向）是模块之间允许的引用方向。上层控制模块可以依赖下层数据与能力模块，下层模块不应反向依赖上层控制器。**

本章采用：

```text
__init__.py
├── agent.py
├── llm.py
├── state.py
└── tools.py

agent.py
├── action.py
├── llm.py
├── parser.py
├── tools.py
└── state.py

parser.py → action.py、tools.py
state.py  → action.py、llm.py、tools.py
tools.py  → action.py
```

箭头表示“左侧模块直接导入右侧模块”。这张图不表示运行时调用顺序；更准确的依赖表为：

| 模块 | 可以直接依赖 |
|---|---|
| `action.py` | Python 标准库 |
| `llm.py` | Python 标准库、模型 SDK |
| `tools.py` | `action.py` |
| `parser.py` | `action.py`、`tools.py` |
| `state.py` | `action.py`、`llm.py`、`tools.py` |
| `agent.py` | `action.py`、`llm.py`、`parser.py`、`tools.py`、`state.py` |
| `__init__.py` | 需要公开的包内模块 |

例如，`agent.py` 可以导入 `ToolRegistry`，因为 Agent 需要调用工具；`tools.py` 不应反向导入 `Agent`，因为工具不需要知道循环步数、模型重试或终止状态。

> 依赖应从稳定的数据结构和单项能力流向上层编排，而不是让所有模块彼此调用。

## 15.4 哪些内容进入核心包

前十四章已经出现许多代码，但不是所有内容都应进入 `simple_agent/`。判断标准不是“它是否重要”，而是“它是否属于多个应用都会复用的核心职责”。

| 内容 | 去向 | 原因 |
|---|---|---|
| `AgentAction` 与 Action 序列化 | `action.py` | Parser、重复检测和轨迹都需要 |
| LLM 最小接口与真实适配器 | `llm.py` | Agent 不应绑定某个全局客户端 |
| Tool、ToolRegistry、Tool Result | `tools.py` | 不同应用共享相同注册与执行方式 |
| Action Parser | `parser.py` | 模型文本与程序执行之间的公共边界 |
| State、Trace、Run Result | `state.py` | 所有 Agent 运行都需要统一结果结构 |
| Agent Loop 与重试编排 | `agent.py` | 核心 Controller 职责 |
| 天气、景点、计算器数据 | 应用或示例 | 属于旅行场景，不是通用框架 |
| `.env` 读取 | 应用入口 | 核心包不应在导入时读取本地配置 |
| Logging 配置 | 应用入口 | 包可以记录日志，但不应决定全局格式和级别 |
| Mock LLM | `tests/` | 是测试替代对象，不是运行时依赖 |
| 基础 Metrics 汇总 | 测试或应用层 | 它从状态派生，不属于 Agent Loop 必需能力 |
| Plan-and-Solve 与 Reflection 脚本 | 对应策略或应用层 | 控制结构不同，不应强行塞入一个通用循环 |

第九章中的 ReAct 可以继续复用核心数据结构。`AgentAction` 保留可选的 `reason`，普通模式为 `None`；启用 ReAct Prompt 时，Parser 再要求该字段存在。这样不需要为了多一个可读摘要复制 ToolRegistry、State 和 Agent Loop。

Plan-and-Solve 与 Reflection 的控制流程与普通 Action—Observation Loop 不完全相同。本章不把它们改写成：

```python
if mode == "react":
    ...
elif mode == "plan":
    ...
elif mode == "reflection":
    ...
```

这种大分支会让刚刚拆开的职责重新集中到 `agent.py`。公共包先保存已经稳定的最小循环；其他控制策略可以在应用层组合已有模块。

## 15.5 提取七个模块

本节只展示每个模块最关键的接口。完整实现应放在项目根目录的 `simple_agent/` 中，而不是把所有源码重新拼进正文。

### 15.5.1 `action.py`：稳定的行动对象

`AgentAction` 从第六章开始一直位于模型输出、Parser、工具和轨迹之间，因此最适合首先提取：

```python
# simple_agent/action.py

from copy import deepcopy
from dataclasses import dataclass
import json


@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, object]
    reason: str | None = None


def snapshot_action(
    action: AgentAction,
) -> AgentAction:
    return AgentAction(
        name=action.name,
        arguments=deepcopy(action.arguments),
        reason=action.reason,
    )


def action_to_json(
    action: AgentAction,
) -> str:
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
    )


def action_fingerprint(
    action: AgentAction,
) -> str:
    return action_to_json(
        AgentAction(
            name=action.name,
            arguments=action.arguments,
        )
    )
```

`action_fingerprint()` 有意忽略 `reason`。模型可能用不同措辞解释同一个行动，但真正可能被重复执行的是相同工具和参数。

`AgentAction` 不包含工具执行状态。通过 Parser 只说明行动符合协议，不说明工具一定成功。成功、失败和重试记录仍属于 `ToolExecutionResult` 与 `StepRecord`。

### 15.5.2 `llm.py`：Agent 只依赖最小模型接口

前面的脚本经常直接创建 OpenAI 客户端。公共 Agent 不应在 `run()` 中读取 `.env` 或固定创建某个客户端，而应接收一个能够根据消息生成文本的对象：

```python
# simple_agent/llm.py

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


Message = dict[str, str]


class LLM(Protocol):
    def generate(
        self,
        messages: Sequence[Message],
    ) -> str:
        ...


class LLMRequestError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class OpenAIChatLLM:
    client: Any
    model_id: str
    temperature: float = 0.0

    def generate(
        self,
        messages: Sequence[Message],
    ) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=list(messages),
                temperature=self.temperature,
            )
        except Exception as error:
            raise LLMRequestError(
                f"模型请求失败：{error}",
                retryable=_looks_retryable(error),
            ) from error

        content = response.choices[0].message.content

        if not isinstance(content, str):
            raise LLMRequestError(
                "模型没有返回文本内容。",
                retryable=False,
            )

        text = content.strip()

        if not text:
            raise LLMRequestError(
                "模型返回了空文本。",
                retryable=False,
            )

        return text
```

`LLM` 只描述 Agent 需要的行为。真实适配器和第十四章的 Mock LLM 都可以提供 `generate(messages) -> str`，因此 Agent 不需要知道当前对象是否访问网络。当前适配器使用 `Any` 接收兼容的客户端，并在适配器边界把 SDK 异常统一转换为 `LLMRequestError`。

底层 SDK 异常怎样映射为可重试或不可重试的 `LLMRequestError`，应由真实适配器完成。Agent 只读取统一错误类型和 `retryable` 属性。

### 15.5.3 `tools.py`：工具定义、注册与执行

公共工具层需要保留工具说明、参数验证、重试属性和确认属性：

```python
# simple_agent/tools.py

from collections.abc import Callable
from dataclasses import dataclass

from .action import AgentAction


ToolFunction = Callable[..., object]
ArgumentValidator = Callable[
    [dict[str, object]],
    None,
]


@dataclass(frozen=True)
class ToolExecutionResult:
    success: bool
    content: str
    error_type: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, str]
    function: ToolFunction
    validator: ArgumentValidator | None = None
    retryable: bool = False
    requires_confirmation: bool = False
```

注册表由每个 Agent 实例单独创建：

```python
class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        tool: Tool,
    ) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"工具已经注册：{tool.name}"
            )

        self._tools[tool.name] = tool

    def get(
        self,
        name: str,
    ) -> Tool:
        try:
            return self._tools[name]
        except KeyError as error:
            raise ValueError(
                f"工具不存在：{name}"
            ) from error

    def names(self) -> set[str]:
        return set(self._tools)

    def validate(
        self,
        action: AgentAction,
    ) -> None:
        tool = self.get(action.name)

        if tool.validator is not None:
            tool.validator(action.arguments)
```

注册表还可以提供：

```text
render_descriptions()
execute(action)
requires_confirmation(action)
```

但它不决定下一步 Action。ToolRegistry 管理“当前有哪些能力以及怎样执行”，LLM 与 Agent Loop 决定“当前应使用哪项能力”。

注册表不能是模块级全局单例。否则两个 Agent、两个测试甚至两次运行都可能意外共享工具集合。

这里的 `Tool.retryable` 表示工具是否允许自动重试，`ToolExecutionResult.retryable` 表示当前错误是否可能恢复。两者属于不同层次，必须同时满足。

当前 `ToolRegistry.execute()` 仍会把工具函数抛出的 `TypeError` 和 `ValueError` 转换为工具失败结果，可能混淆业务错误和程序缺陷；这一点是教学包的已知限制。

### 15.5.4 `parser.py`：只处理一次模型输出

Parser 接收模型文本和当前工具注册表：

```python
# simple_agent/parser.py

def parse_action(
    model_output: str,
    tools: ToolRegistry,
    *,
    require_reason: bool = False,
) -> AgentAction:
    text = normalize_model_output(model_output)
    data = parse_json_object(text)

    reason = validate_reason(
        data=data,
        required=require_reason,
    )
    name, arguments = validate_action_fields(data)

    action = AgentAction(
        name=name,
        arguments=arguments,
        reason=reason,
    )

    if action.name == "finish":
        validate_finish(action)
    else:
        tools.validate(action)

    return action
```

Parser 负责回答：

```text
这段输出是否符合当前 Action Protocol？
```

它不负责回答：

```text
输出不合法时是否还要调用一次模型？
```

是否进行 Format Retry、最多允许多少次，以及怎样构造协议修复消息，仍由 `Agent` 根据第十二章的策略决定。

### 15.5.5 `state.py`：统一运行数据结构

第十二至十四章形成的结构化结果集中到 `state.py`：

```python
# simple_agent/state.py

from dataclasses import dataclass, field
from enum import Enum

from .action import AgentAction
from .llm import Message
from .tools import ToolExecutionResult


class TerminationReason(str, Enum):
    SUCCESS = "success"
    INVALID_INPUT = "invalid_input"
    LLM_ERROR = "llm_error"
    PARSE_ERROR = "parse_error"
    TOOL_ERROR = "tool_error"
    REPEATED_ACTION = "repeated_action"
    MAX_STEPS = "max_steps"
    TIMEOUT = "timeout"
    CONFIRMATION_REQUIRED = (
        "confirmation_required"
    )
    USER_REJECTED = "user_rejected"
```

模型尝试和步骤记录保持第十三章的含义：

```python
@dataclass(frozen=True)
class ModelAttemptRecord:
    attempt: int
    model_output: str | None
    request_error: str | None = None
    parse_error: str | None = None


@dataclass(frozen=True)
class StepRecord:
    step: int
    model_attempts: tuple[
        ModelAttemptRecord,
        ...,
    ]
    action: AgentAction | None
    tool_results: tuple[
        ToolExecutionResult,
        ...,
    ]
    observation: str | None
    termination_reason: (
        TerminationReason | None
    ) = None
    error: str | None = None
```

当前状态、最终结果和轨迹分别表达不同层次：

```python
@dataclass
class AgentState:
    messages: list[Message]
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
    termination_reason: (
        TerminationReason | None
    ) = None


@dataclass(frozen=True)
class AgentRunResult:
    success: bool
    message: str
    termination_reason: TerminationReason
    steps: int
    error: str | None = None


@dataclass(frozen=True)
class ExecutionTrace:
    records: tuple[StepRecord, ...]
    steps: int
    termination_reason: (
        TerminationReason | None
    )


@dataclass(frozen=True)
class AgentExecution:
    result: AgentRunResult
    state: AgentState
    trace: ExecutionTrace

    @property
    def message(self) -> str:
        return self.result.message
```

`Agent.run()` 不只返回字符串，因为字符串无法表达运行是否成功、为什么终止以及发生了哪些步骤。`AgentExecution.message` 提供简洁访问方式，同时保留完整结构。

### 15.5.6 `agent.py`：只负责编排

`agent.py` 连接已经提取的组件。它可以继续使用第十二章的 `RetryPolicy`：

```python
# simple_agent/agent.py

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

当前 `timeout_seconds` 只在 Agent Step 边界检查，是软时间预算：它可以阻止超预算的下一步开始，但不能中断正在进行的同步模型请求或工具调用。

`Agent` 的构造函数接收依赖，而不是在内部创建它们：

```python
class Agent:
    def __init__(
        self,
        *,
        llm: LLM,
        tools: ToolRegistry,
        system_prompt: str,
        policy: RetryPolicy | None = None,
        require_reason: bool = False,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.policy = policy or RetryPolicy()
        self.require_reason = require_reason
```

`run()` 仍然沿用前面已经验证的控制顺序：

```text
创建全新 AgentState
→ 请求并解析当前 Action
→ 处理网络与格式重试
→ 检查重复 Action 和终止条件
→ 执行工具并处理安全重试
→ 构造 Observation
→ 更新 messages 与 StepRecord
→ 返回 AgentExecution
```

正文不再拼接完整 Controller。完整实现位于：

```text
simple_agent/agent.py
```

`Agent` 可以使用 `_request_valid_action()`、`_execute_tool_with_retry()` 和 `_finish_failure()` 等私有辅助方法，降低 `run()` 的阅读负担。但这些内部函数不需要成为 Public API。

如果 `agent.py` 中出现下面的内容，说明边界再次被破坏：

```python
WEATHER_DATA = {...}
load_dotenv()
client = OpenAI(...)
def calculator(...): ...
```

旅行数据和具体工具属于应用；环境变量和客户端创建属于入口；Agent 只编排已经注入的依赖。


### 输入边界与历史快照

公共 Parser 的 `load_json_object()` 在字段校验之前限制输出为 65,536 个字符、最多 64 层嵌套和 128 位整数，并拒绝非有限数字。Action 与最终应用的 Critique 共用这一步解析，随后分别检查各自字段。教学代码不是通用的大型 JSON 处理器；超出范围的模型输出应按协议错误处理。

工具返回 `None` 或空白文本时，执行结果为 `empty_result`，不能作为成功证据；数值零仍是有效结果。导出 Trace 时深拷贝 State 的记录，避免两者共享参数字典。`frozen=True` 只禁止字段重新赋值，快照内部的字典仍可修改；应用应把 Trace 当作只读记录使用，这里不承诺递归不可变的数据结构。

## 15.6 用 `__init__.py` 建立 Public API

包内模块拆分之后，应用当然可以这样导入：

```python
from simple_agent.agent import Agent
from simple_agent.tools import Tool
from simple_agent.tools import ToolRegistry
```

但使用者不应为了完成最常见操作，记住所有内部文件位置。可以在 `simple_agent/__init__.py` 中集中暴露稳定名称：

```python
from .agent import Agent, RetryPolicy
from .llm import (
    LLM,
    LLMRequestError,
    OpenAIChatLLM,
)
from .state import (
    AgentExecution,
    AgentRunResult,
    TerminationReason,
)
from .tools import (
    Tool,
    ToolExecutionResult,
    ToolRegistry,
)


__all__ = [
    "Agent",
    "AgentExecution",
    "AgentRunResult",
    "LLM",
    "LLMRequestError",
    "OpenAIChatLLM",
    "RetryPolicy",
    "TerminationReason",
    "Tool",
    "ToolExecutionResult",
    "ToolRegistry",
]
```

在本书中：

> **Public API（公共接口）是包明确提供给应用代码使用，并承诺保持相对稳定的一组名称、参数和返回结构。**

应用可以写成：

```python
from simple_agent import (
    Agent,
    OpenAIChatLLM,
    RetryPolicy,
    Tool,
    ToolRegistry,
)
```

`normalize_model_output()`、`action_fingerprint()` 和 `_request_valid_action()` 等辅助函数没有进入 `__all__`。它们仍可在包内部使用，但不属于第一版顶层承诺。

Public API 越大，后续修改成本越高。判断一个名称是否需要从顶层导出，可以问：

```text
普通应用是否经常直接使用它？
它的职责是否已经稳定？
隐藏它是否会迫使用户复制核心逻辑？
```

只有答案明确时，才把名称加入顶层 API。

## 15.7 Distribution Name、Import Package Name 与 `pyproject.toml`

Python 项目中经常同时出现两个相近名称。

| 名称 | 本项目 | 出现位置 |
|---|---|---|
| Distribution Name（分发名称） | `simple-agent` | 安装元数据、构建产物、依赖声明 |
| Import Package Name（导入包名） | `simple_agent` | Python `import` 语句 |

在本书中：

> **Distribution Name 是安装工具和项目元数据识别的项目名称。**

> **Import Package Name 是 Python 代码在 `import` 或 `from ... import ...` 中使用的名称。**

连字符不能直接用于普通 Python 导入，因此：

```bash
python -m pip install simple-agent
```

与：

```python
import simple_agent
```

可以指向同一个项目。本书只进行本地安装，并不表示该分发名称已经在公共包索引中可用。

项目根目录创建 `pyproject.toml`：

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "simple-agent"
version = "1.0.0"
description = "A minimal educational LLM agent package"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "openai>=1.0"
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "python-dotenv>=1.0"
]

[tool.setuptools.packages.find]
include = ["simple_agent*"]
```

其中：

| 配置 | 作用 |
|---|---|
| `[build-system]` | 指定构建后端及构建所需工具 |
| `[project]` | 保存分发名称、版本、Python 要求和运行依赖 |
| `[project.optional-dependencies]` | 保存测试与示例使用的可选依赖 |
| `[tool.setuptools.packages.find]` | 告诉 setuptools 查找 `simple_agent` 包 |

核心包依赖 `openai`，因为其中提供了 `OpenAIChatLLM`。`python-dotenv` 只用于示例读取 `.env`，不应由包导入时自动执行。

本章暂时不加入发布账号、上传配置、命令行入口和复杂分类信息。当前目标是使项目可以在本地被正常安装、导入和测试。

## 15.8 Editable Install：让工作区源码成为当前安装

项目根目录执行：

```bash
python -m pip install -e ".[dev]"
```

`-e` 表示 **Editable Install（可编辑安装）**。

> **Editable Install 是一种开发安装方式。项目依赖和分发元数据会进入当前环境，而导入包继续指向工作区中的源码。**

因此，修改：

```text
simple_agent/parser.py
```

之后，不需要每次重新复制一份包文件，测试和示例会继续使用当前工作区实现。

安装完成后，可以在项目根目录之外验证：

```bash
python -c "import simple_agent; print(simple_agent.Agent)"
```

随后运行测试：

```bash
python -m pytest -q
```

不推荐在示例中加入：

```python
import sys
sys.path.append("..")
```

这种方式依赖当前启动目录，可能让错误的包结构暂时“看起来可以导入”，也无法验证 `pyproject.toml` 是否正确。Editable Install 让测试和示例通过正常安装机制找到包。

普通安装与可编辑安装解决不同场景：

```bash
python -m pip install .
```

适合验证正常构建与安装；

```bash
python -m pip install -e ".[dev]"
```

适合持续修改源码的开发过程。

## 15.9 在测试保护下逐步迁移

第十四章的测试位于：

```text
code/chapter14/tests/
```

包化后，稳定测试迁移到项目根目录：

```text
tests/
├── conftest.py
├── fakes.py
├── test_parser.py
├── test_tools.py
├── test_agent.py
└── test_state.py
```

`MockLLM` 可以移动到 `tests/fakes.py`，或由 Fixture 在 `conftest.py` 中创建。它不进入 `simple_agent/`，因为生产代码并不需要预设模型输出。

测试导入从章节局部模块：

```python
from main import run_agent
from parser import parse_action
```

改成公共包：

```python
from simple_agent import (
    Agent,
    TerminationReason,
    Tool,
    ToolRegistry,
)

from simple_agent.parser import (
    ActionParseError,
    parse_action,
)
```

应用测试优先使用顶层 Public API；Parser 单元测试可以从具体模块导入 Parser 边界。

推荐迁移顺序如下：

| 顺序 | 操作 | 完成标准 |
|---:|---|---|
| 1 | 复制第十四章测试到根目录 | 旧实现仍可通过测试 |
| 2 | 提取 `action.py` | Action 与快照测试通过 |
| 3 | 提取 `tools.py` | 工具和注册表测试通过 |
| 4 | 提取 `parser.py` | Parser 测试切换后通过 |
| 5 | 提取 `state.py` | State 与 Trace 测试通过 |
| 6 | 提取 `llm.py` | Mock 和真实适配器可注入 |
| 7 | 提取 `agent.py` | Controller 全部测试通过 |
| 8 | 配置 `__init__.py` | 应用只依赖顶层 API |
| 9 | 添加 `pyproject.toml` | 正常与 Editable Install 均成功 |
| 10 | 删除临时重复公共实现 | 测试仍然全部通过 |

迁移遵守两个原则。

**先复制，再切换。** 先把某项职责复制到新模块，让测试改用新导入并比较行为；确认无误后，再删除临时重复代码。不要一次剪切所有文件。

**一次只改变一种关系。** 一个提交可以只提取 `AgentAction`，或只引入 `ToolRegistry`。不要同时修改目录、协议、异常类型和算法行为。

重构后的测试至少继续保护：

```text
Step 与 Attempt 仍然分开统计
Parser 失败不会执行工具
Observation 仍然进入下一轮请求
ToolRegistry 不允许重复名称
不同注册表互不共享工具
不同 run() 调用使用全新 AgentState
高风险工具未确认时不会执行
重复 Action 在再次执行工具前终止
失败步骤仍然进入 Execution Trace
结果与状态保存相同 TerminationReason
```

包化还应增加隔离测试：

```python
def test_registries_are_independent() -> None:
    first = ToolRegistry()
    second = ToolRegistry()

    first.register(calculator_tool)

    assert "calculator" in first.names()
    assert "calculator" not in second.names()
```

```python
def test_agent_runs_use_fresh_state() -> None:
    first = agent.run("任务一")
    second = agent.run("任务二")

    assert first.state is not second.state
    assert (
        first.state.messages
        is not second.state.messages
    )
```

这两项测试防止公共包重新引入全局 ToolRegistry 或共享可变状态。

## 15.10 使用 Mock LLM 验证包级入口

本章不构建新的业务案例，只验证公共包能够通过同一入口连接 LLM、ToolRegistry 和 Agent。

测试中准备一个最小工具：

```python
def echo(text: str) -> str:
    return text


def validate_echo(
    arguments: dict[str, object],
) -> None:
    if set(arguments) != {"text"}:
        raise ValueError(
            "echo 只接受 text 参数。"
        )

    if not isinstance(
        arguments["text"],
        str,
    ):
        raise ValueError(
            "text 必须是字符串。"
        )
```

注册工具：

```python
tools = ToolRegistry()

tools.register(
    Tool(
        name="echo",
        description="原样返回一段文本。",
        parameters={"text": "需要返回的文本"},
        function=echo,
        validator=validate_echo,
    )
)
```

使用第十四章的 Mock LLM：

```python
llm = MockLLM(
    outputs=[
        (
            '{"action":"echo",'
            '"arguments":{"text":"hello"}}'
        ),
        (
            '{"action":"finish",'
            '"arguments":{"answer":"hello"}}'
        ),
    ]
)
```

创建 Agent：

```python
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    policy=RetryPolicy(
        max_steps=4,
    ),
)

execution = agent.run(
    "请返回 hello。"
)
```

检查结果：

```python
assert execution.result.success is True
assert execution.message == "hello"
assert execution.state.llm_calls == 2
assert execution.state.tool_calls == 1
assert len(execution.trace.records) == 2
```

这段代码验证了 Public API 和安装后的模块协作，不承担旅行助手业务。包的完整旅行应用将在独立示例中使用同一入口。

## 15.11 失败实验：制造循环导入

暂时在 `simple_agent/tools.py` 中加入：

```python
from .agent import Agent
```

而 `agent.py` 已经存在：

```python
from .tools import ToolRegistry
```

此时形成：

```text
agent.py → tools.py → agent.py
```

运行导入：

```bash
python -c "from simple_agent import Agent"
```

可能出现“无法从部分初始化的模块导入名称”之类的错误。原因不是 `Agent` 类不存在，而是 Python 正在加载 `agent.py` 时进入 `tools.py`，随后 `tools.py` 又试图读取尚未完成初始化的 `agent.py`。

修复方法不是改变导入顺序，而是恢复模块边界：Tool 不需要知道 Agent，因此删除 `tools.py` 对 `agent.py` 的依赖。若两个低层模块确实共享一个数据结构，应把该结构移动到更低层的独立模块，而不是让它们互相引用。

恢复后运行：

```bash
python -m pytest -q
```

全部测试应重新通过。

这个实验说明：

> 模块化不是文件数量增加，而是依赖方向能够被清楚说明并由代码遵守。

## 15.12 当前系统快照

完成这一章后，项目形成三种互补代码形态：

```text
code/chapter01/ ... code/chapter14/
保存各个概念出现时的教学快照

simple_agent/
保存当前可复用公共实现

tests/
保护公共行为、状态隔离和模块边界
```

最终公共包结构为：

```text
simple_agent/
├── __init__.py
├── llm.py
├── action.py
├── parser.py
├── tools.py
├── state.py
└── agent.py
```

项目根目录至少包含：

```text
simple-agent/
├── pyproject.toml
├── README.md
├── simple_agent/
├── tests/
├── code/
└── docs/
```

公共入口可以保持为：

```python
agent = Agent(
    llm=llm,
    tools=tools,
    system_prompt=system_prompt,
    policy=RetryPolicy(
        max_steps=8,
    ),
)

execution = agent.run(user_task)

print(execution.message)
```

需要诊断时，调用方仍然可以读取：

```python
execution.result
execution.state
execution.trace
```

当前包已经具备同步模型调用、工具注册、Action 解析、Observation 反馈、有限重试、明确终止、状态与轨迹，以及可替换 LLM 接口。它仍然保持教学型边界：

```text
状态只保存在内存
Action 使用手写 JSON 协议
不提供异步与流式执行
不提供长期记忆和 RAG
不提供多智能体通信
不提供生产级权限与沙箱
不负责真实业务工具和数据
```

这定义了当前 Public API 的范围。核心包只保存已经理解、验证并稳定的职责。

## 15.13 本章小结

这一章没有增加新的 Agent 决策方式，而是把已经出现并通过测试的职责提取成一个公共 Python 包。

Refactoring 要求在调整内部结构时保持已有外部行为。Package 让公共代码能够被正常导入和安装；Module Boundary 规定每个模块负责什么；Dependency Direction 保证低层模块不会反向依赖上层 Controller；Public API 则通过 `__init__.py` 控制应用最常使用的稳定名称。

`pyproject.toml` 使用 `simple-agent` 作为 Distribution Name，Python 使用 `simple_agent` 作为 Import Package Name。Editable Install 让当前环境通过正常安装机制直接使用工作区源码，而不需要修改 `sys.path`。

完成本章后，应当能够回答：

1. 为什么教学章节中的重复代码不应全部删除？
2. Refactoring 与重新设计一套 Agent 有什么区别？
3. Module Boundary 和 Dependency Direction 分别约束什么？
4. 为什么 ToolRegistry、Mock LLM 和业务旅行工具不应成为同一种全局对象？
5. Distribution Name 与 Import Package Name 为什么可以不同？
6. `__init__.py` 为什么只应暴露小而稳定的 Public API？
7. Editable Install 比手动修改 `sys.path` 可靠在哪里？

## 习题

**1. 提取 Action 模块**

把第十四章教学实现中的 `AgentAction`、`snapshot_action()`、`action_to_json()` 和 `action_fingerprint()` 移入 `simple_agent/action.py`。修改测试导入，并确认重复 Action 检测结果不变。

**2. 建立独立 ToolRegistry**

创建两个注册表，分别注册 `calculator` 与 `get_weather`。确认两个注册表的 `names()` 结果互不影响，并为重复注册编写异常测试。

**3. 控制 Public API**

在 `simple_agent/__init__.py` 中只导出本章列出的公共名称。验证应用可以从包顶层创建 Agent，同时 Parser 单元测试仍可从 `simple_agent.parser` 导入 `parse_action()`。

**4. 验证 Editable Install**

在项目根目录执行可编辑安装，然后切换到另一个目录运行：

```bash
python -c "from simple_agent import Agent; print(Agent)"
```

删除任何 `sys.path.append()` 后再次验证。

**5. 制造并修复循环导入**

让 `tools.py` 反向导入 `Agent`，记录实际错误；随后恢复单向依赖，并解释为什么工具层不应知道 Controller。

## 参考资料

1. [Python Packaging User Guide: Writing your pyproject.toml](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/).
2. [Distribution package vs. import package](https://packaging.python.org/en/latest/discussions/distribution-package-vs-import-package/).
3. [Development Mode (Editable Installs)](https://setuptools.pypa.io/en/latest/userguide/development_mode.html).
4. [Package Discovery and Namespace Packages](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html).
5. [Refactoring: Improving the Design of Existing Code](https://refactoring.com/). 2nd Edition. Addison-Wesley, 2018.
