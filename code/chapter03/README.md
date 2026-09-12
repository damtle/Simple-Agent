# Chapter 03：上下文与对话状态

本目录对应《第三章 上下文与对话状态》。代码实现 `Simple Travel Assistant v0.2`：程序在命令行中持续接收输入，按顺序保存 `system`、`user` 和 `assistant` 消息，并在下一轮请求中重新发送完整 `messages`，从而支持依赖历史的连续追问。

本章实现的是当前 Python 进程中的会话状态，不是长期记忆。程序关闭后，内存中的历史会消失；代码也不包含工具、结构化 Action、Observation 或 Agent Loop。

## 文件

```text
code/chapter03/
├── README.md
└── main.py
```

第三章继续使用项目根目录中的模型配置：

```text
simple-agent/
├── .env
├── .env.example
├── .gitignore
└── code/
    └── chapter03/
```

## 环境要求

建议使用 Python 3.10 或更高版本。安装依赖：

```bash
python -m pip install openai python-dotenv
```

## 模型配置

在项目根目录创建 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

项目根目录的 `.gitignore` 应包含：

```gitignore
.env
```

真实 API Key 不应写进代码或提交到仓库。

## 运行

从仓库根目录执行：

```bash
python code/chapter03/main.py
```

程序启动后支持两个本地命令：

| 命令 | 作用 |
|---|---|
| `/clear` | 清除当前用户与模型历史，但保留 `system` 消息 |
| `/exit` | 结束程序 |

连续对话示例：

```text
城市旅行助手已启动。
输入 /clear 清空当前对话，输入 /exit 结束程序。

你：请简单介绍故宫。

旅行助手：故宫是中国明清两代的皇家宫殿，
以宫殿建筑、历史展陈和传统文化价值闻名。

你：它适合雨天参观吗？

旅行助手：故宫有部分室内展馆，但宫殿之间需要较多室外步行。
雨天参观应准备雨具，并提前核实开放安排。
```

模型回答的具体措辞可能不同。验证重点不是逐字匹配，而是第二轮能否根据历史判断“它”指故宫。

## 状态更新流程

程序启动时：

```text
System
```

用户完成第一轮后：

```text
System → User 1 → Assistant 1
```

用户提出第二个问题并调用模型时：

```text
System → User 1 → Assistant 1 → User 2
```

核心代码对应三步：

```python
messages.append({"role": "user", "content": user_input})
answer = request_answer(client, model_id, messages)
messages.append({"role": "assistant", "content": answer})
```

`messages` 必须在 `while` 循环外创建。若每一轮都重新初始化列表，历史会被丢弃，程序仍然只能处理独立问题。

## `/clear` 为什么重新创建列表

代码使用：

```python
messages = create_initial_messages()
```

而不是：

```python
messages.clear()
```

后者会连同 `system` 消息一起删除。重新创建初始列表可以清除对话历史，同时保留旅行助手的固定回答要求。

## 失败实验：只发送最新问题

原实现发送完整历史：

```python
answer = request_answer(
    client=client,
    model_id=model_id,
    messages=messages,
)
```

可暂时改成只发送系统消息和最新问题：

```python
latest_messages = [
    messages[0],
    messages[-1],
]

answer = request_answer(
    client=client,
    model_id=model_id,
    messages=latest_messages,
)
```

然后依次输入：

```text
请记住，这次旅行的确认代号是 Maple-47。
我的确认代号是什么？
```

只发送最新问题时，第二次请求中不包含 `Maple-47`，模型无法可靠回答。实验结束后应恢复为 `messages=messages`。

## 当前能力边界

本章已经具备：有序消息历史、连续多轮回答、`assistant` 历史保存，以及 `/clear` 会话状态重置。

当前流程仍然是：

```text
等待用户输入 → 调用模型 → 输出文本 → 再次等待用户输入
```

下一轮由用户触发，模型只生成自然语言回答，也不会执行外部操作。因此，这仍然是一个有上下文的多轮 LLM 应用，而不是完整 Agent Loop。
