"""第四章：手动执行旅行工具。

开发者在 calls 中明确指定工具名称和参数，程序通过统一的
execute_tool() 入口执行。这里没有调用大语言模型，也没有让模型
选择工具。
"""

from tools import execute_tool, list_tools


def run_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> None:
    """执行一次开发者指定的工具调用并显示结果。"""
    print(f"\n工具名称：{tool_name}")
    print(f"工具参数：{arguments}")

    try:
        result = execute_tool(
            tool_name=tool_name,
            arguments=arguments,
        )
    except (TypeError, ValueError) as error:
        print(f"执行失败：{error}")
        return

    print(f"Tool Result：{result}")


def main() -> None:
    """依次执行天气、景点和费用计算三个示例。"""
    print("当前可用工具：")
    print(list_tools())

    calls = [
        (
            "get_weather",
            {
                "city": "北京",
            },
        ),
        (
            "get_attraction_info",
            {
                "name": "故宫",
            },
        ),
        (
            "calculator",
            {
                "operation": "multiply",
                "a": 60,
                "b": 2,
            },
        ),
    ]

    for tool_name, arguments in calls:
        run_tool(
            tool_name=tool_name,
            arguments=arguments,
        )


if __name__ == "__main__":
    main()
