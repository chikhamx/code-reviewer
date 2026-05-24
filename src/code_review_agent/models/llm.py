from dataclasses import dataclass

from pydantic import BaseModel, Field


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: Usage = Field(default_factory=Usage)
    finish_reason: str = "stop"


@dataclass
class ResolvedModel:
    provider_name: str
    model_id: str
    alias: str
    max_tokens: int = 4096
    supports_tools: bool = False
    supports_vision: bool = False
