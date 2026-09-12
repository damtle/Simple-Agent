# Chapter 01：规则温控智能体

本目录对应《第一章 从语言模型到智能体》。代码不调用大语言模型，而是通过规则温控任务展示最小 Agent Loop：观察环境、选择行动、执行行动、获得新观察，并根据反馈继续运行。

## 文件

```text
code/chapter01/
├── README.md
└── simple_reflex_agent.py
```

`simple_reflex_agent.py` 包含三个部分：

- `RoomEnvironment`：保存温度、提供观察并执行行动；
- `SimpleReflexAgent`：根据当前温度选择 `cool`、`heat` 或 `maintain`；
- `run_agent()`：连接环境和 Agent，推动循环并限制最大步数。

## 运行

在仓库根目录执行：

```bash
python code/chapter01/simple_reflex_agent.py
```

预期输出：

```text
Step 1: temperature=30.0℃, action=cool, after=28.5℃
Step 2: temperature=28.5℃, action=cool, after=27.0℃
Step 3: temperature=27.0℃, action=cool, after=25.5℃
Step 4: temperature=25.5℃, action=maintain, after=25.5℃
目标温度已达到，任务结束。
```

## 代码中的概念对应

| 概念 | 代码中的对应内容 |
|---|---|
| Goal | `target_temperature=25.0` 与 `tolerance=0.5` 共同定义目标范围 |
| Environment | `RoomEnvironment` |
| Environment State | `RoomEnvironment.temperature` |
| Observation | `environment.observe()` 返回的温度字典 |
| Decision | `SimpleReflexAgent.decide()` |
| Action | `cool`、`heat`、`maintain` |
| Agent Loop | `run_agent()` 中的 `for` 循环 |

## 失败实验

将 `run_agent()` 中的：

```python
change_per_action=1.5,
```

修改为：

```python
change_per_action=3.0,
```

温度会在 `24.0℃` 与 `27.0℃` 之间震荡，并在达到 `max_steps` 后停止。这个实验说明：闭环允许程序根据反馈持续调整，但不能保证当前规则和环境参数一定能够完成目标。

本章只使用 Python 标准语法，不需要安装第三方依赖。
