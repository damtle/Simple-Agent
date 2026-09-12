# Chapter 12：失败、重试与终止

本目录对应《第十二章 失败、重试与终止》，实现 `Simple Travel Assistant v1.4`。

本章不再假设模型、Parser 和工具始终成功，而是把失败处理分层，并让所有预期运行结局统一返回 `AgentRunResult`。

## 放置位置

```text
code/
└── chapter12/
    ├── README.md
    ├── agent.py
    ├── result.py
    ├── retry.py
    └── tools.py
```

文件职责：

| 文件 | 职责 |
|---|---|
| `result.py` | 定义 `TerminationReason`、`AgentRunResult` 和常见受控结果 |
| `retry.py` | 定义 `RetryPolicy`、`LLMRequestError`、Network Retry 与 Tool Retry |
| `tools.py` | 定义 `ToolExecutionResult`、`ToolSpec`、旅行工具和故障注入包装器 |
| `agent.py` | 保存本章最小 Parser，处理 Format/Decision Retry、重复检测、Confirmation 和 Agent Loop |
| `README.md` | 说明运行、演示场景、重试预算与能力边界 |

本章将最小 Action 与 Parser 放在 `agent.py` 中，以便集中观察失败处理与循环控制。第十五章再按职责拆分模块。

## 四种重试

```text
Network Retry
重复同一次模型请求，不修改消息语义。

Format Retry
将协议错误反馈给模型，重新生成当前决策位置的 Action。

Tool Retry
在错误可恢复且工具幂等时，重新执行同一个 AgentAction。

Decision Retry
把失败结果作为 Observation 加入上下文，让模型进入下一决策步骤。
```

`RetryPolicy` 的默认配置为：

```python
RetryPolicy(
    max_network_retries=2,
    max_format_retries=2,
    max_tool_retries=1,
    max_steps=8,
    repeated_action_limit=2,
    timeout_seconds=30.0,
)
```

前三个 `max_*_retries` 表示额外重试次数。`max_format_retries=2` 表示初始输出失败后最多再生成两次，总共最多得到三份模型输出。

## 工具执行结果与幂等性

工具统一返回：

```python
ToolExecutionResult(
    success=False,
    content="模拟天气服务暂时不可用。",
    error_type="temporary_unavailable",
    retryable=True,
)
```

工具注册信息为：

```python
ToolSpec(
    name="get_weather",
    function=get_weather,
    idempotent=True,
    requires_confirmation=False,
)
```

Tool Retry 必须同时满足：

```text
ToolExecutionResult.retryable == True
ToolSpec.idempotent == True
仍未达到 max_tool_retries
```

`retryable=True` 表示故障可能恢复，`idempotent=True` 表示重复执行不会产生额外副作用，两者不能互相替代。

## Confirmation

`submit_reservation` 只创建模拟预订，不连接真实账号、支付或预订服务，但它代表具有副作用的工具：

```python
ToolSpec(
    name="submit_reservation",
    function=submit_reservation,
    idempotent=False,
    requires_confirmation=True,
)
```

执行顺序为：

```text
模型提出 Action
→ Parser 校验
→ 程序检查 requires_confirmation
→ 用户确认
→ 执行或拒绝
```

没有确认回调时返回 `confirmation_required`；回调返回 `False` 时返回 `user_rejected`；只有回调返回 `True` 才会执行工具。

## TerminationReason

```python
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

`SUCCESS` 只表示 Agent 正常得到 `finish`，不等于最终答案已经通过 Reflection，也不证明工具数据源本身正确。

## 安装

建议使用 Python 3.10 或更高版本。

真实模型模式需要：

```bash
python -m pip install openai python-dotenv
```

项目根目录的 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

真实 `.env` 不应提交到 Git 仓库。

## 运行确定性演示

默认成功案例：

```bash
python code/chapter12/agent.py
```

其他场景：

```bash
python code/chapter12/agent.py --scenario network-retry
python code/chapter12/agent.py --scenario format-retry
python code/chapter12/agent.py --scenario tool-retry
python code/chapter12/agent.py --scenario repeated-action
python code/chapter12/agent.py --scenario parse-error
python code/chapter12/agent.py --scenario confirmation-required
python code/chapter12/agent.py --scenario confirmation-approved
python code/chapter12/agent.py --scenario user-rejected
python code/chapter12/agent.py --scenario max-steps
```

这些演示通过确定性输出和故障开关展示本章机制，但不把它们定义为正式的 Mock LLM。完整 Mock、自动化测试和基础评估属于后续章节。

## 使用真实模型

```bash
python code/chapter12/agent.py --scenario real
```

指定任务：

```bash
python code/chapter12/agent.py   --scenario real   --task "请查询广州的模拟天气并给出建议。"
```

真实模型模式关闭 SDK 内部自动重试，由本章 `call_with_network_retry()` 统一管理网络重试，避免两层重试预算叠加。

## 典型结果

格式错误耗尽：

```text
success：False
termination_reason：parse_error
steps：1
```

连续两次相同 Action：

```text
success：False
termination_reason：repeated_action
steps：2
```

未提供高风险确认渠道：

```text
success：False
termination_reason：confirmation_required
steps：1
```

最大步骤耗尽：

```text
success：False
termination_reason：max_steps
steps：2
```

## 当前能力边界

本章已经能够：

```text
分类模型请求、协议、工具、决策、权限和 Controller 失败
对模型请求、格式和幂等工具进行有限重试
把不可原样重试的工具失败转成 Observation
检测连续相同 Action
限制最大决策步骤与总运行时间
在模拟副作用工具前要求用户确认
统一返回 AgentRunResult
```

本章仍然不能：

```text
保存每次模型尝试和工具调用的完整轨迹
统计 LLM、Parser 和 Tool 的调用次数
在运行结束后完整还原 messages
持久化等待确认的任务并恢复
使用退避、抖动、幂等键或外部事务检查
自动判断最终答案质量
```

下一章将引入状态、执行轨迹、日志和测试。
