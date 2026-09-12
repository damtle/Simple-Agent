# Simple Agent：从零构建 LLM Agent

> 从最小实现开始，逐步理解智能体的构造、运行、可靠性与工程化。

开源教程 · 第一版（v1.0.0）

第一次编程？先完成[环境与 Python 入门](getting-started.md)，运行不需要密钥的示例，再进入十六章主线。

`Simple Agent` 是一本配有完整 Python 代码的渐进式开源教程。全书不从成熟 Agent 框架讲起，而是从规则程序和一次大语言模型调用开始，逐步加入上下文、工具、Action、Parser、Observation 和 Agent Loop。

每一个新结构都用于解决前一阶段已经出现的问题。读者不仅会得到一个能够运行的旅行助手，还能看见模型输出怎样变成程序行动、工具结果怎样影响下一轮决策，以及失败、状态、轨迹和测试为什么不可缺少。

## 全书路线

| 部分 | 章节 | 核心问题 |
|---|---:|---|
| [第一部分：从程序到可对话模型](part-1/index.md) | 01—04 | LLM、上下文和工具怎样进入普通 Python 程序 |
| [第二部分：从模型行动到最小 Agent](part-2/index.md) | 05—08 | 怎样建立 Action、Parser、Observation 和 Agent Loop |
| [第三部分：Agent 控制与改进策略](part-3/index.md) | 09—11 | ReAct、Plan-and-Solve 与 Reflection 分别解决什么问题 |
| [第四部分：从可运行到可维护系统](part-4/index.md) | 12—16 | 怎样处理失败、保存轨迹、建立测试并提取公共包 |

完整构造路径是：

```text
规则 Agent
→ LLM 调用
→ 对话上下文
→ Tool
→ Action 与 Parser
→ Observation
→ Agent Loop
→ ReAct / Plan-and-Solve / Reflection
→ Retry / State / Trace / Test
→ simple_agent 包
→ 完整旅行助手
```

## 你将获得什么

完成全书后，你将能够：

- 区分普通程序、工作流、LLM 应用和 Agent；
- 解释模型选择工具与程序执行工具之间的边界；
- 独立实现结构化 Action、Parser 和 Agent Loop；
- 为网络、格式、工具和重复行动建立有限恢复策略；
- 使用 State、Execution Trace 和日志观察运行过程；
- 使用 Mock LLM 编写确定性的自动化测试；
- 理解公共包应当在职责稳定后提取，而不是提前设计；
- 使用最终的 `simple_agent` 包构建完整工具型应用。

## 文档与代码

第 01—14 章都有一份对应的教学快照：

```text
docs/part-1/01-agent-basics.md  ↔  code/chapter01/
...
docs/part-4/14-mock-test-metrics.md  ↔  code/chapter14/
```

第十五章之后不再复制一套章节实现：

```text
simple_agent/               第十五章形成的当前公共实现
tests/                      公共实现的稳定测试
examples/travel_assistant/  第十六章完整应用
```

详细说明见[阅读路线与仓库结构](meta/reading-guide.md)。第一次阅读建议先看[前言](前言.md)，然后按章节顺序运行代码。查阅概念的统一定义和易混淆边界时可使用[术语表](glossary.md)。

## 版权与许可

Copyright © 2026 Simple Agent Contributors。书稿正文、图表及非代码文档采用 [CC BY-NC-SA 4.0](LICENSE.md)，软件源代码与代码示例采用 MIT License。
