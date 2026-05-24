from code_review_agent.actions.base import BaseAction


class ExplainAction(BaseAction):
    name = "explain"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        # Use pinned code from session if user is asking about a previous finding
        code = session.pinned_code or ""
        if not code:
            code = "No specific code was referenced in the conversation."

        prompt = (
            f"Explain the following code clearly and concisely.\n\n"
            f"User question: {text}\n\n"
            f"Code:\n```\n{code}\n```"
        )

        if self.fallback:
            resp = await self.fallback.call_with_fallback("explain", [
                {"role": "user", "content": prompt},
            ])
            return resp.content

        return "Explain action requires LLM configuration."
