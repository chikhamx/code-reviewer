from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: Usage | None = None
    finish_reason: str = "stop"


class BaseLLMProvider(ABC):
    provider_name: str

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stream: bool = False,
    ) -> LLMResponse: ...

    @abstractmethod
    def supports_tools(self) -> bool: ...

    @abstractmethod
    def supports_vision(self) -> bool: ...

    async def health_check(self) -> bool:
        """Quick connectivity test. Default: ping with minimal chat."""
        try:
            resp = await self.chat(
                [{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0.0,
            )
            return bool(resp.content)
        except Exception:
            return False
