"""仅供测试使用的确定性 LLM 替代对象。"""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy

from simple_agent.llm import Message


MockOutput = str | Exception


class MockLLM:
    def __init__(self, outputs: Sequence[MockOutput]) -> None:
        self._outputs = list(outputs)
        self._index = 0
        self.calls: list[list[Message]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def remaining_outputs(self) -> int:
        return len(self._outputs) - self._index

    def generate(self, messages: Sequence[Message]) -> str:
        self.calls.append(deepcopy(list(messages)))

        if self._index >= len(self._outputs):
            raise AssertionError("MockLLM 没有更多预设输出。")

        output = self._outputs[self._index]
        self._index += 1

        if isinstance(output, Exception):
            raise output
        if not isinstance(output, str):
            raise TypeError("MockLLM 输出必须是字符串或异常。")

        return output
