# 第五章 让模型选择工具

第四章已经建立了一组可以实际执行的旅行工具。只要开发者明确写出工具名称和参数，程序就能从注册表中找到对应函数，并取得工具返回的结果：

```python
result = execute_tool(
    tool_name="get_weather",
    arguments={
        "city": "北京",
    },
)
```

问题在于，真实用户不会使用这种方式表达需求。他更可能输入：

```text
请查询北京的模拟天气。
```

这句话没有直接给出 `get_weather`，也没有把“北京”组织成 Python 字典。虽然程序已经拥有工具，但用户的自然语言与工具执行器需要的数据之间，仍然缺少一次转换。

大语言模型可以理解“查询天气”“介绍景点”和“计算总价”等不同意图，也能够从句子中提取城市、景点和数字。现在，我们不再让它直接生成一段最终回答，而是让它根据用户任务选择下一步操作，并按照固定结构写出工具名称和参数。

例如：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

这段内容还没有执行天气工具。它只是模型提出的一项行动请求，但它第一次把开放的自然语言任务转换成了程序可以进一步处理的结构。

## 5.1 工具已经存在，为什么程序仍然不会选择

第四章的 `execute_tool()` 接收两个参数：

```python
execute_tool(
    tool_name="get_weather",
    arguments={"city": "北京"},
)
```

它能够回答“怎样执行一个已经确定的工具调用”，却不能回答“用户现在想调用哪个工具”。

假设我们使用普通条件判断完成工具选择：

```python
if "天气" in user_input:
    tool_name = "get_weather"
elif "景点" in user_input:
    tool_name = "get_attraction_info"
elif "计算" in user_input:
    tool_name = "calculator"
```

这种方法可以处理少量固定表达，但很快会遇到问题。用户可能说“北京今天热不热”“故宫开不开门”或者“六十元一张，两张多少钱”，句子中未必出现“天气”“景点”或“计算”这些关键词。随着表达方式增加，条件分支也会不断增长。

大语言模型更适合处理这种开放表达。它可以把不同说法映射到相同的程序意图：

| 用户表达 | 希望得到的行动 |
|---|---|
| 帮我看看北京的模拟天气 | `get_weather(city="北京")` |
| 查询一下故宫的模拟开放信息 | `get_attraction_info(name="故宫")` |
| 60 元一张，两张一共多少元 | `calculator(operation="multiply", a=60, b=2)` |

不过，模型理解了用户意图，并不表示 Python 程序已经获得了可用参数。若模型只回答：

```text
我认为应该调用天气查询工具。
```

人类可以理解这句话，程序却仍然需要从中猜测工具名称、参数名称和参数值。要让模型输出成为程序接口的一部分，还需要一种稳定的表达方式。

## 5.2 从自然语言回答到结构化 Action

前面的城市旅行助手主要生成自然语言回答。例如，用户询问：

```text
参观大型博物馆前为什么要提前规划？
```

模型可以直接回答：

```text
提前规划有助于确认开放安排、预约要求和参观路线，也能减少现场等待。
```

这种回答面向用户，目标是清楚、自然地传达信息。

工具选择则面向程序。用户输入：

```text
请查询北京的模拟天气。
```

模型此时不应编写一段天气描述，因为它还没有调用天气工具，也没有取得工具结果。它应该说明程序下一步要做什么：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

在本书中，第一章已经把 Action 解释为 Agent 选择并交给环境执行的行动。从这一章开始，我们把它具体化为一种适合语言模型和 Python 程序交换信息的形式：

> **Action 是模型根据当前任务生成的结构化行动请求，用于描述程序下一步应当执行的操作及其参数。**

一个 Action 至少回答两个问题：

```text
执行什么？
执行时需要哪些参数？
```

在 JSON 中，这两个问题分别由 `action` 和 `arguments` 字段表达：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

这里需要区分概念名称与字段名称：

| 写法 | 含义 |
|---|---|
| Action | 完整的结构化行动请求 |
| `action` | JSON 中保存行动名称的字段 |
| `arguments` | JSON 中保存行动参数的字段 |

模型输出 Action，只表示它建议程序执行这项操作。天气尚未被查询，景点数据尚未被读取，乘法也尚未交给计算器。真正的环境变化只能由 Python 程序执行函数后产生。

## 5.3 定义最小 Action Protocol

模型与程序需要对输出结构达成约定。这项约定称为 **Action Protocol（行动协议）**。

> **Action Protocol 是模型与程序共同遵守的结构化输出约定。它规定一个行动应当包含哪些字段、字段表达什么含义，以及允许使用哪些行动名称。**

本书使用的最小协议如下：

```json
{
  "action": "行动名称",
  "arguments": {
    "参数名称": "参数值"
  }
}
```

其中：

| 字段 | 类型 | 含义 |
|---|---|---|
| `action` | 字符串 | 模型建议程序执行的行动名称 |
| `arguments` | JSON 对象 | 执行该行动所需的参数 |

`arguments` 必须始终存在。没有参数时，也使用空对象：

```json
{
  "action": "some_action",
  "arguments": {}
}
```

一次模型输出只描述一个 Action。这样，程序只需要处理一个明确决定，不必猜测多个行动之间的顺序和依赖关系。

### Tool Action：请求执行工具

需要使用工具时，模型生成 **Tool Action（工具行动）**。其中 `action` 必须使用工具的注册名称。

查询天气：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

查询景点信息：

```json
{
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

执行乘法：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

模型不能把 `get_weather` 随意改成 `weather`、`query_weather` 或“天气查询”。这些名称对人类可能意思相近，但程序注册表只认识准确的标识符。

Tool Action 描述的是“请求执行工具”，不是 Tool Result。下面的输出：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

不包含计算结果 `120`。它只把计算任务交给程序。

### Finish Action：直接完成当前任务

并不是所有问题都需要工具。用户可能询问：

```text
请用一句话说明参观博物馆前为什么要提前规划。
```

当前工具只能读取模拟天气、查询模拟景点信息和执行四则运算。解释一般旅行常识不需要这些工具，模型可以直接回答。为此，协议中加入一个特殊行动 `finish`：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "提前规划可以帮助游客确认开放安排、预约要求和参观路线。"
  }
}
```

这种行动称为 **Finish Action（完成行动）**。

`finish` 不对应一个 Python 工具函数。它属于 Action Protocol，用来表示模型认为当前任务不需要再请求工具，并已经能够给出回答。最终文本放在：

```text
arguments.answer
```

当用户提出当前工具无法完成的要求时，模型也可以使用 `finish` 说明能力边界。例如：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "当前没有预订工具，因此无法完成景点预约。"
  }
}
```

这比编造一个不存在的 `book_ticket` 工具更符合当前程序的真实能力。

需要区分两个层次：`finish` 表示模型提出了一个结束请求，Controller 接受合法的 `finish` 后可以正常结束运行；它不证明用户目标已经客观完成。模型也可以用合法的 `finish` 诚实说明当前能力不足，因此“正常结束”不等于“任务完成”。

## 5.4 什么是 Structured Output

自然语言允许同一个意思有许多表达方式：

```text
我建议查询北京天气。
请调用天气工具，城市是北京。
Tool: get_weather, City: Beijing.
下一步应该获取北京的气象信息。
```

这些句子对人类都很清楚，却没有统一字段。程序必须针对不同表达编写不同规则，仍然无法保证覆盖所有情况。

按照固定语法和字段组织的模型输出，称为 **Structured Output（结构化输出）**。在这一章中，结构化输出采用 JSON 形式：

> 本章所说的 Structured Output，是由 Prompt 约束模型生成的 JSON 文本。当前模型服务没有按照程序提供的 Schema 保证其合法性，它也不是 SDK 原生 Tool Calling。程序收到的仍然是普通字符串，因此必须继续经过 Parser 和 Validation。

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

结构化输出的价值不在于文字更美观，而在于它把模型输出变成一份具有稳定位置的数据约定：

```text
行动名称总是在 action 字段
行动参数总是在 arguments 字段
```

需要注意，JSON 与 Python 字典的写法相似，但并不完全相同。合法 JSON 使用双引号：

```json
{
  "action": "get_weather"
}
```

下面则是 Python 字典写法，不是严格 JSON：

```python
{
    'action': 'get_weather'
}
```

JSON 中的布尔值写作 `true` 和 `false`，空值写作 `null`，也不能加入 Python 风格的注释。

更重要的是，**结构化不等于可靠**。模型可能输出：

```text
下面是工具调用：

{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

也可能输出：

```json
{
  "action": "weather",
  "arguments": {
    "location": "北京"
  }
}
```

第一段在 JSON 前增加了说明文字；第二段虽然外形规则，却使用了不存在的工具名称和错误参数。Action Protocol 可以告诉模型“应该怎样输出”，但不能证明模型每次都已经正确遵守。

这一章中的 Structured Output 仍然是模型生成的文本。Python 接收到的类型还是：

```python
str
```

## 5.5 模型怎样知道有哪些工具

大语言模型不会自动读取第四章中的 `TOOL_REGISTRY`，也不会因为项目里存在 `get_weather()`，就自动知道这个函数的名称和参数。

如果程序只发送：

```text
请查询北京的模拟天气。
```

模型可能知道现实中存在天气查询服务，却不知道当前程序开放了哪些工具。它可能输出 `search_weather`、`weather_api`，甚至直接生成一段天气内容。

因此，程序必须把工具说明放入模型上下文。每项说明至少包含：

```text
工具名称
工具用途
参数名称
参数含义
允许取值或数据范围
```

本章使用下面三项说明：

```text
工具名称：get_weather
用途：读取指定城市的本地模拟天气。
参数：
- city：城市名称，字符串。
数据范围：北京、上海、广州。

工具名称：get_attraction_info
用途：读取指定景点的本地模拟开放状态、成人票价和活动类型。
参数：
- name：景点名称，字符串。
数据范围：故宫、上海博物馆、广东省博物馆。

工具名称：calculator
用途：执行两个数字之间的加、减、乘、除。
参数：
- operation：add、subtract、multiply 或 divide。
- a：第一个数字。
- b：第二个数字。
```

工具注册表与工具说明描述的是同一组能力，但面向不同对象：

| 表示 | 使用者 | 作用 |
|---|---|---|
| Tool Registry | Python 程序 | 根据名称找到并执行真实函数 |
| Tool Description | 大语言模型 | 理解当前有哪些能力以及参数怎样填写 |

如果程序注册的是 `get_weather`，Prompt 却写成 `weather_query`，模型即使完全遵守说明，也会生成程序注册表无法识别的名称。因此，工具名称、参数名称和能力边界需要保持一致。

工具说明也不能夸大函数能力。本章中的天气和景点信息来自本地模拟数据，因此描述中必须明确“本地模拟”，不能把它们写成实时网络查询。

## 5.6 构造 Action 系统提示词

为了让模型完成自然语言到 Action 的转换，系统消息需要同时提供工具说明和行动协议。

本章把这部分内容放在：

```text
code/chapter05/prompts.py
```

`prompts.py` 的核心内容如下：

```python
TOOL_DESCRIPTIONS = """
工具名称：get_weather
用途：读取指定城市的本地模拟天气。
参数：
- city：城市名称，字符串。
数据范围：北京、上海、广州。

工具名称：get_attraction_info
用途：读取指定景点的本地模拟开放状态、
成人票价和活动类型。
参数：
- name：景点名称，字符串。
数据范围：故宫、上海博物馆、广东省博物馆。

工具名称：calculator
用途：执行两个数字之间的加、减、乘、除。
参数：
- operation：add、subtract、multiply 或 divide。
- a：第一个数字。
- b：第二个数字。
""".strip()


ACTION_RULES = """
请严格遵守以下规则：

1. 每次只输出一个 JSON 对象。
2. 不要输出 Markdown 代码块。
3. 不要在 JSON 前后添加解释文字。
4. action 只能是：
   get_weather、get_attraction_info、calculator 或 finish。
5. arguments 必须是一个 JSON 对象。
6. 需要程序执行工具时，使用对应工具名称。
7. 不需要工具即可回答时，使用 finish。
8. 当前工具无法完成任务时，不要编造新工具；
   使用 finish 说明能力边界。

Tool Action 格式：
{
  "action": "工具名称",
  "arguments": {
    "参数名称": "参数值"
  }
}

Finish Action 格式：
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
""".strip()


def build_action_system_prompt() -> str:
    return (
        "你是城市旅行助手中的行动选择模块。\n"
        "请根据用户任务选择下一步行动，并输出结构化 Action。\n\n"
        "当前可用工具：\n"
        f"{TOOL_DESCRIPTIONS}\n\n"
        f"{ACTION_RULES}"
    )
```

这段 Prompt 解决了三个问题。

第一，它告诉模型当前身份不是自由聊天者，而是行动选择模块。模型需要输出下一步 Action，而不是假装已经执行了工具。

第二，它提供当前工具的准确名称、用途和参数。模型只能从真实开放的能力中选择。

第三，它规定输出格式。模型每次只输出一个 JSON 对象，并在 Tool Action 与 Finish Action 之间作出选择。

Prompt 中的规则是对模型行为的约束说明，不是 Python 执行代码。`TOOL_DESCRIPTIONS` 不会读取天气数据，`ACTION_RULES` 也不会自动调用工具。它们只是进入模型上下文的文本。

## 5.7 完成最小模型调用

本章代码目录为：

```text
code/chapter05/
├── main.py
├── prompts.py
└── README.md
```

与第二章相比，模型连接方式没有改变。新的内容主要位于系统消息：以前的系统消息要求模型作为旅行助手回答问题，现在的系统消息要求模型从工具集合中选择 Action。

`main.py` 如下：

```python
import os

from dotenv import load_dotenv
from openai import OpenAI

from prompts import build_action_system_prompt


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"缺少环境变量 {name}，"
            "请检查项目根目录下的 .env 文件。"
        )

    return value


def request_action(
    client: OpenAI,
    model_id: str,
    user_task: str,
) -> str:
    messages = [
        {
            "role": "system",
            "content": build_action_system_prompt(),
        },
        {
            "role": "user",
            "content": user_task,
        },
    ]

    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    model_output = response.choices[0].message.content

    if not model_output:
        raise RuntimeError(
            "模型返回了响应，但没有可用的 Action 文本。"
        )

    return model_output


def main() -> None:
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
    print(f"\nPython 类型：{type(model_output).__name__}")


if __name__ == "__main__":
    main()
```

程序的执行过程为：

```text
用户任务
→ Action 系统提示词
→ 模型服务
→ 原始 Action 文本
→ 打印到终端
```

最后一行会输出：

```text
Python 类型：str
```

这行信息十分重要。即使终端中的内容看起来像 JSON，当前程序也没有读取其中的 `action` 或 `arguments`，更没有调用任何工具。

`README.md` 需要明确说明这一点：

```markdown
# Chapter 05

本章演示大语言模型怎样根据用户任务生成原始 JSON Action 字符串。

运行：

```bash
python code/chapter05/main.py
```

程序只显示模型输出，不解析或执行任何工具。
天气、景点和票价均为本地模拟能力说明。
```

## 5.8 运行四类任务

从项目根目录执行：

```bash
python code/chapter05/main.py
```

模型生成具有不确定性，实际空格、换行和措辞可能不同。当前应观察的是：模型是否选择了合适的行动，以及是否按照协议组织输出。

### 查询模拟天气

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

终端不会显示“晴，30℃”，因为天气函数还没有执行。当前程序只获得了查询请求。

### 查询模拟景点信息

输入：

```text
请查询故宫的模拟开放状态和成人票价。
```

模型可能输出：

```json
{
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

模型没有自行编写开放状态和票价，而是选择了能够读取这类信息的工具。

### 请求精确计算

输入：

```text
一张票 60 元，两张票一共多少元？
```

模型可能输出：

```json
{
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

程序此时仍然不会输出 `120`。Action 只描述应当进行的乘法。

### 不需要工具的旅行问题

输入：

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

这个问题不需要当前三个工具，模型直接使用 `finish` 提供回答。

还可以输入一个超出工具能力的问题：

```text
请直接帮我预订两张故宫门票。
```

当前没有预订工具。合理输出是：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "当前没有预订工具，因此无法完成门票预约。"
  }
}
```

模型不应自行创造 `book_ticket` 或 `submit_order`。

## 5.9 失败实验：看起来像 JSON 仍然不够

系统提示词已经要求模型只输出 JSON，但语言模型的输出仍具有不确定性。为了观察问题，可以暂时把 `ACTION_RULES` 中的前两条改成：

```text
请先用一句话解释你的选择，再输出 JSON Action。
可以使用 Markdown 代码块展示 JSON。
```

再次运行天气任务，模型可能输出：

````text
北京天气需要通过模拟天气工具获取。
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
````

人类可以看出其中包含一个正确的 Tool Action，但 Python 当前接收到的是完整字符串：

例如模型可能输出：

```text
北京天气需要通过模拟天气工具获取。
```

随后输出：

```json
{
  "action": "weather",
  "arguments": {
    "location": "北京"
  }
}
```

这段文本语法上看起来规整，语义却不符合当前工具名称和参数约定。

这个实验揭示了模型输出与真实执行之间的一道边界：

```text
模型愿意按照协议输出 ≠ 程序已经证明输出符合协议
```

因此，当前程序必须停在“显示原始文本”这一步，不能因为输出看起来合理就直接执行。

## 5.10 当前系统快照

完成这一章后，城市旅行助手已经能够读取用户的自然语言任务，并在四种行动中作出选择：

```text
get_weather
get_attraction_info
calculator
finish
```

当前流程为：

```text
用户自然语言任务
→ 工具说明与 Action Protocol
→ LLM
→ 原始 JSON Action 字符串
```

与第四章相比，工具名称和参数不再完全由开发者写死，而是由模型根据用户表达生成。模型可以把“帮我看看北京的模拟天气”转换成 `get_weather`，也可以把“60 元一张，两张多少钱”转换成 `calculator`。

不过，程序当前只获得一个 `str`。它还不能确认：

```text
输出是否为合法 JSON
是否存在 action 和 arguments
工具名称是否属于允许范围
参数名称和参数类型是否正确
finish 是否真正包含 answer
```

这些问题不能继续交给 Prompt 自己保证。程序需要一种明确的方法，把原始字符串转换成可读取的数据，并拒绝不符合协议的内容。

## 5.11 本章小结

这一章完成了城市旅行助手从“开发者手动指定工具”到“模型提出工具行动”的变化。

Action 是模型生成的结构化行动请求；`action` 字段保存行动名称，`arguments` 字段保存行动参数。Action Protocol 规定了模型和程序共同使用的输出格式，Structured Output 则让开放的自然语言决定具有固定字段。

协议中包含两类行动：Tool Action 请求执行一个已注册工具，Finish Action 表示当前可以直接回答或需要说明能力边界。无论哪种行动，模型输出都仍然只是文本，不代表工具已经执行，也不代表程序已经确认它符合协议。

完成本章后，应当能够回答：

1. 为什么第四章的工具执行器不能直接理解用户自然语言？
2. Action、`action` 和 `arguments` 分别表示什么？
3. Tool Action 与 Finish Action 有什么区别？
4. 工具注册表与工具说明为什么必须保持一致？
5. 为什么结构化输出仍然不能被程序直接信任？

## 习题

**1. 测试不同表达**

分别输入：

```text
帮我看看上海的模拟天气。
上海现在的模拟气象情况怎样？
我想了解上海这组本地天气数据。
```

观察模型是否都能选择 `get_weather`，并正确填写 `city`。

**2. 测试景点工具**

输入：

```text
广东省博物馆在模拟数据中是否开放？
```

检查模型是否生成 `get_attraction_info`，而不是直接编写开放状态。

**3. 测试运算映射**

依次输入：

```text
37 加 58 是多少？
100 减去 28 是多少？
25 的 8 倍是多少？
144 平均分成 12 份，每份多少？
```

观察模型是否把自然语言映射为 `add`、`subtract`、`multiply` 和 `divide`。不要执行计算器。

**4. 测试能力边界**

输入：

```text
请帮我搜索今天最新的北京旅游新闻。
```

当前没有网页搜索工具。观察模型是否使用 `finish` 说明限制，还是编造了不存在的工具。

**5. 破坏输出规则**

允许模型在 JSON 前后添加解释文字，再运行一个天气任务。记录原始输出，并说明为什么“人类能够看懂”不等于“程序已经能够安全执行”。

## 参考资料

1. [Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat).
2. [Prompt Engineering Guide](https://platform.openai.com/docs/guides/prompt-engineering).
3. [The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259). RFC 8259, 2017.
