# 第三部分总结

第三部分比较了三种在不同时间点发挥作用的控制与改进方法。

| 方法 | 发生位置 | 核心问题 | 主要输入 | 主要输出 |
|---|---|---|---|---|
| ReAct | 执行过程中 | 根据最新反馈，当前下一步做什么 | 目标与 Observation | Reason + Action |
| Plan-and-Solve | 执行之前 | 整个任务应当怎样拆分 | 目标与工具能力 | Plan + StepResult |
| Reflection | 得到候选答案之后 | 当前答案是否合格、怎样修改 | Evidence 与 Draft | Critique + Revision |

三者不是从简单到高级的升级关系：

```text
Plan-and-Solve 组织全局任务分解
ReAct 组织局部反馈决策
Reflection 检查最终答案质量
```

更自然的理解关系是：

```text
第 8 章 Agent Loop
├── ReAct Strategy
└── Plan-and-Solve Strategy
       \
        └── 两条路线均可连接 Reflection
```

当任务步骤明确时，预先规划可以让执行结构更清楚；当环境信息需要逐步补齐时，ReAct 更适合根据新观察调整行动；当执行结果已完整却仍有表述缺口时，Reflection 则用于补齐答案质量。

这些方法可以组合，但组合越多并不自动意味着质量越高。每增加一次模型调用，都要重新面对格式、网络、错误传播和终止问题。第四部分将把注意力从“怎样控制任务”转向“怎样让系统的成功与失败都可解释、可限制、可验证”。

[返回第三部分导读](index.md) · [进入第四部分](../part-4/index.md)
