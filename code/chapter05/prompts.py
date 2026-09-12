"""第五章：让模型选择工具。

本模块只负责构造供大语言模型读取的工具说明和 Action Protocol。
这些字符串不会执行任何工具，也不会解析模型输出。
"""

TOOL_DESCRIPTIONS = """
工具名称：get_weather
用途：读取指定城市的本地模拟天气。
参数：
- city：城市名称，字符串。
数据范围：北京、上海、广州。

工具名称：get_attraction_info
用途：读取指定景点的本地模拟开放状态、
成人票价和活动类型。
参数：
- name：景点名称，字符串。
数据范围：故宫、上海博物馆、广东省博物馆。

工具名称：calculator
用途：执行两个数字之间的加、减、乘、除。
参数：
- operation：add、subtract、multiply 或 divide。
- a：第一个数字。
- b：第二个数字。
""".strip()


ACTION_RULES = """
请严格遵守以下规则：

1. 每次只输出一个 JSON 对象。
2. 不要输出 Markdown 代码块。
3. 不要在 JSON 前后添加解释文字。
4. action 只能是：
   get_weather、get_attraction_info、calculator 或 finish。
5. arguments 必须是一个 JSON 对象。
6. 需要程序执行工具时，使用对应工具名称。
7. 不需要工具即可回答时，使用 finish。
8. 当前工具无法完成任务时，不要编造新工具；
   使用 finish 说明能力边界。

Tool Action 格式：
{
  "action": "工具名称",
  "arguments": {
    "参数名称": "参数值"
  }
}

Finish Action 格式：
{
  "action": "finish",
  "arguments": {
    "answer": "最终回答"
  }
}
""".strip()


def build_action_system_prompt() -> str:
    """构造完整的 Action 选择系统提示词。"""
    return (
        "你是城市旅行助手中的行动选择模块。\n"
        "请根据用户任务选择下一步行动，并输出结构化 Action。\n\n"
        "当前可用工具：\n"
        f"{TOOL_DESCRIPTIONS}\n\n"
        f"{ACTION_RULES}"
    )
