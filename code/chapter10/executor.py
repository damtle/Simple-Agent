"""第十章：顺序执行静态 Plan，并完成 Finalize。"""

import json
import math
from collections.abc import Callable

from models import (
    AgentAction,
    Plan,
    PlanExecutionError,
    PlanStep,
    StepResult,
)
from planner import plan_step_to_dict, plan_to_dict


EXECUTOR_SYSTEM_PROMPT = """
你是城市旅行助手的 Executor。

请严格执行 current_step，不要重新设计或修改 Plan。
根据用户目标和 completed_results，
为当前步骤生成一个具体工具 Action。

输出必须是一个 JSON 对象，只包含：
step_id、action、arguments。

规则：
1. step_id 必须等于 current_step.id。
2. action 必须等于 current_step.tool。
3. arguments 必须符合对应工具接口。
4. 只能使用用户目标或 completed_results
   中已经获得的数据。
5. 不要猜测尚未执行步骤的结果。
6. 每次只输出一个 Action。
7. 不要输出额外说明或 Markdown 代码块。

工具参数接口（arguments 必须严格使用以下字段名，
不得自行改名、增加或省略字段）：

1. get_weather
   arguments：{"city": "城市名称"}
   示例：{"step_id": 1, "action": "get_weather", "arguments": {"city": "北京"}}

2. get_attraction_info
   arguments：{"name": "景点名称"}
   示例：{"step_id": 2, "action": "get_attraction_info", "arguments": {"name": "故宫"}}
   注意：参数名只能是 name，不能使用 attraction_name、attraction 或其他名称。

3. calculator
   arguments：{"operation": "add | subtract | multiply | divide", "a": 数字, "b": 数字}
   示例：{"step_id": 3, "action": "calculator", "arguments": {"operation": "multiply", "a": 60, "b": 2}}

仅使用 current_step.tool 对应的接口。
""".strip()


FINALIZE_SYSTEM_PROMPT = """
你是城市旅行助手的最终回答模块。

请根据用户目标、已执行 Plan 和全部 StepResult
生成简洁、完整的中文回答。

规则：
1. 天气、开放状态、票价和计算结果
   必须来自 StepResult。
2. 不要补充未执行工具提供的事实。
3. 覆盖用户目标中的全部要求。
4. 明确说明信息来自本地模拟数据。
5. 只输出最终自然语言回答。
""".strip()


WEATHER_DATA = {
    "北京": {
        "condition": "晴",
        "temperature": 30,
        "humidity": 45,
        "wind": "微风",
    },
    "上海": {
        "condition": "多云",
        "temperature": 27,
        "humidity": 70,
        "wind": "东南风",
    },
    "广州": {
        "condition": "阵雨",
        "temperature": 32,
        "humidity": 82,
        "wind": "南风",
    },
}

ATTRACTION_DATA = {
    "故宫": {
        "city": "北京",
        "open": True,
        "adult_ticket": 60,
        "activity_type": "室内外步行",
        "description": "以宫殿建筑、历史展陈和步行参观为主。",
    },
    "上海博物馆": {
        "city": "上海",
        "open": True,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "以历史文物和艺术展陈为主。",
    },
    "广东省博物馆": {
        "city": "广州",
        "open": False,
        "adult_ticket": 0,
        "activity_type": "室内参观",
        "description": "当前模拟数据中处于闭馆状态。",
    },
}



def _load_bounded_json(text: str) -> object:
    """为教学快照限制不可信 JSON 的资源消耗。"""
    if len(text) > 65_536:
        raise json.JSONDecodeError("模型输出长度超过限制", text, 0)
    depth = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "{[":
            depth += 1
            if depth > 64:
                raise json.JSONDecodeError("JSON 嵌套层数超过限制", text, 0)
        elif character in "}]":
            depth -= 1

    def parse_integer(value: str) -> int:
        if len(value.lstrip("-")) > 128:
            raise ValueError("整数位数超过限制")
        return int(value)

    try:
        return json.loads(text, parse_int=parse_integer)
    except (ValueError, RecursionError) as error:
        raise json.JSONDecodeError("JSON 格式或数值超出允许范围", text, 0) from error


def get_weather(city: str) -> str:
    """读取本地模拟天气。"""
    data = WEATHER_DATA.get(city)

    if data is None:
        raise ValueError(
            f"没有找到城市“{city}”的模拟天气数据。"
        )

    return (
        f"{city}当前模拟天气为{data['condition']}，"
        f"温度{data['temperature']}℃，"
        f"湿度{data['humidity']}%，"
        f"{data['wind']}。"
    )


def get_attraction_info(name: str) -> str:
    """读取本地模拟景点信息。"""
    data = ATTRACTION_DATA.get(name)

    if data is None:
        raise ValueError(
            f"没有找到景点“{name}”的模拟信息。"
        )

    open_status = "开放" if data["open"] else "闭馆"

    return (
        f"{name}位于{data['city']}，"
        f"在当前模拟数据中处于{open_status}状态，"
        f"成人票价{data['adult_ticket']}元，"
        f"活动类型为{data['activity_type']}。"
        f"{data['description']}"
    )


def calculator(
    operation: str,
    a: float,
    b: float,
) -> str:
    """执行受限的四则运算。"""
    if operation == "add":
        result = a + b
    elif operation == "subtract":
        result = a - b
    elif operation == "multiply":
        result = a * b
    elif operation == "divide":
        if b == 0:
            raise ValueError("除数不能为 0。")
        result = a / b
    else:
        raise ValueError(
            f"不支持的计算操作：{operation}"
        )

    if float(result).is_integer():
        return str(int(result))

    return str(result)


ToolFunction = Callable[..., str]

TOOL_REGISTRY: dict[str, ToolFunction] = {
    "get_weather": get_weather,
    "get_attraction_info": get_attraction_info,
    "calculator": calculator,
}

ALLOWED_TOOL_NAMES = frozenset(TOOL_REGISTRY)

TOOL_DESCRIPTIONS = {
    "get_weather": "查询一个城市的本地模拟天气。",
    "get_attraction_info": (
        "查询一个景点的本地模拟开放状态、"
        "成人票价和活动类型。"
    ),
    "calculator": "执行加、减、乘、除。",
}


def execute_tool(
    tool_name: str,
    arguments: dict[str, object],
) -> str:
    """通过注册名称执行工具。"""
    tool_function = TOOL_REGISTRY.get(tool_name)

    if tool_function is None:
        allowed = ", ".join(sorted(TOOL_REGISTRY))
        raise ValueError(
            f"未知工具：{tool_name}。可用工具：{allowed}。"
        )

    try:
        result = tool_function(**arguments)
    except TypeError as error:
        raise ValueError(
            f"工具“{tool_name}”的参数不正确：{error}"
        ) from error

    if not isinstance(result, str):
        raise TypeError(
            f"工具“{tool_name}”必须返回字符串。"
        )

    return result


def normalize_json_text(model_output: str) -> str:
    """整理 Executor 的完整 JSON 文本外壳。"""
    if not isinstance(model_output, str):
        raise PlanExecutionError("Executor 输出必须是字符串。")

    text = model_output.strip()

    if not text:
        raise PlanExecutionError("Executor 输出为空。")

    lines = text.splitlines()
    first_line = lines[0].strip()
    last_line = lines[-1].strip()

    if first_line.startswith("```"):
        if first_line not in {"```", "```json", "```JSON"}:
            raise PlanExecutionError(
                "Executor 只允许完整 json 代码围栏。"
            )

        if last_line != "```":
            raise PlanExecutionError(
                "Executor 的 Markdown 代码围栏没有闭合。"
            )

        text = "\n".join(lines[1:-1]).strip()

        if not text:
            raise PlanExecutionError(
                "Executor 代码围栏中没有内容。"
            )

    elif any(
        line.strip().startswith("```")
        for line in lines
    ):
        raise PlanExecutionError(
            "Executor 代码围栏必须完整包裹全部输出。"
        )

    return text


def parse_json_object(model_output: str) -> dict[str, object]:
    """将 Executor 输出解析为 JSON 对象。"""
    text = normalize_json_text(model_output)

    try:
        data = _load_bounded_json(text)
    except json.JSONDecodeError as error:
        raise PlanExecutionError(
            "Executor 输出不是合法 JSON："
            f"{error.msg}，第 {error.lineno} 行，"
            f"第 {error.colno} 列。"
        ) from error

    if not isinstance(data, dict):
        raise PlanExecutionError(
            "Executor Action 顶层必须是 JSON 对象。"
        )

    return data


def validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    """要求 Executor 对象字段完全符合协议。"""
    actual = set(data)
    missing = expected - actual
    extra = actual - expected
    details: list[str] = []

    if missing:
        details.append("缺少 " + ", ".join(sorted(missing)))

    if extra:
        details.append("多出 " + ", ".join(sorted(extra)))

    if details:
        raise PlanExecutionError(
            f"{context}字段不正确：" + "；".join(details) + "。"
        )


def require_non_empty_string(
    value: object,
    field_name: str,
) -> str:
    """校验非空字符串参数。"""
    if not isinstance(value, str):
        raise PlanExecutionError(f"{field_name} 必须是字符串。")

    normalized = value.strip()

    if not normalized:
        raise PlanExecutionError(f"{field_name} 不能为空。")

    return normalized


def is_finite_number(value: object) -> bool:
    """判断值是否为有限数字，并排除 bool。"""
    if isinstance(value, bool):
        return False

    if isinstance(value, int):
        return True

    if isinstance(value, float):
        return math.isfinite(value)

    return False


def validate_agent_action(
    action_name: object,
    arguments: object,
) -> AgentAction:
    """校验工具名称及其参数。"""
    if not isinstance(action_name, str):
        raise PlanExecutionError("action 必须是字符串。")

    if action_name != action_name.strip() or not action_name:
        raise PlanExecutionError(
            "action 必须是前后无空白的非空字符串。"
        )

    if not isinstance(arguments, dict):
        raise PlanExecutionError(
            "arguments 必须是 JSON 对象。"
        )

    if action_name == "get_weather":
        validate_exact_fields(
            arguments,
            {"city"},
            "get_weather.arguments",
        )
        require_non_empty_string(
            arguments["city"],
            "get_weather.city",
        )

    elif action_name == "get_attraction_info":
        validate_exact_fields(
            arguments,
            {"name"},
            "get_attraction_info.arguments",
        )
        require_non_empty_string(
            arguments["name"],
            "get_attraction_info.name",
        )

    elif action_name == "calculator":
        validate_exact_fields(
            arguments,
            {"operation", "a", "b"},
            "calculator.arguments",
        )

        operation = arguments["operation"]

        if not isinstance(operation, str):
            raise PlanExecutionError(
                "calculator.operation 必须是字符串。"
            )

        if operation not in {
            "add",
            "subtract",
            "multiply",
            "divide",
        }:
            raise PlanExecutionError(
                f"不支持的计算操作：{operation!r}。"
            )

        if not is_finite_number(arguments["a"]):
            raise PlanExecutionError(
                "calculator.a 必须是有限数字。"
            )

        if not is_finite_number(arguments["b"]):
            raise PlanExecutionError(
                "calculator.b 必须是有限数字。"
            )

    else:
        allowed = ", ".join(sorted(ALLOWED_TOOL_NAMES))
        raise PlanExecutionError(
            f"未知行动：{action_name!r}。"
            f"允许的工具：{allowed}。"
        )

    return AgentAction(
        name=action_name,
        arguments=dict(arguments),
    )


def parse_step_action(
    model_output: str,
    current_step: PlanStep,
) -> AgentAction:
    """校验 Executor Action 是否严格服从当前 PlanStep。"""
    data = parse_json_object(model_output)

    validate_exact_fields(
        data=data,
        expected={"step_id", "action", "arguments"},
        context=f"Step {current_step.id} Executor Action",
    )

    step_id = data["step_id"]

    if isinstance(step_id, bool) or not isinstance(step_id, int):
        raise PlanExecutionError("step_id 必须是整数。")

    if step_id != current_step.id:
        raise PlanExecutionError(
            f"Executor 返回了错误的 step_id："
            f"期望 {current_step.id}，实际 {step_id}。"
        )

    if data["action"] != current_step.tool_name:
        raise PlanExecutionError(
            "Executor 选择的工具与 PlanStep 不一致："
            f"计划要求 {current_step.tool_name!r}，"
            f"实际为 {data['action']!r}。"
        )

    return validate_agent_action(
        action_name=data["action"],
        arguments=data["arguments"],
    )


def step_result_to_dict(
    result: StepResult,
) -> dict[str, object]:
    """将 StepResult 转换为可序列化字典。"""
    return {
        "step_id": result.step_id,
        "description": result.description,
        "tool": result.tool_name,
        "arguments": dict(result.arguments),
        "output": result.output,
    }


def build_executor_input(
    user_goal: str,
    plan: Plan,
    current_step: PlanStep,
    completed_results: list[StepResult],
) -> str:
    """为当前 PlanStep 构造完整 Executor 输入。"""
    payload = {
        "user_goal": user_goal,
        "plan": plan_to_dict(plan),
        "current_step": plan_step_to_dict(current_step),
        "completed_results": [
            step_result_to_dict(result)
            for result in completed_results
        ],
    }

    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )


def request_step_action_text(
    client: object,
    model_id: str,
    user_goal: str,
    plan: Plan,
    current_step: PlanStep,
    completed_results: list[StepResult],
) -> str:
    """请求 Executor 为当前步骤生成具体 Action。"""
    request_text = build_executor_input(
        user_goal=user_goal,
        plan=plan,
        current_step=current_step,
        completed_results=completed_results,
    )

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": EXECUTOR_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": request_text,
            },
        ],
    )

    if not response.choices:
        raise RuntimeError(
            f"Step {current_step.id} 的 Executor "
            "choices 列表为空。"
        )

    text = response.choices[0].message.content

    if not text or not text.strip():
        raise RuntimeError(
            f"Step {current_step.id} 的 Executor "
            "没有返回可用文本。"
        )

    return text


def request_step_action(
    client: object,
    model_id: str,
    user_goal: str,
    plan: Plan,
    current_step: PlanStep,
    completed_results: list[StepResult],
) -> AgentAction:
    """请求并校验当前步骤的具体 Action。"""
    model_output = request_step_action_text(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
        plan=plan,
        current_step=current_step,
        completed_results=completed_results,
    )

    print("\nExecutor 原始输出：")
    print(model_output)

    return parse_step_action(
        model_output=model_output,
        current_step=current_step,
    )


def execute_plan_step(
    action: AgentAction,
    current_step: PlanStep,
) -> StepResult:
    """执行一个经过校验的计划步骤。"""
    try:
        output = execute_tool(
            tool_name=action.name,
            arguments=action.arguments,
        )
    except (TypeError, ValueError) as error:
        raise PlanExecutionError(
            f"Step {current_step.id} 执行失败：{error}"
        ) from error

    return StepResult(
        step_id=current_step.id,
        description=current_step.description,
        tool_name=action.name,
        arguments=dict(action.arguments),
        output=output,
    )


def execute_plan(
    client: object,
    model_id: str,
    user_goal: str,
    plan: Plan,
) -> list[StepResult]:
    """按照静态计划顺序执行全部步骤。"""
    completed_results: list[StepResult] = []

    for current_step in plan.steps:
        print(
            f"\n=== Solving Step "
            f"{current_step.id}/{len(plan.steps)} ==="
        )
        print(f"Description：{current_step.description}")
        print(f"Plan Tool：{current_step.tool_name}")
        print(f"Expected Output：{current_step.expected_output}")

        action = request_step_action(
            client=client,
            model_id=model_id,
            user_goal=user_goal,
            plan=plan,
            current_step=current_step,
            completed_results=completed_results,
        )

        print("\nParsed Action：")
        print(f"  name={action.name}")
        print(
            "  arguments="
            + json.dumps(
                action.arguments,
                ensure_ascii=False,
                sort_keys=True,
            )
        )

        result = execute_plan_step(
            action=action,
            current_step=current_step,
        )
        completed_results.append(result)

        print("\nStepResult：")
        print(result.output)

    return completed_results


def validate_finalize_inputs(
    plan: Plan,
    step_results: list[StepResult],
) -> None:
    """确保只有完整计划结果才能进入 Finalize。"""
    if len(step_results) != len(plan.steps):
        raise PlanExecutionError(
            "计划尚未全部完成，不能进入 Finalize。"
        )

    for step, result in zip(plan.steps, step_results):
        if result.step_id != step.id:
            raise PlanExecutionError(
                "StepResult 顺序或 step_id 与 Plan 不一致。"
            )

        if result.tool_name != step.tool_name:
            raise PlanExecutionError(
                f"Step {step.id} 的结果工具与 Plan 不一致。"
            )


def finalize_answer(
    client: object,
    model_id: str,
    user_goal: str,
    plan: Plan,
    step_results: list[StepResult],
) -> str:
    """根据完整 Plan 与 StepResult 生成最终回答。"""
    validate_finalize_inputs(
        plan=plan,
        step_results=step_results,
    )

    payload = {
        "user_goal": user_goal,
        "plan": plan_to_dict(plan),
        "step_results": [
            step_result_to_dict(result)
            for result in step_results
        ],
    }

    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": FINALIZE_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
    )

    if not response.choices:
        raise RuntimeError("Finalize choices 列表为空。")

    text = response.choices[0].message.content

    if not text or not text.strip():
        raise RuntimeError("Finalize 没有返回可用文本。")

    return text.strip()
