# Chapter 07：工具结果与 Observation

本目录对应《第七章 工具结果与 Observation》，实现 `Simple Travel Assistant v0.6`。

第六章已经能把模型输出转换为经过校验的 `AgentAction`。本章继续执行一次工具，把 Tool Result 连同 Action 和执行状态构造成 Tool Observation，再通过 Observation Message 放入第二次模型请求，使工具执行结果真正影响最终回答。

## 放置位置

```text
code/
└── chapter07/
    ├── README.md
    ├── main.py
    ├── parser.py
    ├── prompts.py
    └── tools.py
```

各文件职责：

| 文件 | 职责 |
|---|---|
| `parser.py` | 定义 `AgentAction`、`ActionParseError` 和 `parse_action()` |
| `tools.py` | 保存三个本地模拟工具、工具注册表和执行器 |
| `prompts.py` | 保存 Action 选择提示词和最终回答提示词 |
| `main.py` | 连接两次模型调用、工具执行和 Observation |
| `README.md` | 说明运行方式、案例和当前能力边界 |

为了让章节代码可以独立运行，`parser.py` 和 `tools.py` 保留前面章节已经建立的完整实现。

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
python code/chapter07/main.py
```

输入：

```text
请查询北京的模拟天气，并告诉我是否需要注意防晒。
```

一次可能的运行过程为：

```text
第一次模型输出：
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}

程序接受的 AgentAction：
AgentAction(name='get_weather', arguments={'city': '北京'})

构造的 Observation：
Observation:
工具名称：get_weather
工具参数：{"city": "北京"}
执行状态：成功
工具结果：北京当前模拟天气为晴，温度30℃，湿度45%，微风。

最终回答：
北京当前模拟天气为晴，温度30℃，需要注意防晒并及时补水。
以上信息来自本地模拟数据。
```

模型输出具有不确定性，具体措辞可能不同。

## 固定调用流程

工具任务的执行顺序是：

```text
用户任务
→ 第一次模型调用生成 Action
→ Parser 得到 AgentAction
→ 执行一次工具
→ 构造 Tool Observation
→ 第二次模型调用生成最终回答
```

如果第一次模型直接生成 `finish`，程序只调用一次模型并返回 `arguments.answer`，不会执行工具，也不会进行第二次调用。

本章的调用次数由程序预先规定：

```text
Finish Action：一次模型调用
Tool Action：两次模型调用 + 一次工具执行
```

## Tool Result、Tool Observation 与 Message

| 概念 | 当前代码 | 作用 |
|---|---|---|
| Tool Result | `execute_tool()` 的返回值 | 工具直接交给 Python 的数据 |
| Tool Observation | `build_observation()` 的返回值 | 描述工具、参数、状态和结果 |
| Observation Message | 第二次请求中的最后一条 `user` 消息 | 让反馈进入模型上下文 |

`print(tool_result)` 只让终端用户看到结果。只有把 Observation 放入 `messages` 并再次发送给模型，模型才真正获得这项信息。

## Action-Observation Pair

第二次请求保留：

```text
原始用户任务
规范 Action JSON
对应 Tool Observation
```

`action_to_json()` 使用已经通过 Parser 的 `AgentAction`，不会把原始 `model_output` 重新放回上下文。

`build_final_answer_messages()` 生成的消息顺序为：

```text
system
→ 原始 user task
→ assistant 规范 Action
→ user Observation
```

Action 与 Observation 必须来自同一次真实执行，不能任意拼接。

## 成功 Observation

```python
action = AgentAction(
    name="calculator",
    arguments={
        "operation": "multiply",
        "a": 60,
        "b": 2,
    },
)

print(execute_action_once(action))
```

输出：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "multiply", "a": 60, "b": 2}
执行状态：成功
工具结果：120
```

## 失败实验：合法 Action 也可能执行失败

输入：

```text
请计算 10 除以 0，并告诉我结果。
```

对应 Action：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "divide",
    "a": 10,
    "b": 0
  }
}
```

该 Action 的字段、参数名称和类型均符合协议，因此可以通过 Parser。计算器真正执行时才抛出 `ValueError`。

`execute_action_once()` 会把错误转换为：

```text
Observation:
工具名称：calculator
工具参数：{"operation": "divide", "a": 10, "b": 0}
执行状态：失败
错误类型：ValueError
工具结果：除数不能为 0。
```

第二次模型调用应根据失败 Observation 说明原因，不能编造计算结果。本章不会自动修改参数、重试工具或重新选择 Action。

## 对照实验：删除 Observation Message

临时从 `build_final_answer_messages()` 中删除：

```python
{
    "role": "user",
    "content": observation,
}
```

工具仍会执行，Python 变量中也仍然保存结果，但第二次请求不再包含该结果。即使模型碰巧回答正确，也没有使用本次工具执行提供的可靠依据。

实验结束后应恢复该消息。

## 当前能力边界

本章已经能够：

```text
解析并校验一个 Action
执行一次工具
构造成功或失败 Tool Observation
把 Action-Observation Pair 放入模型上下文
生成最终自然语言回答
```

本章不负责：

```text
不确定次数的循环
连续多工具调用
工具自动重试
失败后重新选择 Action
最大执行步数
重复行动检测
结构化执行轨迹
```

若任务同时要求查询天气、读取景点信息并计算门票总价，当前程序最多只能执行其中一个工具。下一章将把固定两阶段流程改造成完整 Agent Loop。
