"""Simple Agent 使用的最小 LLM 协议与 OpenAI 兼容适配器。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


Message = dict[str, str]


class LLM(Protocol):
    """Agent 所依赖的最小模型行为。"""

    def generate(self, messages: Sequence[Message]) -> str:
        """根据当前完整消息历史返回一段模型文本。"""


class LLMRequestError(RuntimeError):
    """模型服务没有返回可供 Parser 使用的文本。"""


@dataclass
class OpenAIChatLLM:
    """把 OpenAI 兼容 SDK 客户端适配为统一 LLM 接口。"""

    client: Any
    model_id: str
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id 必须是非空字符串。")
        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature, (int, float)
        ):
            raise TypeError("temperature 必须是数字。")

    def generate(self, messages: Sequence[Message]) -> str:
        normalized_messages = [dict(message) for message in messages]

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=normalized_messages,
                temperature=float(self.temperature),
            )
            content = response.choices[0].message.content
        except Exception as error:  # SDK 细分异常由具体应用按需继续适配。
            raise LLMRequestError(f"模型请求失败：{error}") from error

        if not isinstance(content, str) or not content.strip():
            raise LLMRequestError("模型返回了响应，但没有文本内容。")

        return content.strip()
