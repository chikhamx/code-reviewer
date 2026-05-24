from code_review_agent.actions.base import BaseAction


class ChatAction(BaseAction):
    name = "chat"

    def __init__(self, llm_router=None, fallback=None):
        self.llm_router = llm_router
        self.fallback = fallback

    async def execute(self, normalized: dict, session) -> str:
        text = normalized.get("text", "")

        system_prompt = (
            "You are a helpful code review assistant. "
            "You can help with code review, explaining code, suggesting fixes, "
            "and answering general programming questions. "
            "Be concise and helpful."
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Include session history for continuity
        for msg in session.history[-6:]:
            messages.append({
                "role": msg["role"] if isinstance(msg, dict) else msg.role,
                "content": msg["content"] if isinstance(msg, dict) else msg.content,
            })
        messages.append({"role": "user", "content": text})

        if self.fallback:
            resp = await self.fallback.call_with_fallback("chat", messages)
            return resp.content

        # Fallback without LLM
        return (
            "I'm a code review assistant. Here's what I can do:\n"
            "- `review https://github.com/org/repo/pull/42` — Review a PR\n"
            "- `explain <code>` — Explain code logic\n"
            "- `suggest fix for <issue>` — Get fix suggestions\n"
            "- `refactor <code>` — Get refactoring advice\n"
            "- `help` — Show this menu"
        )
