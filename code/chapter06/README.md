# Chapter 06：解析与校验模型行动

本目录对应《第六章 解析与校验模型行动》，实现 `Simple Travel Assistant v0.5`。

第五章只能取得模型生成的原始字符串。本章在模型输出和程序内部行动之间建立 Parser 边界：经过 Text Normalization、JSON Parsing 和 Protocol Validation 后，合法输出被转换为 `AgentAction`；任何错误统一产生 `ActionParseError`。

## 放置位置

```text
code/
└── chapter06/
    ├── README.md
    ├── action.py
    ├── main.py
    └── parser.py
```

`action.py` 定义 `AgentAction` 和 `ActionParseError`；`parser.py` 实现文本标准化、JSON 解析及四种 Action 的协议校验；`main.py` 请求模型生成 Action，并把原始字符串交给 Parser。

本章不创建 `tools.py`，也不执行任何旅行工具。合法的 `AgentAction` 只会被打印出来。

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

## 运行主线程序

从项目根目录执行：

```bash
python code/chapter06/main.py
```

输入：

```text
请查询北京的模拟天气。
```

模型可能输出：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

终端显示：

```text
模型原始输出：
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}

程序接受的 AgentAction：
name = get_weather
arguments = {"city": "北京"}
```

当前程序只完成：

```text
请求模型生成 Action
→ 解析并校验 Action
```

它不会真正查询天气。

## Parser 处理顺序

```text
normalize_model_output()
→ parse_json_object()
→ validate_action_data()
→ AgentAction
```

任何一步失败都会抛出 `ActionParseError`，调用方不会得到半合法的行动对象。

## 当前支持的 Action

| Action | 必需参数 | 参数要求 |
|---|---|---|
| `get_weather` | `city` | 非空字符串 |
| `get_attraction_info` | `name` | 非空字符串 |
| `calculator` | `operation`、`a`、`b` | 运算名称合法，`a` 和 `b` 为有限数字 |
| `finish` | `answer` | 非空字符串 |

每层字段都采用严格检查。缺少字段和额外字段都会被拒绝，Parser 不会默默忽略模型自行添加的协议字段。

## Text Normalization 的边界

Parser 只允许两种无歧义的整理：

1. 去除整段文本首尾空白；
2. 当完整输出只由一个 Markdown 代码围栏包裹时，去除最外层围栏。

下面的输出可以被接受：

````text
```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```
````

下面的输出会被拒绝：

````text
我建议使用天气工具。

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```
````

Parser 不会从任意说明文字中寻找花括号，也不会猜测哪一段才是模型真正想表达的 Action。

## 直接测试 Parser

进入章节目录：

```bash
cd code/chapter06
python
```

导入：

```python
from action import ActionParseError
from parser import parse_action
```

### 合法的未知城市

```python
parse_action(
    """
    {
      "action": "get_weather",
      "arguments": {
        "city": "成都"
      }
    }
    """
)
```

返回：

```python
AgentAction(
    name="get_weather",
    arguments={"city": "成都"},
)
```

“成都”是合法的非空字符串，因此可以通过协议校验。数据是否存在属于工具执行阶段，本章不会检查。

### 错误行动名称

```python
parse_action(
    """
    {
      "action": "weather",
      "arguments": {
        "location": "北京"
      }
    }
    """
)
```

产生：

```text
ActionParseError:
未知行动：'weather'。允许的行动：get_weather, get_attraction_info, calculator, finish。
```

Parser 不会自动执行：

```text
weather → get_weather
location → city
```

### 字符串数字

```python
parse_action(
    """
    {
      "action": "calculator",
      "arguments": {
        "operation": "multiply",
        "a": "60",
        "b": 2
      }
    }
    """
)
```

产生：

```text
ActionParseError:
calculator.a 必须是有限数字。
```

Parser 不会把 `"60"` 自动转换为 `60`。

### 协议合法但执行可能失败

```python
parse_action(
    """
    {
      "action": "calculator",
      "arguments": {
        "operation": "divide",
        "a": 10,
        "b": 0
      }
    }
    """
)
```

这个 Action 可以通过 Parser，因为参数名称与类型均符合协议。除数为零属于工具执行错误，不是 Parser 错误。

## 当前能力边界

本章能够判断：

```text
输出是否为空
JSON 语法是否正确
顶层是否为对象
字段是否严格符合协议
行动名称是否允许
参数名称、类型和允许值是否正确
```

本章不负责：

```text
模型格式重试
工具执行
工具执行重试
业务数据是否存在
Observation
Agent 决策重试
完整 Agent Loop
```

下一章将执行一次经过校验的 `AgentAction`，并把 Tool Result 组织成 Observation 重新提供给模型。
