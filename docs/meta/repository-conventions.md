# 文档与代码约定

这份约定用于持续保持教材正文、教学代码和 Docsify 导航的一致性。

## 命名规则

- 文档部分目录使用 `part-1`—`part-4`；
- 章节文件使用 `NN-kebab-case.md`，例如 `08-agent-loop.md`；
- 教学代码目录使用 `chapterNN`，例如 `code/chapter08/`；
- Python 包使用下划线命名：`simple_agent`；
- 可安装项目名使用连字符命名：`simple-agent`；
- 应用示例放在 `examples/<application_name>/`。

## 章节结构

正文原则上包含以下内容：

1. 前一版本留下的问题；
2. 本章概念与职责边界；
3. 关键数据结构或控制流程；
4. 与 `code/chapterNN/` 对应的实现；
5. 成功运行与失败实验；
6. 当前系统快照；
7. 本章小结和习题。

章节正文只引用仓库中真实存在的路径。文件移动后，需要同步检查正文、部分导读、Docsify 侧边栏、根目录 README 和代码目录 README。

更完整的章节骨架、标题粒度、代码展示和习题规则见[章节写作规范](writing-guide.md)。主线数据、工具协议和跨章任务演化见[主线项目规范](travel-assistant-spec.md)。

## 内容唯一归属（避免重复定义）

以下主题在全书只保留一处完整定义，其他章节只引用结论：

| 主题 | 完整归属 |
|---|---|
| Agent、LLM 应用与 Workflow 的区别 | 第 01 章 |
| 模型不会自动记住历史 | 第 03 章 |
| 工具本质与 Tool Registry | 第 04 章 |
| Action Protocol 与结构化输出 | 第 05 章 |
| Parser、Validation 与 `AgentAction` | 第 06 章 |
| Tool Result 与 Observation 的区别 | 第 07 章 |
| 模型选择权与程序执行权 | 第 08 章 |
| 三种控制与改进范式总比较 | 第三部分总结 |
| 失败分类与恢复策略 | 第 12 章 |
| State、Trace、Log 与 User Output | 第 13 章 |
| Mock LLM 与确定性测试 | 第 14 章 |
| 为什么最后才建立公共包 | 第 15 章 |

## 结构冻结规则（先归类再新增）

第一版的章节职责和主线目录已经冻结。新增内容前应先判断：

1. 它属于哪一个已定义的核心问题；
2. 是否已经在其他章节有正式归属；
3. 是主线必需内容，还是扩展示例或维护资料；
4. 是否会造成相邻章节重复定义；
5. 是否提前引入了后续章节才负责的抽象。

无法明确归属的内容不直接插入主线章节。业务扩展示例进入 `examples/`，维护规则进入 `docs/meta/`；真正面向读者但不属于主线的内容，后续可单独建立 `docs/appendix/`。

## 代码边界

- `code/chapter01`—`code/chapter14` 是教学快照，不被后续应用导入；
- `simple_agent/` 不包含旅行数据、具体业务工具或 `.env` 读取；
- `tests/` 使用 Mock LLM，不访问网络，也不要求 API Key；
- `examples/travel_assistant/` 负责配置、Prompt、业务数据和应用层 Reflection；
- 高风险工具必须由程序要求确认，不能只依赖 Prompt；
- `.env` 只用于本地配置，仓库仅提交 `.env.example`。

## 更新检查清单

新增或调整章节时，至少检查：

- `docs/_sidebar.md` 是否包含正确链接；
- 所属部分的 `index.md` 和 `summary.md` 是否同步；
- `docs/README.md` 和根目录 `README.md` 的章节范围是否正确；
- `code/chapterNN/README.md` 是否说明运行方式；
- 正文中的文件树是否与真实目录一致；
- 本地 Markdown 链接是否存在；
- Python 文件是否通过语法检查，测试是否通过。
