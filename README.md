# Simple Agent

一本使用原生 Python、从零构建 LLM Agent 的渐进式开源教程。

> 开源教程 · 第一版（v1.0.0）

Simple Agent 不以生产级框架为目标。它希望用尽可能直接的代码回答一个基础问题：

> 一个能够选择工具、接收环境反馈并持续完成任务的 Agent，究竟是怎样构造出来的？

[在线阅读](https://damtle.github.io/Simple-Agent/) · [从前言开始](docs/前言.md) · [查看阅读路线](docs/meta/reading-guide.md)

## 内容概览

全书共四部分、十六章：

| 部分 | 章节 | 内容 |
|---|---:|---|
| 从程序到可对话模型 | 01—04 | Agent 基础、LLM 调用、上下文、工具 |
| 从模型行动到最小 Agent | 05—08 | Action、Parser、Observation、Agent Loop |
| Agent 控制与改进策略 | 09—11 | ReAct、Plan-and-Solve、Reflection |
| 从可运行到可维护系统 | 12—16 | 重试、终止、状态、轨迹、测试、包化与完整应用 |

核心路径如下：

```text
LLM → Message → Context → Tool → Action → Parser
→ Observation → Agent Loop → Reliability → State → Test → Package
```

这条路径遵循三个原则：

- 原理优先：先看见 Agent 内部发生什么，再讨论框架封装；
- 渐进构造：每章只引入少量新概念，并解决前一版本的具体缺口；
- 程序掌权：模型提出行动，Parser 和工具边界决定行动能否真正执行。

## 仓库结构

```text
Simple-Agent/
├── docs/                     # Docsify 教材正文
│   ├── part-1/               # 第 01—04 章
│   ├── part-2/               # 第 05—08 章
│   ├── part-3/               # 第 09—11 章
│   ├── part-4/               # 第 12—16 章
│   ├── glossary.md
│   └── meta/
├── code/
│   ├── chapter01/            # 各章独立教学快照
│   └── ... chapter14/
├── simple_agent/             # 第十五章形成的公共包
├── tests/                    # 公共包的确定性测试
├── examples/
│   └── travel_assistant/     # 第十六章完整应用
└── pyproject.toml
```

`code/chapter01`—`code/chapter14` 保留概念逐步出现时的教学实现。根目录 `simple_agent/` 是当前公共实现，后续应用只依赖这一份代码。

## 运行代码

环境要求：Python 3.10+。

编程零基础的读者请先阅读[环境与 Python 入门](docs/getting-started.md)，其中说明了下载代码、创建虚拟环境和运行离线示例的方法。

```bash
python -m pip install -c constraints.txt -e ".[dev]"
python -m pytest
```

两套教学实现应使用独立虚拟环境。第十四章的测试需在 `code/chapter14/` 内单独安装和运行；不要在同一个环境中先后可编辑安装两个同名包。

`constraints.txt` 记录本次验证过的依赖版本，便于复现环境。升级依赖时请重新运行两套测试。

需要调用真实模型时，将 `.env.example` 复制为 `.env`，并填写 OpenAI 兼容服务配置：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

运行最终旅行助手：

```bash
python -m examples.travel_assistant.main --show-trace
```

旅行助手使用本地模拟天气、景点和票价数据，不代表真实世界状态。

## 项目边界

当前实现提供同步模型调用、工具注册、Action 解析、Observation 反馈、有限重试、终止原因、状态、轨迹和基础测试。它不提供真实票务、支付、长期记忆、完整 RAG、多智能体、生产级权限系统或部署能力。

项目的学习思路受到 Datawhale [Hello-Agents](https://github.com/datawhalechina/hello-agents) 启发，但 Simple Agent 不是其官方精简版，也不复用其框架实现；本项目只聚焦最小单智能体的构造过程。

## 作者与贡献

本书欢迎社区参与维护。欢迎通过 Issue 或 Pull Request 报告错误、改进示例或完善说明，具体方式见[贡献指南](CONTRIBUTING.md)。所有实际参与者都会保留在 Git 历史和 GitHub Contributors 记录中。

## 版权与许可

Copyright © 2026 Simple Agent Contributors.

- 软件源代码与代码示例采用 [MIT License](LICENSE)；
- 书稿正文、图表及非代码文档采用 [CC BY-NC-SA 4.0](docs/LICENSE.md)。

转载或改编书稿时，请保留项目名称及原始仓库链接。代码片段与书稿正文适用不同许可，使用时请分别遵守对应条款。
