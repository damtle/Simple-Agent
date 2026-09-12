"""Agent 使用的最小 LLM 接口与 OpenAI Chat 适配器。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


Message = dict[str, str]


class LLM(Protocol):
    """Agent 运行时只依赖这一项生成能力。"""

    def generate(self, messages: Sequence[Message]) -> str:
        ...


class LLMRequestError(RuntimeError):
    """统一表示模型请求层错误。"""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass
class OpenAIChatLLM:
    """兼容 OpenAI Chat Completions 客户端的同步适配器。

    核心包不读取 ``.env``，客户端和模型标识由应用入口创建并注入。
    """

    client: Any
    model_id: str
    temperature: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id 不能为空。")

    def generate(self, messages: Sequence[Message]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[dict(message) for message in messages],
                temperature=self.temperature,
            )
        except Exception as error:
            # 具体 SDK 异常在适配器边界统一转换，Agent 不依赖 SDK 类型。
            raise LLMRequestError(
                f"模型请求失败：{error}",
                retryable=_looks_retryable(error),
            ) from error

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as error:
            raise LLMRequestError(
                "模型响应结构中没有可读取的文本内容。",
                retryable=False,
            ) from error

        if not isinstance(content, str):
            raise LLMRequestError(
                "模型没有返回文本内容。",
                retryable=False,
            )

        text = content.strip()

        if not text:
            raise LLMRequestError(
                "模型返回了空文本。",
                retryable=False,
            )

        return text


def _looks_retryable(error: Exception) -> bool:
    """用通用信号判断临时网络或服务错误。"""
    name = type(error).__name__.lower()
    retryable_names = (
        "timeout",
        "connection",
        "ratelimit",
        "temporar",
    )

    if any(token in name for token in retryable_names):
        return True

    status_code = getattr(error, "status_code", None)
    return status_code in {408, 409, 429, 500, 502, 503, 504}
