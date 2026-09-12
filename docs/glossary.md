# 术语表

本术语表统一 Simple Agent 第一版中的核心概念。正文首次出现术语时给出正式定义，后续章节引用本表或术语所属章节，不再重复完整解释。

按字母浏览：[A](#a) · [B](#b) · [C](#c) · [D](#d) · [E](#e) · [F](#f) · [G](#g) · [I](#i) · [L](#l) · [M](#m) · [N](#n) · [O](#o) · [P](#p) · [R](#r) · [S](#s) · [T](#t) · [U](#u) · [V](#v) · [W](#w)

## A

### Action（行动）

Agent 根据目标、状态和观察选择的下一步行为。

在第一章中，Action 是一般意义上的行动；从第五章开始，Action 具体指模型按协议生成的结构化行动请求。

Action 可以修改环境，也可以查询环境。只读查询虽然不改变外部状态，但取得的新信息仍可能改变 Agent 后续的决策依据。本书用“通过执行器作用于环境并产生可观察执行结果”作为区分普通 LLM 应用与工具型 Agent 的工程判断标准。

相关术语：

```text
Action Protocol
AgentAction
Tool Action
Finish Action
```

正式定义章节：

```text
第 1 章：一般行动
第 5 章：结构化 Action
```

### Action Protocol（行动协议）

模型与程序约定的结构化输出格式。

本书的最小协议为：

```json
{
  "action": "行动名称",
  "arguments": {}
}
```

它规定允许字段、行动名称和参数结构，但不能保证模型一定遵守。

正式定义章节：

```text
第 5 章
```

### ActionParseError

表示模型输出无法被解析，或未通过 Action 协议校验的自定义异常。

它属于模型输出与程序执行之间的边界错误，不等于工具执行失败。

正式定义章节：

```text
第 6 章
```

### Agent（智能体）

围绕目标运行，能够感知环境、维护状态、选择行动，并根据行动结果继续调整行为的程序系统。

Agent 可以使用大语言模型，也可以使用规则或其他决策方法。使用 LLM 不自动意味着系统已经是 Agent。

正式定义章节：

```text
第 1 章
```

### AgentAction

程序内部使用的行动对象，表示模型输出已经通过解析和校验。

示例：

```python
AgentAction(
    name="get_weather",
    arguments={"city": "北京"},
)
```

它表示“程序认可这是一项符合协议的行动”，不表示工具一定会执行成功。

正式定义章节：

```text
第 6 章
```

### AgentExecution

一次 Agent 运行的完整结构化结果，通常组合：

```text
AgentRunResult
AgentState
Execution Trace
```

它用于同时访问最终结果和运行过程。

正式使用章节：

```text
第 13 章以后
```

### Agent Loop（智能体循环）

程序围绕用户目标，重复执行模型决策、行动解析、工具执行、结果反馈和状态更新，直到正常结束或触发终止条件的控制循环。

其中，正常结束表示 Controller 接受合法的 `finish` 并收束运行，不等于用户目标已经客观完成。

最小过程：

```text
LLM → Action → Tool → Observation → LLM
```

正式工程实现章节：

```text
第 8 章
```

### AgentRunResult

一次 Agent 运行结束后返回的结构化结果。

在最终公共包中通常包含：

```text
success
message
termination_reason
steps
error
```

它描述运行结局，不保存完整逐步轨迹。字段 `success=True` 表示 Controller 正常接受 `finish`，不是对用户任务完成或答案正确性的证明。

正式定义章节：

```text
第 12 章
```

### AgentState

会影响 Agent 当前和后续运行的可变状态。

通常包含：

```text
messages
当前 step
调用计数
轨迹记录
终止状态
```

它不同于最终结果，也不同于日志。

正式定义章节：

```text
第 13 章
```

### API Key

模型服务用于确认调用者身份和权限的凭证。

真实 API Key 不应写入公开代码，也不应提交到 Git 仓库。

正式定义章节：

```text
第 2 章
```

### Assistant Message

消息角色为 `assistant` 的模型历史回答。

多轮对话中，程序需要把模型回答加入 `messages`，下一轮模型才能看到自己此前说过什么。

正式定义章节：

```text
第 3 章
```

### Attempt（尝试）

同一个 Agent Step 内的一次模型输出尝试。

例如，模型第一次输出非法 JSON，第二次输出合法 Action，这属于：

```text
1 个 Step
2 个 Attempt
```

正式定义章节：

```text
第 13 章
```

## B

### Base URL

模型 API 的基础服务地址，用于决定请求发送到哪里。

它与 Model ID、API Key 解决的问题不同：

```text
API Key：谁在调用
Base URL：请求发到哪里
Model ID：调用哪个模型
```

正式定义章节：

```text
第 2 章
```

## C

### Context（上下文）

模型在当前一次调用中能够看到并用于生成输出的信息。

在本书的对话接口中，上下文主要来自有序的 `messages`。

Context 不等于长期记忆，也不等于 Python 程序中存在的全部变量。

正式定义章节：

```text
第 3 章
```

### Controller（控制器）

推动 Agent Loop 的程序代码。

Controller 负责：

```text
调用模型
解析输出
执行工具
更新上下文
限制步数
处理终止
```

模型负责提出行动，Controller 负责决定行动是否可以成为真实程序行为。

正式定义章节：

```text
第 8 章
```

### Conversation History（对话历史）

程序保存的历史消息序列。

通常包含：

```text
system
user
assistant
```

对话历史只有被重新发送给模型，才会成为当前上下文的一部分。

正式定义章节：

```text
第 3 章
```

### Conversation State（对话状态）

程序为维持当前对话而保存的信息。

最小形式是 `messages`。它是 AgentState 的一种早期、局部形式，不包含完整工具轨迹和终止状态。

正式定义章节：

```text
第 3 章
```

### Confirmation（确认）

程序在执行高风险或有副作用的 Action 前，要求用户明确授权的控制步骤。

模型只能提出需要确认的行动，不能代表用户完成授权。没有确认、用户拒绝和确认后执行应当产生不同的结构化结局。

正式定义章节：

```text
第 12 章
```

### Critic（评审者）

Reflection 中负责检查当前 Draft 的逻辑角色。

Critic 根据用户任务、Evidence 和当前 Draft 生成 Critique，但不直接执行工具，也不应自行补充无证据事实。

正式定义章节：

```text
第 11 章
```

### Critique（评审结果）

Critic 对当前 Draft 生成的结构化检查结果。

它应指出：

```text
是否通过
问题类型
具体问题
修改建议
```

正式定义章节：

```text
第 11 章
```

## D

### Decision（决策）

根据目标、当前状态和观察选择 Action 的过程。

在规则 Agent 中，Decision 可以由 `if-else` 完成；在 LLM Agent 中，核心决策通常由大语言模型生成。

正式定义章节：

```text
第 1 章
```

### Decision Retry（决策重试）

把失败或新信息作为 Observation 提供给模型，让 Agent 重新选择下一步 Action。

它不同于：

```text
网络请求重试
模型格式重试
工具执行重试
```

正式定义章节：

```text
第 12 章
```

### Dependency Direction（依赖方向）

模块之间允许依赖的单向关系。低层数据结构和工具边界不应反向导入高层 Agent Controller；应用层可以依赖公共包，公共包不依赖具体旅行应用。

正式定义章节：

```text
第 15 章
```

### Distribution Name（分发名称）

安装工具和项目元数据识别的项目名称。本项目在 `pyproject.toml` 中使用 `simple-agent`，它与 Python 代码中的导入包名 `simple_agent` 解决不同问题。

正式定义章节：

```text
第 15 章
```

### Draft（候选答案）

Reflection 中尚未经过检查或尚未通过检查的答案。

Draft 不是最终结果，后续可能被 Critic 指出问题并由 Refiner 修改。

正式定义章节：

```text
第 11 章
```

## E

### Environment（环境）

Agent 所处并与之交互的外部系统。

环境可以是：

```text
物理世界
文件系统
数据库
网络服务
工具集合
用户交互界面
```

正式定义章节：

```text
第 1 章
```

### Environment State（环境状态）

环境本身在某一时刻的真实状态。

Agent 通常不能直接获得全部环境状态，只能通过接口、传感器或工具得到 Observation。

正式定义章节：

```text
第 1 章
```

### Evidence（证据）

当前任务中已经获得，并允许答案使用的可信信息。

在本书的旅行助手中，Evidence 主要来自已执行工具的结果，并分为两类：

```text
Domain Evidence：成功取得的领域事实
Execution Evidence：not_found、权限拒绝和工具失败等执行事实
```

Evidence 不等于模型常识；Reflection 不能使用未提供的事实修复答案。

正式定义章节：

```text
第 11 章
```

### Execution Trace（执行轨迹）

按顺序保存一次 Agent 运行中各个 Step 的结构化记录。

轨迹可以包含：

```text
模型尝试
Action
Tool Result
Observation
错误
```

它主要用于调试、测试和分析，通常不直接进入模型上下文。

正式定义章节：

```text
第 13 章
```

### Executor（执行器）

在 Plan-and-Solve 中，负责执行当前 PlanStep 的逻辑角色。

Executor 根据用户目标、完整 Plan、当前步骤和前序 StepResult 生成并执行当前 Action。

正式定义章节：

```text
第 10 章
```

## F

### Failure Classification（失败分类）

根据错误发生位置和性质，对 Agent 失败进行分层。

本书主要区分：

```text
配置与输入层
LLM 请求层
模型协议层
Parser / Validation 层
Tool 层
Agent 决策层
权限与安全层
Controller 层
```

正式定义章节：

```text
第 12 章
```

### Final Answer（最终回答）

Agent 面向用户返回的最终自然语言结果。

最终回答可能由 `finish` Action、Finalize 阶段或 Reflection 修订产生。它不同于 Action、Plan、Tool Result 和 Observation。

### Finalize（最终整理）

Plan-and-Solve 中，在所有步骤执行完成后，根据完整 StepResult 生成最终回答的阶段。

正式定义章节：

```text
第 10 章
```

### Finish Action

表示模型认为当前任务可以结束的特殊 Action。

示例：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
```

它不是普通工具，不进入工具注册表。

正式定义章节：

```text
第 5 章
```

### Format Retry（格式重试）

模型输出未通过 Parser 时，向模型反馈协议错误并请求重新生成 Action。

格式重试会再次调用模型，并改变临时修复上下文。

正式定义章节：

```text
第 12 章
```

## G

### Generator（生成者）

Reflection 中负责根据用户任务和 Evidence 生成初始 Draft 的逻辑角色。

正式定义章节：

```text
第 11 章
```

### Goal（目标）

Agent 希望达到的结果。

目标用于判断任务是否完成。它不同于当前输入，也不同于当前 Observation。

正式定义章节：

```text
第 1 章
```

## I

### Idempotency（幂等性）

同一操作重复执行多次，外部效果与执行一次相同或可安全控制的性质。

查询天气通常近似幂等；发送邮件、创建订单和支付通常不能假定幂等。工具能否重试，需要同时考虑错误类型和幂等性。

正式定义章节：

```text
第 12 章
```

### Integration Test（集成测试）

验证多个组件组合后是否按预期协同工作的测试。

本书主要用于验证 Mock LLM、Parser、Tool Executor、Agent Loop 和 State 组合后的行为。

正式定义章节：

```text
第 14 章
```

### Import Package Name（导入包名）

Python 代码在 `import` 或 `from ... import ...` 中使用的名称。本项目的导入包名为 `simple_agent`。

它可以与分发名称不同：

```text
安装或元数据：simple-agent
Python 导入：simple_agent
```

正式定义章节：

```text
第 15 章
```

## L

### LLM Application（大语言模型应用）

以大语言模型调用为核心的程序应用。

它可以完成问答、摘要和生成任务，但不一定具备工具执行、环境反馈、动态行动和 Agent Loop。

正式定义章节：

```text
第 1 章
```

### Log（日志）

程序运行时输出的事件记录。

日志通常包含时间、级别、模块、事件名称和摘要字段。日志主要面向开发和运维，不应直接进入模型上下文。

正式定义章节：

```text
第 13 章
```

## M

### Message（消息）

发送给模型的一条结构化输入。

最小字段通常包括：

```text
role
content
```

正式定义章节：

```text
第 2 章
```

### `messages`

按时间顺序排列的消息列表，是本书对话接口中的主要上下文容器。

示例：

```python
messages = [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
]
```

正式定义章节：

```text
第 3 章
```

### Metrics（指标）

从一次或多次 Agent 运行中汇总的基础数字。

本书可记录：

```text
总步骤
LLM 调用次数
工具调用次数
解析失败次数
正常结束率（不是用户任务完成率）
终止原因分布
```

Metrics 不替代完整 Trace。

正式定义章节：

```text
第 14 章
```

### Mock LLM

返回预设输出的确定性测试替身。

它不调用真实模型服务，用于稳定验证 Parser、工具和 Agent Loop。

正式定义章节：

```text
第 14 章
```

### ModelAttemptRecord

记录同一个 Step 中某次模型输出尝试的数据结构。

通常包含：

```text
attempt
model_output
request_error
parse_error
```

正式定义章节：

```text
第 13 章
```

### Model ID

模型服务中用于指定具体模型的名称或标识符。

正式定义章节：

```text
第 2 章
```

### Module Boundary（模块边界）

一个模块明确负责的职责，以及它允许其他模块通过哪些数据和函数与自己交互。

模块边界用于避免 Parser、工具、状态和 Agent Loop 的职责重新混在同一个文件中，也决定哪些名称应当进入 Public API。

正式定义章节：

```text
第 15 章
```

## N

### Network Retry（网络请求重试）

在模型请求因为临时连接、超时、限流或服务端错误失败时，重复同一次请求。

它通常不改变模型上下文。

正式定义章节：

```text
第 12 章
```

## O

### Observation（观察）

Agent 从环境获得并用于后续决策的反馈。

第一章使用一般定义；第七章将 Tool Result 组织为 Tool Observation。

正式定义章节：

```text
第 1 章
```

### Observation Message

程序把 Action 执行结果包装后写入模型上下文的消息。本书使用 `assistant` 保存 Action、使用 `user` 承载 `Observation:`，这是为了展示原理而手写的消息协议，不代表所有模型服务的角色结构。

它通常包含工具名称、参数、成功状态、结果或错误。

正式定义章节：

```text
第 7 章
```

## P

### Package（包）

可被安装和导入的 Python 模块集合。

本书最终包名为：

```text
simple_agent
```

项目分发名称可以使用：

```text
simple-agent
```

正式定义章节：

```text
第 15 章
```

### Parser（解析器）

将模型输出文本转换为 Python 数据，并检查其是否符合基本结构的组件。

Parser 不负责执行工具，也不应自动猜测并修改行动语义。

正式定义章节：

```text
第 6 章
```

### Plan（计划）

Planner 针对当前用户目标生成的有序任务步骤集合。

Plan 描述“需要完成哪些步骤”，不代表工具已经执行。

正式定义章节：

```text
第 10 章
```

### Plan-and-Solve

先由 Planner 生成完整计划，再由 Executor 按步骤执行并汇总结果的控制范式。

它强调执行前的全局任务分解。

正式定义章节：

```text
第 10 章
```

### Planner（规划者）

Plan-and-Solve 中负责生成 Plan 的逻辑角色。

Planner 不执行工具，也不应提前编造尚未获得的数据。

正式定义章节：

```text
第 10 章
```

### PlanStep（计划步骤）

Plan 中的一项有序步骤。

通常包含：

```text
id
description
tool
expected_output
```

正式定义章节：

```text
第 10 章
```

### Public API（公共接口）

包承诺给使用者的稳定导入和调用接口。

它通常通过 `__init__.py` 暴露，不应把所有内部实现都作为公共接口。

正式定义章节：

```text
第 15 章
```

## R

### ReAct

将简洁推理摘要、行动和环境观察交替组织的 Agent 控制范式。

本书使用：

```text
Reason → Action → Observation
```

正式定义章节：

```text
第 9 章
```

### Reason

模型面向执行轨迹生成的简洁决策摘要。

它用于说明当前已知什么、还缺少什么、为什么选择下一步 Action。

Reason 不是完整内部思维过程，也不是可执行代码。

正式定义章节：

```text
第 9 章
```

### Refactoring（重构）

在契约已经统一后，保持已有外部行为并调整内部代码结构。重构不同于重写；它依赖自动化测试证明解析、工具执行、终止原因和轨迹等行为没有被意外改变。若同时统一枚举名称或返回字段，应明确记录为包化前的契约迁移，而不能称为纯粹的行为保持重构。

正式定义章节：

```text
第 15 章
```

### Refiner（修订者）

Reflection 中根据用户任务、Evidence、当前 Draft 和 Critique 生成修订答案的逻辑角色。

正式定义章节：

```text
第 11 章
```

### Reflection

根据用户任务、Evidence 和当前 Draft 生成 Critique，再据此修订答案的控制过程。

本书中的 Reflection 只处理当前答案层，不训练模型，也不自动重新执行工具。

正式定义章节：

```text
第 11 章
```

### Regression Test（回归测试）

用于确认代码修改或重构后，已有行为没有被意外破坏的测试。

第十五章重构依赖第十四章建立的回归测试保护网。

正式使用章节：

```text
第 14、15 章
```

### Retry（重试）

针对可恢复失败进行的有限再次尝试。

重试必须明确：

```text
为什么失败
重试什么
是否安全
最多几次
```

正式定义章节：

```text
第 12 章
```

### Retry Policy（重试策略）

规定哪些错误可以重试、重试对象、次数和停止条件的程序规则。本书当前最小实现不提供等待间隔或退避策略；若实现了这些机制，它们才属于 Retry Policy 的完整内容。

正式定义章节：

```text
第 12 章
```

## S

### SDK

封装底层网络请求、认证、序列化和响应对象的开发工具包。

本书使用模型 SDK 进行基础文本调用，但 SDK 本身不是 Agent 框架。

正式定义章节：

```text
第 2 章
```

### State（状态）

Agent 在运行过程中保存并可能影响后续行为的信息。

本书分层使用：

```text
第 1 章：一般 State
第 3 章：Conversation State
第 13 章：AgentState
```

### Step（步骤）

Agent Loop 中一次有效决策的编号。

一个 Step 可以包含多个格式 Attempt，但最终只产生一个通过校验的 Action，或因解析耗尽而失败。

正式定义章节：

```text
第 13 章
```

### StepRecord

记录某一个 Agent Step 完整过程的数据结构。

通常包含：

```text
model_attempts
action
tool_results
observation
termination_reason
error
```

正式定义章节：

```text
第 13 章
```

### StepResult

Plan-and-Solve 中某个 PlanStep 执行后的结构化结果。

它通常保存：

```text
step_id
description
tool_name
arguments
output
```

正式定义章节：

```text
第 10 章
```

### Structured Output（结构化输出）

本书中特指由 Prompt 约束模型生成的 JSON 文本。当前模型服务没有按照程序提供的 Schema 保证其合法性，也不是 SDK 原生 Tool Calling；程序收到的仍然是普通字符串。

结构化输出可以提高可解析性，但仍然必须经过 Parser 和 Validation。

正式定义章节：

```text
第 5 章
```

### System Message

消息角色为 `system` 的总体指令。

它用于规定模型角色、行为边界、输出格式和任务规则。

正式定义章节：

```text
第 2 章
```

## T

### Termination（终止）

Agent 停止运行的状态。

终止可以是正常完成、解析失败、工具失败、重复行动、达到最大步数、超时、用户拒绝或权限不足。

正式定义章节：

```text
第 12 章
```

### TerminationReason

表示 Agent 为什么停止的枚举或结构化字段。

它让调用者能够区分不同结束原因，而不是只收到一段模糊文本。

正式定义章节：

```text
第 12 章
```

### Tool（工具）

被程序明确开放、能够接收参数、执行特定能力并返回结果的函数或服务。

工具可以是本地函数、文件操作、数据库查询、网络 API 或系统操作。

正式定义章节：

```text
第 4 章
```

### ToolExecutionResult（工具执行结果）

后期工具执行层使用的结构化结果，通常包含 `success`、`content`、`error_type` 和 `retryable`。它与第四章只强调函数返回值的 Tool Result 不同：ToolExecutionResult 还表达执行状态和恢复信息。

其中，工具元数据上的 `retryable` 或 `safe_to_retry` 表示操作是否允许自动重试；结果上的 `retryable` 表示当前错误是否可能恢复，两者不是同一层含义。

正式定义章节：

```text
第 12 章、第 15 章
```

### Timeout（超时）

当前同步 Agent 中，`timeout_seconds` 是在 Agent Step 边界检查的软时间预算。它可以阻止超预算的下一步开始，但不能中断已经进行中的同步模型请求或工具调用。

正式定义章节：

```text
第 12 章
```

### Tool Action

请求程序执行某个已注册工具的 Action。

示例：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

正式定义章节：

```text
第 5 章
```

### Tool Description

提供给模型的工具说明。

它应描述工具名称、用途、参数、返回内容和限制。

正式定义章节：

```text
第 4 章
```

### Tool Executor

根据工具名称和参数，从注册表中找到对应函数并执行的程序组件。

它不负责决定应该使用哪个工具。

正式定义章节：

```text
第 4 章
```

### Tool Observation

Tool Result 被程序包装并反馈给模型后的 Observation。

正式定义章节：

```text
第 7 章
```

### Tool Registry

保存程序允许调用的工具及其元数据的注册表。

工具未进入注册表，即使模型输出其名称，也不能被执行。

正式定义章节：

```text
第 4 章
```

### Tool Result

工具函数直接返回给 Python 程序的数据。

它只有被构造成 Observation 并进入模型上下文后，才会影响模型后续决策。

正式定义章节：

```text
第 4 章
```

### Tool Retry（工具执行重试）

在工具发生可恢复且可安全重复的临时错误时，再次执行同一个工具 Action。

它必须考虑副作用和幂等性。

正式定义章节：

```text
第 12 章
```

## U

### Unit Test（单元测试）

验证单个组件在明确输入下是否产生预期输出的测试。

本书主要用于 Parser、Tool 和数据结构。

正式定义章节：

```text
第 14 章
```

### User Message

消息角色为 `user` 的用户输入或程序构造的用户侧消息。

在手写 Observation 协议中，程序也可能使用 `user` 角色承载 `Observation:` 文本，但应明确其语义不是新的普通用户任务。

正式定义章节：

```text
第 2、7 章
```

### User Output

最终面向用户展示的答案或失败说明。

它不应包含 API Key、完整堆栈、本机路径、内部 Prompt 或完整调试轨迹。

正式区分章节：

```text
第 13 章
```

## V

### Validation（校验）

检查解析后的数据是否符合当前 Action 协议和工具约束的过程。

它包括字段存在性、字段类型、工具白名单、参数名称、参数类型和参数取值。

正式定义章节：

```text
第 6 章
```

## W

### Workflow（工作流）

由开发者预先确定步骤、顺序和分支的执行流程。

工作流可以包含 LLM，但整体控制路径通常仍由程序提前设计。Workflow 与 Agent 不是非此即彼，实际系统可以组合两者。

正式定义章节：

```text
第 1 章
```

## 术语关系总图

```text
Goal
  ↓
AgentState + Context
  ↓
LLM
  ↓
Action Protocol
  ↓
Parser + Validation
  ↓
AgentAction
  ↓
Tool Registry + Tool Executor
  ↓
Tool Result
  ↓
Tool Observation
  ↓
Agent Loop
  ↓
Finish / Termination
```

策略层：

```text
ReAct：Reason + Action + Observation
Plan-and-Solve：Plan + StepResult + Finalize
Reflection：Draft + Critique + Revision
```

工程层：

```text
Retry Policy
→ AgentRunResult
→ AgentState
→ Execution Trace
→ Log
→ Mock LLM
→ Tests
→ Package
```
