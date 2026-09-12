# 第一章 从语言模型到智能体

大语言模型能够回答问题、解释概念，也能够根据自然语言生成代码和文本。于是一个很自然的问题出现了：  

> 只要程序调用了大语言模型，它就是智能体吗？

要回答这个问题，不能只看程序使用了什么模型，而要看它是怎样运行的。一个系统是否具有智能体结构，关键在于它能否围绕目标观察环境、选择行动，并根据行动后的变化继续调整。  
明确这一判断标准，有助于理解后续章节中模型、环境、对话与工具的关系。

我们先从一个不使用大语言模型的温控程序开始。

## 1.1 一个简单的温控任务

假设房间当前温度为 30℃，我们希望把它调节到 25℃ 左右。允许温度在 24.5℃ 到 25.5℃ 之间波动。

程序可以采用下面的规则：

```text
温度高于 25.5℃：制冷
温度低于 24.5℃：制热
温度位于目标范围：保持
```

如果每次制冷或制热都会让温度变化 1.5℃，程序的运行过程可能是：

```text
30.0℃ → 制冷 → 28.5℃
28.5℃ → 制冷 → 27.0℃
27.0℃ → 制冷 → 25.5℃
25.5℃ → 保持 → 任务完成
```

这个过程并不是一次计算后直接返回结果。程序每执行一次行动，都要重新读取房间温度，再根据新的温度决定下一步。

它形成了一个闭环：

```text
读取温度 → 选择行动 → 改变温度 → 再次读取温度
```

如果温度仍然偏高，程序继续制冷；如果已经进入目标范围，程序停止调节。下一步行动并不是在程序启动时一次性确定的，而是随着房间温度的变化逐步产生。

这已经具备了智能体最基本的运行方式。

## 1.2 普通程序、工作流和智能体

温控程序与我们熟悉的普通程序有什么不同？可以先比较三个例子。

### 普通程序：一次输入得到一次结果

下面的函数接收两个数字并返回它们的和：

```python
def add(a: float, b: float) -> float:
    return a + b
```

它的运行过程是：

```text
输入 → 处理 → 输出
```

程序不需要持续观察外部变化，也不会在输出之后继续决定下一步。

### 工作流：按照预先安排的步骤运行

报销流程可以写成：

```text
提交申请 → 检查金额 → 主管审批 → 财务归档
```

其中也可以包含分支：

```text
金额不超过 1000 元 → 主管审批
金额超过 1000 元 → 主管审批 + 财务复核
```

这类系统比单个函数更复杂，但主要步骤和分支通常由开发者提前写好。程序运行时只是沿着已经设计好的路径前进。

这种结构称为**工作流（Workflow）**。

### 智能体：根据当前情况决定下一步

温控程序没有提前写死“先制冷三次，再保持一次”。它只规定了判断规则。每一轮究竟制冷、制热还是保持，要根据当前温度决定。

如果房间从 20℃ 开始，程序会先制热；如果从 25℃ 开始，它会直接保持。初始环境不同，实际行动序列也会不同。

因此，工作流与智能体的主要区别不在于代码长短，而在于下一步怎样产生：

```text
工作流：下一步主要由预设流程决定
智能体：下一步根据目标和当前环境决定
```

现实系统并不一定只能属于其中一类。一个完整应用可以在稳定环节使用固定工作流，在需要动态判断的环节使用智能体。这里需要识别的是两种不同的控制方式。

## 1.3 大语言模型应用与智能体

现在回到开头的问题。

下面的程序把用户问题发送给大语言模型，再返回模型生成的回答：

```python
answer = llm.generate(user_input)
```

它的结构仍然可以概括为：

```text
用户输入 → 大语言模型 → 文本回答
```

这样的程序属于**大语言模型应用（LLM Application）**。它使用模型理解自然语言或生成内容，但一次模型调用本身并没有自动形成观察、行动和反馈的闭环。

例如，模型可以生成：

```text
房间温度过高，建议开启空调制冷。
```

这只是文本。除非程序真的执行制冷操作、读取新的温度，并把变化用于下一次判断，否则环境并没有因为这句话发生改变。

因此：

> 使用大语言模型不等于拥有智能体；不使用大语言模型，也不妨碍一个程序具有智能体结构。

温控程序只使用固定规则，却能够根据环境变化持续调整行动。相反，一个只调用模型生成回答的程序虽然使用了 LLM，却可能没有任何环境交互。

四种程序结构可以这样比较：

| 类型 | 主要特点 | 典型过程 |
|---|---|---|
| 普通程序 | 对输入进行确定性处理 | 输入 → 处理 → 输出 |
| 工作流 | 按照预设步骤和分支运行 | 步骤 A → 步骤 B → 步骤 C |
| LLM 应用 | 使用模型理解或生成内容 | 用户输入 → LLM → 文本回答 |
| Agent | 围绕目标，根据环境反馈持续选择行动 | 观察 → 决策 → 行动 → 新观察 |

这四类结构并不是互相排斥的。普通代码构成了所有系统的基础，工作流中可以调用 LLM，Agent 内部也可以包含固定规则和模型调用。判断时应关注系统的运行关系，而不是名称。

## 1.4 从温控过程认识 Agent 的组成

温控案例中已经出现了智能体的几个基本部分。我们现在逐一为它们命名。

### 目标：系统希望达到什么结果

**目标（Goal）**描述系统希望达到的结果。

温控任务的目标不是“当前温度为 30℃”，而是：

```text
将房间温度保持在 24.5℃ 到 25.5℃ 之间
```

当前温度描述现在发生了什么，目标描述最终希望环境变成什么样。没有目标，程序就无法判断任务是否已经完成。

### 环境：系统正在与什么交互

**环境（Environment）**是 Agent 所处并能够影响的外部对象。

在温控案例中，环境是房间及其温度变化过程。程序执行制冷或制热后，房间温度会发生变化。

环境不一定是物理世界。文件系统、数据库、网页、游戏世界或软件界面，都可以成为程序交互的环境。

### 环境状态：环境现在是什么样

**环境状态（Environment State）**表示环境在某一时刻的真实情况。

房间环境中可能同时存在：

```text
当前温度
湿度
空调状态
室外温度
```

这些信息共同构成环境状态。

### 观察：Agent 实际看到了什么

Agent 不一定能够直接获得环境的全部状态。它通过传感器或程序接口取得的信息，称为**观察（Observation）**。

本例只读取当前温度：

```python
observation = {
    "temperature": 30.0
}
```

环境中可能还有湿度和室外温度，但如果程序没有读取它们，它们就不属于当前 Observation。

因此，环境状态与观察并不完全相同：

```text
环境状态：世界真实是什么样
观察：Agent 此刻获得了哪些信息
```

### 状态：Agent 自己保存了什么

**状态（State）**是 Agent 在运行过程中保存，并可能影响后续判断的信息。

最简单的温控程序只依赖当前温度，不需要记住之前发生了什么。它的内部状态可以很少，甚至为空。

如果程序需要记录上一轮行动、连续制冷次数或历史温度，这些信息就属于 Agent 的状态。

### 决策：根据当前情况选择什么

**决策（Decision）**是根据目标、当前观察以及已有状态，选择下一步行动的过程。

温控程序中的决策规则是：

```python
if temperature > upper_bound:
    return "cool"

if temperature < lower_bound:
    return "heat"

return "maintain"
```

这里没有复杂模型，只有开发者写下的条件判断。但它仍然完成了“根据当前信息选择下一步”的职责。

### 行动：Agent 要环境做什么

**行动（Action）**是 Agent 选择并交给环境执行的操作。

温控程序允许三种行动：

```text
cool       制冷
heat       制热
maintain   保持
```

行动与决策不是同一件事。决策负责选择 `cool`，环境执行制冷后，温度才真正下降。

把这些概念放回温控任务，可以得到：

| 概念 | 温控任务中的对应内容 |
|---|---|
| Goal | 温度进入 24.5℃～25.5℃ |
| Environment | 房间及其温度变化 |
| Environment State | 当前真实温度等环境信息 |
| Observation | 程序读取到的温度 |
| State | Agent 内部保存的历史或计数 |
| Decision | 根据温度选择制冷、制热或保持 |
| Action | `cool`、`heat`、`maintain` |

## 1.5 Agent Loop：把行动结果带回决策

如果程序只读取一次温度、选择一次行动，然后立即结束，它仍然无法保证目标已经达到。

例如，当前温度为 30℃，程序选择一次制冷，温度下降到 28.5℃。此时房间仍然过热，程序必须再次读取温度并继续判断。

因此，完整过程需要不断重复：

```text
观察 → 决策 → 行动 → 新观察
```

这种围绕目标持续运行的闭环称为 **Agent Loop（智能体循环）**。

最小伪代码如下：

```python
while not finished:
    observation = environment.observe()
    action = agent.decide(observation)
    environment.apply(action)
    finished = check_goal(environment)
```

重点并不在于代码中出现了 `while`。下面的代码也有循环：

```python
for number in range(10):
    print(number)
```

但它只是重复打印数字。每次打印的结果不会改变下一次选择，也不存在需要达到的环境目标，所以它不是 Agent Loop。

判断一个循环是否具有智能体闭环，应当检查：

```text
行动是否通过执行器作用于环境，并产生可观察的执行结果
环境是否产生新的观察
新的观察是否改变下一步决策
```

本书在这里采用的是区分普通 LLM 应用与工具型 Agent 的工程判断标准，不是唯一的正式定义。Action 可以修改环境，也可以查询环境；只读查询虽然不改变外部状态，但取得的新信息仍会改变 Agent 后续的决策依据。

## 1.6 实现规则温控 Agent

完整代码位于：

```text
code/chapter01/simple_reflex_agent.py
```

代码分为环境、Agent 和运行循环三部分。

### 环境保存温度并执行行动

```python
class RoomEnvironment:
    def __init__(
        self,
        temperature: float = 30.0,
        change_per_action: float = 1.5,
    ) -> None:
        self.temperature = temperature
        self.change_per_action = change_per_action

    def observe(self) -> dict[str, float]:
        return {"temperature": self.temperature}

    def apply(self, action: str) -> None:
        if action == "cool":
            self.temperature -= self.change_per_action
        elif action == "heat":
            self.temperature += self.change_per_action
        elif action == "maintain":
            return
        else:
            raise ValueError(f"未知行动：{action}")
```

`observe()` 返回当前温度，`apply()` 根据行动改变温度。环境不负责决定应该执行哪个行动。

### Agent 根据观察选择行动

```python
class SimpleReflexAgent:
    def __init__(
        self,
        target_temperature: float = 25.0,
        tolerance: float = 0.5,
    ) -> None:
        self.target_temperature = target_temperature
        self.tolerance = tolerance

    def decide(self, observation: dict[str, float]) -> str:
        temperature = observation["temperature"]
        lower_bound = self.target_temperature - self.tolerance
        upper_bound = self.target_temperature + self.tolerance

        if temperature > upper_bound:
            return "cool"

        if temperature < lower_bound:
            return "heat"

        return "maintain"
```

这个 Agent 只读取当前温度，不保存历史，因此称为**简单反射智能体（Simple Reflex Agent）**。相同的 Observation 总会得到相同的 Action。

### 循环连接 Agent 与环境

```python
def run_agent(max_steps: int = 10) -> None:
    environment = RoomEnvironment(
        temperature=30.0,
        change_per_action=1.5,
    )
    agent = SimpleReflexAgent(
        target_temperature=25.0,
        tolerance=0.5,
    )

    for step in range(1, max_steps + 1):
        observation = environment.observe()
        action = agent.decide(observation)

        before = observation["temperature"]
        environment.apply(action)
        after = environment.observe()["temperature"]

        print(
            f"Step {step}: "
            f"temperature={before:.1f}℃, "
            f"action={action}, "
            f"after={after:.1f}℃"
        )

        if action == "maintain":
            print("目标温度已达到，任务结束。")
            return

    print("在限定步数内未达到目标温度。")
```

这里的职责是清楚分开的：

```text
Environment：提供观察并执行行动
Agent：根据观察选择行动
run_agent()：让观察、决策和行动不断循环
```

如果把判断和环境修改全部写进同一个函数，程序仍然可能运行，但我们很难分辨哪一部分属于决策，哪一部分属于环境变化。将职责分开，可以更清楚地观察闭环是怎样形成的。

## 1.7 运行并分析结果

执行：

```bash
python code/chapter01/simple_reflex_agent.py
```

预期输出为：

```text
Step 1: temperature=30.0℃, action=cool, after=28.5℃
Step 2: temperature=28.5℃, action=cool, after=27.0℃
Step 3: temperature=27.0℃, action=cool, after=25.5℃
Step 4: temperature=25.5℃, action=maintain, after=25.5℃
目标温度已达到，任务结束。
```

逐轮观察：

| 轮次 | 读取到的温度 | 选择的行动 | 行动后的温度 |
|---:|---:|---|---:|
| 1 | 30.0℃ | `cool` | 28.5℃ |
| 2 | 28.5℃ | `cool` | 27.0℃ |
| 3 | 27.0℃ | `cool` | 25.5℃ |
| 4 | 25.5℃ | `maintain` | 25.5℃ |

第三轮行动结束后，温度已经进入目标范围。但程序需要在第四轮重新观察，才能知道目标已经达到，并选择 `maintain`。

这正是闭环的意义：

```text
行动造成变化
→ 程序重新观察变化
→ 新观察影响下一步行动
```

## 1.8 失败实验：有闭环不等于一定成功

将每次行动造成的温度变化改为 3℃：

```python
environment = RoomEnvironment(
    temperature=30.0,
    change_per_action=3.0,
)
```

运行过程可能变成：

```text
Step 1: temperature=30.0℃, action=cool, after=27.0℃
Step 2: temperature=27.0℃, action=cool, after=24.0℃
Step 3: temperature=24.0℃, action=heat, after=27.0℃
Step 4: temperature=27.0℃, action=cool, after=24.0℃
...
在限定步数内未达到目标温度。
```

温度在 24℃ 和 27℃ 之间来回变化，始终无法进入 24.5℃～25.5℃ 的目标范围。

程序仍然具有完整闭环：

```text
观察温度 → 选择行动 → 改变温度 → 再次观察
```

失败的原因不是缺少循环，而是行动幅度与决策规则不匹配。每次变化 3℃ 太大，使程序不断越过目标区间。

可以采用多种改进方法，例如减小每次温度变化、扩大允许误差，或者提供强弱不同的制冷行动。这里最重要的结论是：

> Agent Loop 只能让系统根据反馈持续调整，不能保证当前决策规则一定能够完成目标。

## 1.9 如何判断一个系统是否具有 Agent 结构

面对一个程序，可以依次检查四件事：

1. 它是否围绕一个明确目标运行？
2. 它是否能够获得环境的当前观察？
3. 它是否会根据目标和观察选择行动？
4. 行动产生的结果或新观察是否会影响下一次选择？

如果这四项关系都存在，程序通常已经具有 Agent 的核心结构。

下面几种判断并不可靠：

| 说法 | 为什么不可靠 |
|---|---|
| 使用了大语言模型，所以是 Agent | 模型可能只生成一次文本 |
| 包含多个步骤，所以是 Agent | 多个步骤可能只是固定工作流 |
| 代码中存在循环，所以是 Agent | 循环结果可能不会影响下一次决策 |
| 类名叫 `Agent`，所以是 Agent | 名称不能代替运行结构 |
| 没有使用大语言模型，所以不是 Agent | 规则同样可以完成决策 |

因此，判断 Agent 的重点不是寻找某个类名或框架，而是寻找下面的闭环：

```text
目标 → 观察 → 决策 → 行动 → 新观察
```

## 1.10 本章小结

这一章从规则温控任务出发，认识了普通程序、工作流、大语言模型应用和 Agent 的结构差异。

普通程序通常完成一次输入到输出的处理；工作流按照开发者预先安排的步骤运行；大语言模型应用使用模型理解或生成内容；Agent 则围绕目标，根据环境观察选择行动，并让行动结果继续影响后续决策。

温控程序虽然没有使用大语言模型，却已经包含 Agent 的基本组成：

```text
Goal
Environment
Environment State
Observation
State
Decision
Action
Agent Loop
```

本章最重要的结论是：

> Agent 不是某个模型、框架或类名，而是一种围绕目标，通过观察、决策、行动和反馈持续运行的程序结构。

规则能够处理开发者已经预见并写入代码的情况。当输入不再是明确的数值，而是“房间有些闷热”“调到适合办公的温度”这样的自然语言时，固定条件就很难覆盖所有表达。仅靠增加更多 `if-else`，程序会越来越复杂。

这时，问题从“怎样写出更多规则”转变为“程序怎样理解自然语言”。

## 习题

**1. 判断程序结构**

判断下面的系统更接近普通程序、工作流、大语言模型应用还是 Agent，并说明理由。

- 输入两个数字并返回它们的和；
- 按照固定顺序读取文章、生成摘要并保存文件；
- 接收一个问题并返回大语言模型生成的回答；
- 根据当前库存决定补货数量，补货后重新读取库存并继续判断；
- 根据报销金额进入开发者预先设置的审批分支。

**2. 修改目标**

将目标温度修改为 22℃，保持其他参数不变。运行程序并记录完成任务所需的轮数。

分别指出代码中的 Goal、Observation、Decision 和 Action。

**3. 修改环境**

将初始温度改为 20℃，观察 Agent 会选择什么行动。说明环境状态变化后，为什么不需要修改决策函数的结构。

**4. 制造震荡**

将 `change_per_action` 分别改为 2℃、3℃ 和 4℃，观察哪些设置能够进入目标区间。解释失败时问题出在循环、规则还是环境参数。

**5. 设计一个 Agent**

从自动浇花、库存补充、游戏角色巡逻或机器人避障中选择一个场景，写出它的 Goal、Environment、Environment State、Observation、State、Decision 和 Action。

## 参考资料

1. [Artificial Intelligence: A Modern Approach](https://aima.cs.berkeley.edu/). 4th Edition. Pearson, 2020.
2. [An Introduction to MultiAgent Systems](https://www.wiley.com/en-us/An+Introduction+to+MultiAgent+Systems%2C+2nd+Edition-p-9780470519462). 2nd Edition. Wiley, 2009.
3. [Hello-Agents：从零开始构建智能体](https://github.com/datawhalechina/hello-agents). GitHub 开源教程。
