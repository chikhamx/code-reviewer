from code_review_agent.models.conversation import SessionContext


class ContextBuilder:
    """Builds LLM conversation context from session history and pinned code."""

    MAX_HISTORY_TURNS = 10

    def build_messages(
        self,
        session: SessionContext,
        system_prompt: str = "",
        current_message: str = "",
    ) -> list[dict]:
        messages: list[dict] = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        # Add pinned code context if present
        if session.pinned_code:
            messages.append({
                "role": "system",
                "content": f"The user is discussing this code:\n```\n{session.pinned_code}\n```",
            })

        # Add conversation history
        recent = session.history[-self.MAX_HISTORY_TURNS * 2:]
        for msg in recent:
            messages.append({
                "role": msg["role"] if isinstance(msg, dict) else msg.role,
                "content": msg["content"] if isinstance(msg, dict) else msg.content,
            })

        # Add current message
        if current_message and (not messages or messages[-1].get("content") != current_message):
            messages.append({"role": "user", "content": current_message})

        return messages

    def build_review_context(self, session: SessionContext) -> dict:
        """Extract review-relevant context from session."""
        return {
            "current_intent": session.current_intent,
            "current_target": session.current_target,
            "pinned_code": session.pinned_code,
            "metadata": session.metadata,
        }
