# 第二章 第一次调用大语言模型

上一章的温控程序可以根据温度选择制冷、制热或保持，但它能够理解的输入已经被写进了固定条件。  
当用户改成“房间有些闷热”或“调到适合办公的温度”这类更自然的表达时，程序就开始失去判断力。  
要让程序理解这类语句，我们下一步把“规则”让给大语言模型，而把“执行”放回程序本身。

自然语言很难通过少量固定规则完整覆盖。以旅行咨询为例，用户可能会说：

```text
请简单介绍故宫适合什么样的游客参观。
```

也可能说：

```text
哪些人会比较喜欢参观故宫？
```

两句话的表达方式不同，实际询问的内容却十分接近。要让程序处理这类输入，我们可以把用户问题交给大语言模型，再读取模型生成的回答。

这一章将完成一个最小的城市旅行助手：程序接收一条旅行问题，将它发送给模型服务，然后把回答打印到终端。

## 2.1 Python 程序怎样使用大语言模型

大语言模型通常不会直接存在于当前 Python 文件中。程序需要把输入发送给模型服务，等待服务完成生成，再接收返回结果。

最小过程可以表示为：

```text
Python 程序 → 模型服务 → Python 程序
```

向右的过程是**请求（Request）**。请求中需要包含模型名称和用户消息等信息。向左的过程是**响应（Response）**。响应中包含模型生成的内容以及其他结构化信息。

程序与模型服务之间通过 **API（Application Programming Interface，应用程序编程接口）** 进行通信。API 规定了程序应当怎样发送请求，以及服务会按照什么结构返回响应。

因此，“调用大语言模型”并不是 Python 直接执行模型内部代码，而是一次程序之间的通信：

```text
组织请求 → 发送请求 → 模型生成 → 返回响应 → 提取回答
```

## 2.2 一次调用需要哪些信息

下面是一段模型调用的核心代码：

```python
response = client.chat.completions.create(
    model=model_id,
    messages=messages,
)
```

这段代码使用一个已经配置好的客户端，将 `model` 和 `messages` 发送给模型服务。为了使请求到达正确的位置并通过验证，程序还需要三项连接配置。

| 配置 | 回答的问题 |
|---|---|
| API Key | 谁在调用，是否具有访问权限 |
| Base URL | 请求应当发送到哪里 |
| Model ID | 这次使用哪个模型 |

### API Key：访问服务的凭证

**API Key** 是模型服务用来识别调用者和验证权限的凭证。它的作用接近密码，因此不应直接写进代码：

```python
api_key = "真实密钥"
```

一旦代码被提交到公开仓库，密钥就有泄露风险。更合适的方式是把密钥保存在环境变量中，由程序在运行时读取。

### Base URL：模型服务的地址

**Base URL** 是接口的基础地址。它决定请求被发送到哪个模型服务。

不同服务可能提供不同的 Base URL。若使用实现了兼容接口的其他模型服务，通常只需要修改配置，而不必重写主要调用代码。

Base URL 一般是服务的基础路径，而不是某个具体模型名称，也不是完整的单次请求地址。具体值应以所使用服务的文档为准。

### Model ID：需要调用的模型

同一个服务可能提供多个模型。**Model ID** 用来指定这次请求交给哪一个模型处理。

例如，一个服务可能同时提供通用对话模型、代码模型和轻量模型。程序不能根据模型的自然语言名称自行猜测 Model ID，必须使用服务实际公布的标识。

这三项配置承担不同职责：

```text
API Key：验证身份
Base URL：定位服务
Model ID：选择模型
```

## 2.3 SDK：把接口调用封装成 Python 方法

直接使用 HTTP 发送请求是可行的，但程序需要自行组织请求头、认证信息、JSON 数据和响应解析。为了减少这些通信细节，我们使用 **SDK（Software Development Kit，软件开发工具包）**。

SDK 是服务提供方或社区为某种编程语言准备的开发库。它把底层接口封装为 Python 类和方法，使调用过程更接近普通函数调用。

这里使用 OpenAI Python SDK：

```python
from openai import OpenAI
```

创建客户端：

```python
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
)
```

`client` 是 Python 程序与模型服务通信的客户端对象。创建客户端时只是保存连接配置，并不会立即向模型发送问题。真正的网络请求发生在调用：

```python
client.chat.completions.create(...)
```

SDK 改变的是调用方式，而不是模型调用的本质。完整过程仍然是：

```text
Python 参数
→ SDK 组织接口请求
→ 模型服务生成结果
→ SDK 解析响应
→ Python 对象
```

## 2.4 Message：模型收到的结构化输入

模型接口接收的输入通常不是一个孤立字符串，而是一组有明确角色的**消息（Message）**。

一条最小消息包含两个字段：

```python
{
    "role": "user",
    "content": "请简单介绍故宫适合什么样的游客参观。",
}
```

`content` 保存消息内容，`role` 表示这条消息在当前请求中的作用。

这一章使用两种角色。

### `system`：规定总体回答方式

`system` 消息用于告诉模型应当以什么身份和方式回答。例如：

```python
{
    "role": "system",
    "content": (
        "你是一名城市旅行助手。"
        "请使用简洁、清晰的中文回答。"
    ),
}
```

它描述的是总体要求，而不是用户当前提出的具体问题。

系统消息还可以补充必要边界。例如，模型无法仅凭一般知识保证天气、票价和开放状态始终是最新的，因此可以要求它在涉及这类信息时提醒用户进一步核实：

```python
{
    "role": "system",
    "content": (
        "你是一名城市旅行助手。"
        "请使用简洁、清晰的中文回答。"
        "当问题涉及实时天气、票价或开放状态时，"
        "请明确提醒用户进一步核实。"
    ),
}
```

### `user`：表示用户当前的问题

`user` 消息保存用户希望模型处理的内容：

```python
{
    "role": "user",
    "content": "请简单介绍故宫适合什么样的游客参观。",
}
```

将两条消息放在一起，就得到本次请求的消息列表：

```python
messages = [
    {
        "role": "system",
        "content": (
            "你是一名城市旅行助手。"
            "请使用简洁、清晰的中文回答。"
            "当问题涉及实时天气、票价或开放状态时，"
            "请明确提醒用户进一步核实。"
        ),
    },
    {
        "role": "user",
        "content": "请简单介绍故宫适合什么样的游客参观。",
    },
]
```

模型会先读取总体要求，再处理用户问题。这里的消息顺序表示：

```text
回答要求 → 具体问题
```

消息列表仍然只是当前 Python 进程中的普通数据。只有当程序执行模型调用后，它才会被 SDK 转换为接口请求并发送出去。

## 2.5 准备运行环境

项目中需要安装两个第三方库：

```bash
python -m pip install openai python-dotenv
```

`openai` 用于创建客户端和调用模型接口，`python-dotenv` 用于从 `.env` 文件读取配置。

建议在项目根目录准备下面几个文件：

```text
simple-agent/
├── .env
├── .env.example
├── .gitignore
└── code/
    └── chapter02/
        └── main.py
```

### 使用 `.env` 保存本地配置

在项目根目录创建 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

把占位符替换为实际使用的模型服务配置。

`.env` 的作用是让配置与代码分离。它并没有对密钥进行加密，因此仍然不能公开。

### 使用 `.env.example` 说明需要哪些配置

仓库中可以保存一个不包含真实信息的 `.env.example`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

其他读者可以复制这份文件，再填写自己的配置：

```bash
cp .env.example .env
```

Windows 用户也可以直接在文件管理器中复制并重命名。

### 使用 `.gitignore` 排除真实密钥

在项目根目录的 `.gitignore` 中加入：

```gitignore
.env
```

`.env.example` 可以提交，因为其中只有占位符；真实 `.env` 不应进入版本控制。

## 2.6 读取并检查模型配置

调用 `load_dotenv()` 后，`.env` 中的配置会被加载到当前进程。程序可以使用 `os.getenv()` 读取它们：

```python
import os

from dotenv import load_dotenv


load_dotenv()

api_key = os.getenv("LLM_API_KEY")
base_url = os.getenv("LLM_BASE_URL")
model_id = os.getenv("LLM_MODEL_ID")
```

当变量不存在时，`os.getenv()` 会返回 `None`。若程序继续向下运行，错误可能直到创建客户端或发送请求时才出现。为了让错误位置更清楚，可以定义一个读取必需配置的函数：

```python
def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请检查项目根目录下的 .env 文件。"
        )

    return value
```

随后读取配置：

```python
api_key = require_env("LLM_API_KEY")
base_url = require_env("LLM_BASE_URL")
model_id = require_env("LLM_MODEL_ID")
```

这个函数不会打印任何配置值。尤其是 API Key，即使程序报错，也不应把真实内容写入终端或日志。

## 2.7 完成城市旅行助手

完整代码放在：

```text
code/chapter02/main.py
```

代码如下：

```python
import os

from dotenv import load_dotenv
from openai import OpenAI


SYSTEM_MESSAGE = (
    "你是一名城市旅行助手。"
    "请使用简洁、清晰的中文回答。"
    "当问题涉及实时天气、票价或开放状态时，"
    "请明确提醒用户进一步核实。"
)


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，请检查项目根目录下的 .env 文件。"
        )

    return value


def main() -> None:
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model_id = require_env("LLM_MODEL_ID")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    user_message = input("请输入旅行问题：").strip()

    if not user_message:
        raise ValueError("用户问题不能为空。")

    messages = [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
        },
        {
            "role": "user",
            "content": user_message,
        },
    ]

    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    answer = response.choices[0].message.content

    if not answer:
        raise RuntimeError("模型返回了响应，但没有可用的文本回答。")

    print("\n旅行助手：")
    print(answer)


if __name__ == "__main__":
    main()
```

下面按照实际执行顺序阅读这段代码。

**第一步：加载配置。**

```python
load_dotenv()
```

程序读取 `.env`，再通过 `require_env()` 获得 API Key、Base URL 和 Model ID。

**第二步：创建客户端。**

```python
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
)
```

此时程序已经知道怎样连接模型服务，但还没有发送请求。

**第三步：读取用户问题。**

```python
user_message = input("请输入旅行问题：").strip()
```

`strip()` 去掉输入前后的空白。空问题会被程序直接拒绝。

**第四步：构造消息。**

```python
messages = [
    {"role": "system", "content": SYSTEM_MESSAGE},
    {"role": "user", "content": user_message},
]
```

系统消息规定回答方式，用户消息提供当前问题。

**第五步：发送请求。**

```python
response = client.chat.completions.create(
    model=model_id,
    messages=messages,
)
```

执行到这里时，SDK 才会真正访问模型服务。程序会等待服务返回响应。

**第六步：提取回答。**

```python
answer = response.choices[0].message.content
```

模型服务返回的是结构化响应，不是一个普通字符串。`choices` 保存候选结果，`choices[0]` 表示第一条候选回答，`message.content` 是其中的文本内容。

最后，程序检查文本是否为空，并将回答打印到终端。

## 2.8 运行程序

从项目根目录执行：

```bash
python code/chapter02/main.py
```

输入：

```text
请简单介绍故宫适合什么样的游客参观。
```

终端可能得到：

```text
请输入旅行问题：请简单介绍故宫适合什么样的游客参观。

旅行助手：
故宫适合对中国历史、传统建筑和宫廷文化感兴趣的游客，
也适合喜欢博物馆、摄影和城市文化游览的人群。
参观区域较大，需要较多步行，行动不便的游客应提前规划路线。
```

模型生成具有不确定性。不同模型或不同运行次数可能使用不同措辞，只要回答与问题相关，并遵守系统消息中的基本要求，就说明调用过程已经完成。

这次运行可以按数据变化分成五步：

| 阶段 | 程序中的数据 |
|---|---|
| 用户输入 | `user_message` |
| 构造请求 | `messages` |
| 模型调用 | `client.chat.completions.create(...)` |
| 接收响应 | `response` |
| 提取文本 | `answer` |

最小调用链由此形成：

```text
用户问题 → Message → SDK → 模型服务 → Response → 文本回答
```

## 2.9 失败实验：缺少模型配置

暂时删除 `.env` 中的这一行：

```dotenv
LLM_MODEL_ID=YOUR_MODEL_ID
```

再次运行程序，会在发送网络请求之前得到类似错误：

```text
RuntimeError: 缺少环境变量 LLM_MODEL_ID，请检查项目根目录下的 .env 文件。
```

这个错误说明程序还没有调用模型。失败发生在本地配置检查阶段，而不是模型生成阶段。

重新加入正确的 Model ID 后，程序才会继续创建请求。这个实验说明：

> 模型配置也是程序输入的一部分。配置不完整时，应当尽早停止，而不是带着不确定值继续访问服务。

完成实验后，将 `.env` 恢复为正确配置。

## 2.10 一次调用能够记住什么

当前程序每次运行只构造两条消息：

```text
System Message
User Message
```

模型生成回答后，程序将文本打印出来，然后结束。

假设第一次输入：

```text
请简单介绍故宫适合什么样的游客参观。
```

程序回答后退出。再次启动程序，只输入：

```text
它适合雨天参观吗？
```

第二次请求中只有新的 System Message 和新的 User Message。“它”指的是哪个景点，并没有出现在这次发送的数据中。模型可能根据常见语境进行猜测，也可能要求补充信息，但它没有可靠依据知道上一轮讨论的是故宫。

这不是模型是否足够聪明的问题，而是第二次请求实际收到的信息中缺少了前一次对话。

于是，一个新的问题出现了：

> 程序怎样把已经发生的对话带入下一次模型调用？

## 2.11 本章小结

这一章完成了 Python 程序与大语言模型服务之间的第一次连接。

一次模型调用需要三项连接配置：API Key 用于验证身份，Base URL 指定服务地址，Model ID 指定实际使用的模型。OpenAI Python SDK 将这些配置和 Python 数据转换为接口请求，并把服务返回的数据转换为响应对象。

模型输入由 Message 组成。当前程序使用 `system` 消息规定总体回答方式，使用 `user` 消息保存用户问题。完整过程是：

```text
用户问题
→ 构造 Message
→ SDK 发送请求
→ 模型服务生成
→ 返回 Response
→ 程序提取回答
```

按照第一章建立的判断方式，这个城市旅行助手目前属于一次性的 LLM 应用。它能够理解开放的自然语言问题并生成回答，但一次运行结束后，前面的消息也随之离开了当前请求。

## 习题

**1. 修改系统消息**

将系统消息改为：

```text
你是一名面向小学生的城市旅行助手。
请避免生僻词，每次回答不超过 100 字。
```

保持用户问题不变，比较修改前后的回答风格。指出发生变化的是用户问题还是总体回答要求。

**2. 删除系统消息**

从 `messages` 中删除 `system` 消息，只保留 `user` 消息。观察模型是否仍能回答，并比较回答的语言、长度和结构。

**3. 更换旅行问题**

分别输入下面的问题：

```text
喜欢传统建筑的人适合参观故宫吗？
第一次去北京，怎样安排一天的一般性文化参观？
参观大型博物馆时通常需要做哪些准备？
```

观察不同表达能否被模型正确理解。不要使用当前天气、实时票价或即时开放状态判断调用是否成功。

**4. 查看响应结构**

在提取 `answer` 前临时加入：

```python
print(response)
```

观察响应中除了回答文本外还包含哪些字段。实验结束后删除这行调试输出。

**5. 验证独立请求**

先询问一个具体景点，程序结束后重新运行，只输入：

```text
它适合带老人参观吗？
```

记录模型的回答，并解释为什么第二次调用无法可靠确认“它”指什么。

## 参考资料

1. [The official Python library for the OpenAI API](https://github.com/openai/openai-python).
2. [Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat).
3. [Read key-value pairs from a .env file and set them as environment variables](https://bbc2.github.io/python-dotenv/).
4. [os — Miscellaneous operating system interfaces](https://docs.python.org/3/library/os.html).
