"""第一章：规则温控智能体。

该示例不调用大语言模型，只使用固定规则展示最小 Agent Loop：
观察环境 -> 选择行动 -> 执行行动 -> 获得新观察。
"""


class RoomEnvironment:
    """保存房间温度，并根据行动改变环境状态。"""

    def __init__(
        self,
        temperature: float = 30.0,
        change_per_action: float = 1.5,
    ) -> None:
        self.temperature = temperature
        self.change_per_action = change_per_action

    def observe(self) -> dict[str, float]:
        """返回 Agent 当前能够获得的观察。"""
        return {"temperature": self.temperature}

    def apply(self, action: str) -> None:
        """执行行动并改变房间温度。"""
        if action == "cool":
            self.temperature -= self.change_per_action
        elif action == "heat":
            self.temperature += self.change_per_action
        elif action == "maintain":
            return
        else:
            raise ValueError(f"未知行动：{action}")


class SimpleReflexAgent:
    """只根据当前温度观察选择行动的简单反射智能体。"""

    def __init__(
        self,
        target_temperature: float = 25.0,
        tolerance: float = 0.5,
    ) -> None:
        self.target_temperature = target_temperature
        self.tolerance = tolerance

    def decide(self, observation: dict[str, float]) -> str:
        """根据目标温度和当前观察选择下一步行动。"""
        temperature = observation["temperature"]
        lower_bound = self.target_temperature - self.tolerance
        upper_bound = self.target_temperature + self.tolerance

        if temperature > upper_bound:
            return "cool"

        if temperature < lower_bound:
            return "heat"

        return "maintain"


def run_agent(max_steps: int = 10) -> None:
    """运行温控 Agent，直到达到目标或耗尽最大步数。"""
    environment = RoomEnvironment(
        temperature=30.0,
        change_per_action=1.5,
    )
    agent = SimpleReflexAgent(
        target_temperature=25.0,
        tolerance=0.5,
    )

    for step in range(1, max_steps + 1):
        observation = environment.observe()
        action = agent.decide(observation)

        before = observation["temperature"]
        environment.apply(action)
        after = environment.observe()["temperature"]

        print(
            f"Step {step}: "
            f"temperature={before:.1f}℃, "
            f"action={action}, "
            f"after={after:.1f}℃"
        )

        if action == "maintain":
            print("目标温度已达到，任务结束。")
            return

    print("在限定步数内未达到目标温度。")


if __name__ == "__main__":
    run_agent()
