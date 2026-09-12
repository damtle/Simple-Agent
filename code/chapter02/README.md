# Chapter 02：第一次调用大语言模型

本目录对应《第二章 第一次调用大语言模型》。代码实现 `Simple Travel Assistant v0.1`：读取一条旅行问题，构造 `system` 和 `user` 消息，通过 OpenAI Python SDK 调用一次兼容 Chat Completions 的模型服务，再从结构化响应中提取文本回答。

本章仍然是一次性的 LLM 应用，不保存多轮历史，也不包含工具、结构化 Action、Observation 或 Agent Loop。

## 文件

```text
code/chapter02/
├── README.md
└── main.py
```

项目根目录还需要：

```text
simple-agent/
├── .env
├── .env.example
├── .gitignore
└── code/
    └── chapter02/
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

三个配置分别表示：

| 配置 | 作用 |
|---|---|
| `LLM_API_KEY` | 验证调用身份和访问权限 |
| `LLM_BASE_URL` | 指定模型服务地址 |
| `LLM_MODEL_ID` | 指定本次调用使用的模型 |

仓库中的 `.env.example` 只应保存占位符：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

项目根目录的 `.gitignore` 应包含：

```gitignore
.env
```

真实 API Key 不应写进代码、提交到仓库或打印到终端。

## 运行

从仓库根目录执行：

```bash
python code/chapter02/main.py
```

输入示例：

```text
请简单介绍故宫适合什么样的游客参观。
```

终端可能得到：

```text
请输入旅行问题：请简单介绍故宫适合什么样的游客参观。

旅行助手：
故宫适合对中国历史、传统建筑和宫廷文化感兴趣的游客，
也适合喜欢博物馆、摄影和城市文化游览的人群。
```

模型输出具有不确定性，具体措辞可能不同。只要回答与问题相关，并遵守系统消息中的基本要求，就说明本次调用已经完成。

## 调用流程

```text
用户问题 → Message → SDK → 模型服务 → Response → 文本回答
```

代码中的对应关系：

| 阶段 | 代码中的对应内容 |
|---|---|
| 加载配置 | `load_dotenv()` 与 `require_env()` |
| 创建客户端 | `OpenAI(api_key=..., base_url=...)` |
| 用户输入 | `user_message` |
| 构造消息 | `messages` |
| 发送请求 | `client.chat.completions.create(...)` |
| 接收响应 | `response` |
| 提取回答 | `response.choices[0].message.content` |

## 失败实验：缺少模型配置

暂时删除 `.env` 中的：

```dotenv
LLM_MODEL_ID=YOUR_MODEL_ID
```

再次运行时，程序会在发送网络请求前终止：

```text
RuntimeError: 缺少环境变量 LLM_MODEL_ID，请检查项目根目录下的 .env 文件。
```

这个失败发生在本地配置检查阶段。完成实验后，应恢复正确配置。

## 当前能力边界

本章程序每次只发送：

```text
System Message + 当前 User Message
```

模型回答被打印后，程序立即结束。再次运行时，上一轮内容不会自动进入新的请求，因此程序无法可靠理解“它”“继续介绍”或“刚才提到的景点”。多轮对话将在第三章实现。
