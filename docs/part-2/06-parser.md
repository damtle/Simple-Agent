# 第六章 解析与校验模型行动

第五章中的城市旅行助手已经能够把自然语言任务转换为结构化 Action。用户输入：

```text
请查询北京的模拟天气。
```

模型可能返回：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

这段输出在人看来已经表达得很清楚，但 Python 接收到的仍然只是一个字符串：

```python
model_output: str
```

字符串没有 `action` 属性，也不能证明其中的 JSON 语法正确。即使它能够被解析成字典，也不能证明工具名称存在、参数名称正确，或者参数类型符合工具接口。

因此，模型输出不能因为“看起来合理”就被程序接受。程序需要先把文本转换为 Python 数据，再按照第五章的 Action Protocol 检查它。只有全部检查通过后，这段外部文本才能成为程序内部认可的行动对象。

这一章建立的正是这道边界：

```text
不可信的 model_output
→ 解析与校验
→ AgentAction 或 ActionParseError
```

## 6.1 为什么不能直接读取模型输出

假设模型返回：

```python
model_output = """
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
"""
```

直接执行：

```python
print(model_output["action"])
```

程序会报错，因为 `model_output` 是字符串，不是字典。字符串只能按照字符位置读取，不能按照 JSON 字段读取。

Python 可以使用 `json.loads()` 将 JSON 文本转换为 Python 对象：

```python
import json

data = json.loads(model_output)

print(data["action"])
print(data["arguments"])
```

输出为：

```text
get_weather
{'city': '北京'}
```

这一步解决了“字符串怎样变成 Python 数据”的问题，但还没有解决“这份数据是否符合当前行动协议”的问题。

下面的内容也是合法 JSON：

```json
{
  "name": "get_weather",
  "parameters": {
    "city": "北京"
  }
}
```

`json.loads()` 可以成功解析它，但第五章规定的字段是 `action` 和 `arguments`，程序不能把 `name` 和 `parameters` 自动当成同义字段。

下面的内容同样是合法 JSON：

```json
{
  "action": "search_web",
  "arguments": {
    "query": "北京旅游新闻"
  }
}
```

它具有正确的顶层结构，但当前程序没有 `search_web` 工具。

还有一种情况：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": "60",
    "b": 2
  }
}
```

字段名称都正确，但 `"60"` 是字符串，而计算器需要数字。

由此可以看出，模型输出至少要经过两个阶段：

```text
JSON 解析：文本是否符合 JSON 语法
协议校验：解析后的数据是否符合 Action Protocol
```

> `json.loads()` 只能理解 JSON 语法，不能替程序判断一个行动是否可以被接受。

## 6.2 Parser 与 Validation

负责处理模型输出的组件称为 **Parser（解析器）**。

在本书中，我们采用下面的定义：

> **Parser 是接收模型输出文本，将其转换为 Python 数据，并检查它是否符合当前协议的程序组件。**

Parser 内部包含两类工作。

第一类是**解析**：检查输出是否为空，整理有限的格式外壳，再通过 `json.loads()` 得到 Python 对象。

第二类是**校验（Validation）**：检查顶层类型、字段名称、行动名称、参数集合和参数类型。

其中，专门检查 Action Protocol 的过程称为 **Protocol Validation（协议校验）**。它关心的是：

```text
是否只有 action 和 arguments
action 是否为允许的名称
arguments 是否为 JSON 对象
每个行动是否使用了规定参数
参数类型是否正确
```

Parser 不负责判断北京的天气数据是否存在，也不负责计算 `60 × 2`。这些都需要真正执行工具之后才能知道。

本章的处理边界可以整理为：

| 阶段 | 输入 | 输出 | 回答的问题 |
|---|---|---|---|
| Text Normalization | 原始模型字符串 | 规范化文本 | 是否存在可以安全去除的格式外壳 |
| JSON Parsing | 规范化文本 | Python 对象 | 文本是否符合 JSON 语法 |
| Protocol Validation | Python 对象 | 合法行动数据 | 字段、行动和参数是否符合协议 |
| Action Construction | 合法行动数据 | `AgentAction` | 怎样表示程序已经接受的行动 |

只要其中任一步失败，Parser 都不会创建 `AgentAction`。

## 6.3 用 AgentAction 表示程序认可的行动

若程序始终使用普通字典表示行动，几个不同阶段很容易混在一起：

```python
model_output: str
parsed_data: dict[str, object]
validated_data: dict[str, object]
```

它们看起来相似，但可信程度不同。`model_output` 完全来自模型；`parsed_data` 只证明 JSON 语法正确；只有经过完整校验的数据，才能被程序当作行动使用。

为了明确区分这些阶段，我们定义一个数据类：

```python
from dataclasses import dataclass


@dataclass
class AgentAction:
    name: str
    arguments: dict[str, object]
```

例如：

```python
action = AgentAction(
    name="get_weather",
    arguments={
        "city": "北京",
    },
)
```

这里使用属性 `name`，而不是继续沿用 JSON 字段名 `action`。这样可以区分外部协议和程序内部对象：

| 外部模型文本 | 程序内部对象 |
|---|---|
| `data["action"]` | `agent_action.name` |
| `data["arguments"]` | `agent_action.arguments` |

在本书中：

> **AgentAction 是通过解析和协议校验后，由程序创建的内部行动对象。**

它表示“当前 Parser 接受了这项行动”，但不表示工具一定会成功。例如：

```python
AgentAction(
    name="get_weather",
    arguments={"city": "成都"},
)
```

其中 `city` 是非空字符串，参数结构也正确，因此可以成为 `AgentAction`。至于本地模拟数据中是否存在成都，要等天气工具真正执行时才能知道。

同样：

```python
AgentAction(
    name="calculator",
    arguments={
        "operation": "divide",
        "a": 10,
        "b": 0,
    },
)
```

在协议层面也是合法行动。`b` 是数字，`divide` 是允许的运算名称。除数为零属于计算器执行时才会发现的问题，不应被伪装成 JSON 或协议错误。

## 6.4 用 ActionParseError 拒绝不合法输出

解析过程中可能发生多种问题：

```text
输出为空
JSON 语法错误
顶层不是对象
缺少 action
arguments 不是对象
行动名称不存在
参数名称错误
参数类型错误
```

如果任由 `JSONDecodeError`、`KeyError`、`TypeError` 和 `ValueError` 分别向外传播，调用者很难判断这些异常是否都来自同一条边界。

因此，本章定义一个专门异常：

```python
class ActionParseError(ValueError):
    """模型输出无法被解析，或未通过 Action Protocol 校验。"""
```

当 Parser 拒绝模型输出时，统一抛出 `ActionParseError`：

```python
raise ActionParseError("Action 缺少字段：arguments。")
```

调用方只需要处理一种结果：

```python
try:
    action = parse_action(model_output)
except ActionParseError as error:
    print(f"Action 解析失败：{error}")
else:
    print(action)
```

这使 `parse_action()` 的接口非常明确：

```text
成功：返回 AgentAction
失败：抛出 ActionParseError
```

`ActionParseError` 不负责自动重写模型输出。它只是明确告诉调用方：当前文本没有通过程序边界，不能继续被当作合法行动使用。

## 6.5 Text Normalization：只整理格式外壳

模型可能在 JSON 前后加入空行，也可能把整个 JSON 放进 Markdown 代码块：

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

这些字符不属于行动语义。Parser 可以在正式解析前进行有限的 **Text Normalization（文本标准化）**。

本章只允许两种整理：

1. 去除整段文本首尾的空白；
2. 当整个输出被一个完整 Markdown 代码围栏包裹时，去除最外层围栏。

实现如下：

```python
def normalize_model_output(model_output: str) -> str:
    if not isinstance(model_output, str):
        raise ActionParseError("模型输出必须是字符串。")

    text = model_output.strip()

    if not text:
        raise ActionParseError("模型输出为空。")

    lines = text.splitlines()
    first_line = lines[0].strip()
    last_line = lines[-1].strip()

    if first_line.startswith("```"):
        if first_line not in {"```", "```json", "```JSON"}:
            raise ActionParseError(
                "只允许使用未标注语言或 json 标记的代码围栏。"
            )

        if last_line != "```":
            raise ActionParseError("Markdown 代码围栏没有完整闭合。")

        text = "\n".join(lines[1:-1]).strip()

        if not text:
            raise ActionParseError("Markdown 代码围栏中没有内容。")

    elif any(line.strip().startswith("```") for line in lines):
        raise ActionParseError(
            "Markdown 代码围栏必须完整包裹整个模型输出。"
        )

    return text
```

这里有意不从任意说明文字中寻找第一个 `{` 和最后一个 `}`。例如：

```text
我建议使用天气工具。

{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

当前 Parser 会拒绝它，而不是自动忽略第一句话。原因在于，自动截取花括号可能掩盖多个 JSON、附加指令或混合内容。文本标准化可以去除明确、无歧义的格式外壳，但不应该把一段任意文本猜测成合法协议。

这一原则可以概括为：

> **格式外壳可以有限整理，行动语义和协议结构不能由 Parser 猜测。**

## 6.6 从 JSON 语法进入 Protocol Validation

文本标准化后，Parser 使用 `json.loads()` 解析 JSON：

```python
import json


def parse_json_object(text: str) -> dict[str, object]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ActionParseError(
            "模型输出不是合法 JSON："
            f"{error.msg}，第 {error.lineno} 行，"
            f"第 {error.colno} 列。"
        ) from error

    if not isinstance(data, dict):
        raise ActionParseError(
            "Action 的顶层 JSON 必须是对象。"
        )

    return data
```

顶层必须是 JSON 对象。下面的数组虽然是合法 JSON，但不是合法 Action：

```json
[
  {
    "action": "get_weather",
    "arguments": {
      "city": "北京"
    }
  }
]
```

本书的协议规定每次只输出一个对象，因此 Parser 应当拒绝数组，而不是自动取出其中第一个元素。

完成 JSON 解析后，程序开始 Protocol Validation。第一步是检查顶层字段是否严格等于：

```text
action
arguments
```

可以编写一个通用函数：

```python
def validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    actual = set(data)
    missing = expected - actual
    extra = actual - expected

    details = []

    if missing:
        details.append(
            "缺少 " + ", ".join(sorted(missing))
        )

    if extra:
        details.append(
            "多出 " + ", ".join(sorted(extra))
        )

    if details:
        raise ActionParseError(
            f"{context}字段不正确："
            + "；".join(details)
            + "。"
        )
```

顶层检查为：

```python
validate_exact_fields(
    data=data,
    expected={"action", "arguments"},
    context="Action 顶层",
)
```

严格检查额外字段可以防止模型自行扩展协议。例如：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  },
  "execute_immediately": true
}
```

当前协议没有 `execute_immediately`。Parser 既不能执行它，也不应默默忽略它，否则模型和程序对协议的理解会逐渐分离。

接下来检查字段类型：

```python
action_name = data["action"]
arguments = data["arguments"]

if not isinstance(action_name, str):
    raise ActionParseError("action 必须是字符串。")

if not action_name:
    raise ActionParseError("action 不能为空。")

if action_name != action_name.strip():
    raise ActionParseError(
        "action 前后不能包含空白字符。"
    )

if not isinstance(arguments, dict):
    raise ActionParseError(
        "arguments 必须是 JSON 对象。"
    )
```

至此，程序只知道行动名称是一个格式正确的字符串，参数是一个对象。它还需要针对不同 Action 检查具体参数。

## 6.7 校验四种 Action

第五章允许四种行动：

```text
get_weather
get_attraction_info
calculator
finish
```

每种行动使用不同的参数协议。

### 天气与景点参数

天气工具必须且只能包含 `city`：

```python
def validate_weather_arguments(
    arguments: dict[str, object],
) -> None:
    validate_exact_fields(
        data=arguments,
        expected={"city"},
        context="get_weather.arguments",
    )

    city = arguments["city"]

    if not isinstance(city, str):
        raise ActionParseError(
            "get_weather.city 必须是字符串。"
        )

    if not city.strip():
        raise ActionParseError(
            "get_weather.city 不能为空。"
        )
```

景点工具采用相同结构，只是参数名为 `name`：

```python
def validate_attraction_arguments(
    arguments: dict[str, object],
) -> None:
    validate_exact_fields(
        data=arguments,
        expected={"name"},
        context="get_attraction_info.arguments",
    )

    name = arguments["name"]

    if not isinstance(name, str):
        raise ActionParseError(
            "get_attraction_info.name 必须是字符串。"
        )

    if not name.strip():
        raise ActionParseError(
            "get_attraction_info.name 不能为空。"
        )
```

这两个函数只检查参数名称和类型，不检查城市或景点是否存在于本地模拟数据中。

因此：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "成都"
  }
}
```

可以通过 Parser。它描述的是一个格式合法的天气查询，数据是否存在属于工具层问题。

### 计算器参数

计算器要求三个参数：

```text
operation
a
b
```

其中 `operation` 只能是 `add`、`subtract`、`multiply` 或 `divide`，`a` 与 `b` 必须是 JSON 数字。

```python
import math


def is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False

    if isinstance(value, int):
        return True

    if isinstance(value, float):
        return math.isfinite(value)

    return False


def validate_calculator_arguments(
    arguments: dict[str, object],
) -> None:
    validate_exact_fields(
        data=arguments,
        expected={"operation", "a", "b"},
        context="calculator.arguments",
    )

    operation = arguments["operation"]

    if not isinstance(operation, str):
        raise ActionParseError(
            "calculator.operation 必须是字符串。"
        )

    allowed_operations = {
        "add",
        "subtract",
        "multiply",
        "divide",
    }

    if operation not in allowed_operations:
        raise ActionParseError(
            f"不支持的计算操作：{operation!r}。"
        )

    if not is_finite_number(arguments["a"]):
        raise ActionParseError(
            "calculator.a 必须是有限数字。"
        )

    if not is_finite_number(arguments["b"]):
        raise ActionParseError(
            "calculator.b 必须是有限数字。"
        )
```

这里不能只写：

```python
isinstance(value, (int, float))
```

因为在 Python 中：

```python
isinstance(True, int)
```

结果为 `True`。但 JSON 中的 `true` 不应该被当作数字 `1` 使用，因此需要明确排除 `bool`。

Parser 也不会把字符串 `"60"` 自动转换为数字 `60`。这种转换看似方便，却是在替模型修正参数类型。协议已经要求模型输出 JSON 数字，违反协议时应当明确拒绝。

### Finish 参数

`finish` 必须且只能包含非空的 `answer`：

```python
def validate_finish_arguments(
    arguments: dict[str, object],
) -> None:
    validate_exact_fields(
        data=arguments,
        expected={"answer"},
        context="finish.arguments",
    )

    answer = arguments["answer"]

    if not isinstance(answer, str):
        raise ActionParseError(
            "finish.answer 必须是字符串。"
        )

    if not answer.strip():
        raise ActionParseError(
            "finish.answer 不能为空。"
        )
```

Parser 能够确认 `answer` 是非空字符串，却不能确认其中事实一定正确。例如：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "北京位于法国。"
  }
}
```

在结构上符合协议，仍然可以成为 `AgentAction`。内容是否正确属于另一类检查，不能由结构校验假装解决。

## 6.8 实现完整的 parse_action()

本章代码目录为：

```text
code/chapter06/
├── action.py
├── parser.py
├── main.py
└── README.md
```

`action.py` 保存程序内部行动对象和解析异常：

```python
from dataclasses import dataclass


@dataclass
class AgentAction:
    name: str
    arguments: dict[str, object]


class ActionParseError(ValueError):
    """模型输出无法被解析，或未通过 Action Protocol 校验。"""
```

`parser.py` 将前面的步骤连接起来：

下面只保留连接前面组件的 `parse_action()`；导入、配置和辅助函数见 [code/chapter06/parser.py](https://github.com/damtle/Simple-Agent/blob/main/code/chapter06/parser.py)。运行时使用该完整文件。

```python
def parse_action(model_output: str) -> AgentAction:
    """把模型原始字符串转换为经过校验的 AgentAction。"""
    text = normalize_model_output(model_output)
    data = parse_json_object(text)
    action_name, arguments = validate_action_data(data)

    return AgentAction(
        name=action_name,
        arguments=dict(arguments),
    )
```

这份实现遵循一个固定顺序：

```text
normalize_model_output()
→ parse_json_object()
→ validate_action_data()
→ AgentAction
```

任何一步抛出 `ActionParseError`，程序都不会得到 `AgentAction`。

模型文本的规模同样需要检查。完整 `parser.py` 中的 `_load_bounded_json()` 限制输出长度、嵌套深度和整数位数，并把超限情况转换成解析错误。字段正确不代表输入规模可接受；后续独立快照沿用这一边界。

## 6.9 在主线程序中接入 Parser

`main.py` 仍然向模型请求 Action，但收到文本后不再直接结束，而是把结果交给 `parse_action()`。

为了让本章目录可以独立运行，行动提示词继续放在 `main.py` 中。它与第五章使用同一组工具名称和参数协议。

下面只保留连接前面组件的 `main()`；导入、配置和辅助函数见 [code/chapter06/main.py](https://github.com/damtle/Simple-Agent/blob/main/code/chapter06/main.py)。运行时使用该完整文件。

```python
def main() -> None:
    """请求模型行动，并将其交给 Parser 检查。"""
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    user_task = input("请输入旅行任务：").strip()

    if not user_task:
        raise ValueError("用户任务不能为空。")

    model_output = request_action(
        client=client,
        model_id=model_id,
        user_task=user_task,
    )

    print("\n模型原始输出：")
    print(model_output)

    try:
        action = parse_action(model_output)
    except ActionParseError as error:
        print(f"\nAction 解析失败：{error}")
        return

    print("\n程序接受的 AgentAction：")
    print(f"name = {action.name}")
    print(
        "arguments = "
        + json.dumps(
            action.arguments,
            ensure_ascii=False,
        )
    )
```

程序现在只做两件事：

```text
请求模型生成 Action
→ 解析并校验 Action
```

它没有调用 `get_weather`、`get_attraction_info` 或 `calculator`。即使得到合法的 `AgentAction`，程序也只是将对象打印到终端。

`README.md` 可以写成：

````markdown
# Chapter 06

本章将模型返回的原始字符串转换为经过校验的
`AgentAction`。

运行：

```bash
python code/chapter06/main.py
```

成功时，程序输出 `AgentAction` 的名称与参数；
失败时，输出 `ActionParseError`。

本章不会执行任何旅行工具。
````

## 6.10 运行成功案例

从项目根目录执行：

```bash
python code/chapter06/main.py
```

输入：

```text
请查询北京的模拟天气。
```

模型可能返回：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

终端输出：

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

这时，字符串已经经过以下检查：

```text
输出非空
→ JSON 语法正确
→ 顶层是对象
→ 字段只有 action 和 arguments
→ get_weather 是允许行动
→ 参数只有 city
→ city 是非空字符串
```

`finish` 也可以成为合法行动。输入：

```text
请用一句话说明参观博物馆前为什么要提前规划。
```

模型可能输出：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "提前规划有助于确认开放安排、预约要求和参观路线。"
  }
}
```

Parser 会得到：

```text
name = finish
arguments = {"answer": "提前规划有助于确认开放安排、预约要求和参观路线。"}
```

程序仍然只打印 `AgentAction`。它不会把 `finish.answer` 当作最终界面逻辑，也不会执行任何工具。

## 6.11 失败实验：Parser 不替模型猜测

可以直接在 Python 交互环境中测试 `parse_action()`：

```python
from parser import parse_action
```

先输入错误工具名称和错误参数名称：

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

结果为：

```text
ActionParseError:
未知行动：'weather'。
允许的行动：get_weather, get_attraction_info, calculator, finish。
```

Parser 不会把：

```text
weather → get_weather
location → city
```

自动修正为它猜测的含义。因为一旦允许这种行为，程序就无法区分“明显笔误”和“模型正在使用另一套协议”。

再测试字符串数字：

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

结果为：

```text
ActionParseError:
calculator.a 必须是有限数字。
```

Parser 也不会执行：

```python
float("60")
```

协议要求模型输出数字，程序便按照数字检查。拒绝错误输入比悄悄修改输入更容易定位问题。

最后测试一项结构合法但数据可能不存在的行动：

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

这次会成功返回：

```python
AgentAction(
    name="get_weather",
    arguments={"city": "成都"},
)
```

因为“成都”是合法的非空字符串。Parser 不读取天气数据，也不知道工具执行后是否能够找到结果。

这三个案例共同说明：

```text
Parser 检查协议
不替模型改写协议
也不提前执行工具业务
```

## 6.12 当前系统快照

完成这一章后，城市旅行助手已经建立了模型输出与程序内部行动之间的边界。

当前流程为：

```text
用户任务
→ LLM
→ model_output: str
→ Text Normalization
→ JSON Parsing
→ Protocol Validation
→ AgentAction
```

若任何检查失败，流程变为：

```text
model_output: str
→ Parser
→ ActionParseError
```

与第五章相比，程序不再只是打印一段看起来像 JSON 的文本。它已经能够明确判断：

```text
JSON 是否合法
顶层结构是否正确
行动名称是否允许
参数集合是否完整
参数类型是否符合协议
```

不过，`AgentAction` 仍然只是一项经过认可的行动请求。天气还没有被查询，景点信息还没有被读取，计算器也没有运行。程序下一步需要执行这项行动，并决定怎样把执行结果重新提供给模型。

## 6.13 本章小结

这一章建立了 Action Parser。

Parser 接收不可信的 `model_output: str`，先进行有限的 Text Normalization，再解析 JSON，并完成 Protocol Validation。通过检查的数据被转换为 `AgentAction`；任何语法、结构或参数问题都会产生 `ActionParseError`。

`AgentAction` 表示程序已经接受当前行动的结构，不表示工具执行成功，也不保证 `finish.answer` 中的事实正确。Parser 只负责协议边界，不负责执行工具、验证业务数据，或者替模型猜测并修改行动语义。

完成本章后，应当能够回答：

1. 为什么 `json.loads()` 不能代替完整的 Action 校验？
2. Parser、Validation 和 Protocol Validation 分别表示什么？
3. `AgentAction` 与模型原始 JSON 有什么区别？
4. 为什么错误输出应产生 `ActionParseError`，而不是被自动修正？
5. 为什么 `get_weather(city="成都")` 可以通过 Parser，却仍可能无法得到工具结果？

## 习题

**1. 检查顶层结构**

分别测试：

```json
{
  "action": "get_weather"
}
```

和：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  },
  "run": true
}
```

记录两个错误信息，并说明一个属于缺失字段，另一个属于额外字段。

**2. 检查 JSON 类型**

把顶层对象改成数组：

```json
[
  {
    "action": "get_weather",
    "arguments": {
      "city": "北京"
    }
  }
]
```

观察为什么合法 JSON 仍然不能成为合法 Action。

**3. 检查 Markdown 围栏**

使用一个完整代码围栏包裹天气 Action，确认 Parser 可以去除围栏。随后在围栏外增加一句说明文字，观察 Parser 为什么拒绝。

**4. 增加参数错误案例**

分别测试：

```json
{"action": "get_weather", "arguments": {"location": "北京"}}
```

```json
{"action": "calculator", "arguments": {"operation": "power", "a": 2, "b": 3}}
```

```json
{"action": "finish", "arguments": {"answer": ""}}
```

说明每个错误发生在 Protocol Validation 的哪一层。

**5. 解释协议与业务边界**

比较下面两个 Action：

```json
{"action": "calculator", "arguments": {"operation": "divide", "a": 10, "b": "0"}}
```

```json
{"action": "calculator", "arguments": {"operation": "divide", "a": 10, "b": 0}}
```

说明为什么第一个应被 Parser 拒绝，而第二个可以成为 `AgentAction`，但执行时仍可能失败。

## 参考资料

1. [json — JSON encoder and decoder](https://docs.python.org/3/library/json.html).
2. [dataclasses — Data Classes](https://docs.python.org/3/library/dataclasses.html).
3. [Errors and Exceptions](https://docs.python.org/3/tutorial/errors.html).
4. [The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259). RFC 8259, 2017.
