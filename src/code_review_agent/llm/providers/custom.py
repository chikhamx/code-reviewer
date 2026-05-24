from code_review_agent.llm.base import BaseLLMProvider, LLMResponse, Usage


class CustomProvider(BaseLLMProvider):
    """Any OpenAI-compatible API endpoint, configured at runtime."""

    provider_name: str

    def __init__(self, name: str, api_key: str, base_url: str):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package is required for CustomProvider. pip install openai")

        self.provider_name = name
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def chat(
        self,
        messages: list[dict],
        *,
        model: str | None = None,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
        stream: bool = False,
    ) -> LLMResponse:
        if model is None:
            raise ValueError("model must be specified for CustomProvider")
        resp = await self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]

        input_tokens = resp.usage.prompt_tokens if resp.usage else 0
        output_tokens = resp.usage.completion_tokens if resp.usage else 0

        return LLMResponse(
            content=choice.message.content or "",
            model=resp.model,
            provider=self.provider_name,
            usage=Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason=choice.finish_reason or "stop",
        )

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return False
