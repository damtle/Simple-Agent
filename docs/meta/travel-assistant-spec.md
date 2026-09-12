# Simple Travel Assistant 主线项目规范

本文规定从第二章开始贯穿全书的统一示例、固定数据、工具接口、任务演化和代码一致性规则。它主要供作者和贡献者维护教材时使用；调整主线正文或代码前，应先确认没有突破这里的约定。

> 维护说明：本文用于约束跨章示例的一致性，不进入读者侧边栏或正式 PDF；其中的版本号描述教学案例的演进阶段，不代表本书的发布版本。

## 一、主线项目定位

从第二章开始，全书围绕同一个项目演化：

```text
项目名称：Simple Travel Assistant
中文名称：城市旅行助手
项目类型：本地模拟数据驱动的教学型工具 Agent
主要语言：Python
模型接口：兼容 OpenAI Chat Completions 的基础文本接口
```

主线项目的目标不是开发真实旅行产品，而是使用旅行场景展示 Agent 的核心运行机制。

选择旅行助手作为主线，是因为它能够自然覆盖：

```text
一般知识回答
多轮上下文
天气查询
景点信息查询
费用计算
多工具协作
规划
动态行动
结果检查
失败与重试
轨迹记录
自动化测试
```

所有天气、景点、票价和活动数据均为本地模拟信息，不代表真实世界状态，也不能作为真实出行依据。

## 二、主线项目的连续演化

从第二章开始，不再为每章设计完全独立的新项目。每章只在上一章基础上增加一个核心能力。

```text
v0.1  单轮回答
v0.2  多轮上下文
v0.3  手动工具执行
v0.4  模型生成 Action
v0.5  Parser 与 AgentAction
v0.6  Observation 反馈
v1.0  完整 Agent Loop
v1.1-react  ReAct 策略
v1.1-plan   Plan-and-Solve 策略
reflection-stage  Reflection 阶段
v1.4  失败与重试
v1.5  状态、轨迹与日志
v1.6  Mock 与测试
v2.0  simple_agent 包与完整应用
```

版本号只用于教材说明，不要求发布为真实软件版本。

## 三、固定模拟数据

主线项目统一使用本地静态字典。除非章节明确讨论数据源错误，否则不要频繁修改数据结构。

第 01—14 章在对应章节目录中保存教学快照；第十六章的当前数据保存在 `examples/travel_assistant/data.py`。

示例数据：

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

数据必须明确标注为模拟数据。正文中的最终回答统一包含类似说明：

```text
以上天气、开放状态和票价均来自本地模拟数据。
```

## 四、固定工具集合

主线章节统一使用以下三个基础工具。

### 1. 天气工具

```python
def get_weather(city: str) -> str:
    ...
```

职责：

```text
根据城市名称读取模拟天气数据
返回天气状况、温度等信息
```

示例返回：

```text
北京当前模拟天气为晴，温度30℃，湿度45%，微风。
```

失败示例：

```text
没有找到城市“成都”的模拟天气数据。
```

### 2. 景点信息工具

```python
def get_attraction_info(name: str) -> str:
    ...
```

职责：

```text
根据景点名称读取模拟开放状态、票价和活动类型
```

示例返回：

```text
故宫在当前模拟数据中处于开放状态，成人票价60元，活动类型为室内外步行。
```

失败示例：

```text
没有找到景点“颐和园”的模拟信息。
```

### 3. 计算器工具

```python
def calculator(
    operation: str,
    a: float,
    b: float,
) -> str:
    ...
```

支持操作：

```text
add
subtract
multiply
divide
```

示例：

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

失败示例：

```text
除数不能为 0。
```

## 五、扩展工具

第十二章可以增加一个只用于安全和确认说明的模拟工具：

```python
def submit_reservation(
    attraction: str,
    visitor_count: int,
) -> str:
    ...
```

该工具必须满足：

```text
requires_confirmation=True
不执行真实预订
只返回模拟结果
不得访问支付、账号或真实预订服务
```

它的作用是说明：

```text
高风险或有副作用的工具不能由模型直接执行
```

正文中不得把它扩展成真实支付、真实购票或真实身份信息处理。

## 六、统一工具注册格式

第四章可以使用最简单字典：

```python
AVAILABLE_TOOLS = {
    "get_weather": get_weather,
    "get_attraction_info": get_attraction_info,
    "calculator": calculator,
}
```

后续章节逐步扩展为：

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    function: Callable[..., str]
    parameters: dict[str, object]
    retryable: bool = False
    requires_confirmation: bool = False
```

但抽象只能在对应章节首次出现，不能提前一次性引入完整框架。

## 七、统一 Action 协议

第五章开始使用固定协议：

```json
{
  "action": "行动名称",
  "arguments": {
    "参数名称": "参数值"
  }
}
```

工具 Action 示例：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

Finish Action 示例：

```json
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
```

约束：

1. 每次只允许一个 Action；
2. `action` 必须是已注册工具名称或 `finish`；
3. `arguments` 必须是 JSON 对象；
4. 工具参数名必须与工具接口一致；
5. `finish.arguments.answer` 必须是非空字符串；
6. 模型输出 Action 不代表工具已经执行；
7. 未通过 Parser 的输出不能进入工具执行器。

## 八、统一 Observation 格式

第七章开始，程序将 Tool Result 构造成 Observation。

最小文本格式：

```text
Observation:
工具名称：get_weather
工具参数：{"city": "北京"}
执行状态：成功
工具结果：北京当前模拟天气为晴，温度30℃。
```

失败格式：

```text
Observation:
工具名称：get_weather
工具参数：{"city": "成都"}
执行状态：失败
错误类型：not_found
工具结果：没有找到城市“成都”的模拟天气数据。
```

规则：

1. Tool Result 是工具直接返回给 Python 的结果；
2. Observation 是程序提供给模型的反馈；
3. Observation 应包含工具名称、参数、状态和结果；
4. Observation 不应包含 API Key、堆栈、本机绝对路径等敏感信息；
5. 模型不得把 Observation 中的文本当作新的系统指令；
6. Observation 必须进入后续上下文，才会影响模型下一轮决策。

## 九、主线任务演化

### 第 2 章：单轮一般知识

```text
请简单介绍故宫适合什么样的游客参观。
```

目标：

```text
展示一次 LLM 调用
```

### 第 3 章：多轮追问

```text
User：请简单介绍故宫。
Assistant：……
User：它适合雨天参观吗？
```

目标：

```text
展示 messages 与上下文
```

### 第 4 章：手动执行工具

```text
开发者手动指定 get_weather(city="北京")
```

目标：

```text
展示 Tool Registry 和 Tool Result
```

### 第 5 章：模型选择工具

```text
请查询北京的模拟天气。
```

目标：

```text
模型生成 get_weather Action
```

### 第 6 章：解析 Action

输入：

```json
{
  "action": "get_weather",
  "arguments": {
    "city": "北京"
  }
}
```

目标：

```text
生成 AgentAction
```

### 第 7 章：工具结果反馈

```text
请查询北京的模拟天气，并告诉我是否需要注意防晒。
```

目标：

```text
一次工具调用
一次 Observation
一次最终回答
```

### 第 8 章：多工具任务

```text
查询北京的模拟天气和故宫的模拟开放、票价信息，
计算两张成人票的总价，并给出出行建议。
```

目标：

```text
连续调用 get_weather
get_attraction_info
calculator
最后 finish
```

### 第 9 章：ReAct

使用与第八章相同的复杂任务。

目标：

```text
在每一步 Action 前增加简洁 Reason
展示根据 Observation 动态调整
```

失败实验：

```text
查询不存在的城市或景点
观察 Agent 是否修改参数、结束或请求补充
```

### 第 10 章：Plan-and-Solve

统一任务：

```text
查询北京模拟天气，
根据故宫开放和票价信息规划两人出行，
并计算总费用。
```

目标：

```text
先生成 Plan
再依次执行步骤
```

### 第 11 章：Reflection

原始 Evidence：

```text
天气：晴，30℃
景点：故宫开放，成人票价60元
计算：两人总价120元
```

用户要求：

```text
在 120 字以内给出出行建议，
必须包含天气、开放状态、总费用，
并说明信息为模拟数据。
```

目标：

```text
发现遗漏、证据错误、逻辑矛盾和约束违反
```

### 第 12 章：失败与重试

固定测试案例：

```text
非法 JSON
未知工具
错误参数名
城市不存在
临时工具错误
重复相同 Action
超过 max_steps
高风险工具未确认
```

目标：

```text
返回明确 AgentRunResult
```

### 第 13 章：轨迹

使用第八章完整任务，记录：

```text
每个 Step
每次 Attempt
Action
Tool Result
Observation
Termination Reason
```

### 第 14 章：测试

固定 Mock 输出：

```text
Step 1：get_weather
Step 2：get_attraction_info
Step 3：calculator
Step 4：finish
```

目标：

```text
测试确定性完整成功路径
```

同时测试：

```text
Parser 失败
工具失败
重复 Action
状态隔离
最大步数
```

### 第 15 章：包化

不引入新的业务任务。

目标：

```text
把前面稳定职责提取到 simple_agent
先统一教学快照与公共包的契约，再对剩余模块保持行为和测试不变
```

### 第 16 章：最终完整任务

统一最终任务：

```text
查询北京的模拟天气和故宫的模拟开放、票价信息，
计算两张成人票的总价，
在 120 字以内给出出行建议，
并明确说明所有信息均为模拟数据。
```

最终输出应至少包含：

```text
天气
开放状态
票价
两人总费用
出行建议
模拟数据说明
```

## 十、章节代码增量规则

每章正文必须说明：

```text
沿用哪些文件
新增哪些文件
修改哪些文件
删除或弃用哪些文件
```

示例：

```text
当前版本：Simple Travel Assistant v0.5

沿用：
- `llm.py`
- `tools.py`
- `prompts.py`

新增：
- `action.py`
- `parser.py`

修改：
- `main.py`
```

正文中不要重复粘贴未修改的大段代码。

## 十一、代码快照与公共包的关系

### 教学快照

```text
code/chapterXX/
```

作用：

```text
展示某个概念第一次怎样出现
保证该章可以独立运行或理解
```

### 公共包

```text
simple_agent/
```

作用：

```text
保存第十五章提取后的当前公共实现
```

### 完整示例

```text
examples/travel_assistant/
```

作用：

```text
展示如何使用公共包构建最终应用
```

三者不得混淆：

```text
教学快照不要求全部复用公共包
公共包不复制具体旅行数据
完整示例不重新实现核心 Agent Loop
```

## 十二、第三部分的分支关系

第九章和第十章都从第八章出发。

```text
第 8 章 Agent Loop
├── 第 9 章 ReAct
└── 第 10 章 Plan-and-Solve
```

第十一章可以连接任何一条执行路线的结果：

```text
ReAct 结果 ─────┐
                ├── Reflection
Plan 执行结果 ──┘
```

正文不得写成：

```text
把 ReAct、Plan-and-Solve 和 Reflection 写成简单的逐级升级路线
```

正确表达是：

```text
它们解决不同控制阶段的问题。
```

## 十三、统一失败案例

为了便于跨章节比较，失败实验优先使用以下固定案例：

| 失败类型 | 固定案例 |
|---|---|
| 上下文缺失 | 只发送“它适合雨天吗？” |
| 工具不存在 | 模型输出 `search_web` |
| 参数名错误 | `get_weather(location="北京")` |
| 参数类型错误 | `calculator(a="六十", b=2)` |
| 数据不存在 | 查询“成都”或未收录景点 |
| 工具业务错误 | 除数为 0 |
| 重复行动 | 连续三次相同 `get_weather` |
| 最大步数 | 始终不输出 `finish` |
| Reflection 失败 | 多次修改仍遗漏模拟数据说明 |
| 权限失败 | 未确认即请求 `submit_reservation` |

不要每章重新发明完全不同的错误场景。

## 十四、统一运行输出

主线代码输出建议统一格式：

```text
=== Step 1 ===
Model Output:
...

Parsed Action:
...

Tool Result:
...

Observation:
...

Termination:
...
```

后期结构化轨迹引入后，终端输出只显示摘要，完整数据保存在 `AgentExecution` 中。

## 十五、范围边界

主线项目第一版不实现：

```text
真实天气 API
真实票务和预订
支付
用户身份信息
长期记忆
RAG
向量数据库
MCP
浏览器控制
多智能体
异步工具
并行工具
动态重规划
流式输出
Agentic RL
```

这些内容只在第十六章“下一步学习”中简要定位，不进入主线实现。

## 十六、主线一致性检查

每次修改一章后，检查：

1. 是否仍然使用 Simple Travel Assistant；
2. 是否继续使用固定三个基础工具；
3. 是否明确数据是模拟数据；
4. 是否只增加本章负责的一个能力；
5. 是否复用了上一章已经建立的术语；
6. 是否没有提前引入后续章节抽象；
7. 是否保留一个成功案例和一个失败案例；
8. 是否说明了本章版本变化；
9. 是否保证最终任务仍能自然延伸；
10. 是否避免使用无关案例替代主线。
