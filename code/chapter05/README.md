# Chapter 05：让模型选择工具

本目录对应《第五章 让模型选择工具》，实现 `Simple Travel Assistant v0.4`。

第四章由开发者手动指定工具名称和参数；本章把工具选择交给大语言模型。程序向模型提供工具说明和 Action Protocol，让模型把自然语言任务转换为 Tool Action 或 Finish Action。

本章的输出仍然只是原始字符串。程序不会调用 `json.loads()`，不会校验字段，也不会执行任何工具。

## 放置位置

```text
code/
└── chapter05/
    ├── README.md
    ├── main.py
    └── prompts.py
```

`prompts.py` 保存工具说明、Action 规则和系统提示词构造函数；`main.py` 读取模型配置、接收用户任务、调用模型并原样打印输出。

本章不复制第四章的 `tools.py`，因为这里只让模型“提出行动”，不执行真实工具。

## 环境要求

建议使用 Python 3.10 或更高版本。

安装依赖：

```bash
python -m pip install openai python-dotenv
```

项目根目录继续使用第二章建立的 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

真实 `.env` 不应提交到 Git 仓库。

## 运行

从项目根目录执行：

```bash
python code/chapter05/main.py
```

程序会等待输入：

```text
请输入旅行任务：
```

输入任务后，它只显示模型原始输出及其 Python 类型：

```text
请输入旅行任务：请查询北京的模拟天气。

模型原始输出：
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}

Python 类型：str
```

模型输出具有不确定性，空格、换行和回答措辞可能不同。

## 当前 Action Protocol

Tool Action：

```json
{
  "action": "工具名称",
  "arguments": {
    "参数名称": "参数值"
  }
}
```

Finish Action：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
```

当前允许的行动名称为：

```text
get_weather
get_attraction_info
calculator
finish
```

`finish` 是协议中的完成行动，不对应 Python 工具函数。

## 建议测试的四类任务

**查询模拟天气**

```text
请查询北京的模拟天气。
```

预期模型选择 `get_weather`，参数为 `city="北京"`。终端不会显示天气结果，因为天气工具尚未执行。

**查询模拟景点信息**

```text
请查询故宫的模拟开放状态和成人票价。
```

预期模型选择 `get_attraction_info`，参数为 `name="故宫"`。

**请求精确计算**

```text
一张票 60 元，两张票一共多少元？
```

预期模型选择 `calculator`，并把“60 元一张、两张”映射为 `multiply`、`60` 和 `2`。程序不会输出 `120`，因为计算器尚未执行。

**不需要工具**

```text
请用一句话说明参观博物馆前为什么要提前规划。
```

预期模型使用 `finish`，在 `arguments.answer` 中直接回答。

还可以测试能力边界：

```text
请直接帮我预订两张故宫门票。
```

当前没有预订工具，模型应使用 `finish` 说明限制，而不是编造 `book_ticket` 或其他不存在的工具。

## Prompt 与程序边界

`prompts.py` 中的工具说明只是一段进入模型上下文的文字。它不会读取天气数据，也不会调用 Python 函数。

Action 系统提示词负责告诉模型：

1. 当前有哪些工具；
2. 每个工具适合什么任务；
3. 参数名称和允许取值；
4. Tool Action 与 Finish Action 的格式；
5. 不得编造未开放工具。

Prompt 只能提高模型遵守协议的概率，不能证明模型输出一定正确。

## 失败实验：放宽输出规则

临时把 `ACTION_RULES` 的前两条改为：

```text
请先用一句话解释你的选择，再输出 JSON Action。
可以使用 Markdown 代码块展示 JSON。
```

模型可能返回：

````text
北京天气需要通过模拟天气工具获取。

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```
````

人类能够看出其中包含正确 Action，但 Python 得到的是包含解释文字和 Markdown 标记的完整 `str`。

模型也可能生成外形规整、语义却不符合协议的内容：

```json
{
  "action": "weather",
  "arguments": {
    "location": "北京"
  }
}
```

当前程序不会发现这些问题，因为它只打印字符串。这正是下一章需要 Parser 与 Validation 的原因。

实验结束后，应恢复 `ACTION_RULES` 原有约束。

## 当前能力边界

当前流程为：

```text
用户自然语言任务
→ 工具说明与 Action Protocol
→ LLM
→ 原始 JSON Action 字符串
```

本章已经能够让模型在 `get_weather`、`get_attraction_info`、`calculator` 和 `finish` 之间作出语义选择。

它仍然不能确认：

```text
输出是否为合法 JSON
是否包含 action 和 arguments
行动名称是否属于允许范围
参数名称和参数类型是否正确
finish 是否包含非空 answer
```

因此，不要在本章中把 `model_output` 直接交给第四章的 `execute_tool()`。下一章会把原始字符串转换为经过校验的 `AgentAction`。
