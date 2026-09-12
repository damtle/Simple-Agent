# 第三章 上下文与对话状态

第二章的城市旅行助手只做了一次问答：用户发一条问题，程序返回一条回答。  
这次我们把场景拉长，想象两次、三次甚至更多轮对话，看看“连续性”在代码里要从哪里保存。  
假设第一次输入：

```text
请简单介绍故宫。
```

模型可能回答：

```text
故宫是中国明清两代的皇家宫殿，以宫殿建筑、历史展陈和传统文化闻名。
```

接着，用户继续问：

```text
它适合雨天参观吗？
```

这里的“它”指故宫。人类可以根据前一句自然地理解这个指代，但模型能否理解，取决于第二次请求中是否仍然包含前面的对话。

如果程序只把“它适合雨天参观吗？”发送给模型，那么模型看到的只是一个缺少指代对象的问题。它可能猜测“它”指某个景点，也可能要求用户补充说明，但它没有可靠依据知道上一轮讨论的是故宫。

要让一次回答延续到下一次回答，程序必须保存已经发生的对话，并在新的请求中再次发送这些内容。

## 3.1 两次调用为什么彼此不知道

先看两次独立的模型调用。

第一次请求：

```python
messages = [
    {
        "role": "user",
        "content": "请简单介绍故宫。",
    },
]

response = client.chat.completions.create(
    model=model_id,
    messages=messages,
)
```

第二次请求：

```python
messages = [
    {
        "role": "user",
        "content": "它适合雨天参观吗？",
    },
]

response = client.chat.completions.create(
    model=model_id,
    messages=messages,
)
```

两次请求使用同一个 `client`、同一个 `model_id`，也可能在同一个 Python 程序中连续执行，但第二次请求中没有第一轮的问题和回答。对于当前使用的 Chat Completions 调用方式，模型主要根据本次传入的消息生成结果，不会因为程序刚刚调用过一次，就自动取得上一次请求的内容。

因此，下面这些信息解决的是连接问题，而不是对话延续问题：

| 对象 | 作用 |
|---|---|
| `client` | 保存模型服务的连接配置 |
| `api_key` | 验证访问权限 |
| `base_url` | 指定模型服务地址 |
| `model_id` | 指定使用的模型 |
| `messages` | 提供本次调用中模型能够读取的消息 |

同一个客户端不等于同一段对话。要延续对话，关键不在于重复使用哪个客户端，而在于下一次调用实际发送了哪些消息。

## 3.2 从一组消息到一段对话

第二章中的 `messages` 只有两条消息：

```python
messages = [
    {
        "role": "system",
        "content": SYSTEM_MESSAGE,
    },
    {
        "role": "user",
        "content": "请简单介绍故宫。",
    },
]
```

模型生成回答后，程序只是把回答打印到终端。如果希望继续追问，就要把模型回答也保存下来：

```python
messages.append(
    {
        "role": "assistant",
        "content": answer,
    }
)
```

这里出现了第三种消息角色：**`assistant`**。

`assistant` 表示模型已经生成的回答。它不是新的用户问题，也不是总体回答要求，而是当前对话中模型一方已经说过的内容。

第一轮结束后，消息列表变成：

```python
messages = [
    {
        "role": "system",
        "content": SYSTEM_MESSAGE,
    },
    {
        "role": "user",
        "content": "请简单介绍故宫。",
    },
    {
        "role": "assistant",
        "content": "故宫是中国明清两代的皇家宫殿……",
    },
]
```

当用户继续提问时，再把新问题追加到列表末尾：

```python
messages.append(
    {
        "role": "user",
        "content": "它适合雨天参观吗？",
    }
)
```

第二次调用前，模型看到的消息顺序是：

```text
system：你是一名城市旅行助手
user：请简单介绍故宫
assistant：故宫是中国明清两代的皇家宫殿……
user：它适合雨天参观吗
```

这时，“它”前面已经有了明确指代对象，模型便可以根据完整对话继续回答。

## 3.3 `messages` 是一份有顺序的记录

在本书中，`messages` 表示按发生顺序保存的一组 Message。它不是一个无序集合，也不是只保存最新问题的临时变量。

一段正常的多轮对话通常具有下面的顺序：

```text
system
→ user 1
→ assistant 1
→ user 2
→ assistant 2
→ user 3
→ assistant 3
```

顺序本身包含语义。模型需要知道哪一句是用户提出的问题，哪一句是自己此前作出的回答，以及某个追问发生在什么内容之后。

假设把消息顺序打乱：

```text
user 2
→ assistant 1
→ system
→ user 1
```

即使所有句子都还在，模型也很难正确还原对话关系。因此，程序保存历史时不能只关心“有没有这些内容”，还要保持它们原来的先后次序和角色。

每完成一轮对话，`messages` 会发生两次更新：

```python
messages.append(user_message)
messages.append(assistant_message)
```

第一条记录用户刚刚说了什么，第二条记录模型针对这个问题回答了什么。下一轮模型调用时，整个列表会被重新发送。

## 3.4 什么是上下文

模型在当前一次调用中能够读取并用于生成回答的信息，称为**上下文（Context）**。

在这一章的程序里，上下文主要由 `messages` 提供。第二轮调用的上下文包括：

```text
系统要求
第一轮用户问题
第一轮模型回答
第二轮用户问题
```

需要区分“程序中存在的信息”和“模型当前能够看到的信息”。例如，Python 程序中可能还有：

```text
API Key
模型名称
当前循环次数
最近一次错误
终端显示内容
```

这些数据虽然存在于程序中，但只要没有被放入请求消息，模型就不能直接读取它们。

因此：

> 某段信息曾经出现在程序里，不等于它已经进入模型上下文。

上下文只描述当前这一次调用中模型实际收到的输入。上一轮回答只有被保存到 `messages`，并在下一次请求中重新发送，才会继续成为上下文的一部分。

## 3.5 对话历史与对话状态

在理解上下文之后，还需要区分两个相近的概念。

**对话历史（Conversation History）**是已经发生的用户消息和模型回答。例如：

```text
user：请简单介绍故宫
assistant：故宫是中国明清两代的皇家宫殿……
user：它适合雨天参观吗
assistant：故宫包含室内展陈和室外步行区域……
```

它强调的是“双方此前说过什么”。

**对话状态（Conversation State）**是程序为了让当前对话能够继续而保存的数据。在这个最小程序中，对话状态主要就是 `messages`。程序只有保留这份列表，下一轮才知道应当向模型重新发送哪些内容。

三者的关系可以整理为：

| 概念 | 关注的问题 | 当前程序中的表现 |
|---|---|---|
| `messages` | 消息怎样在 Python 中保存 | 一个有顺序的列表 |
| Conversation History | 用户和模型此前说过什么 | `user` 与 `assistant` 消息 |
| Context | 模型这一次实际看到了什么 | 本次请求发送的完整 `messages` |
| Conversation State | 程序依靠什么继续当前对话 | 运行期间保存的 `messages` |

对话历史通常会成为上下文的一部分，但上下文还包括 `system` 消息。对话状态则属于 Python 程序：程序可以保存某项数据，却不一定把它发送给模型。

当前状态只存在于正在运行的进程中。关闭程序后，内存中的 `messages` 会消失；重新启动程序时，对话会从初始系统消息重新开始。

## 3.6 为什么用户消息和模型回答都要保存

一轮完整对话包含用户消息和模型回答。缺少任何一方，后面的语义都可能不完整。

**只保存用户消息**时，历史可能变成：

```text
system
→ user：请简单介绍故宫
→ user：你刚才提到的第二点是什么意思
```

模型知道用户连续提出了两个问题，却看不到自己“刚才”具体回答了什么，因此无法定位“第二点”。

**只保存模型回答**时，历史可能变成：

```text
system
→ assistant：故宫是中国明清两代的皇家宫殿……
```

模型能够看到一段此前回答，却不知道这段回答针对什么问题产生。

完整结构应当保持交替关系：

```text
user 1 → assistant 1 → user 2 → assistant 2
```

| 保存方式 | 缺少的信息 | 可能造成的问题 |
|---|---|---|
| 只保存 `user` | 模型此前回答 | 无法理解“你刚才说的……” |
| 只保存 `assistant` | 用户原始问题 | 无法判断回答的来源和意图 |
| 两者都保存 | 无 | 可以还原完整对话关系 |

这里的 `assistant` 消息不是为了让模型“模仿自己”，而是为了把已经发生的对话完整地放回上下文。

## 3.7 构造多轮城市旅行助手

完整代码位于：

```text
code/chapter03/main.py
```

与第二章相比，模型连接配置和系统消息保持不变。主要变化是：`messages` 在循环外创建；每轮保存用户消息；调用模型后保存 `assistant` 消息。

完整实现如下：

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


def create_initial_messages() -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
        }
    ]


def request_answer(
    client: OpenAI,
    model_id: str,
    messages: list[dict[str, str]],
) -> str:
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
    )

    answer = response.choices[0].message.content

    if not answer:
        raise RuntimeError("模型返回了响应，但没有可用的文本回答。")

    return answer


def main() -> None:
    load_dotenv()

    api_key = require_env("LLM_API_KEY")
    base_url = require_env("LLM_BASE_URL")
    model_id = require_env("LLM_MODEL_ID")

    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )

    messages = create_initial_messages()

    print("城市旅行助手已启动。")
    print("输入 /clear 清空当前对话，输入 /exit 结束程序。")

    while True:
        user_input = input("\n你：").strip()

        if not user_input:
            print("请输入有效内容。")
            continue

        if user_input == "/exit":
            print("对话结束。")
            break

        if user_input == "/clear":
            messages = create_initial_messages()
            print("当前对话已清空。")
            continue

        messages.append(
            {
                "role": "user",
                "content": user_input,
            }
        )

        answer = request_answer(
            client=client,
            model_id=model_id,
            messages=messages,
        )

        messages.append(
            {
                "role": "assistant",
                "content": answer,
            }
        )

        print(f"\n旅行助手：{answer}")


if __name__ == "__main__":
    main()
```

这段程序的核心变化只有下面几行：

```python
messages.append(
    {
        "role": "user",
        "content": user_input,
    }
)

answer = request_answer(
    client=client,
    model_id=model_id,
    messages=messages,
)

messages.append(
    {
        "role": "assistant",
        "content": answer,
    }
)
```

每一轮都先把用户输入放进列表，再把完整 `messages` 发送给模型，最后将模型回答作为 `assistant` 消息保存。循环回到开头后，下一次请求自然会携带此前历史。

`messages` 必须在 `while` 循环外创建。若在循环内部重新执行：

```python
messages = create_initial_messages()
```

每一轮都会得到一份新的列表，之前保存的内容也会随之丢失，程序仍然只能处理单个问题。

## 3.8 运行连续追问

从项目根目录运行：

```bash
python code/chapter03/main.py
```

进行下面的对话：

```text
城市旅行助手已启动。
输入 /clear 清空当前对话，输入 /exit 结束程序。

你：请简单介绍故宫。

旅行助手：故宫是中国明清两代的皇家宫殿，
以宏大的宫殿建筑、丰富的历史展陈和传统文化价值闻名。

你：它适合雨天参观吗？

旅行助手：故宫有室内展馆，但宫殿之间需要较多室外步行。
小雨时可以准备雨具参观；遇到大雨或恶劣天气，
应提前核实开放安排并适当调整行程。

你：继续解释需要提前准备什么。

旅行助手：可以提前准备舒适的鞋、雨具和饮用水，
并核实预约、开放时间与入场要求。
```

第二个问题中的“它”指向第一轮的“故宫”；第三个问题中的“继续解释”则要求模型延续前一轮回答。模型能够处理这些表达，是因为程序发送的内容已经从单个问题变成了一段有顺序的对话：

```text
system
→ user：请简单介绍故宫
→ assistant：……
→ user：它适合雨天参观吗
→ assistant：……
→ user：继续解释需要提前准备什么
```

模型输出仍然具有不确定性，不同运行结果的措辞可能不同。判断程序是否成功时，应重点观察回答是否能够延续前面的对象和话题。

## 3.9 `/clear` 怎样改变对话状态

输入 `/clear` 时，程序执行：

```python
messages = create_initial_messages()
```

清空前，列表可能是：

```text
system
→ user 1
→ assistant 1
→ user 2
→ assistant 2
```

清空后，只剩：

```text
system
```

系统消息仍然保留，因此旅行助手的总体回答方式没有改变；此前的用户问题和模型回答已经离开当前状态。

例如：

```text
你：请简单介绍故宫。
旅行助手：……

你：/clear
当前对话已清空。

你：它适合雨天参观吗？
```

最后一个问题再次缺少明确对象。这个现象说明，模型对当前对话的延续依赖程序保存的 `messages`。改变对话状态，也会改变下一次模型调用的上下文。

这里重新创建列表，而不是直接执行：

```python
messages.clear()
```

因为 `clear()` 会连同 `system` 消息一起删除。重新调用 `create_initial_messages()` 可以清除历史，同时保留旅行助手的基本回答要求。

## 3.10 失败实验：只发送最新问题

为了验证历史是否真正发挥作用，可以暂时修改 `request_answer()` 的调用参数。

原来的代码发送完整列表：

```python
answer = request_answer(
    client=client,
    model_id=model_id,
    messages=messages,
)
```

将它改为只发送系统消息和最新用户消息：

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

完整发送历史时，第二次请求中包含 `Maple-47`，模型通常可以正确回答。只发送最新问题时，第二次请求中没有这个代号，模型便无法可靠知道答案。

使用任意代号比只测试“它适合雨天参观吗”更可靠，因为模型可能根据常见表达猜出“它”大概率指某个景点。`Maple-47` 无法从一般知识中推测，更能证明答案来自当前上下文。

实验完成后，应恢复为：

```python
messages=messages
```

这个实验说明：

> 模型是否能够延续对话，不能只看它有没有碰巧答对，还要检查相关历史是否真的进入了本次请求。

## 3.11 对话越长，发送的内容越多

当前实现每完成一轮对话，就向 `messages` 中加入一条 `user` 消息和一条 `assistant` 消息。

一轮结束后：

```text
1 条 system + 2 条对话消息
```

三轮结束后：

```text
1 条 system + 6 条对话消息
```

十轮结束后：

```text
1 条 system + 20 条对话消息
```

下一次调用不是只发送最新问题，而是重新发送当前列表中的全部消息。因此，对话持续得越久，每次请求携带的文本通常越多。

这会带来三个直接影响。

**处理时间可能增加。** 模型需要读取更多输入后再生成回答。

**调用成本可能增加。** 许多模型服务会根据输入和输出文本量计费，重复发送较长历史会增加消耗。

**旧内容可能干扰当前问题。** 当话题已经改变，早期对话未必仍然有帮助。保存更多信息不一定总能得到更好的回答。

模型一次能够处理的上下文也有容量限制，具体范围取决于实际使用的模型和服务。当前程序适合观察多轮对话原理，但不能假设 `messages` 可以无限增长。

## 3.12 对话循环与 Agent Loop

现在的程序包含一个 `while` 循环，也保存了会影响后续回答的状态，但它仍然属于多轮 LLM 应用，而不是第一章介绍的完整 Agent Loop。

当前循环由用户输入推动：

```text
等待用户输入
→ 调用模型
→ 输出回答
→ 再次等待用户输入
```

模型每轮只生成自然语言文本，不会让程序对外部环境执行行动。回答结束后，是否继续也由用户决定，而不是程序根据目标完成情况自行判断。

第一章中的温控 Agent 则会在每次行动后重新观察温度，并根据环境变化主动决定下一步。两种循环的区别是：

| 对比 | 对话循环 | 温控 Agent Loop |
|---|---|---|
| 下一轮由谁触发 | 用户再次输入 | 环境变化后程序继续 |
| 模型或规则产生什么 | 自然语言回答 | 环境行动 |
| 是否改变外部环境 | 否 | 是 |
| 是否围绕目标自主继续 | 否 | 是 |

因此，有上下文、有状态和有循环，仍然不足以单独构成 Agent。判断重点仍然是系统是否围绕目标形成了观察、决策、行动和反馈关系。

## 3.13 本章小结

这一章把第二章的一次性模型调用改造成了连续对话。

模型不会因为相同的客户端被连续调用，就自动取得上一轮内容。程序需要保存用户消息和模型回答，保持原有顺序，并在下一次请求中重新发送完整 `messages`。

这一过程中形成了几个重要概念：

- `messages` 是 Python 中保存消息的有序列表；
- `assistant` 表示模型此前生成的回答；
- Context 是模型在当前调用中实际看到的信息；
- Conversation History 是已经发生的用户与模型消息；
- Conversation State 是程序为了继续当前对话而保存的数据。

当前城市旅行助手已经能够理解“它”“继续解释”和“刚才提到的景点”等依赖历史的表达。但这些回答仍然来自模型当前得到的文本信息。

当用户要求“查询今天的天气”“确认景点现在是否开放”或“精确计算两张门票的总价”时，能够延续对话并不能保证程序真的完成了查询或计算。于是，新的问题变成了：

> Python 程序怎样获得模型之外的信息，并真正执行一项明确的能力？

## 习题

**1. 检查消息顺序**

完成两轮旅行对话后，在模型调用前加入：

```python
for message in messages:
    print(message["role"], message["content"])
```

观察 `system`、`user` 和 `assistant` 的排列顺序。说明为什么顺序不能随意改变。

**2. 删除 `assistant` 历史**

暂时注释掉保存模型回答的代码：

```python
messages.append(
    {
        "role": "assistant",
        "content": answer,
    }
)
```

先让模型给出三点旅行建议，再询问“你刚才说的第二点是什么意思？”。比较修改前后的结果。

**3. 实现 `/history`**

增加一个 `/history` 命令，按顺序打印当前保存的消息：

```text
[system] ...
[user] ...
[assistant] ...
```

`/history` 只用于查看程序状态，不应被加入 `messages`，也不应发送给模型。

**4. 验证清空状态**

依次输入：

```text
请记住，这次旅行的确认代号是 Maple-47。
我的确认代号是什么？
/clear
我的确认代号是什么？
```

解释两次询问为何可能得到不同结果。

**5. 限制最近三轮**

尝试让程序始终保留 `system` 消息，但只发送最近三轮 `user` 与 `assistant` 消息。思考一轮对话包含几条消息，以及列表切片怎样避免把一轮对话从中间截断。

## 参考资料

1. [The official Python library for the OpenAI API](https://github.com/openai/openai-python).
2. [Chat Completions API Reference](https://platform.openai.com/docs/api-reference/chat).
3. [Data Structures — Lists](https://docs.python.org/3/tutorial/datastructures.html).
4. [Built-in Functions — input()](https://docs.python.org/3/library/functions.html#input).
