# 第十四章：Mock、测试与基础评估

本目录是第十四章的独立教学快照。它使用本地 `simple_agent/` 保存第十三章已经形成的实现，再通过 Mock LLM、自动化测试和 Metrics 验证现有行为。

这里的 `simple_agent/` 只属于本章快照。第十五章完成重构后，后续应用应当依赖仓库根目录中的公共包，而不是导入本目录。

## 结构

```text
code/chapter14/
├── simple_agent/        # 本章用于测试的教学实现
├── tests/               # Parser、工具、Agent、State 与 Metrics 测试
├── mock_llm.py          # 按顺序返回预设输出的确定性 LLM
├── metrics.py           # 从 AgentExecution 汇总基础运行指标
├── main.py              # 不访问网络的固定案例入口
├── pyproject.toml
└── README.md
```

## 安装与测试

先在本目录创建独立虚拟环境，再使用该环境执行：

```bash
python -m pip install -c ../../constraints.txt -e ".[dev]"
python -m pytest
```

全部测试使用 Mock LLM，不访问网络，也不需要 API Key。

## 运行固定案例

```bash
python main.py
```

入口会运行正常完成和格式重试两个固定案例，并输出完成率、平均模型调用次数、平均工具调用次数和终止原因分布。Metrics 只说明当前协议下的运行现象，不等于真实模型质量或事实正确率。

## 本章边界

第十四章的目标是为已有行为建立保护网，不是提前设计最终 Public API。根目录 `simple_agent/`、`tests/` 和 `pyproject.toml` 在第十五章中形成，职责边界以根目录公共实现为准。
