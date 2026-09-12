# Chapter 11：Reflection：检查与修正

本目录对应《第十一章 Reflection：检查与修正》，实现 `Simple Travel Assistant v1.3`。

第九章的 ReAct 解决获得 Observation 后“下一步做什么”，第十章的 Plan-and-Solve 解决执行前“整个任务怎样分解”。本章转向结果层：检查候选答案是否完整、是否正确使用 Evidence、是否内部一致，以及是否满足用户约束。

## 放置位置

```text
code/
└── chapter11/
    ├── README.md
    ├── critic.py
    ├── generator.py
    ├── main.py
    └── refiner.py
```

文件职责：

| 文件 | 职责 |
|---|---|
| `generator.py` | 根据用户任务和 Evidence 生成 Draft |
| `critic.py` | 定义 Critique 数据结构，生成、解析并校验 Critique |
| `refiner.py` | 根据 Evidence、Draft 和 Critique 生成 Revision |
| `main.py` | 准备主线 Evidence，控制有限 Reflection Loop |
| `README.md` | 说明运行方法、协议、失败实验和能力边界 |

本章不导入前面章节目录，也不重新执行旅行工具。固定 Evidence 模拟 ReAct 的成功 Observation 或 Plan-and-Solve 的 StepResult 已经完成整理。

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
python code/chapter11/main.py
```

默认任务要求两人出行建议不超过 120 字，并包含北京天气、故宫开放状态、两张成人票总价和本地模拟数据说明。

固定 Evidence 为：

```text
北京当前模拟天气为晴，30℃，湿度45%，微风。
故宫在模拟数据中开放，成人票价60元。
calculator 对60×2的执行结果为120。
```

## Reflection 流程

```text
用户任务 + Evidence
→ Generator
→ Draft
→ Critic
→ Critique
→ passed=true：返回当前答案
→ passed=false：Refiner 生成 Revision
→ 再次交给 Critic
```

Generator 是本章为了独立演示而保留的角色。在真实整合中，第九章的 `finish.arguments.answer` 或第十章的 Finalize 输出可以直接作为 Draft，跳过 Generator。

## Critique 协议

Critic 必须只输出：

```json
{
  "passed": false,
  "summary": "答案遗漏总价和模拟数据说明。",
  "issues": [
    {
      "dimension": "completeness",
      "problem": "没有给出两张成人票总价。",
      "suggestion": "补充 Evidence 中 calculator 返回的120元。"
    }
  ]
}
```

允许的 `dimension`：

```text
completeness
evidence_grounding
consistency
constraint_compliance
```

通过时必须满足：

```json
{
  "passed": true,
  "summary": "当前答案满足用户任务。",
  "issues": []
}
```

`parse_critique()` 会严格检查：

```text
输出是否为合法 JSON
顶层是否且仅有 passed、summary、issues
passed 是否为布尔值
summary 是否为非空字符串
issues 是否为数组
每个 issue 是否且仅有规定字段
dimension 是否属于允许集合
problem 和 suggestion 是否为非空字符串
passed 与 issues 是否逻辑一致
```

本章按 Prompt 要求拒绝 Markdown 代码块和 JSON 前后的额外说明，不自动猜测或提取其中内容。

## Evidence 的优先级

修订时的边界为：

```text
用户任务：决定需要完成什么
Evidence：决定允许使用哪些事实
Draft：提供当前文本基础
Critique：指出应当怎样修改
```

Critique 不是新的 Evidence。若 Critic 建议把总价改为 180 元，而 Evidence 明确记录 120，Refiner 仍应以 Evidence 为准。

## 最大修订次数

默认：

```python
DEFAULT_MAX_REVISIONS = 2
```

它限制最多生成两个 Revision，而不是最多进行两次 Critique。

最坏轨迹为：

```text
Draft 0 → Critique 1
Revision 1 → Critique 2
Revision 2 → Critique 3
```

因此最多发生：

```text
Generator：1 次
Critic：3 次
Refiner：2 次
合计：6 次模型调用
```

每一个候选答案都会先经过 Critic 检查。若第三次 Critique 仍未通过，程序抛出 `RuntimeError`。下一章再把它改为统一的结构化终止结果。

## 失败实验

**遗漏信息。** 让 Generator 只输出天气和开放状态，观察 Critic 是否指出缺少两张票总价和模拟数据说明。

**错误使用 Evidence。** 让 Draft 把两张票总价写成 60 元，确认 Critic 将其归为 `evidence_grounding`。

**协议矛盾。** 向 `parse_critique()` 传入 `passed=true` 但 `issues` 非空的 JSON，程序必须拒绝。

**零次修订。** 将 `DEFAULT_MAX_REVISIONS` 改为 `0`。程序仍会生成 Draft 并进行一次 Critique，但不会调用 Refiner。

**错误 Evidence。** 将计算结果从 120 改为 150。Reflection 可能让答案与错误 Evidence 更一致，但不能证明 Evidence 正确，也不会重新执行计算器。

## 当前能力边界

本章已经能够：

```text
根据任务和 Evidence 生成 Draft
从四个维度生成结构化 Critique
严格校验 Critique 协议
根据 Critique 生成 Revision
在通过或达到修订上限时停止
```

本章仍然不能：

```text
重新执行工具
修复错误数据源
补充缺失 Evidence
修改 ReAct 行动路径
修改 Plan-and-Solve 计划
自动处理模型请求失败
返回统一结构化终止结果
保存跨任务反思记忆
使用确定性规则检查字数
进行自动化质量评估
```

下一章将集中处理失败、重试与终止。
