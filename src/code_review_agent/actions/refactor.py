from code_review_agent.actions.base import BaseAction


class RefactorAction(BaseAction):
    name = "refactor"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")
        code = session.pinned_code or ""

        if not code and not text:
            return "Please specify which code you'd like to refactor."

        prompt = (
            "Suggest a refactoring for the following code. "
            "Focus on improving readability, reducing complexity, and following best practices. "
            "Show the refactored code and explain the key changes.\n\n"
            f"User request: {text}\n\n"
            f"Code:\n```\n{code}\n```"
        )

        if self.fallback:
            resp = await self.fallback.call_with_fallback("refactor", [
                {"role": "user", "content": prompt},
            ])
            return resp.content

        return "Refactor action requires LLM configuration."
