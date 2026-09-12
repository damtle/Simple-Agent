# Simple Travel Assistant

本目录对应《第十六章 构建完整旅行助手》，使用第十五章形成的 `simple_agent` 公共包构建最终旅行助手。

## 放置位置

将本目录放在仓库根目录：

```text
simple-agent/
├── pyproject.toml
├── simple_agent/
├── tests/
└── examples/
    └── travel_assistant/
        ├── main.py
        ├── tools.py
        ├── prompts.py
        ├── data.py
        └── README.md
```

本目录只保存旅行场景的数据、工具、Prompt 和应用入口。Parser、Tool Registry、Agent Loop、重试、状态与 Execution Trace 继续由根目录 `simple_agent/` 提供。

## 环境要求

```text
Python 3.10+
simple_agent 已完成第十五章安装
OpenAI 兼容的 Chat Completions 模型服务
```

在仓库根目录安装项目及开发依赖：

```bash
python -m pip install -e ".[dev]"
```

## 模型配置

在项目根目录创建 `.env`：

```dotenv
LLM_API_KEY=YOUR_API_KEY
LLM_BASE_URL=YOUR_BASE_URL
LLM_MODEL_ID=YOUR_MODEL_ID
```

真实 `.env` 不应提交到 Git。仓库中只保留不含密钥的 `.env.example`。

## 运行

从项目根目录运行：

```bash
python -m examples.travel_assistant.main
```

直接回车会使用默认任务：

```text
请查询北京的模拟天气和故宫的模拟开放、票价信息，
计算两张成人票的总价，并给出一段不超过120字的出行建议。
回答必须明确说明数据来自本地模拟信息。
```

也可以直接传入任务：

```bash
python -m examples.travel_assistant.main \
  "查询上海模拟天气和上海博物馆信息，并给出雨天参观建议。"
```

查看完整 Execution Trace：

```bash
python -m examples.travel_assistant.main \
  --show-trace
```

已经完成 Editable Install 后，也可以直接执行：

```bash
python examples/travel_assistant/main.py
```

代码不会通过修改 `sys.path` 绕过正常安装。

## 运行流程

```text
用户任务
→ Agent 连续选择并执行旅行工具
→ AgentExecution 保存 Result、State 与 Trace
→ 从成功 Tool Result 整理 Evidence
→ Reflection 检查并有限修订 Draft
→ 输出最终回答和运行摘要
```

Agent 失败时不会进入 Reflection。Reflection 自身失败时，程序保留已经成功取得的 Agent Draft，不把答案改进失败误写成 Agent 执行失败。

## 本地模拟数据

当前天气数据只包含：

```text
北京
上海
广州
```

当前景点数据只包含：

```text
故宫
上海博物馆
广东省博物馆
```

天气、开放状态、票价和活动信息全部来自本地模拟字典，不代表真实世界状态，不能作为实际出行依据。

## 当前能力边界

本示例不提供：

```text
真实天气查询
实时票价和开放状态
地图、交通或酒店搜索
真实购票、预订和支付
账号与身份信息处理
长期记忆、RAG 或多智能体协作
生产级权限、监控和持久化
```

工具返回数据不存在时，Agent 应根据 Observation 诚实说明当前能力边界，而不是改用模型常识编造结果。
