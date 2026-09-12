# 第三部分：Agent 控制与改进策略

第二部分已经构建了一个最小 Agent Loop。模型可以读取用户目标和已有 Observation，选择下一项工具，也可以在任务完成后通过 `finish` 返回回答。

同一个 Agent Loop 并不只有一种组织方式。面对不同任务，我们可能更关心当前反馈到来后应该怎样调整下一步，也可能希望在执行之前先检查任务是否被完整分解；即使执行过程正确，最终答案仍然可能遗漏证据或违反用户约束。

本部分讨论三种常见方法：ReAct、Plan-and-Solve 和 Reflection。它们不是依次替代前一种方法的线性升级关系，也不是“第一种简单、第三种高级”的三层框架。三者分别处理不同阶段的问题。

ReAct 关注局部决策。模型在每次行动前生成简洁 Reason，并在新的 Observation 到来后重新判断下一步。它回答的是：

> 根据当前已经获得的信息，现在应该做什么？

Plan-and-Solve 关注整体分解。Planner 在执行工具之前生成一份有序 Plan，Executor 再根据计划和前序 StepResult 逐项执行。它回答的是：

> 在开始执行之前，整个任务应当怎样拆分？

Reflection 关注结果改进。Generator 产生 Draft，Critic 根据用户任务和 Evidence 生成 Critique，Refiner 再完成 Revision。它回答的是：

> 当前候选答案是否合格，若不合格应当怎样修改？

三种方法在时间位置上的区别是：

```text
Plan-and-Solve：执行之前形成整体计划
ReAct：执行过程中根据 Observation 决定下一步
Reflection：得到候选答案之后检查并修订
```

ReAct 与 Plan-and-Solve 主要组织执行过程，Reflection 处理答案层。一个应用可以只使用一种，也可以按任务需要组合使用，但组合并不会改变它们各自的职责边界。

## 章节路线

| 章节 | 主要问题 | 本章建立的能力 |
|---|---|---|
| [第九章：ReAct：边行动边观察](09-react.md) | 每次获得 Observation 后怎样选择下一步 | 生成简洁 Reason 与下一项 Action |
| [第十章：Plan-and-Solve：先规划再执行](10-plan-and-solve.md) | 复杂任务在执行前怎样完整分解 | 生成 Plan，并按 PlanStep 得到 StepResult |
| [第十一章：Reflection：检查与修正](11-reflection.md) | 候选答案怎样依据 Evidence 被检查和修改 | 生成 Critique 与 Revised Answer |

阅读这一部分时，不应只比较三种方法谁更复杂，而应判断问题发生在哪个阶段。遗漏下一项工具属于执行决策问题，任务分解不完整属于规划问题，最终回答漏写总价则属于答案检查问题。只有先确定问题位置，才能选择合适的方法。

[进入第九章](09-react.md) · [查看第三部分总结](summary.md)
