# Chapter 04：工具——让程序连接外部能力

本目录对应《第四章 工具：让程序连接外部能力》。代码实现 `Simple Travel Assistant v0.3`：使用三个普通 Python 函数提供模拟天气查询、模拟景点查询和确定性计算，并通过统一的工具描述、工具注册表和工具执行器进行管理。

本章不调用大语言模型。工具名称和参数仍由开发者在 `main.py` 中明确指定，也不包含 Action、Parser、Observation 或 Agent Loop。

## 文件

```text
code/chapter04/
├── README.md
├── main.py
└── tools.py
```

`tools.py` 保存本地模拟数据、三个工具函数、`TOOL_DESCRIPTIONS`、`TOOL_REGISTRY`、`list_tools()` 和 `execute_tool()`。`main.py` 负责手动指定工具调用并展示 Tool Result。

## 环境要求

建议使用 Python 3.10 或更高版本。

本章只使用 Python 标准库，不需要安装 `openai`、`python-dotenv`，也不需要配置 `.env`。

## 运行

从仓库根目录执行：

```bash
python code/chapter04/main.py
```

程序会先列出当前开放的工具，再依次执行天气查询、景点查询和票价计算：

```text
当前可用工具：
- get_weather: 根据城市名称读取本地模拟天气。参数：city，字符串。
- get_attraction_info: 根据景点名称读取本地模拟开放状态、成人票价和活动类型。参数：name，字符串。
- calculator: 执行加、减、乘、除。参数：operation、a、b。

工具名称：get_weather
工具参数：{'city': '北京'}
Tool Result：北京当前模拟天气为晴，温度30℃，湿度45%，微风。

工具名称：get_attraction_info
工具参数：{'name': '故宫'}
Tool Result：故宫位于北京，在当前模拟数据中处于开放状态，成人票价60元，活动类型为室内外步行。以宫殿建筑、历史展陈和步行参观为主。

工具名称：calculator
工具参数：{'operation': 'multiply', 'a': 60, 'b': 2}
Tool Result：120
```

天气、开放状态和票价都来自本地模拟数据，不代表真实世界信息。

## 工具系统结构

本章的统一调用关系是：

```text
tool_name + arguments → execute_tool() → TOOL_REGISTRY
→ Python 工具函数 → Tool Result
```

四个组成部分分别承担以下职责：

| 组成部分 | 当前代码 | 职责 |
|---|---|---|
| Tool Function | `get_weather()` 等 | 真正执行能力并返回结果 |
| Tool Description | `TOOL_DESCRIPTIONS` | 说明工具用途和参数 |
| Tool Registry | `TOOL_REGISTRY` | 保存稳定名称与函数之间的映射 |
| Tool Executor | `execute_tool()` | 统一查找、传参和返回结果 |

`execute_tool()` 不判断“当前应该使用哪个工具”，只执行调用方已经给出的工具名称和参数。

## 为什么工具必须 `return`

工具需要把结果交回调用方：

```python
def get_weather(city: str) -> str:
    return f"{city}当前模拟天气为晴。"
```

若改成只执行 `print()`：

```python
def get_weather(city: str) -> None:
    print(f"{city}当前模拟天气为晴。")
```

函数的正式返回值会变成 `None`。当前执行器会检测到工具没有返回字符串，并报告：

```text
工具“get_weather”必须返回字符串。
```

`print()` 面向终端，`return` 面向调用程序，二者不能互相替代。

## 失败实验：调用未注册工具

将 `main.py` 中第一个工具名称临时改为：

```python
(
    "search_weather",
    {
        "city": "北京",
    },
)
```

再次运行会得到：

```text
工具名称：search_weather
工具参数：{'city': '北京'}
执行失败：未知工具：search_weather。可用工具：get_weather, get_attraction_info, calculator
```

这说明 `TOOL_REGISTRY` 同时是一份允许列表。只有注册表中的函数，才能通过统一工具入口执行。实验结束后应恢复为 `get_weather`。

## 其他失败情况

参数名称错误：

```python
execute_tool(
    tool_name="get_weather",
    arguments={"location": "北京"},
)
```

执行器会把函数调用产生的 `TypeError` 转换为更明确的参数错误。

除数为零：

```python
execute_tool(
    tool_name="calculator",
    arguments={
        "operation": "divide",
        "a": 10,
        "b": 0,
    },
)
```

错误在 `calculator()` 内产生，并由调用方决定如何显示。本章尚未建立统一错误结果、重试或 Observation。

## 当前能力边界

本章已经能够通过统一名称和参数执行三个旅行工具，并得到真实的 Python 返回值。

当前调用仍然写在：

```python
calls = [
    ("get_weather", {"city": "北京"}),
]
```

程序不能把“帮我看看北京的天气”自动转换成工具名称和参数，也不能自行决定是否需要连续执行多个工具。下一章将让大语言模型根据自然语言任务生成结构化 Action，但模型输出仍然不会被直接执行。
