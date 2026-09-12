# 第十一章 Reflection：检查与修正

第九章的 ReAct 可以在每次 Observation 到来后重新选择行动，第十章的 Plan-and-Solve 可以在执行前生成完整计划。无论使用哪一种方式，工具执行最终都会产生一组已经获得的结果，并由模型整理成面向用户的回答。

不过，工具调用正确，不代表最终回答一定正确。

假设旅行助手已经获得：

```text
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
故宫在当前模拟数据中处于开放状态，成人票价60元。
两张成人票总价为120元。
```

用户要求：

```text
请根据这些结果，为两人写一段不超过120字的出行建议。
回答必须包含天气、故宫开放状态、两张票总价，
并明确说明数据为模拟信息。
```

这里的“不超过120字”是 Reflection 需要尝试检查的用户约束。达到修订上限后，程序仍可能返回未通过检查的答案，因此这不是程序保证的长度上限。

模型第一次生成的回答可能是：

```text
北京天气晴朗，故宫开放，成人票价60元。
建议避开正午并注意防晒补水。
```

这段文字读起来没有明显语病，但它遗漏了两张票总价，也没有说明信息来自模拟数据。问题通常不在天气工具、景点工具或计算器，而在于候选答案是否完整、准确地使用了已获得的结果。

Reflection 处理的就是这个阶段：先检查当前答案是否满足任务，再根据明确反馈进行修订。

```text
用户任务 + Evidence + Draft
→ Critic
→ Critique
→ Refiner
→ Revised Answer
```

## 11.1 当执行过程正确，答案仍可能不合格

一个工具型 Agent 至少包含两个不同层次的正确性。

第一层是执行过程是否正确。例如，程序是否真正调用了 `get_weather`，景点信息是否来自 `get_attraction_info`，票价乘法是否交给了 `calculator`。

第二层是最终回答是否正确使用这些结果。即使工具都已成功执行，回答仍可能出现：

| 问题类型 | 示例 | 结果 |
|---|---|---|
| 信息遗漏 | 没有写两张票总价 | 用户要求没有全部完成 |
| Evidence 使用错误 | 把单张票价60元写成总价 | 回答与执行结果不一致 |
| 逻辑矛盾 | 前文写晴天，后文却建议因暴雨取消 | 答案内部冲突 |
| 用户约束违反 | 超过字数，或没有说明模拟数据 | 没有遵守明确要求 |

这些问题不一定需要重新执行工具。重查一次天气，并不能直接补上遗漏的总费用；再次执行计算器，也不能自动确保回答补上“模拟数据”说明。

因此，答案层需要独立回答一个问题：

> 当前候选答案是否真正满足用户任务？若不满足，具体问题是什么，应当怎样修订？

## 11.2 什么是 Reflection

在本书中，我们采用下面的工程化定义：

> **Reflection 是根据用户任务、Evidence 和当前 Draft 生成 Critique，再依据 Critique 对答案进行 Revision 的结果改进过程。**

最小过程可以写成：

```text
Generator 生成 Draft
→ Critic 检查 Draft
→ 通过：返回当前答案
→ 未通过：Refiner 生成 Revision
→ 再次检查
```

这里的循环对象不是 Action 和 Observation，而是 Draft 和 Critique。

第八章的 Agent Loop 推进外部任务：

```text
Action → Tool → Observation → 下一项 Action
```

Reflection 改进已经生成的答案：

```text
Draft → Critique → Revision → 新 Draft
```

两者都可能使用循环，但职责不同。Reflection 不会执行天气查询、修改 Plan，也不会替换已经完成的工具路径。它只处理答案层。

本章使用“Reflection”作为广义名称，具体实现更接近“生成—反馈—改进”的迭代过程：模型参数不更新，程序只是将当前答案和评审反馈重新作为新的模型输入。它也不保存跨任务的长期反思记忆。

## 11.3 Generator、Draft、Critic 与 Refiner

Reflection 包含三个逻辑角色。它们可以由同一个模型通过不同 Prompt 承担，也可以由不同模型承担。

| 角色 | 输入 | 输出 | 职责 |
|---|---|---|---|
| Generator | 用户任务、Evidence | Draft | 生成第一次候选答案 |
| Critic | 用户任务、Evidence、Draft | Critique | 找出可验证的问题并提出修改建议 |
| Refiner | 用户任务、Evidence、Draft、Critique | Revised Answer | 修复问题并保留正确内容 |

**Generator（生成器）**负责根据已有信息完成用户任务。它生成的第一次回答称为 **Draft（候选答案）**。Draft 还没有经过检查，不能因为语句自然就自动视为最终答案。

**Critic（评审者）**负责检查 Draft。它不执行工具，也不直接生成新的最终回答。它的输出称为 **Critique（评审结果）**，应当说明答案是否通过、具体问题位于哪个维度，以及怎样修改。

**Refiner（修订者）**负责根据 Critique 修改 Draft。一次从旧答案到新答案的变化称为 **Revision（修订）**。Refiner 不重新查询数据，也不能把 Critique 中出现的新数字直接当成事实。

三个角色不要求三个不同模型。最小实现可以继续使用同一个 `client` 和 `model_id`：

```python
draft = generate_draft(...)
critique = critique_draft(...)
revised_answer = revise_draft(...)
```

角色分离首先是职责、Prompt 和输入边界的分离，而不是模型部署数量的分离。

## 11.4 Evidence：答案可以依赖哪些事实

Reflection 要检查“答案是否正确”，必须先明确允许答案使用哪些事实。这些已经获得、允许被答案引用的信息称为 **Evidence（证据）**。

在本书中：

> **Evidence 是当前任务中已经获得，并允许 Generator、Critic 和 Refiner 使用的可信输入。**

主线任务的 Evidence 可以由 ReAct 的成功 Observation 整理而来：

```text
1. get_weather({"city": "北京"})
   北京当前模拟天气为晴，温度30℃，湿度45%，微风。

2. get_attraction_info({"name": "故宫"})
   故宫位于北京，在当前模拟数据中处于开放状态，
   成人票价60元，活动类型为室内外步行。

3. calculator({"operation": "multiply", "a": 60, "b": 2})
   120
```

Evidence 不应只按“是否成功”简单理解。成功工具结果构成 **Domain Evidence**，用于支撑天气、开放状态、票价和计算结果；`not_found`、权限拒绝和工具失败等结果构成 **Execution Evidence**，用于支撑能力边界和失败说明。两类证据都来自实际执行记录，但承担的事实范围不同。

也可以由 Plan-and-Solve 的 StepResult 整理而来。Reflection 不关心这些证据来自哪一种执行策略，只要求它们已经由前面的程序过程获得。

信息优先级应保持清楚：

```text
用户任务：决定答案需要完成什么
Evidence：决定答案可以使用哪些事实
Draft：提供当前需要检查和修改的文本
Critique：指出 Draft 应当怎样改
```

其中，Critique 不是新的 Evidence。

假设 Critic 错误地建议：

```text
把两张票总价修改为180元。
```

而 Evidence 明确记录计算器结果为 `120`。Refiner 仍然应以 Evidence 为准，不能因为建议来自 Critic 就采用 `180`。

> Critique 可以指出修改方向，但不能覆盖 Evidence，也不能授权 Refiner 补充无证据事实。

## 11.5 Critic 应检查哪些问题

只让模型“评价一下这段回答”，往往会得到：

```text
整体不错，可以更具体一些。
```

这种反馈没有指出具体缺失项，也无法直接指导修订。为了让 Critique 可执行，本章将检查范围限定为四个维度。

| 维度 | 检查内容 | 主线案例 |
|---|---|---|
| `completeness` | 是否覆盖用户全部要求 | 是否包含天气、开放状态和总价 |
| `evidence_grounding` | 事实和数字是否与 Evidence 一致 | 是否把60元误写成两张票总价 |
| `consistency` | 答案内部是否前后矛盾 | 晴天与暴雨建议是否冲突 |
| `constraint_compliance` | 是否满足格式、长度和表达约束 | 是否不超过120字并注明模拟数据 |

Critic 只应指出可以根据任务和 Evidence 检查的问题。它不应因为个人写作偏好而强制改写已经合格的句子，也不应使用自身常识补充未执行工具提供的事实。

一条可操作的 Critique 至少包含：

```text
问题属于哪个维度
Draft 中具体哪里有问题
Refiner 应怎样修复
```

例如：

```json
{
  "dimension": "completeness",
  "problem": "Draft 没有给出两张成人票总价。",
  "suggestion": "补充 Evidence 中 calculator 返回的120元，并明确这是两张票总价。"
}
```

## 11.6 定义结构化 Critique 协议

Critic 的结果需要由程序读取，因此不能只返回任意自然语言。我们使用下面的 JSON 协议：

```json
{
  "passed": false,
  "summary": "当前答案遗漏总价和模拟数据说明。",
  "issues": [
    {
      "dimension": "completeness",
      "problem": "没有给出两张成人票总价。",
      "suggestion": "补充 Evidence 中的120元总价。"
    },
    {
      "dimension": "constraint_compliance",
      "problem": "没有说明信息来自本地模拟数据。",
      "suggestion": "在回答结尾增加模拟数据说明。"
    }
  ]
}
```

通过时使用：

```json
{
  "passed": true,
  "summary": "当前答案与 Evidence 一致，并满足用户全部要求。",
  "issues": []
}
```

协议包含三个顶层字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `passed` | 布尔值 | 当前 Draft 是否可以直接返回 |
| `summary` | 字符串 | 对本次检查的简短结论 |
| `issues` | 数组 | 需要修复的具体问题 |

`passed` 与 `issues` 必须保持一致：

```text
passed = true  → issues 必须为空
passed = false → issues 至少包含一项
```

每个 issue 只能包含：

```text
dimension
problem
suggestion
```

Critic 输出仍然属于模型文本，因此程序要解析和校验它。这里沿用第六章已经建立的原则：结构化输出不等于已经可信。

## 11.7 在 `critic.py` 中表示和校验 Critique

本章没有为 Critique 单独增加 `models.py`。相关的数据结构与解析逻辑放在 `critic.py` 中：

```python
from dataclasses import dataclass


ALLOWED_DIMENSIONS = {
    "completeness",
    "evidence_grounding",
    "consistency",
    "constraint_compliance",
}


@dataclass(frozen=True)
class CritiqueIssue:
    dimension: str
    problem: str
    suggestion: str


@dataclass(frozen=True)
class Critique:
    passed: bool
    summary: str
    issues: tuple[CritiqueIssue, ...]


class CritiqueParseError(ValueError):
    """Critic 输出没有通过 Critique 协议校验。"""
```

解析函数先读取 JSON，再检查协议：

```python
def parse_critique(model_output: str) -> Critique:
    try:
        data = json.loads(model_output)
    except json.JSONDecodeError as error:
        raise CritiqueParseError(
            f"Critique 不是合法 JSON：{error.msg}。"
        ) from error

    if not isinstance(data, dict):
        raise CritiqueParseError(
            "Critique 顶层必须是 JSON 对象。"
        )

    if set(data) != {"passed", "summary", "issues"}:
        raise CritiqueParseError(
            "Critique 必须且只能包含 "
            "passed、summary 和 issues。"
        )

    passed = data["passed"]
    summary = data["summary"]
    raw_issues = data["issues"]

    if not isinstance(passed, bool):
        raise CritiqueParseError(
            "passed 必须是布尔值。"
        )

    if not isinstance(summary, str) or not summary.strip():
        raise CritiqueParseError(
            "summary 必须是非空字符串。"
        )

    if not isinstance(raw_issues, list):
        raise CritiqueParseError(
            "issues 必须是 JSON 数组。"
        )

    issues = tuple(
        parse_issue(raw_issue)
        for raw_issue in raw_issues
    )

    if passed and issues:
        raise CritiqueParseError(
            "passed 为 true 时，issues 必须为空。"
        )

    if not passed and not issues:
        raise CritiqueParseError(
            "passed 为 false 时，issues 不能为空。"
        )

    return Critique(
        passed=passed,
        summary=summary.strip(),
        issues=issues,
    )
```

`parse_issue()` 继续检查字段和维度：

```python
def parse_issue(raw_issue: object) -> CritiqueIssue:
    if not isinstance(raw_issue, dict):
        raise CritiqueParseError(
            "每个 issue 都必须是 JSON 对象。"
        )

    if set(raw_issue) != {
        "dimension",
        "problem",
        "suggestion",
    }:
        raise CritiqueParseError(
            "issue 必须且只能包含 "
            "dimension、problem 和 suggestion。"
        )

    dimension = raw_issue["dimension"]
    problem = raw_issue["problem"]
    suggestion = raw_issue["suggestion"]

    if dimension not in ALLOWED_DIMENSIONS:
        raise CritiqueParseError(
            f"未知评审维度：{dimension!r}。"
        )

    for name, value in {
        "problem": problem,
        "suggestion": suggestion,
    }.items():
        if not isinstance(value, str) or not value.strip():
            raise CritiqueParseError(
                f"{name} 必须是非空字符串。"
            )

    return CritiqueIssue(
        dimension=dimension,
        problem=problem.strip(),
        suggestion=suggestion.strip(),
    )
```

这些检查只能证明 Critique 符合数据协议，不能证明 Critic 的判断一定正确。一个结构合法的 Critique 仍可能误判答案，或者提出与 Evidence 冲突的建议。

## 11.8 Generator：先产生可以检查的 Draft

为了让本章代码可以独立运行，`generator.py` 根据用户任务和 Evidence 生成第一次候选答案。

```python
GENERATOR_SYSTEM_PROMPT = """
你是城市旅行助手的答案生成器 Generator。

请根据用户任务和 Evidence 生成一段完整的中文候选答案。

规则：
1. 只能使用 Evidence 中已有的事实和数字。
2. 不要声称执行了新的工具。
3. 满足用户明确提出的长度、格式和内容要求。
4. 涉及天气、开放状态和票价时，
   明确说明它们来自本地模拟数据。
5. 只输出候选答案，不要输出分析、JSON 或代码块。
""".strip()
```

调用函数为：

```python
def generate_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
) -> str:
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": GENERATOR_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task}\n\n"
                    f"Evidence：\n{evidence}"
                ),
            },
        ],
    )

    draft = response.choices[0].message.content

    if not draft or not draft.strip():
        raise RuntimeError(
            "Generator 没有返回可用 Draft。"
        )

    return draft.strip()
```

在真实整合中，Generator 不是必需的额外步骤。ReAct 的 `finish.arguments.answer` 或 Plan-and-Solve 的 Finalize 输出，本身就可以作为 Draft 进入 Critic。本章保留 Generator，是为了完整展示“生成—评审—修订”三个职责，并让示例能够独立运行。

## 11.9 Critic：只检查，不直接重写

`critic.py` 使用结构化 Prompt 生成 Critique：

```python
CRITIC_SYSTEM_PROMPT = """
你是城市旅行助手的答案评审者 Critic。

请根据用户任务、Evidence 和当前 Draft 进行检查。

只检查四个维度：
- completeness
- evidence_grounding
- consistency
- constraint_compliance

输出必须是一个 JSON 对象，只包含：
passed、summary、issues。

每个 issue 只能包含：
dimension、problem、suggestion。

规则：
1. 只依据用户任务和 Evidence 判断。
2. 不要使用外部常识补充事实。
3. 不要重新执行工具。
4. 不要直接输出修订后的完整答案。
5. passed=true 时 issues 必须为空。
6. passed=false 时 issues 至少包含一项。
7. 不要输出 Markdown 代码块或额外说明。
""".strip()
```

模型调用完成后，立即进入 `parse_critique()`：

```python
def critique_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    draft: str,
) -> Critique:
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": CRITIC_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task}\n\n"
                    f"Evidence：\n{evidence}\n\n"
                    f"当前 Draft：\n{draft}"
                ),
            },
        ],
    )

    model_output = response.choices[0].message.content

    if not model_output:
        raise RuntimeError(
            "Critic 没有返回可用文本。"
        )

    return parse_critique(model_output)
```

Critic 的输出不会直接显示给最终用户。它是程序内部用于决定“当前答案是否需要修改”的结构化反馈。

## 11.10 Refiner：根据反馈进行 Revision

Refiner 必须同时看到用户任务、Evidence、当前 Draft 和 Critique。只给它旧答案与修改建议，会让 Critique 变成唯一事实来源；只给它 Evidence，又无法知道当前答案具体哪里需要修改。

`refiner.py` 中的 Prompt 可以写成：

```python
REFINER_SYSTEM_PROMPT = """
你是城市旅行助手的答案修订者 Refiner。

请根据用户任务、Evidence、当前 Draft 和 Critique，
生成一版修订后的完整答案。

规则：
1. 修复 Critique 中指出的有效问题。
2. Evidence 的优先级高于 Critique。
3. 只能使用 Evidence 中已有的事实和数字。
4. 保留 Draft 中已经正确且符合要求的内容。
5. 不要提及评审、修改、旧答案或修订过程。
6. 继续满足用户的长度、格式和表达约束。
7. 只输出修订后的答案，不要输出 JSON 或代码块。
""".strip()
```

先把 Critique 转换成清晰文本：

```python
def format_critique(critique: Critique) -> str:
    lines = [f"评审结论：{critique.summary}"]

    for index, issue in enumerate(
        critique.issues,
        start=1,
    ):
        lines.extend(
            [
                f"问题 {index}",
                f"维度：{issue.dimension}",
                f"问题：{issue.problem}",
                f"建议：{issue.suggestion}",
            ]
        )

    return "\n".join(lines)
```

随后请求修订：

```python
def revise_draft(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    draft: str,
    critique: Critique,
) -> str:
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": REFINER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f"用户任务：\n{user_task}\n\n"
                    f"Evidence：\n{evidence}\n\n"
                    f"当前 Draft：\n{draft}\n\n"
                    f"Critique：\n"
                    f"{format_critique(critique)}"
                ),
            },
        ],
    )

    revised_answer = (
        response.choices[0].message.content
    )

    if not revised_answer or not revised_answer.strip():
        raise RuntimeError(
            "Refiner 没有返回可用 Revision。"
        )

    return revised_answer.strip()
```

Refiner 输出的是新的自然语言答案，不是新的 Critique。它会成为下一轮 Critic 检查的 Draft。

## 11.11 为什么要限制修订次数

Critic 和 Refiner 都由大语言模型承担，它们不能保证一定收敛。可能出现：

```text
Critic 每轮提出新的写作偏好
Refiner 修复总价后又遗漏天气
Critic 与 Refiner 对字数理解不一致
答案在两种表达之间来回变化
```

因此，Reflection 必须设置有限的修订额度。本章使用：

```python
max_revisions: int = 2
```

这里限制的是最多生成多少个 Revision，而不是 Critique 调用次数。

当 `max_revisions=2` 时，最多发生：

```text
Draft 0 → Critique 1
Revision 1 → Critique 2
Revision 2 → Critique 3
```

如果第三次 Critique 仍然未通过，程序停止，不再生成 Revision 3。

核心循环为：

```python
def run_reflection(
    client: OpenAI,
    model_id: str,
    user_task: str,
    evidence: str,
    max_revisions: int = 2,
) -> str:
    if max_revisions < 0:
        raise ValueError(
            "max_revisions 不能小于 0。"
        )

    current_answer = generate_draft(
        client=client,
        model_id=model_id,
        user_task=user_task,
        evidence=evidence,
    )

    revisions = 0

    while True:
        critique = critique_draft(
            client=client,
            model_id=model_id,
            user_task=user_task,
            evidence=evidence,
            draft=current_answer,
        )

        show_critique(critique)

        if critique.passed:
            return current_answer

        if revisions >= max_revisions:
            raise RuntimeError(
                "已达到最大修订次数，"
                "当前答案仍未通过 Critic。"
            )

        current_answer = revise_draft(
            client=client,
            model_id=model_id,
            user_task=user_task,
            evidence=evidence,
            draft=current_answer,
            critique=critique,
        )
        revisions += 1
```

本章只设置一个最小硬边界。模型请求失败、Critique 格式错误和更完整的终止结果将在可靠性部分统一处理。

## 11.12 本章代码组织

本章目录为：

```text
code/chapter11/
├── generator.py
├── critic.py
├── refiner.py
├── main.py
└── README.md
```

各文件职责如下：

| 文件 | 职责 |
|---|---|
| `generator.py` | 根据用户任务和 Evidence 生成 Draft |
| `critic.py` | 生成、解析并校验 Critique |
| `refiner.py` | 根据 Evidence、Draft 和 Critique 生成 Revision |
| `main.py` | 准备主线 Evidence，控制有限修订过程 |
| `README.md` | 说明运行方式、默认任务和答案层边界 |

`main.py` 使用已经执行完成的模拟结果，而不再调用旅行工具：

```python
DEFAULT_USER_TASK = """
请根据已经获得的结果，为两人写一段不超过120字的出行建议。
回答必须包含北京天气、故宫开放状态、两张成人票总价，
并明确说明数据为本地模拟信息。
""".strip()


DEFAULT_EVIDENCE = """
1. get_weather({"city": "北京"})
   北京当前模拟天气为晴，温度30℃，湿度45%，微风。

2. get_attraction_info({"name": "故宫"})
   故宫位于北京，在当前模拟数据中处于开放状态，
   成人票价60元，活动类型为室内外步行。

3. calculator({"operation": "multiply", "a": 60, "b": 2})
   120
""".strip()
```

主程序连接三个角色：

```python
def main() -> None:
    load_dotenv()

    client = OpenAI(
        api_key=require_env("LLM_API_KEY"),
        base_url=require_env("LLM_BASE_URL"),
    )
    model_id = require_env("LLM_MODEL_ID")

    try:
        final_answer = run_reflection(
            client=client,
            model_id=model_id,
            user_task=DEFAULT_USER_TASK,
            evidence=DEFAULT_EVIDENCE,
            max_revisions=2,
        )
    except (
        CritiqueParseError,
        RuntimeError,
    ) as error:
        print(f"\nReflection 未完成：{error}")
        return

    print("\n最终回答：")
    print(final_answer)
```

程序不会在本章重新执行 `get_weather`、`get_attraction_info` 或 `calculator`。这些结果已经被整理成 Evidence，Reflection 只检查答案如何使用它们。

本章完整代码见：

```text
code/chapter11/
```

## 11.13 运行主线案例

从项目根目录运行：

```bash
python code/chapter11/main.py
```

一次可能的 Draft 为：

```text
北京天气晴朗，故宫开放，成人票价60元。
建议避开正午并注意防晒补水。
```

Critic 可能返回：

```json
{
  "passed": false,
  "summary": "答案遗漏总价和模拟数据说明。",
  "issues": [
    {
      "dimension": "completeness",
      "problem": "没有给出两张成人票总价。",
      "suggestion": "补充 Evidence 中 calculator 返回的120元。"
    },
    {
      "dimension": "constraint_compliance",
      "problem": "没有说明信息来自本地模拟数据。",
      "suggestion": "在回答中加入模拟数据说明。"
    }
  ]
}
```

Refiner 根据反馈生成 Revision：

```text
北京模拟天气为晴、30℃，故宫处于开放状态，
成人票价60元，两张票共120元。
建议避开正午并注意防晒补水。
以上信息来自本地模拟数据。
```

第二次 Critic 可能返回：

```json
{
  "passed": true,
  "summary": "答案与 Evidence 一致，覆盖全部要求且未超过120字。",
  "issues": []
}
```

程序随后返回当前答案。

完整过程为：

```text
用户任务 + Evidence
→ Generator
→ Draft
→ Critic
→ Critique
→ Refiner
→ Revision
→ Critic
→ 通过
→ Revised Answer
```

不同模型可能第一次就生成合格答案。此时 Critic 直接返回 `passed=true`，程序不会为了“体现 Reflection”而强制改写。

## 11.14 失败实验：错误 Evidence 不能靠 Reflection 修好

将默认 Evidence 中的计算结果从：

```text
120
```

改成：

```text
150
```

其他内容保持不变，再次运行程序。

Critic 可能要求答案使用“两张票总价150元”，Refiner 也可能将所有版本统一修改为150元。最终回答与 Evidence 变得一致，却仍然不符合真实乘法结果。

这不是 Reflection Loop 的格式错误。程序已经按照当前 Evidence 正常工作，真正的问题发生在更早的数据或工具层。

这个实验说明：

> Reflection 可以修复答案与 Evidence 之间的不一致，不能证明 Evidence 本身正确。

若工具结果错误，需要返回执行层检查数据源、参数或工具实现；若计划遗漏必要工具，需要返回计划或行动阶段。Reflection 不会自行重新执行工具，也不会自动重规划。

Critic 和 Refiner 也可能共享同一盲点。即使 Evidence 正确，它们也可能同时忽略某项约束；Refiner 修复一个问题时，也可能引入另一个问题。因此，有限修订提高的是发现和修复问题的机会，而不是正确性的保证。

## 11.15 Reflection 位于系统的什么位置

Reflection 可以接在不同执行策略之后。

ReAct 路径可以写成：

```text
ReAct 执行
→ Action-Observation Trace
→ finish.answer 作为 Draft
→ Reflection
→ Revised Answer
```

Plan-and-Solve 路径可以写成：

```text
Plan
→ StepResult
→ Finalize 生成 Draft
→ Reflection
→ Revised Answer
```

Reflection 不替代前面的工具、Parser、Agent Loop、Planner 或 Executor。它只接收已经获得的 Evidence 与候选答案。

三种策略在当前章节中的局部关系是：

```text
ReAct：获得 Observation 后决定下一步 Action
Plan-and-Solve：执行前生成并顺序完成 Plan
Reflection：候选答案生成后检查并修订
```

完整比较将放在第三部分总结中。本章只需要确认：Reflection 属于结果改进阶段，因此可以附加在不同执行策略之后。

## 11.16 当前系统快照

完成这一章后，城市旅行助手已经能够：

```text
接收用户任务、Evidence 和 Draft
→ 使用 Critic 生成结构化 Critique
→ 检查遗漏、证据错误、逻辑矛盾和用户约束
→ 使用 Refiner 生成 Revision
→ 在通过或达到修订上限时停止
```

当前流程为：

```text
执行策略产生 Evidence 与 Draft
→ Critic
→ Critique
→ Refiner
→ Revised Answer
```

程序仍然不能：

```text
重新执行失败工具
修复错误数据源
修改 ReAct 的行动路径
修改 Plan-and-Solve 的计划
对不同失败自动选择恢复策略
返回统一的结构化终止结果
```

当模型请求失败、Critique 输出非法 JSON、工具执行失败或 Agent 重复行动时，仅靠答案修订无法解决。下一章将集中处理：

> 不同层级的失败应当怎样区分，哪些问题值得重试，程序又应在什么条件下终止？

## 11.17 本章小结

这一章实现了答案层的 Reflection。

Generator 根据用户任务和 Evidence 生成 Draft；Critic 从完整性、Evidence 使用、逻辑一致性和用户约束四个维度生成结构化 Critique；Refiner 依据 Critique 修订当前答案，并始终继续受到原始任务和 Evidence 的约束。

Reflection 可以接在 ReAct 或 Plan-and-Solve 之后，但不替代执行策略。它能够改进候选答案如何使用已有结果，却不能修复错误工具数据、重新执行工具或自动修改计划。

完成本章后，应当能够回答：

1. 为什么工具执行正确，最终答案仍可能不合格？
2. Evidence、Draft、Critique 和 Revision 分别承担什么职责？
3. 为什么 Critique 不能被当作新的 Evidence？
4. Critic 为什么需要输出结构化、可操作的问题说明？
5. 为什么 Reflection 必须限制最大修订次数？

## 习题

**1. 检查遗漏问题**

把 Generator 的 Draft 固定为：

```text
北京天气晴朗，故宫开放，建议注意防晒。
```

观察 Critic 是否同时指出票价总额和模拟数据说明缺失。

**2. 检查 Evidence 使用错误**

让 Draft 把两张票总价写成60元。确认 Critique 将它归入 `evidence_grounding`，而不是只说“表达不清楚”。

**3. 检查协议矛盾**

手动向 `parse_critique()` 传入：

```json
{
  "passed": true,
  "summary": "答案通过。",
  "issues": [
    {
      "dimension": "completeness",
      "problem": "缺少总价。",
      "suggestion": "补充120元。"
    }
  ]
}
```

说明为什么程序应拒绝这份 Critique。

**4. 调整修订额度**

将 `max_revisions` 分别设置为 `0`、`1` 和 `2`。观察 Critic 与 Refiner 的调用次数，并说明为什么“修订次数”不等于“评审次数”。

**5. 接入已有候选答案**

把第九章的 `finish.arguments.answer` 或第十章的 Finalize 输出直接作为 Draft，跳过 Generator。说明 Reflection 为什么不依赖特定执行策略。

## 参考资料

1. [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651). NeurIPS, 2023.
2. [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366). NeurIPS, 2023.
