from code_review_agent.actions.base import BaseAction


class SuggestFixAction(BaseAction):
    name = "suggest_fix"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")
        code = session.pinned_code or ""

        if not code and not text:
            return "Please specify which issue you'd like a fix suggestion for."

        prompt = (
            "Provide a concrete fix suggestion for the following code issue.\n"
            "Show the before and after code, and explain the change.\n\n"
            f"User request: {text}\n\n"
            f"Code context:\n```\n{code}\n```"
        )

        if self.fallback:
            resp = await self.fallback.call_with_fallback("suggest_fix", [
                {"role": "user", "content": prompt},
            ])
            return resp.content

        return "Suggest fix action requires LLM configuration."
