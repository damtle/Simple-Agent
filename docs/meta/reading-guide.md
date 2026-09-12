# 阅读路线与仓库结构

## 建议怎样阅读

如果还没有运行过 Python 程序，请先完成[环境与 Python 入门](../getting-started.md)。能够运行离线示例后，再按下面的路线学习。

第一次接触 Agent 时，建议从前言开始，按 01—16 章顺序阅读。每一章都建立在前一章已经出现的问题上，跳过中间章节可能会看见一个接口，却不知道它为什么需要存在。

每章可以按照下面的顺序学习：

1. 阅读章节导入，先确认当前版本还缺少什么；
2. 在运行代码前预测模型能看到哪些消息、程序会执行什么；
3. 运行 `code/chapter01/` 至 `code/chapter14/` 中与当前章节对应的教学快照；
4. 主动制造一次正文建议的失败；
5. 阅读本章小结，并回答“新增结构解决了什么问题”。

如果已经使用过 Agent 框架，可以先阅读第二部分和第四部分。第二部分揭示工具型 Agent 的最小闭环，第四部分说明成熟框架中的重试、状态、轨迹和测试为什么存在。

## 文档组织

Docsify 使用 `docs/README.md` 作为首页，因此首页与四个部分目录并存：

```text
docs/
├── README.md
├── 前言.md
├── part-1/
│   ├── index.md
│   ├── 01-agent-basics.md
│   ├── 02-first-llm-call.md
│   ├── 03-context-state.md
│   ├── 04-tools.md
│   └── summary.md
├── part-2/                  # 第 05—08 章
├── part-3/                  # 第 09—11 章
├── part-4/                  # 第 12—16 章
├── glossary.md
└── meta/
```

每个部分都包含：

- `index.md`：说明这一部分要解决的问题和章节关系；
- `NN-topic.md`：使用两位数编号的章节正文；
- `summary.md`：回收本部分概念，并指出下一部分的缺口。

## 代码组织

第 01—14 章保留相互独立的教学快照：

```text
code/chapter01/
code/chapter02/
...
code/chapter14/
```

这些目录允许为了教学而保留重复代码。学习者可以直接比较相邻章节，观察新结构怎样进入系统。

第十五章开始不再复制公共实现：

```text
simple_agent/               当前唯一的公共包实现
tests/                      公共包的稳定测试
examples/travel_assistant/  使用公共包构建的完整应用
```

因此，“教学快照”和“当前实现”承担不同职责：

| 位置 | 作用 | 是否允许重复 |
|---|---|---|
| `code/chapter01/`—`code/chapter14/` | 重现对应章节的认知阶段 | 允许 |
| `simple_agent/` | 后续应用依赖的公共实现 | 不允许多份 |
| `examples/` | 展示公共包怎样进入具体场景 | 只保留业务代码 |

## 三条阅读线索

全书可以沿三条线索理解：

| 线索 | 演化路径 |
|---|---|
| 执行闭环 | Tool → Action → Parser → Observation → Agent Loop |
| 控制策略 | ReAct / Plan-and-Solve → Reflection（可选组合） |
| 可靠性 | Retry → Termination → State → Trace → Test → Package |

遇到陌生概念时，先判断它属于哪条线索，再回到相应章节。概念的简短定义可以在[术语表](../glossary.md)中查找。

## 作者与贡献者

本书欢迎社区参与维护。欢迎读者通过 GitHub Issue 或 Pull Request 报告问题和参与改进；所有实际参与者都会保留在 Git 历史和 GitHub Contributors 记录中。

书稿版权与使用方式见[版权与许可](../LICENSE.md)。
