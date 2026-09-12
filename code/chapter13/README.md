# Chapter 13：状态、轨迹与日志

本目录对应《第十三章 状态、轨迹与日志》，实现 `Simple Travel Assistant v1.5`。

第十二章的 `AgentRunResult` 只能说明最终结局。本章新增 `AgentState`、`ModelAttemptRecord`、`StepRecord` 和 `ExecutionTrace`，让程序能够回答一次运行实际调用了多少次模型、格式重试发生在哪个 Step、工具是否真正执行，以及终止原因怎样产生。

## 放置位置

```text
code/
└── chapter13/
    ├── README.md
    ├── agent.py
    ├── logging_config.py
    ├── state.py
    └── trace.py
```

文件职责：

| 文件 | 职责 |
|---|---|
| `state.py` | 定义可变 `AgentState` 并创建独立初始状态 |
| `trace.py` | 定义 Attempt、Step 和 Execution Trace，负责展示与 JSON 保存 |
| `logging_config.py` | 在入口统一配置 Python logging |
| `agent.py` | 沿用可靠 Agent Loop，更新状态、记录轨迹并提供运行入口 |
| `README.md` | 说明运行、日志级别、故障演示和能力边界 |

本章通过离线场景观察状态和轨迹；下一章再使用 Mock、pytest 和 Metrics 建立自动验证。

## 核心返回值

`run_agent()` 返回：

```python
@dataclass(frozen=True)
class AgentExecution:
    result: AgentRunResult
    state: AgentState
    trace: ExecutionTrace
```

三者职责不同：

```text
AgentRunResult：说明最终结局和 User Output
AgentState：保存运行中的消息、步骤、计数器和记录
ExecutionTrace：保存运行结束后的独立步骤快照
```

## Step 与 Attempt

格式重试不会创建新的 Agent Step：

```text
Step 1 / Attempt 1：Action 缺少 arguments
Step 1 / Attempt 2：合法 get_weather
Step 2 / Attempt 1：get_attraction_info
Step 3 / Attempt 1：calculator
Step 4 / Attempt 1：finish
```

对应状态：

```text
step = 4
llm_calls = 5
parse_failures = 1
```

一次 Step 使用：

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

天气工具第一次临时失败、第二次成功时，两项结果都会保存在同一个 `StepRecord.tool_results` 中，而 Agent Step 只增加一次。

## 环境要求

建议使用 Python 3.10 或更高版本。

离线演示只使用 Python 标准库。真实模型模式需要：

```bash
python -m pip install openai python-dotenv
```

项目根目录 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

真实 `.env` 不应提交到 Git。

## 运行主线案例

从项目根目录运行：

```bash
python code/chapter13/agent.py
```

默认场景会在 Step 1 先制造一次格式错误，再完成天气、景点、计算和 `finish`，用于直接观察 Step 与 Attempt 的区别。

不含格式错误的正常路径：

```bash
python code/chapter13/agent.py --scenario normal
```

模型请求先临时失败一次：

```bash
python code/chapter13/agent.py --scenario network-retry
```

天气工具第一次临时失败、随后安全重试：

```bash
python code/chapter13/agent.py --scenario tool-retry
```

连续生成相同 Action，并在第二次工具执行前终止：

```bash
python code/chapter13/agent.py --scenario repeated-action
```

格式重试全部耗尽：

```bash
python code/chapter13/agent.py --scenario parse-error
```

高风险模拟预订场景：

```bash
python code/chapter13/agent.py --scenario confirmation-required
python code/chapter13/agent.py --scenario user-rejected
python code/chapter13/agent.py --scenario confirmation-approved
```

最大步骤终止：

```bash
python code/chapter13/agent.py --scenario max-steps
```

## 日志

默认日志级别为 `INFO`：

```bash
python code/chapter13/agent.py --log-level INFO
```

查看 Attempt 编号、Action 指纹和重复计数：

```bash
python code/chapter13/agent.py \
  --scenario repeated-action \
  --log-level DEBUG
```

日志只传播运行事件，不改变 `AgentState`，也不能替代 `StepRecord`。

## 保存 Execution Trace

```bash
python code/chapter13/agent.py \
  --scenario main \
  --save-trace artifacts/traces/trace.json
```

JSON 包含：

```text
steps
termination_reason
records
  model_attempts
  action
  tool_results
  observation
  termination_reason
  error
```

轨迹适合开发者调试，不应直接作为普通用户输出。真实系统保存前还需要字段白名单、脱敏、访问权限和保留周期；API Key、访问令牌、密码、完整认证请求头和不必要的个人信息不得写入 Trace。

## 使用真实模型

```bash
python code/chapter13/agent.py --real
```

指定任务：

```bash
python code/chapter13/agent.py \
  "查询上海的模拟天气" \
  --real
```

真实模式关闭 SDK 内部自动重试，由本章 Controller 统一记录每一次模型请求。

## 当前能力边界

本章已经能够：

```text
集中保存 messages、步骤和调用计数
区分 Agent Step 与模型 Attempt
记录网络失败、格式错误和被接受的模型输出
保存同一 Action 的全部工具重试结果
记录成功、失败、重复 Action 和 finish 步骤
从 State 创建不可变 Execution Trace
使用 logging 实时传播运行事件
把轨迹保存为 UTF-8 JSON
分别展示 User Output、State 和 Trace
```

本章仍然不能：

```text
通过正式 Mock LLM 稳定复现所有行为
使用 pytest 自动验证状态和失败路径
汇总基础 Metrics
进行真实模型质量评估
持久化并恢复未完成状态
提供生产级脱敏和分布式追踪
形成可安装 simple_agent 包
```

下一章将引入 Mock、自动化测试和基础评估。
