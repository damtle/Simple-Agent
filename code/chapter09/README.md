# Chapter 09：ReAct：边行动边观察

本目录对应《第九章 ReAct：边行动边观察》，实现 `Simple Travel Assistant v1.1`。

第八章已经建立通用 Agent Loop。本章不重新设计循环，而是在每轮 Action 前加入一段简洁 Reason，使模型根据用户目标和全部 Observation 说明当前已知信息、缺失信息与行动依据。

## 放置位置

```text
code/
└── chapter09/
    ├── README.md
    ├── action.py
    ├── main.py
    ├── parser.py
    └── prompts.py
```

文件职责：

| 文件 | 职责 |
|---|---|
| `action.py` | 定义 `AgentAction`、`ReActDecision` 和 `ActionParseError` |
| `parser.py` | 校验 `reason`、`action`、`arguments` 及工具参数 |
| `prompts.py` | 保存 ReAct 系统提示词 |
| `main.py` | 沿用旅行工具与 Observation，驱动 ReAct Agent Loop |
| `README.md` | 说明运行、协议、轨迹和失败实验 |

本章目录没有单独建立 `tools.py`。为了与正文给出的文件结构一致，三个本地模拟工具及注册表保留在 `main.py` 中。后续统一重构时再提取公共模块。

## 环境要求

建议使用 Python 3.10 或更高版本。

安装依赖：

```bash
python -m pip install openai python-dotenv
```

项目根目录继续使用：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

真实 `.env` 不应提交到 Git 仓库。

## 运行

从项目根目录执行：

```bash
python code/chapter09/main.py
```

推荐任务：

```text
请查询北京的模拟天气和故宫的模拟开放、票价信息，
计算两张成人票的总价，并给出出行建议。
```

一次合理轨迹可能是：

```text
Step 1
Reason：当前缺少北京模拟天气，因此查询天气。
Action：get_weather({"city": "北京"})
Observation：北京模拟天气为晴，温度30℃……

Step 2
Reason：天气已获得，但故宫状态和票价仍未知。
Action：get_attraction_info({"name": "故宫"})
Observation：故宫开放，成人票价60元……

Step 3
Reason：已获得单张票价，需要计算两张票总价。
Action：calculator(
    {"operation": "multiply", "a": 60, "b": 2}
)
Observation：120

Step 4
Reason：完成回答所需信息已经全部获得。
Action：finish
```

工具顺序仍由模型根据当前上下文决定，程序没有写死固定 Workflow。

## ReAct 输出协议

每轮必须输出一个 JSON 对象，且顶层只能包含：

```text
reason
action
arguments
```

示例：

```json
{
  "reason": "已经获得故宫成人票价60元，需要计算两张票总价。",
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

`reason` 必须是非空字符串；`action` 必须为已注册工具或 `finish`；`arguments` 必须符合对应行动协议。

## ReActDecision 与 AgentAction

```python
ReActDecision(
    reason="当前缺少北京模拟天气。",
    action=AgentAction(
        name="get_weather",
        arguments={"city": "北京"},
    ),
)
```

`ReActDecision` 保存本轮 Reason 和 Action；`AgentAction` 仍然是 Controller 与工具执行器之间的数据边界。工具执行器只读取 `decision.action`，不会执行或解释 Reason。

## Parser 能检查什么

Parser 能检查：

```text
JSON 是否合法
顶层字段是否严格为 reason、action、arguments
reason 是否为非空字符串
action 是否在白名单中
arguments 是否为对象
参数名称、类型和允许值是否符合协议
```

Parser 不能证明 Reason 与 Action 在语义上完全一致。例如：

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

该输出可能通过结构校验，但仍然存在语义矛盾。Reason 提高可观察性，不保证决策正确。

## 工具失败后的动态调整

输入：

```text
请计算10除以0，并根据实际执行结果回答，不要猜测。
```

第一轮工具执行产生：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "divide", "a": 10, "b": 0}
执行状态：失败
错误类型：ValueError
工具结果：除数不能为 0。
```

下一轮模型应根据失败 Observation 使用 `finish` 如实说明限制，或者选择有新依据的行动。当前程序不会仅凭 Reason 自动阻止重复 Action，也不会自动重试工具。

## 基础终止边界

| 情况 | 当前处理 |
|---|---|
| 合法 `finish` | 正常返回 `arguments.answer` |
| 空模型输出 | 抛出 `RuntimeError` |
| ReAct 决策未通过 Parser | 抛出 `ActionParseError` |
| 工具抛出 `TypeError` 或 `ValueError` | 转换为失败 Observation |
| 达到 `max_steps` 仍未 `finish` | 抛出 `RuntimeError` |

默认：

```python
DEFAULT_MAX_STEPS = 6
```

## 失败实验

**空 Reason**

```json
{
  "reason": "",
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

Parser 应在工具执行前拒绝该决策。

**删除 Reason 历史**

临时让 `messages` 中只保存 Action 和 Observation，不保存前几轮 Reason。比较任务完成情况和调试体验，观察 Reason 对后续判断与开发者阅读分别有什么价值。

**Reason 与 Action 不一致**

手动构造 Reason 说“查询天气”、Action 却调用计算器的决策，验证基础 Parser 只负责结构和参数校验。

## 当前能力边界

本章已经能够：

```text
让每轮决策包含简洁 Reason
保持 AgentAction 和工具执行边界不变
把规范 ReActDecision 保存到 messages
让失败 Observation 影响下一轮局部判断
展示可读的 Reason-Action-Observation Trace
```

本章仍然不能：

```text
证明 Reason 与 Action 语义一致
自动修复非法决策
自动检测重复 Action
生成执行前的完整计划
检查 finish.answer 是否完整
保存专门的结构化轨迹对象
```

下一章将研究怎样在执行工具之前先生成覆盖完整目标的计划。
