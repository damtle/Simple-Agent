# 开始之前：从零准备 Python 环境

本页面向还没有编程经验的读者。目标很小：找到项目文件，运行一个不需要网络和 API Key 的程序，认识后续章节反复使用的几种 Python 写法。已经能够独立运行 Python 脚本的读者，可以直接阅读[前言](前言.md)。

## 1. 安装 Python，找到终端

从 [Python 官方下载页](https://www.python.org/downloads/)安装 Python 3.10 或更高版本。本书当前在 Python 3.12 环境验证。Windows 安装时勾选把 Python 加入 PATH 的选项，安装完成后重新打开终端。

Windows 可以使用 PowerShell；macOS 和 Linux 可以使用系统的终端应用。终端是输入命令并查看程序输出的窗口。它与编辑 Python 文件的文本编辑器是两个不同的工具。

在终端输入：

```bash
python --version
```

看到 `Python 3.12.x` 这样的输出，说明终端找到了 Python。Windows 如果只能使用 `py`，先用 `py --version` 确认安装；macOS 和 Linux 通常使用 `python3 --version`。后面的命令应使用自己机器上能够运行的名称。

如果看到以 `>>>` 开头的提示符，说明进入了 Python 交互环境。输入 `exit()` 返回终端，再执行安装或运行文件的命令。不要把 `python -m pip ...` 输入到 `>>>` 后面。

## 2. 下载仓库，进入项目目录

在项目仓库页面选择 **Code → Download ZIP**，解压到容易找到的位置。也可以使用 Git 克隆仓库；学习本书不要求先掌握 Git。

打开解压后的目录，应当能看到 `README.md`、`docs`、`code` 和 `pyproject.toml`。这个目录称为“项目根目录”。Windows 可以在文件管理器中打开该目录，再选择“在终端中打开”。

也可以在终端输入 `cd `，把项目文件夹拖到终端窗口中，检查路径后回车。路径含空格时需要使用引号。确认当前位置包含这些文件后再执行后续命令；不要进入 `docs` 后运行 Python 示例。

## 3. 创建独立环境

虚拟环境把本项目使用的 Python 库放到独立目录，避免与其他项目互相影响。从项目根目录执行：

```bash
python -m venv .venv
```

这里的 `.venv` 是将要创建的目录。若系统使用 `python3`，这一步改为 `python3 -m venv .venv`。

Windows PowerShell 可以直接调用虚拟环境内的 Python，不需要调整系统执行策略：

```powershell
.\.venv\Scripts\python.exe -m pip install -c constraints.txt -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

macOS 和 Linux 对应的命令是：

```bash
./.venv/bin/python -m pip install -c constraints.txt -e ".[dev]"
./.venv/bin/python -m pytest
```

`pip install` 安装依赖，首次执行需要联网；`pytest` 检查程序的确定性行为，不调用真实模型、不需要密钥。看到 `passed` 表示测试通过，不要求记住具体测试数量。

后续正文用 `python` 简写命令时，可以一直将它替换成上面虚拟环境内的完整 Python 路径。`-m` 表示把后面的模块作为程序运行；`-e` 表示使用当前目录中的源代码安装项目。

第十四章包含一个同名的教学快照包。学习该章时请在 `code/chapter14` 内另建 `.venv`，不要用同一环境先后安装两个同名包。回到第十五、十六章时，再使用项目根目录的 `.venv`。

## 4. 先运行不需要密钥的程序

从项目根目录执行：

```bash
python code/chapter01/simple_reflex_agent.py
```

若使用虚拟环境的完整路径，将开头的 `python` 替换即可。这个示例只依赖 Python 自带功能，即使尚未安装第三方库，也能运行。

你会看到温度逐步变化，最后出现：

```text
目标温度已达到，任务结束。
```

再运行第四章的本地工具：

```bash
python code/chapter04/main.py
```

程序会打印模拟天气、景点信息和计算结果。这两次运行都不访问模型服务，也不产生模型调用费用。先完成它们，再进入需要模型接口的章节。

## 5. 认识最少的 Python 写法

可以新建一个名为 `practice.py` 的文本文件，保存下面的代码，再在终端运行 `python practice.py`。文件后缀应当是 `.py`，不是 `.py.txt`。

```python
city = "北京"
ticket_price = 60
people = 2

def total_price(price, count):
    return price * count

total = total_price(ticket_price, people)
print(city, total)
```

`city` 和 `total` 是变量，用名称保存数据。引号中的内容是字符串；`60` 和 `2` 是数字。`def` 定义函数，圆括号中的名称是参数；调用函数时传入实际数据，`return` 把结果交回调用位置。`print` 只负责显示内容，不能替代 `return`。

Python 使用缩进表示代码属于哪一层。上面 `return` 前的四个空格说明它属于函数。不要混用 Tab 和空格；复制代码时也要保留缩进。

```python
weather = {"city": "北京", "temperature": 30}
messages = ["查询天气", "给出建议"]

for message in messages:
    print(message)

if weather["temperature"] > 28:
    print("模拟温度较高。")
```

列表 `[...]` 按顺序保存多项内容；字典 `{...}` 用名称关联数据。`for` 逐项处理列表，`if` 根据条件选择是否执行。`while` 则在条件成立时反复执行，因此后面构建 Agent Loop 时必须同时设置结束条件。

第一章还会使用 `class`：它把一组数据和操作组织在一起；创建出来的对象通过 `对象.方法()` 执行操作。方法中的 `self` 指向当前对象。先看每个方法接收什么、返回什么，不必在第一遍阅读时掌握全部面向对象语法。

看到 `def get_weather(city: str) -> str` 时，两个 `str` 都是类型标注：参数预期是字符串，返回结果也预期是字符串。标注帮助阅读，不会自动拒绝错误数据。看到 `@dataclass` 时，可以先把它理解为“自动生成常用初始化方法的数据容器”；`Protocol` 则描述一个对象需要提供哪些方法。相关章节会在实际需要时展开。

程序出错时可能出现 `Traceback`。先看最后一行的错误类型和说明，再找自己的文件名与行号。后面的 `try` / `except` 用于处理预期失败，而不是把所有问题隐藏起来。更多练习见 [Python 官方教程](https://docs.python.org/zh-cn/3/tutorial/)。

## 6. 到第二章时再配置模型

模型接口由你选择的服务提供。按该服务的官方说明取得 API Key、Base URL 和 Model ID，并了解调用计费方式。本书不附带密钥，也不要求把密钥提交给项目维护者。

在项目根目录复制 `.env.example`，将副本命名为 `.env`。使用文本编辑器打开它，把三个示例值替换成自己的配置。注意文件名是 `.env`，不是 `.env.txt`。文件管理器隐藏后缀时，应先打开“显示文件扩展名”。

`.env.example` 用于公开说明配置格式；`.env` 保存私人配置。不要把真实密钥写进 Python 文件、问题反馈或截图中。配置完成后，按照[第二章](part-1/02-first-llm-call.md)运行一次模型调用。

## 7. 常见启动问题

| 看到的提示 | 先检查什么 |
|---|---|
| 找不到 python 命令 | Python 是否安装；重开终端；尝试 `py` 或 `python3` |
| 找不到 main.py 或 pyproject.toml | 当前是否位于项目根目录，路径是否拼写正确 |
| `ModuleNotFoundError` | 安装依赖和运行程序是否使用同一个虚拟环境 |
| `SyntaxError` | 是否把终端命令写进了 Python 文件，或复制时丢失引号、括号 |
| `IndentationError` | 缩进是否一致，是否混入 Tab |
| 缺少环境变量 | `.env` 是否位于项目根目录，文件名是否正确 |
| 模型连接或认证失败 | 按服务文档核对配置与网络；不要公开密钥来排查 |

能够运行离线示例、找到代码文件并读懂最后一行错误提示，就已经具备开始学习的条件。接下来阅读[前言](前言.md)，再进入[第一章](part-1/01-agent-basics.md)。
