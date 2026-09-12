# 第四章 工具：让程序连接外部能力

第三章的城市旅行助手已经可以把对话历史留在 `messages` 里，所以“它”这种指代词可以继续成立。  
这意味着模型理解更连贯了，但我们仍然只是在“讲故事”——模型说得再好，程序还没有真正调用外部能力。

不过，能够理解问题，不等于真正完成了问题中要求的操作。

假设用户询问：

```text
北京现在的天气怎样？
```

模型可以生成一段看起来合理的天气描述，但这段文字本身不能证明程序查询了天气数据。用户再问：

```text
故宫当前是否开放？两张成人票一共多少钱？
```

模型也可能根据已有知识给出答案，却不一定读取了明确的数据源，更没有保证费用是由程序实际计算得到的。

要让程序获得模型文本之外的信息，或者完成一次确定的计算，需要把这些能力写成可以真正执行的 Python 函数。程序调用函数后得到的返回值，才来自一次实际运行。

为了看清这层结构，下面暂时由开发者直接指定要执行的功能和参数。这样可以把注意力集中在一个基础问题上：普通 Python 函数怎样被组织成程序可以统一查找和执行的工具？

## 4.1 文本回答与真实执行

先比较两段代码。

第一段代码只是把一句话保存到变量中：

```python
answer = "北京当前天气为晴，温度 30℃。"
```

这里没有发生天气查询。程序只是得到了一个字符串。

第二段代码调用了一个函数：

```python
result = get_weather(city="北京")
```

如果 `get_weather()` 会从某个数据源读取北京的天气信息，那么 `result` 来自一次真实函数执行。

两者的差异是：

```text
生成或写下一段文字
```

与：

```text
调用明确能力 → 执行程序代码 → 获得返回值
```

大语言模型擅长理解和生成语言，但语言描述不能自动替代程序执行。模型说“我查询了天气”，不表示 Python 已经调用天气函数；模型说“结果是 120 元”，也不表示程序真正完成了乘法。

因此，一个能够回答旅行问题的语言模型应用，还需要明确的执行能力，才能读取外部数据或完成确定性操作。

## 4.2 普通函数怎样成为工具

工具的基础形态并不复杂。下面是一个普通 Python 函数：

```python
def get_weather(city: str) -> str:
    return f"{city}当前模拟天气为晴，温度30℃。"
```

它接收城市名称，执行一项明确能力，再返回结果。只要程序允许通过一个稳定名称找到并调用这个函数，它就可以成为工具。

在本书中，我们采用下面的定义：

> **工具（Tool）是程序明确开放的一项可执行能力。它接收参数，完成特定操作，并把结果返回给调用方。**

这个定义包含四个重点。

第一，工具必须能够执行。只有一段功能说明，而没有对应函数，不能产生真实结果。

第二，工具应当有清晰输入。天气工具需要城市名称，景点工具需要景点名称，计算器需要运算类型和数字。

第三，工具应当返回结果。调用方需要取得执行结果，才能继续处理。

第四，工具必须被程序明确开放。项目中的辅助函数并不会自动成为工具。只有被放入允许调用的集合后，程序才会通过统一入口使用它。

工具也不一定访问互联网。本地计算、文件读取、数据库查询和网络请求都可以被封装成工具。判断标准不是“是否调用 API”，而是它是否提供了一项边界清楚、能够执行并返回结果的能力。

## 4.3 模型知识与工具结果

模型回答与工具结果可能都是字符串，但它们的来源不同。

例如：

```text
北京夏季通常较热。
```

这类内容可能来自模型学习到的一般知识。

下面的内容则来自本章的模拟天气函数：

```text
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

它来自程序读取本地字典后的实际返回值。

| 对比 | 模型生成的内容 | 工具结果 |
|---|---|---|
| 来源 | 模型参数与当前上下文 | Python 函数及其数据源 |
| 是否执行程序能力 | 不一定 | 是 |
| 是否可以读取指定数据 | 不能仅凭文字保证 | 由函数实现决定 |
| 是否适合精确计算 | 可能出错 | 可以交给确定性代码 |
| 是否容易复现 | 可能随生成变化 | 相同输入通常得到相同结果 |

工具结果也不等于绝对正确。函数可能读取过期数据，输入可能不存在，程序也可能出现错误。工具的重要意义在于：结果来自一条可以定位和检查的执行路径，而不是模型根据语言模式自行补全。

本章使用本地模拟数据，是为了让每一次运行都能够重复验证。输出中的天气、开放状态和票价都不代表真实世界信息。

## 4.4 定义三个旅行工具

城市旅行助手使用三个固定工具：模拟天气查询、模拟景点信息查询和计算器。它们分别展示数据读取与确定性计算。

### 4.4.1 模拟天气查询

先准备一组本地数据：

```python
WEATHER_DATA = {
    "北京": {
        "condition": "晴",
        "temperature": 30,
        "humidity": 45,
        "wind": "微风",
    },
    "上海": {
        "condition": "多云",
        "temperature": 27,
        "humidity": 70,
        "wind": "东南风",
    },
    "广州": {
        "condition": "阵雨",
        "temperature": 32,
        "humidity": 82,
        "wind": "南风",
    },
}
```

天气工具根据城市名称读取字典：

```python
def get_weather(city: str) -> str:
    data = WEATHER_DATA.get(city)

    if data is None:
        return f"没有找到城市“{city}”的模拟天气数据。"

    return (
        f"{city}当前模拟天气为{data['condition']}，"
        f"温度{data['temperature']}℃，"
        f"湿度{data['humidity']}%，"
        f"{data['wind']}。"
    )
```

输入：

```python
get_weather(city="北京")
```

返回：

```text
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

这里的天气信息不是由大语言模型生成，而是由函数读取本地数据后拼接得到。

本章暂以普通字符串表示“未找到数据”；结构化工具错误在第十二章统一处理。

### 4.4.2 模拟景点信息查询

景点数据包含所属城市、开放状态、成人票价、活动类型和简介：

```python
ATTRACTION_DATA = {
    "故宫": {
        "city": "北京",
        "open": True,
        "adult_ticket": 60,
        "activity_type": "室内外步行",
        "description": "以宫殿建筑、历史展陈和步行参观为主。",
    },
    "上海博物馆": {
        "city": "上海",
        "open": True,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "以历史文物和艺术展陈为主。",
    },
    "广东省博物馆": {
        "city": "广州",
        "open": False,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "当前模拟数据中处于闭馆状态。",
    },
}
```

查询函数为：

```python
def get_attraction_info(name: str) -> str:
    data = ATTRACTION_DATA.get(name)

    if data is None:
        return f"没有找到景点“{name}”的模拟信息。"

    open_status = "开放" if data["open"] else "闭馆"

    return (
        f"{name}位于{data['city']}，"
        f"在当前模拟数据中处于{open_status}状态，"
        f"成人票价{data['adult_ticket']}元，"
        f"活动类型为{data['activity_type']}。"
        f"{data['description']}"
    )
```

调用：

```python
get_attraction_info(name="故宫")
```

得到：

```text
故宫位于北京，在当前模拟数据中处于开放状态，
成人票价60元，活动类型为室内外步行。
以宫殿建筑、历史展陈和步行参观为主。
```

### 4.4.3 计算器

计算器不读取旅行数据，而是执行确定性运算：

```python
def calculator(
    operation: str,
    a: float,
    b: float,
) -> str:
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("除数不能为 0。")
        result = a / b
    else:
        raise ValueError(
            f"不支持的计算操作：{operation}"
        )

    if float(result).is_integer():
        return str(int(result))

    return str(result)
```

计算两张 60 元门票的总价：

```python
calculator(
    operation="multiply",
    a=60,
    b=2,
)
```

返回：

```text
120
```

这里没有使用：

```python
eval("60 * 2")
```

`eval()` 可以执行任意 Python 表达式。当输入来源不完全受程序控制时，它可能执行超出计算范围的代码。使用有限的操作名称和明确参数，可以把计算能力限制在加、减、乘、除之内。

## 4.5 为什么工具要返回结果

下面的函数会在终端显示天气：

```python
def get_weather(city: str) -> None:
    print(f"{city}当前模拟天气为晴。")
```

它适合直接展示，但调用方无法取得这段内容：

```python
result = get_weather("北京")
print(result)
```

输出会是：

```text
北京当前模拟天气为晴。
None
```

第一行来自函数内部的 `print()`，第二行说明函数没有返回值。

更适合作为工具的写法是：

```python
def get_weather(city: str) -> str:
    return f"{city}当前模拟天气为晴。"
```

此时：

```python
result = get_weather("北京")
```

变量 `result` 中真正保存了返回值。调用方可以打印它、写入文件、继续计算或交给其他程序逻辑。

因此：

> `print()` 把内容显示给当前终端，`return` 把结果交回调用方。

工具的核心职责是提供可继续使用的结果，而不是决定结果最终怎样展示。

工具函数中可以保留必要日志，但日志不能代替正式返回值。对当前三个工具，我们统一返回字符串，使天气、景点和计算结果能够通过同一种方式交给调用程序。

## 4.6 Tool Result：一次执行得到的返回值

工具函数执行后直接返回给 Python 程序的数据，称为 **Tool Result（工具结果）**。

例如：

```python
tool_result = get_weather(city="北京")
```

此时：

```text
tool_result =
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

计算器的 Tool Result 是：

```text
120
```

景点工具的 Tool Result 则是一段景点信息。

Tool Result 强调的是“函数实际返回了什么”。它与函数说明、工具名称和输入参数都不同：

| 内容 | 示例 |
|---|---|
| 工具名称 | `get_weather` |
| 工具参数 | `{"city": "北京"}` |
| Tool Result | `北京当前模拟天气为晴……` |

只写下工具名称不会产生结果，只准备参数也不会产生结果。只有函数真正执行后，程序才会获得 Tool Result。

## 4.7 Tool Description：说明工具能做什么

程序中有三个工具，仅看名称可以大致猜出用途，但名称不能完整说明输入和输出。例如，`calculator` 支持哪些运算？`get_weather` 查询的是真实数据还是模拟数据？`get_attraction_info` 需要城市名称还是景点名称？

因此，可以为每个工具准备一段 **Tool Description（工具描述）**：

```python
TOOL_DESCRIPTIONS = {
    "get_weather": (
        "根据城市名称读取本地模拟天气。"
        "参数：city，字符串。"
    ),
    "get_attraction_info": (
        "根据景点名称读取本地模拟开放状态、"
        "成人票价和活动类型。参数：name，字符串。"
    ),
    "calculator": (
        "执行加、减、乘、除。"
        "参数：operation、a、b。"
    ),
}
```

工具描述面向理解工具的人或程序模块，至少应说明三件事：

```text
工具提供什么能力
需要哪些参数
结果来自什么范围
```

一段清楚的描述可以避免把城市名称传给景点工具，也可以明确天气和票价来自本地模拟数据。

工具描述本身不会执行任何代码。下面这段字符串只是说明：

```text
根据城市名称读取本地模拟天气。
```

真正执行能力的仍然是：

```python
get_weather(city="北京")
```

因此，Tool Description 是工具的说明，Tool Function 才是工具的实现。

## 4.8 Tool Registry：用稳定名称管理工具

目前可以直接调用函数：

```python
get_weather(city="北京")
get_attraction_info(name="故宫")
calculator(operation="multiply", a=60, b=2)
```

但这种写法要求调用代码提前知道具体函数对象。随着工具数量增加，主程序会出现越来越多的分支：

```python
if tool_name == "get_weather":
    ...
elif tool_name == "get_attraction_info":
    ...
elif tool_name == "calculator":
    ...
```

更紧凑的方式是建立一个名称到函数的映射：

```python
from collections.abc import Callable


ToolFunction = Callable[..., str]


TOOL_REGISTRY: dict[str, ToolFunction] = {
    "get_weather": get_weather,
    "get_attraction_info": get_attraction_info,
    "calculator": calculator,
}
```

这份映射称为 **Tool Registry（工具注册表）**。

工具注册表回答两个问题：

```text
当前程序开放了哪些工具？
一个工具名称对应哪个 Python 函数？
```

例如：

```python
tool_function = TOOL_REGISTRY["get_weather"]
result = tool_function(city="北京")
```

这里先通过字符串名称取得函数对象，再调用函数。

不是项目中的所有函数都应该进入注册表。像字符串格式化、读取内部配置和打印调试信息这样的辅助函数，只服务于程序内部，不需要被统一开放。注册表是一份明确的允许列表：只有出现在其中的函数，才属于当前程序可通过工具入口执行的能力。

## 4.9 Tool Executor：统一查找并执行工具

注册表解决了“名称对应哪个函数”的问题。接下来可以把查找和调用封装到一个统一函数中：

```python
def execute_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> str:
    tool_function = TOOL_REGISTRY.get(tool_name)

    if tool_function is None:
        available_tools = ", ".join(TOOL_REGISTRY)
        raise ValueError(
            f"未知工具：{tool_name}。"
            f"可用工具：{available_tools}"
        )

    try:
        result = tool_function(**arguments)
    except TypeError as error:
        raise ValueError(
            f"工具“{tool_name}”的参数不正确：{error}"
        ) from error

    if not isinstance(result, str):
        raise TypeError(
            f"工具“{tool_name}”必须返回字符串。"
        )

    return result
```

这个函数称为 **Tool Executor（工具执行器）**。它接收工具名称和参数，完成三步操作：

```text
从注册表查找函数
→ 将参数传给函数
→ 返回 Tool Result
```

调用方式为：

```python
tool_result = execute_tool(
    tool_name="get_weather",
    arguments={
        "city": "北京",
    },
)
```

`**arguments` 会把字典展开为关键字参数。上面的调用相当于：

```python
get_weather(city="北京")
```

计算器调用：

```python
tool_result = execute_tool(
    tool_name="calculator",
    arguments={
        "operation": "multiply",
        "a": 60,
        "b": 2,
    },
)
```

相当于：

```python
calculator(
    operation="multiply",
    a=60,
    b=2,
)
```

工具执行器不判断当前应该使用哪个工具。它只负责忠实执行调用方已经给出的名称和参数。

## 4.10 组织本章代码

本章代码目录为：

```text
code/chapter04/
├── tools.py
├── main.py
└── README.md
```

`tools.py` 保存模拟数据、三个工具、工具描述、注册表和执行器；`main.py` 负责指定工具调用并显示结果；`README.md` 说明运行方法和模拟数据范围。

`tools.py` 的完整结构如下：

下面只保留连接前面组件的 `execute_tool()`；导入、配置和辅助函数见 [code/chapter04/tools.py](https://github.com/damtle/Simple-Agent/blob/main/code/chapter04/tools.py)。运行时使用该完整文件。

```python
def execute_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> str:
    """根据工具名称查找函数、展开参数并返回 Tool Result。"""
    tool_function = TOOL_REGISTRY.get(tool_name)

    if tool_function is None:
        available_tools = ", ".join(TOOL_REGISTRY)
        raise ValueError(
            f"未知工具：{tool_name}。"
            f"可用工具：{available_tools}"
        )

    try:
        result = tool_function(**arguments)
    except TypeError as error:
        raise ValueError(
            f"工具“{tool_name}”的参数不正确：{error}"
        ) from error

    if not isinstance(result, str):
        raise TypeError(
            f"工具“{tool_name}”必须返回字符串。"
        )

    return result
```

`main.py` 由开发者明确写出三次调用：

```python
from tools import execute_tool, list_tools


def run_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    print(f"\n工具名称：{tool_name}")
    print(f"工具参数：{arguments}")

    try:
        result = execute_tool(
            tool_name=tool_name,
            arguments=arguments,
        )
    except (TypeError, ValueError) as error:
        print(f"执行失败：{error}")
        return

    print(f"Tool Result：{result}")


def main() -> None:
    print("当前可用工具：")
    print(list_tools())

    calls = [
        (
            "get_weather",
            {
                "city": "北京",
            },
        ),
        (
            "get_attraction_info",
            {
                "name": "故宫",
            },
        ),
        (
            "calculator",
            {
                "operation": "multiply",
                "a": 60,
                "b": 2,
            },
        ),
    ]

    for tool_name, arguments in calls:
        run_tool(
            tool_name=tool_name,
            arguments=arguments,
        )


if __name__ == "__main__":
    main()
```

这里没有调用大语言模型。工具名称和参数已经明确写在 `calls` 中，程序只负责按照这些值执行。

## 4.11 运行手动工具调用

从项目根目录执行：

```bash
python code/chapter04/main.py
```

终端会先列出当前开放的工具：

```text
当前可用工具：
- get_weather: 根据城市名称读取本地模拟天气。参数：city，字符串。
- get_attraction_info: 根据景点名称读取本地模拟开放状态、成人票价和活动类型。参数：name，字符串。
- calculator: 执行加、减、乘、除。参数：operation、a、b。
```

随后依次执行三次调用：

```text
工具名称：get_weather
工具参数：{'city': '北京'}
Tool Result：北京当前模拟天气为晴，温度30℃，湿度45%，微风。

工具名称：get_attraction_info
工具参数：{'name': '故宫'}
Tool Result：故宫位于北京，在当前模拟数据中处于开放状态，
成人票价60元，活动类型为室内外步行。
以宫殿建筑、历史展陈和步行参观为主。

工具名称：calculator
工具参数：{'operation': 'multiply', 'a': 60, 'b': 2}
Tool Result：120
```

每次执行都经过同一个入口：

```text
开发者指定名称和参数
→ Tool Executor
→ Tool Registry
→ Python 函数
→ Tool Result
```

天气、景点和计算器具有不同参数与内部实现，但主程序不需要分别编写三个调用分支。它只需要把名称和参数交给 `execute_tool()`。

## 4.12 失败实验：调用未注册的工具

将 `main.py` 中的第一个工具名称改为：

```python
(
    "search_weather",
    {
        "city": "北京",
    },
)
```

注册表中并不存在 `search_weather`。再次运行程序，会得到：

```text
工具名称：search_weather
工具参数：{'city': '北京'}
执行失败：未知工具：search_weather。
可用工具：get_weather, get_attraction_info, calculator
```

这个失败说明，程序不是看到一个字符串就尝试执行同名代码。执行器只会从注册表中查找函数。即使项目中存在其他函数，只要没有注册，就不能通过这个入口调用。

再把名称恢复为：

```python
"get_weather"
```

程序即可重新得到天气结果。

注册表因此不只是为了减少 `if-else`，它还规定了当前程序实际开放的能力范围。

## 4.13 当前程序还缺少什么

现在，程序已经能够通过统一名称执行天气、景点和计算工具。工具描述说明每项能力需要什么输入，工具注册表保存名称与函数之间的关系，工具执行器负责查找函数并传入参数，函数返回的内容则成为 Tool Result。

不过，`main.py` 中的调用仍然由开发者提前写好：

```python
(
    "get_weather",
    {
        "city": "北京",
    },
)
```

真实用户不会按照 Python 字典提问。他更可能输入：

```text
帮我看看北京的天气。
```

或者：

```text
故宫两张成人票一共多少钱？
```

程序当前不能从这些自然语言中自动得到准确的工具名称和参数。它也不能判断第一句话应使用 `get_weather`，第二句话可能需要先读取景点票价，再进行计算。

于是，工具系统建立之后，新的问题自然出现了：

> 怎样把用户的自然语言要求，转换成程序能够读取的工具名称和参数？

## 4.14 本章小结

这一章把城市旅行助手从“只能生成文本”推进到了“能够执行明确能力”。

普通 Python 函数具备清晰输入、实际执行过程和返回值后，可以被程序开放为 Tool。Tool Description 说明工具能够做什么以及需要哪些参数；Tool Registry 保存稳定名称与函数之间的映射；Tool Executor 根据名称查找函数、展开参数并返回执行结果；Tool Result 则是工具实际运行后交给调用方的数据。

三个旅行工具形成了统一调用方式：

```text
tool_name + arguments
→ execute_tool()
→ Tool Result
```

完成本章后，应当能够回答：

1. 为什么模型生成一段天气文字不等于程序执行了天气查询？
2. 普通 Python 函数在什么条件下可以作为 Tool？
3. `print()` 与 `return` 对工具调用有什么不同？
4. Tool Description、Tool Registry 和 Tool Executor 分别承担什么职责？
5. 为什么只有注册表中的函数才能通过统一入口执行？

## 习题

**1. 修改天气数据**

在 `WEATHER_DATA` 中加入成都，并执行：

```python
execute_tool(
    tool_name="get_weather",
    arguments={"city": "成都"},
)
```

确认结果来自新增的本地数据。

**2. 查询未收录景点**

调用：

```python
execute_tool(
    tool_name="get_attraction_info",
    arguments={"name": "颐和园"},
)
```

观察 Tool Result，并说明函数为什么没有直接崩溃。

**3. 测试四则运算**

分别使用 `add`、`subtract`、`multiply` 和 `divide`。再把除数改为 `0`，观察错误发生在哪个函数中。

**4. 对比 `print()` 与 `return`**

将 `get_weather()` 临时改成只执行 `print()`，观察 `execute_tool()` 得到什么结果。恢复代码后，解释工具为什么必须有正式返回值。

**5. 新增距离估算工具**

实现：

```python
def estimate_distance(
    start: str,
    destination: str,
) -> str:
    ...
```

使用本地模拟距离数据，为它编写 Tool Description，并将它加入 `TOOL_REGISTRY`。验证主程序不需要增加新的 `if-else` 分支。

## 参考资料

1. [The Python Tutorial — Defining Functions](https://docs.python.org/3/tutorial/controlflow.html#defining-functions).
2. [The Python Tutorial — Dictionaries](https://docs.python.org/3/tutorial/datastructures.html#dictionaries).
3. [The Python Tutorial — Errors and Exceptions](https://docs.python.org/3/tutorial/errors.html).
4. [Artificial Intelligence: A Modern Approach](https://aima.cs.berkeley.edu/). 4th Edition. Pearson, 2020.
