# Chapter 10：Plan-and-Solve：先规划再执行

本目录对应《第十章 Plan-and-Solve：先规划再执行》，实现 `Simple Travel Assistant v1.2`。

第九章的 ReAct 在每次 Observation 后判断下一步行动。本章从第八章的基础能力分出另一条路线：先由 Planner 生成完整静态 Plan，再由 Executor 按 PlanStep 顺序执行，最后使用全部 StepResult 进入 Finalize。

## 放置位置

```text
code/
└── chapter10/
    ├── README.md
    ├── executor.py
    ├── main.py
    ├── models.py
    └── planner.py
```

文件职责：

| 文件 | 职责 |
|---|---|
| `models.py` | 定义 `AgentAction`、`PlanStep`、`Plan`、`StepResult` 与相关异常 |
| `planner.py` | 请求 Planner，解析并校验静态 Plan |
| `executor.py` | 生成步骤 Action、执行旅行工具、保存 StepResult 并完成 Finalize |
| `main.py` | 加载配置，连接 Planning、Solving 与 Finalize |
| `README.md` | 说明运行方式、协议、失败实验和静态计划边界 |

为了让本章可以独立运行，三个既有旅行工具及本地模拟数据保留在 `executor.py` 中。本章不从第九章目录导入代码。

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

真实 `.env` 不应提交到 Git 仓库。

## 运行

从项目根目录执行：

```bash
python code/chapter10/main.py
```

推荐任务：

```text
请查询北京的模拟天气，
查询故宫的模拟开放状态和成人票价，
计算两张成人票的总价，并给出出行建议。
```

完整运行阶段为：

```text
Planning → Solving → Finalize
```

若计划包含三个步骤，模型调用次数通常为：

```text
Planner 1 次
Executor 3 次
Finalize 1 次
总计 5 次
```

具体计划步骤可能随模型而变化。

## Plan 协议

Planner 必须输出：

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

Plan Parser 会检查：

```text
顶层只能包含 goal、steps
goal 为非空字符串
steps 为非空数组
步骤数量不超过 max_plan_steps
id 从 1 开始连续递增
每步字段严格符合协议
tool 属于当前工具白名单
```

Parser 不能自动证明 Plan 已经覆盖全部用户要求。计划仍需展示、测试和后续评估。

## 为什么 Plan 不包含 arguments

后续步骤的参数可能依赖尚未获得的真实结果。第三步计算总价时使用的成人票价，必须来自第二步的景点查询结果，而不能由 Planner 提前猜测。

因此：

```text
PlanStep：描述要完成什么、使用哪个工具
AgentAction：执行当前步骤时提供具体参数
```

## Executor Action 协议

每个 PlanStep 执行前，Executor 输出：

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

`parse_step_action()` 会检查：

```text
step_id 等于 current_step.id
action 等于 current_step.tool_name
arguments 符合该工具接口
```

Executor 的系统提示词会同时提供精确的工具参数接口。例如，
查询景点时必须使用 `{"name": "故宫"}`，而不能自行使用
`attraction_name` 等未定义字段。提示词负责降低模型猜测字段名
造成的失败概率，程序校验仍会阻止不合法调用。

即使 Executor 选择的是一个真实存在的工具，只要它与当前 PlanStep 不一致，程序也会拒绝执行。

## StepResult

每个步骤执行成功后保存：

```python
StepResult(
    step_id=3,
    description="使用第2步票价计算两张票总价。",
    tool_name="calculator",
    arguments={
        "operation": "multiply",
        "a": 60,
        "b": 2,
    },
    output="120",
)
```

StepResult 保存实际步骤、工具、参数和输出。后续 Executor 与 Finalize 使用的是这些真实结果，而不是 Planner 对结果的猜测。

## 静态终止方式

本章没有 `finish` Action。计划步骤数量在 Planning 阶段已经确定：

```text
遍历完全部 PlanStep → 进入 Finalize
任一步骤失败 → 停止计划，不进入 Finalize
```

这与 ReAct 的“每轮由模型决定工具或 finish”不同。

## 失败实验

**非法计划编号**

把步骤编号改为 `1、3、4`。`parse_plan()` 应在任何工具执行前拒绝计划。

**未知计划工具**

把某一步的 `tool` 改为 `search_web`。Planner 输出虽然是合法 JSON，但不能通过工具白名单校验。

**Executor 偏离计划**

令当前 PlanStep 指定 `get_attraction_info`，Executor 却输出 `calculator`。即使计算器参数合法，`parse_step_action()` 仍应拒绝执行。

**步骤业务失败**

输入：

```text
请计算10除以0，并根据实际结果回答。
```

计算 Action 可以通过协议校验，但工具执行抛出除数为零错误。程序转换为：

```text
PlanExecutionError:
Step 1 执行失败：除数不能为 0。
```

当前静态计划停止，不会进入 Finalize，也不会自动重规划。

## 当前能力边界

本章已经能够：

```text
生成并校验完整线性 Plan
在工具执行前展示计划
按 PlanStep 顺序生成具体 Action
强制 Executor 服从计划工具
把真实工具参数和输出保存为 StepResult
只在全部步骤完成后进入 Finalize
```

本章仍然不能：

```text
自动检查计划语义是否完整
根据失败动态修改计划
执行条件分支或循环计划
并行执行独立步骤
自动重试失败步骤
检查最终回答质量
```

下一章将处理候选答案生成后的检查与修订。
