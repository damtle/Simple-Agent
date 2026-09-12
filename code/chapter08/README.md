# Chapter 08：实现第一个完整 Agent Loop

本目录对应《第八章 实现第一个完整 Agent Loop》，实现 `Simple Travel Assistant v1.0`。

第七章采用固定两阶段流程，只允许执行一次工具。本章删除固定的“最终回答阶段”，让每一轮模型都根据用户目标和此前的 Action-Observation Pair，选择下一个工具 Action 或 `finish`。Controller 持续推进循环，直到正常完成或触发 `max_steps`。

## 放置位置

```text
code/
└── chapter08/
    ├── README.md
    ├── action.py
    ├── main.py
    ├── parser.py
    └── tools.py
```

各文件职责：

| 文件 | 职责 |
|---|---|
| `action.py` | 定义 `AgentAction` 和 `ActionParseError` |
| `parser.py` | 沿用 Action 的解析与协议校验 |
| `tools.py` | 保存三个本地模拟工具和工具注册表 |
| `main.py` | 实现统一 Prompt、Controller 和 Agent Loop |
| `README.md` | 说明运行、终止边界和失败实验 |

本章不修改 Action Protocol，也不重新设计 Tool Observation。主要变化集中在 `main.py`。

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
python code/chapter08/main.py
```

推荐任务：

```text
请查询北京的模拟天气和故宫的模拟开放信息，
计算两张成人票的总价，并给出出行建议。
```

程序持续执行：

```text
LLM → Action → Parser → Tool → Observation → LLM
```

直到模型输出 `finish`，或达到 `max_steps`。

## 一次可能的多工具轨迹

```text
Step 1：get_weather(city="北京")
→ 北京当前模拟天气为晴，温度30℃……

Step 2：get_attraction_info(name="故宫")
→ 故宫在模拟数据中处于开放状态，成人票价60元……

Step 3：calculator(operation="multiply", a=60, b=2)
→ 120

Step 4：finish(answer="……")
→ Agent 正常终止
```

不同模型可能选择不同的合理工具顺序。代码没有写死“天气 → 景点 → 计算器”，每轮 Action 都由模型根据当前 `messages` 决定。

## Controller 的循环职责

`run_agent()` 每轮执行：

```text
读取当前 messages
→ 请求模型输出
→ Parser 校验 Action
→ 保存规范 Action
→ 判断是否 finish
→ 执行工具
→ 构造并保存 Observation
→ 进入下一轮
```

模型负责提出下一步行动，Controller 负责决定模型输出能否进入真实执行流程。

## `messages` 保存执行进度

循环初始状态只有：

```text
system：Agent 运行规则
user：用户目标
```

每次工具执行后，程序追加：

```text
assistant：规范 Action JSON
user：对应 Observation
```

下一轮模型重新读取完整列表，因此能够知道已经执行了哪些工具、获得了什么结果，以及原始任务还有哪些部分尚未完成。

本章暂时不建立复杂 `AgentState`。当前执行进度主要保存在 `messages` 中。

## Finish 与 Max Steps

`finish` 是正常结束信号：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
```

Parser 接受后，Controller 读取 `answer` 并返回。`finish` 不对应工具函数，但它仍然占用一个决策 step。

`max_steps` 是硬边界。默认值为：

```python
max_steps=6
```

若所有步骤用完后仍未得到 `finish`，程序抛出：

```text
Agent 在 6 个步骤内没有生成 finish。
```

## 基础终止边界

| 情况 | 当前处理 |
|---|---|
| 合法 `finish` | 正常返回最终回答 |
| 模型返回空文本 | 抛出 `RuntimeError` |
| Action 未通过 Parser | 抛出 `ActionParseError` |
| 工具抛出 `TypeError` 或 `ValueError` | 转换为失败 Observation，继续下一轮 |
| 达到 `max_steps` 仍未 `finish` | 抛出 `RuntimeError` |

本章不进行格式重试、工具自动重试或重复 Action 检测。

## 工具失败仍可进入下一轮

输入：

```text
请计算 10 除以 0，并根据实际执行结果回答。
```

计算器 Action 可以通过 Parser，但工具执行时会失败。程序构造：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "divide", "a": 10, "b": 0}
执行状态：失败
错误类型：ValueError
工具结果：除数不能为 0。
```

这项失败反馈进入下一轮，模型仍可以使用 `finish` 如实说明失败。程序不会自动修改参数，也不会自动重试计算器。

## 失败实验：没有 `finish`

将调用改为：

```python
answer = run_agent(
    client=client,
    model_id=model_id,
    user_task=user_task,
    max_steps=2,
)
```

再运行需要天气、景点和费用计算的任务。即使前两个 Action 都合法、工具也执行成功，任务仍可能因为没有足够步骤生成 `finish` 而终止：

```text
Agent 异常终止：
Agent 在 2 个步骤内没有生成 finish。
```

这说明 Agent Loop 既需要由 `finish` 提供正常退出，也需要由 `max_steps` 提供程序硬边界。

## 失败实验：删除 Observation 更新

临时删除：

```python
messages.append(
    {
        "role": "user",
        "content": observation,
    }
)
```

工具仍会执行，但下一轮模型看不到执行结果，可能重复调用同一工具或编造结果。实验结束后应恢复该消息。

## 当前能力边界

本章已经能够：

```text
围绕同一用户目标持续调用模型
动态执行多个工具
让 Observation 影响下一轮 Action
通过 finish 正常结束
通过 max_steps 防止无限运行
```

本章仍然不能：

```text
自动修复非法 Action
自动重试工具
检测重复行动
保存结构化步骤轨迹
统计模型和工具调用次数
检查 finish 答案是否完整
```

下一章会在当前 Agent Loop 上加入简短 `reason`，让每次工具选择的依据更容易观察。
