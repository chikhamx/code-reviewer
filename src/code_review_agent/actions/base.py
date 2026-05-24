import logging
from abc import ABC, abstractmethod

from code_review_agent.router.intent_router import Intent

logger = logging.getLogger(__name__)


class BaseAction(ABC):
    """Abstract base for all action handlers."""

    name: str = "base"

    @abstractmethod
    async def execute(self, normalized: dict, session) -> str:
        """Execute the action and return a response string."""
        ...


class ActionDispatcher:
    """Routes intents to their corresponding action handlers."""

    def __init__(self, core_engine=None, llm_router=None, fallback=None):
        self.handlers: dict[Intent, BaseAction] = {}
        self.core_engine = core_engine
        self.llm_router = llm_router
        self.fallback = fallback

    def register(self, intent: Intent, handler: BaseAction) -> None:
        self.handlers[intent] = handler

    async def dispatch(self, intent: Intent, normalized: dict, session) -> str:
        handler = self.handlers.get(intent)
        if handler is None:
            logger.warning("No handler for intent %s, falling back to chat", intent)
            handler = self.handlers.get(Intent.CHAT)
        if handler is None:
            return "I didn't understand that. Try 'review PR #42' or 'help'."
        try:
            return await handler.execute(normalized, session)
        except Exception as e:
            logger.exception("Action '%s' failed", handler.name)
            return f"Action failed: {e}"
