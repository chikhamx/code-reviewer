from code_review_agent.llm.base import BaseLLMProvider, LLMResponse, Usage


class ClaudeProvider(BaseLLMProvider):
    provider_name = "claude"

    def __init__(self, api_key: str, base_url: str | None = None):
        try:
            from anthropic import AsyncAnthropic
        except ImportError:
            raise ImportError("anthropic package is required for ClaudeProvider. pip install anthropic")

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = AsyncAnthropic(**kwargs)

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
        model = model or "claude-sonnet-4-6"
        system = None
        user_messages = []

        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append(m)

        resp = await self.client.messages.create(
            model=model,
            system=system,
            messages=user_messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        input_tokens = resp.usage.input_tokens if resp.usage else 0
        output_tokens = resp.usage.output_tokens if resp.usage else 0

        return LLMResponse(
            content=resp.content[0].text if resp.content else "",
            model=resp.model,
            provider=self.provider_name,
            usage=Usage(
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
            ),
            finish_reason=resp.stop_reason or "stop",
        )

    def supports_tools(self) -> bool:
        return True

    def supports_vision(self) -> bool:
        return True
