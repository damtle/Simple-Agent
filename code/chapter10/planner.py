"""第十章：生成、解析并校验静态 Plan。"""

import json

from models import Plan, PlanParseError, PlanStep


PLANNER_SYSTEM_PROMPT = """
你是城市旅行助手的 Planner。

请根据用户目标生成一份完整的线性工具计划。

当前可用工具：

1. get_weather
   用途：查询一个城市的本地模拟天气。

2. get_attraction_info
   用途：查询一个景点的本地模拟开放状态、
   成人票价和活动类型。

3. calculator
   用途：执行加、减、乘、除。

输出必须是一个 JSON 对象，只包含 goal 和 steps。

每个 step 只能包含：
id、description、tool、expected_output。

规则：
1. 步骤编号从 1 开始连续递增。
2. 每个步骤只使用一个工具。
3. 覆盖用户目标中的全部明确要求。
4. 按依赖顺序排列步骤。
5. 不要提前填写工具 arguments。
6. 不要把未知天气、开放状态或票价写进计划。
7. 不要使用不存在的工具。
8. 不要输出 Markdown 代码块或额外说明。
""".strip()



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


def normalize_json_text(
    model_output: str,
    error_type: type[ValueError] = PlanParseError,
) -> str:
    """去除首尾空白，并有限处理完整 JSON 代码围栏。"""
    if not isinstance(model_output, str):
        raise error_type("模型输出必须是字符串。")

    text = model_output.strip()

    if not text:
        raise error_type("模型输出为空。")

    lines = text.splitlines()
    first_line = lines[0].strip()
    last_line = lines[-1].strip()

    if first_line.startswith("```"):
        if first_line not in {"```", "```json", "```JSON"}:
            raise error_type(
                "只允许未标注语言或 json 标记的完整代码围栏。"
            )

        if last_line != "```":
            raise error_type("Markdown 代码围栏没有完整闭合。")

        text = "\n".join(lines[1:-1]).strip()

        if not text:
            raise error_type("Markdown 代码围栏中没有内容。")

    elif any(
        line.strip().startswith("```")
        for line in lines
    ):
        raise error_type(
            "Markdown 代码围栏必须完整包裹整个模型输出。"
        )

    return text


def parse_json_object(model_output: str) -> dict[str, object]:
    """将 Planner 输出解析为顶层 JSON 对象。"""
    text = normalize_json_text(model_output)

    try:
        data = _load_bounded_json(text)
    except json.JSONDecodeError as error:
        raise PlanParseError(
            "Planner 输出不是合法 JSON："
            f"{error.msg}，第 {error.lineno} 行，"
            f"第 {error.colno} 列。"
        ) from error

    if not isinstance(data, dict):
        raise PlanParseError("Plan 顶层必须是 JSON 对象。")

    return data


def validate_exact_fields(
    data: dict[str, object],
    expected: set[str],
    context: str,
) -> None:
    """要求对象字段与协议完全一致。"""
    actual = set(data)
    missing = expected - actual
    extra = actual - expected
    details: list[str] = []

    if missing:
        details.append("缺少 " + ", ".join(sorted(missing)))

    if extra:
        details.append("多出 " + ", ".join(sorted(extra)))

    if details:
        raise PlanParseError(
            f"{context}字段不正确：" + "；".join(details) + "。"
        )


def require_non_empty_string(
    value: object,
    field_name: str,
) -> str:
    """校验并返回去除首尾空白后的非空字符串。"""
    if not isinstance(value, str):
        raise PlanParseError(f"{field_name} 必须是字符串。")

    normalized = value.strip()

    if not normalized:
        raise PlanParseError(f"{field_name} 不能为空。")

    return normalized


def parse_plan_step(
    raw_step: object,
    expected_id: int,
    allowed_tools: set[str],
) -> PlanStep:
    """解析并校验一个 PlanStep。"""
    if not isinstance(raw_step, dict):
        raise PlanParseError(
            f"Plan.steps[{expected_id - 1}] 必须是 JSON 对象。"
        )

    validate_exact_fields(
        data=raw_step,
        expected={
            "id",
            "description",
            "tool",
            "expected_output",
        },
        context=f"PlanStep {expected_id}",
    )

    step_id = raw_step["id"]

    if isinstance(step_id, bool) or not isinstance(step_id, int):
        raise PlanParseError(
            f"PlanStep {expected_id}.id 必须是整数。"
        )

    if step_id != expected_id:
        raise PlanParseError(
            "PlanStep.id 必须从 1 开始连续递增："
            f"当前位置应为 {expected_id}，实际为 {step_id}。"
        )

    description = require_non_empty_string(
        raw_step["description"],
        f"PlanStep {expected_id}.description",
    )
    tool_name = require_non_empty_string(
        raw_step["tool"],
        f"PlanStep {expected_id}.tool",
    )
    expected_output = require_non_empty_string(
        raw_step["expected_output"],
        f"PlanStep {expected_id}.expected_output",
    )

    if tool_name not in allowed_tools:
        allowed = ", ".join(sorted(allowed_tools))
        raise PlanParseError(
            f"PlanStep {expected_id} 使用了未知工具"
            f" {tool_name!r}。允许的工具：{allowed}。"
        )

    return PlanStep(
        id=step_id,
        description=description,
        tool_name=tool_name,
        expected_output=expected_output,
    )


def parse_plan(
    model_output: str,
    allowed_tools: set[str],
    max_plan_steps: int = 6,
) -> Plan:
    """将 Planner 文本转换为经过校验的静态 Plan。"""
    if max_plan_steps <= 0:
        raise ValueError("max_plan_steps 必须大于 0。")

    if not allowed_tools:
        raise ValueError("allowed_tools 不能为空。")

    data = parse_json_object(model_output)

    validate_exact_fields(
        data=data,
        expected={"goal", "steps"},
        context="Plan 顶层",
    )

    goal = require_non_empty_string(
        data["goal"],
        "Plan.goal",
    )
    raw_steps = data["steps"]

    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanParseError("Plan.steps 必须是非空数组。")

    if len(raw_steps) > max_plan_steps:
        raise PlanParseError(
            f"计划步骤不能超过 {max_plan_steps} 个，"
            f"当前为 {len(raw_steps)} 个。"
        )

    steps = tuple(
        parse_plan_step(
            raw_step=raw_step,
            expected_id=expected_id,
            allowed_tools=allowed_tools,
        )
        for expected_id, raw_step in enumerate(
            raw_steps,
            start=1,
        )
    )

    return Plan(
        goal=goal,
        steps=steps,
    )


def plan_step_to_dict(step: PlanStep) -> dict[str, object]:
    """将 PlanStep 转换为可序列化字典。"""
    return {
        "id": step.id,
        "description": step.description,
        "tool": step.tool_name,
        "expected_output": step.expected_output,
    }


def plan_to_dict(plan: Plan) -> dict[str, object]:
    """将 Plan 转换为可序列化字典。"""
    return {
        "goal": plan.goal,
        "steps": [
            plan_step_to_dict(step)
            for step in plan.steps
        ],
    }


def format_plan(plan: Plan) -> str:
    """生成适合终端展示的计划文本。"""
    lines = [
        "Plan Goal：",
        plan.goal,
    ]

    for step in plan.steps:
        lines.extend(
            [
                "",
                f"Step {step.id}",
                f"Tool：{step.tool_name}",
                f"Description：{step.description}",
                f"Expected Output：{step.expected_output}",
            ]
        )

    return "\n".join(lines)


def request_plan_text(
    client: object,
    model_id: str,
    user_goal: str,
) -> str:
    """调用 Planner 模型并返回原始文本。"""
    response = client.chat.completions.create(
        model=model_id,
        messages=[
            {
                "role": "system",
                "content": PLANNER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_goal,
            },
        ],
    )

    if not response.choices:
        raise RuntimeError("Planner choices 列表为空。")

    text = response.choices[0].message.content

    if not text or not text.strip():
        raise RuntimeError("Planner 没有返回可用文本。")

    return text


def create_plan(
    client: object,
    model_id: str,
    user_goal: str,
    allowed_tools: set[str],
    max_plan_steps: int = 6,
) -> Plan:
    """请求 Planner，并返回经过校验的 Plan。"""
    if not user_goal.strip():
        raise ValueError("用户目标不能为空。")

    model_output = request_plan_text(
        client=client,
        model_id=model_id,
        user_goal=user_goal,
    )

    print("\nPlanner 原始输出：")
    print(model_output)

    return parse_plan(
        model_output=model_output,
        allowed_tools=allowed_tools,
        max_plan_steps=max_plan_steps,
    )
