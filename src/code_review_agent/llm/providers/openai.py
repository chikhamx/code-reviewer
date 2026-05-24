from code_review_agent.llm.base import BaseLLMProvider, LLMResponse, Usage


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    def __init__(self, api_key: str, base_url: str | None = None):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("openai package is required for OpenAIProvider. pip install openai")

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncOpenAI(**kwargs)

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
        model = model or "gpt-4o"
        kwargs = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        resp = await self.client.chat.completions.create(**kwargs)
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
        return True
