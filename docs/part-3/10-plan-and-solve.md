# 第十章 Plan-and-Solve：先规划再执行

第八章已经建立了一个能够连续调用工具的 Agent Loop。第九章在这个循环上加入 ReAct，使模型在每次行动前说明当前已经知道什么、还缺少什么，以及为什么选择下一项 Action。

这种逐轮判断适合根据最新 Observation 动态调整行动，但它通常只回答“当前下一步做什么”。面对一个包含多个明确要求的任务，模型可能在局部执行中漏掉后续目标，也可能在执行到一半才发现步骤顺序不顺。

例如：

```text
请查询北京的模拟天气，
查询故宫的模拟开放状态和成人票价，
计算两张成人票的总价，并给出出行建议。
```

这个任务包含天气查询、景点查询、费用计算和结果整理。ReAct 可以在每轮 Observation 后继续选择工具；另一种思路则是在执行任何工具之前，先把完整目标拆成一份可以检查的计划，再按照计划逐项执行。

这就是 Plan-and-Solve 的基本结构：

```text
用户目标 → Plan → 按步骤执行 → StepResult → Finalize
```

## 10.1 为什么要在执行前生成计划

假设模型没有先形成完整计划，而是直接选择当前 Action。它可能先查询天气，然后立即输出最终回答，遗漏故宫开放状态和费用计算；也可能先调用计算器，却还没有获得成人票价；还可能重复查询已经取得的信息。

这些问题不一定来自工具或 Parser。每一项 Action 都可能合法，工具也可能正常返回，只是连续的局部选择没有覆盖完整目标。

如果先生成一份计划，任务结构会更清楚：

```text
Step 1：查询北京的模拟天气。
Step 2：查询故宫的模拟开放状态和成人票价。
Step 3：使用第 2 步得到的成人票价，计算两张票的总价。
```

此时还没有执行任何工具，但开发者已经可以检查：

- 用户要求是否都被覆盖；
- 步骤顺序是否存在依赖错误；
- 每一步准备使用的工具是否真实存在；
- 计划是否过长；
- 某一步是否承担了多个不易区分的任务。

因此，计划不是为了增加一段模型输出，而是为了把“任务怎样分解”与“当前工具怎样执行”分成两个阶段。

## 10.2 什么是 Plan-and-Solve

Plan-and-Solve 最初是一种面向复杂推理任务的提示方法：模型先制定解决计划，再按照计划完成各个子任务。本章借用“先规划、后求解”的思想，将它落地到工具型 Agent 上。

在本书中，我们采用下面的工程化定义：

> **Plan-and-Solve 是一种先由 Planner 将用户目标分解为有顺序的 Plan，再由 Executor 根据计划和前序结果逐项执行，最后通过 Finalize 生成回答的控制方式。**

它可以写成：

```text
Planning：用户目标 + 工具集合 → Plan
Solving：PlanStep + 前序 StepResult → 当前 StepResult
Finalize：用户目标 + Plan + 全部 StepResult → 最终回答
```

本章实现的是静态线性计划：

```text
计划只生成一次
步骤按照编号顺序执行
每个步骤最多调用一个工具
执行期间不插入、删除或重新排列步骤
某一步失败时停止当前计划
```

这种实现适合依赖关系清楚、可顺序分解的任务。它不会根据工具结果自动修改原计划，也不包含并行、条件分支或循环计划。

## 10.3 Planner、Plan 与 PlanStep

Plan-and-Solve 的第一个阶段由 **Planner（规划器）** 完成。

> **Planner 是根据用户目标和当前工具集合生成任务分解的逻辑角色。**

Planner 不执行工具，也不产生天气、票价或计算结果。它只决定：

```text
需要完成哪些步骤
步骤应按什么顺序出现
每一步准备使用哪个工具
每一步应产生什么信息
```

Planner 的输出称为 **Plan（计划）**。

> **Plan 是针对当前用户目标生成的一组有序 PlanStep。它描述整个任务准备怎样完成，但不表示任何步骤已经执行。**

Plan 中的单个步骤叫做 **PlanStep（计划步骤）**。

> **PlanStep 是计划中的一个最小顺序单元，描述当前步骤的目标、预期工具和预期输出。**

本章使用下面的计划协议：

```json
{
  "goal": "经过整理的用户目标",
  "steps": [
    {
      "id": 1,
      "description": "当前步骤要完成什么",
      "tool": "计划使用的工具名称",
      "expected_output": "当前步骤应产生什么信息"
    }
  ]
}
```

主线任务可能生成：

```json
{
  "goal": "查询北京天气和故宫信息，计算两张成人票总价并给出建议。",
  "steps": [
    {
      "id": 1,
      "description": "查询北京的模拟天气。",
      "tool": "get_weather",
      "expected_output": "天气状况、温度、湿度和风力"
    },
    {
      "id": 2,
      "description": "查询故宫的模拟开放状态和成人票价。",
      "tool": "get_attraction_info",
      "expected_output": "开放状态、成人票价和活动类型"
    },
    {
      "id": 3,
      "description": "使用第2步得到的成人票价计算两张票的总价。",
      "tool": "calculator",
      "expected_output": "两张成人票的总价"
    }
  ]
}
```

计划中有工具名称，但没有具体 `arguments`。这是有意保留的边界。

第一步的城市和第二步的景点可以从用户目标中直接获得；第三步所需的票价却要等第二步执行后才知道。若 Planner 在工具尚未运行时直接写出：

```json
{
  "operation": "multiply",
  "a": 60,
  "b": 2
}
```

其中的 `60` 仍然只是模型猜测，而不是工具结果。Plan 只说明第三步需要使用第二步票价进行计算，具体参数留给 Executor 在执行时生成。

## 10.4 Plan 与 Workflow、Action 的区别

Plan、Workflow 和 Action 都可能包含多个步骤或操作，但它们出现于不同阶段。

| 概念 | 产生者 | 产生时间 | 主要作用 |
|---|---|---|---|
| Workflow | 开发者 | 程序开发阶段 | 为所有任务预先写好固定流程 |
| Plan | Planner | 当前任务开始后 | 针对本次目标生成完整任务分解 |
| PlanStep | Planner | 规划阶段 | 描述某一步要完成什么 |
| Action | Executor | 当前步骤执行前 | 提供真实工具名称和具体参数 |
| StepResult | 工具执行后 | 执行阶段 | 保存当前步骤实际得到的结果 |

固定 Workflow 可能始终规定：

```text
天气 → 景点 → 计算
```

无论用户只问天气，还是只要求计算，程序都沿用相同流程。

Plan 则由本次目标决定。只查询广州天气时，Plan 可以只有一个步骤；查询北京天气、故宫票价并计算三张票总价时，Plan 可以有三个步骤。

不过，Plan 一旦生成，本章的 Executor 会按照它顺序执行。因此，它比固定 Workflow 更能适应不同任务，但没有 ReAct 那样在每次 Observation 后自由改变工具路径。

PlanStep 也不等于 Action。下面是一条计划步骤：

```json
{
  "id": 3,
  "description": "使用第2步得到的成人票价计算两张票的总价。",
  "tool": "calculator",
  "expected_output": "两张成人票的总价"
}
```

它说明第三步准备使用计算器，却没有包含真实票价。等到第二步产生 StepResult 后，Executor 才能生成：

```json
{
  "step_id": 3,
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

前者属于计划，后者才是可以进入工具执行器的 Action。

## 10.5 用数据类表示计划与步骤结果

本章把核心数据结构放在：

```text
code/chapter10/models.py
```

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentAction:
    name: str
    arguments: dict[str, object]


@dataclass(frozen=True)
class PlanStep:
    id: int
    description: str
    tool_name: str
    expected_output: str


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: tuple[PlanStep, ...]


@dataclass(frozen=True)
class StepResult:
    step_id: int
    description: str
    tool_name: str
    arguments: dict[str, object]
    output: str


class PlanParseError(ValueError):
    """Planner 输出没有通过 Plan 协议校验。"""


class PlanExecutionError(RuntimeError):
    """某个计划步骤无法继续执行。"""
```

这里的 `AgentAction` 沿用第六章已经建立的数据边界，不重新赋予新含义。它仍然表示经过校验、可以交给工具执行器的行动。

`Plan` 使用元组保存步骤，是因为计划在解析通过后不应被 Executor 随意插入或删除步骤。`StepResult` 则记录一次 PlanStep 实际执行了什么：

```text
执行的是第几步
当前步骤原本要完成什么
最终调用了哪个工具
传入了哪些参数
工具返回了什么
```

在本书中：

> **StepResult 是 Executor 完成一个 PlanStep 后生成的结构化步骤结果。**

它不同于第七章的 Observation。Observation 主要用于把工具反馈送回模型；StepResult 则用于保存计划执行进度，并为后续步骤和 Finalize 提供结构化输入。

## 10.6 生成并校验 Plan

Planner 的系统提示词需要同时提供工具集合和计划协议。`planner.py` 中可以定义：

```python
PLANNER_SYSTEM_PROMPT = """
你是城市旅行助手的 Planner。

请根据用户目标生成一份完整的线性工具计划。

当前可用工具：

1. get_weather
   用途：查询一个城市的本地模拟天气。

2. get_attraction_info
   用途：查询一个景点的本地模拟开放状态、
   成人票价和活动类型。

3. calculator
   用途：执行加、减、乘、除。

输出必须是一个 JSON 对象，只包含 goal 和 steps。

每个 step 只能包含：
id、description、tool、expected_output。

规则：
1. 步骤编号从 1 开始连续递增。
2. 每个步骤只使用一个工具。
3. 覆盖用户目标中的全部明确要求。
4. 按依赖顺序排列步骤。
5. 不要提前填写工具 arguments。
6. 不要把未知天气、开放状态或票价写进计划。
7. 不要使用不存在的工具。
8. 不要输出 Markdown 代码块或额外说明。
""".strip()
```

模型输出仍然是不可信文本，因此 Plan 也需要解析和校验。`parse_plan()` 至少检查：

```text
顶层必须只有 goal 和 steps
goal 必须是非空字符串
steps 必须是非空列表
步骤数量不能超过 max_plan_steps
每个步骤只能包含规定字段
id 必须从 1 开始连续递增
description 和 expected_output 必须是非空字符串
tool 必须属于当前工具集合
```

核心代码如下：

```python
def parse_plan(
    model_output: str,
    allowed_tools: set[str],
    max_plan_steps: int = 6,
) -> Plan:
    data = parse_json_object(model_output)

    validate_exact_fields(
        data,
        expected={"goal", "steps"},
        context="Plan",
    )

    goal = data["goal"]
    raw_steps = data["steps"]

    if not isinstance(goal, str) or not goal.strip():
        raise PlanParseError("Plan.goal 必须是非空字符串。")

    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanParseError("Plan.steps 必须是非空数组。")

    if len(raw_steps) > max_plan_steps:
        raise PlanParseError(
            f"计划步骤不能超过 {max_plan_steps} 个。"
        )

    steps = []

    for expected_id, raw_step in enumerate(
        raw_steps,
        start=1,
    ):
        step = parse_plan_step(
            raw_step=raw_step,
            expected_id=expected_id,
            allowed_tools=allowed_tools,
        )
        steps.append(step)

    return Plan(
        goal=goal.strip(),
        steps=tuple(steps),
    )
```

结构校验可以拒绝 `search_web`、跳号步骤或额外字段，却不能自动证明计划在语义上覆盖了用户全部要求。例如，一个只包含天气和景点查询、却遗漏费用计算的 Plan，仍可能具有完全正确的 JSON 结构。

因此：

> Plan Parser 保证计划可以被程序安全读取，不保证计划一定完整或合理。

计划可见、可打印的价值就在这里。开发者可以在执行前检查模型怎样理解任务，而不是等所有工具运行结束后才发现遗漏。

## 10.7 Executor：把 PlanStep 变成真实 Action

计划通过校验后，程序进入执行阶段。负责完成当前 PlanStep 的逻辑角色称为 **Executor（执行器）**。

> **Executor 根据用户目标、完整 Plan、当前 PlanStep 和此前 StepResult，生成并执行当前步骤所需的具体 Action。**

Executor 每次只处理一个步骤。它不能重新排列计划，也不能把当前步骤指定的工具换成另一个工具。

执行第 3 步时，模型需要看到：

```text
原始用户目标
完整计划
当前 PlanStep
已经完成的 StepResult
```

请求内容可以组织为：

```python
def build_executor_input(
    user_goal: str,
    plan: Plan,
    current_step: PlanStep,
    completed_results: list[StepResult],
) -> str:
    return json.dumps(
        {
            "user_goal": user_goal,
            "plan": plan_to_dict(plan),
            "current_step": plan_step_to_dict(
                current_step
            ),
            "completed_results": [
                step_result_to_dict(result)
                for result in completed_results
            ],
        },
        ensure_ascii=False,
        indent=2,
    )
```

Executor Prompt 要求模型只为当前步骤生成 Action：

```python
EXECUTOR_SYSTEM_PROMPT = """
你是城市旅行助手的 Executor。

请严格执行 current_step，不要重新设计或修改 Plan。
根据用户目标和 completed_results，
为当前步骤生成一个具体工具 Action。

输出必须是一个 JSON 对象，只包含：
step_id、action、arguments。

规则：
1. step_id 必须等于 current_step.id。
2. action 必须等于 current_step.tool。
3. arguments 必须符合对应工具接口。
4. 只能使用 completed_results 中已经获得的数据。
5. 不要猜测尚未执行步骤的结果。
6. 每次只输出一个 Action。
7. 不要输出额外说明或 Markdown 代码块。
""".strip()
```

以第三步为例，Executor 可以从第二个 StepResult 中读取：

```text
成人票价60元
```

再生成：

```json
{
  "step_id": 3,
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

## 10.8 Executor 输出也必须校验

Planner 输出 Plan 后需要校验，Executor 输出 Action 时同样不能直接执行。

`parse_step_action()` 要检查：

```text
顶层字段只能是 step_id、action、arguments
step_id 必须等于当前 PlanStep.id
action 必须等于当前 PlanStep.tool_name
arguments 必须符合当前工具协议
```

核心边界为：

```python
def parse_step_action(
    model_output: str,
    current_step: PlanStep,
) -> AgentAction:
    data = parse_json_object(model_output)

    validate_exact_fields(
        data,
        expected={
            "step_id",
            "action",
            "arguments",
        },
        context="Executor Action",
    )

    if data["step_id"] != current_step.id:
        raise PlanExecutionError(
            "Executor 返回了错误的 step_id。"
        )

    if data["action"] != current_step.tool_name:
        raise PlanExecutionError(
            "Executor 选择的工具与 PlanStep 不一致。"
        )

    return validate_agent_action(
        action_name=data["action"],
        arguments=data["arguments"],
    )
```

这项检查十分重要。若 PlanStep 指定 `get_attraction_info`，Executor 却生成 `calculator`，程序不能因为计算器也是合法工具就继续执行。否则，Plan 只剩下展示作用，无法真正约束执行路径。

通过校验后，Executor 调用工具并创建 StepResult：

```python
def execute_plan_step(
    action: AgentAction,
    current_step: PlanStep,
) -> StepResult:
    try:
        output = execute_tool(
            tool_name=action.name,
            arguments=action.arguments,
        )
    except (TypeError, ValueError) as error:
        raise PlanExecutionError(
            f"Step {current_step.id} 执行失败：{error}"
        ) from error

    return StepResult(
        step_id=current_step.id,
        description=current_step.description,
        tool_name=action.name,
        arguments=dict(action.arguments),
        output=output,
    )
```

本章先不在步骤失败后自动改写计划。某个步骤无法执行时，Controller 停止当前计划并报告失败位置。是否重试、替换工具或重新规划，需要另行定义恢复策略。

## 10.9 按顺序执行完整计划

计划执行函数只需要遍历 `plan.steps`：

```python
def execute_plan(
    client: OpenAI,
    model_id: str,
    user_goal: str,
    plan: Plan,
) -> list[StepResult]:
    completed_results: list[StepResult] = []

    for current_step in plan.steps:
        action = request_step_action(
            client=client,
            model_id=model_id,
            user_goal=user_goal,
            plan=plan,
            current_step=current_step,
            completed_results=completed_results,
        )

        result = execute_plan_step(
            action=action,
            current_step=current_step,
        )

        completed_results.append(result)

    return completed_results
```

这里没有模型生成的 `finish`。计划中的步骤数量已经确定，Controller 会在全部步骤完成后退出循环。

这与第八章的 Agent Loop 不同：

```text
普通 Agent Loop：
每轮由模型决定继续调用工具还是 finish

Plan-and-Solve：
先确定全部 PlanStep
Controller 按步骤遍历
遍历完成后进入 Finalize
```

模型仍然参与每个步骤的具体参数生成，但它不能临时增加第四步，也不能在第二步后提前结束整个任务。

## 10.10 Finalize：根据完整结果生成回答

所有 PlanStep 完成后，程序已经获得一组 StepResult：

```text
StepResult 1：北京模拟天气为晴，30℃
StepResult 2：故宫开放，成人票价60元
StepResult 3：两张成人票总价120元
```

这些结果仍然不是面向用户组织的最终回答。程序需要根据原始目标、计划和全部结果进行一次汇总，这个阶段称为 **Finalize（最终整理）**。

> **Finalize 是在计划全部执行完成后，根据用户目标、Plan 和全部 StepResult 生成最终回答的阶段。**

Finalize 不执行工具，也不修改计划。它只使用已经得到的结果：

```python
FINALIZE_SYSTEM_PROMPT = """
你是城市旅行助手的最终回答模块。

请根据用户目标、已执行 Plan 和全部 StepResult
生成简洁、完整的中文回答。

规则：
1. 天气、开放状态、票价和计算结果
   必须来自 StepResult。
2. 不要补充未执行工具提供的事实。
3. 覆盖用户目标中的全部要求。
4. 明确说明信息来自本地模拟数据。
5. 只输出最终自然语言回答。
""".strip()
```

Finalize 的输入可以组织为：

```python
{
    "user_goal": user_goal,
    "plan": plan_to_dict(plan),
    "step_results": [
        step_result_to_dict(result)
        for result in completed_results
    ],
}
```

若某个计划步骤没有完成，当前程序不会进入 Finalize。这样可以避免在缺少关键结果时生成看似完整的答案。

## 10.11 连接完整流程

本章代码目录为：

```text
code/chapter10/
├── planner.py
├── executor.py
├── models.py
├── main.py
└── README.md
```

各文件职责如下：

| 文件 | 职责 |
|---|---|
| `models.py` | 保存 `Plan`、`PlanStep`、`StepResult` 和相关错误 |
| `planner.py` | 请求、解析并校验 Plan |
| `executor.py` | 为每个 PlanStep 生成 Action、执行工具并返回 StepResult |
| `main.py` | 加载配置、连接 Planning、Solving 和 Finalize |
| `README.md` | 说明运行方式、模拟数据和静态计划边界 |

`main.py` 的核心流程保持为：

```python
plan = create_plan(
    client=client,
    model_id=model_id,
    user_goal=user_goal,
)

show_plan(plan)

step_results = execute_plan(
    client=client,
    model_id=model_id,
    user_goal=user_goal,
    plan=plan,
)

final_answer = finalize_answer(
    client=client,
    model_id=model_id,
    user_goal=user_goal,
    plan=plan,
    step_results=step_results,
)
```

这段代码清楚地分成三个阶段：

```text
Planning → Solving → Finalize
```

Planner 不执行工具，Executor 不修改全局计划，Finalize 不补做遗漏步骤。

为了让本章代码目录能够独立运行，`executor.py` 可以保留三个既有旅行工具和注册表的教学快照；正文不再重复展示完整模拟数据与工具实现。

## 10.12 运行主线任务

从项目根目录执行：

```bash
python code/chapter10/main.py
```

输入：

```text
请查询北京的模拟天气，
查询故宫的模拟开放状态和成人票价，
计算两张成人票的总价，并给出出行建议。
```

一次可能的运行过程如下。

**Planning**

```text
Plan Goal：
查询北京天气和故宫信息，计算两张成人票总价并给出建议。

Step 1
Tool：get_weather
Description：查询北京的模拟天气。
Expected Output：天气状况、温度、湿度和风力

Step 2
Tool：get_attraction_info
Description：查询故宫的模拟开放状态和成人票价。
Expected Output：开放状态、成人票价和活动类型

Step 3
Tool：calculator
Description：使用第2步票价计算两张成人票总价。
Expected Output：两张成人票的总价
```

此时所有工具都还没有执行。

**Solving Step 1**

```json
{
  "step_id": 1,
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

StepResult：

```text
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

**Solving Step 2**

```json
{
  "step_id": 2,
  "action": "get_attraction_info",
  "arguments": {
    "name": "故宫"
  }
}
```

StepResult：

```text
故宫位于北京，在当前模拟数据中处于开放状态，
成人票价60元，活动类型为室内外步行。
```

**Solving Step 3**

```json
{
  "step_id": 3,
  "action": "calculator",
  "arguments": {
    "operation": "multiply",
    "a": 60,
    "b": 2
  }
}
```

StepResult：

```text
120
```

**Finalize**

最终回答可能为：

```text
北京当前模拟天气为晴，温度30℃；故宫处于开放状态，
成人票价60元，两张成人票共120元。建议避开正午，
注意防晒补水，并准备适合步行的鞋。
以上天气、开放状态和票价均来自本地模拟数据。
```

计划措辞可能不同，但合理运行应满足三个条件：计划覆盖用户全部明确要求；每个 Executor Action 与当前 PlanStep 指定工具一致；最终回答只使用 StepResult 中已获得的数据。

## 10.13 失败实验：步骤执行失败后会发生什么

输入一个确定会触发工具错误的任务：

```text
请计算10除以0，并根据实际结果回答。
```

Planner 可能生成一个计算步骤：

```json
{
  "goal": "计算10除以0并根据实际结果回答。",
  "steps": [
    {
      "id": 1,
      "description": "使用计算器执行10除以0。",
      "tool": "calculator",
      "expected_output": "计算结果或明确错误"
    }
  ]
}
```

Executor 生成：

```json
{
  "step_id": 1,
  "action": "calculator",
  "arguments": {
    "operation": "divide",
    "a": 10,
    "b": 0
  }
}
```

Action 可以通过协议校验，但计算器执行时抛出：

```text
ValueError: 除数不能为 0。
```

程序将其转换为：

```text
PlanExecutionError:
Step 1 执行失败：除数不能为 0。
```

当前计划到此停止，不会进入 Finalize，也不会自动生成替代步骤。

这个例子说明：

```text
Plan 合法
≠
每个步骤一定能够成功

步骤失败
≠
Executor 可以自行修改计划
```

动态重规划需要决定旧计划是否仍然有效、已完成 StepResult 是否保留、失败步骤是否重试，以及后续步骤如何重新编号。当前静态线性实现不处理这些问题。

## 10.14 ReAct 与 Plan-and-Solve 的边界

ReAct 和 Plan-and-Solve 都使用模型、工具、Parser 和 Controller，但决策时机不同。

| 对比维度 | ReAct | Plan-and-Solve |
|---|---|---|
| 核心问题 | 得到新反馈后，下一步做什么 | 执行前，整个任务怎样分解 |
| 计划可见性 | 全局结构通常隐含在逐轮决策中 | 执行前显式生成完整 Plan |
| 工具顺序 | 可以随 Observation 改变 | 当前版本按 Plan 固定 |
| 参数生成 | 每轮 Action 中生成 | 执行当前 PlanStep 时生成 |
| 结束方式 | 模型输出 `finish` | 全部步骤完成后进入 Finalize |
| 异常适应 | 可以在下一轮改变行动 | 当前版本遇到步骤失败即停止 |
| 适合任务 | 探索性强、结果会改变路径 | 结构清楚、依赖关系明确 |

例如，下面的任务更适合 ReAct：

```text
查询一个城市天气；
如果下雨就寻找室内活动；
如果景点关闭，再继续选择替代景点。
```

因为每一项结果都可能改变下一步。

下面的任务更适合当前 Plan-and-Solve：

```text
查询北京天气；
查询故宫票价；
使用票价计算两张票总价；
汇总结果。
```

因为步骤数量和依赖关系在执行前已经可以清楚描述。

两者不是先后升级关系。它们都从第八章的基础能力出发，解决执行控制中的不同问题。最终答案生成后，还可以接入独立的结果检查阶段，但这不会改变本章的计划与执行职责。

## 10.15 当前系统快照

完成这一章后，城市旅行助手已经能够：

```text
根据用户目标生成完整线性 Plan
在执行前展示并校验 Plan
按照 PlanStep 顺序生成具体 Action
保存每一步的 StepResult
使用全部 StepResult 生成最终回答
```

当前流程为：

```text
用户目标
→ Planner
→ Plan
→ Executor 逐步执行
→ StepResult
→ Finalize
→ 最终回答
```

当前系统仍然不会：

```text
根据步骤失败自动修改计划
并行执行彼此独立的步骤
表达 if/else 条件分支
把计划保存为跨任务长期记忆
```

Plan-and-Solve 解决了执行前的任务分解，却不能保证最终回答一定完整、准确地使用所有 StepResult。即使工具结果正确，最终回答仍可能遗漏开放状态、误写总费用，或未遵守用户要求的格式。

由此可以继续检查一个新的问题：

> 候选答案生成后，程序怎样判断它是否真正满足用户任务，并根据已有证据进行修订？

## 10.16 本章小结

这一章在第八章的基础组件上实现了 Plan-and-Solve。

Planner 根据用户目标和工具集合生成 Plan；Plan 由有序 PlanStep 组成，只描述步骤目标、预期工具和预期结果，不提前编造依赖工具执行的数据。Executor 根据当前 PlanStep 和已有 StepResult 生成具体 Action，并且不能偏离计划指定的工具。每一步执行完成后，程序保存 StepResult；所有步骤完成后，Finalize 根据完整结果生成最终回答。

完成本章后，应当能够回答：

1. Plan-and-Solve 为什么要把任务分解与工具执行分开？
2. Plan、PlanStep 和 Action 的区别是什么？
3. 为什么 Planner 不应提前填写依赖工具结果的参数？
4. Executor 为什么必须同时看到当前步骤和前序 StepResult？
5. 为什么当前静态计划在步骤失败后会停止，而不是自动修改计划？

## 习题

**1. 检查计划覆盖范围**

运行主线任务，逐项对照用户要求与 PlanStep。说明天气、景点信息和费用计算分别由哪一步负责。

**2. 构造非法计划**

把计划步骤编号修改为 `1、3、4`，或者把第二步工具改为 `search_web`。确认 `parse_plan()` 在工具执行前拒绝该计划。

**3. 让 Executor 偏离计划**

构造一个当前步骤为 `get_attraction_info`、Executor 却输出 `calculator` 的案例。说明为什么 Action 本身可能合法，但仍不能执行。

**4. 验证前序结果依赖**

暂时不把第二步 StepResult 提供给第三步 Executor，再观察它能否可靠生成票价参数。解释为什么计划描述不能代替真实执行结果。

**5. 比较两种控制方式**

对同一个天气、景点和费用任务分别运行 ReAct 与 Plan-and-Solve。比较执行前是否存在完整结构、工具顺序是否可变、结束方式和步骤失败后的行为。

## 参考资料

1. [Plan-and-Solve Prompting: Improving Zero-Shot Chain-of-Thought Reasoning by Large Language Models](https://arxiv.org/abs/2305.04091). ACL, 2023.
2. [Artificial Intelligence: A Modern Approach](https://aima.cs.berkeley.edu/). 4th Edition. Pearson, 2020.
