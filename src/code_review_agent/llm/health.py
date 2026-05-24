import asyncio
import logging

from code_review_agent.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)


class HealthChecker:
    """Periodic health checks for all registered providers."""

    def __init__(self, providers: dict[str, BaseLLMProvider]):
        self.providers = providers
        self._status: dict[str, bool] = {}

    async def check_provider(self, name: str) -> bool:
        provider = self.providers.get(name)
        if provider is None:
            return False
        try:
            ok = await provider.health_check()
            self._status[name] = ok
            return ok
        except Exception:
            self._status[name] = False
            return False

    async def check_all(self) -> dict[str, bool]:
        tasks = {name: self.check_provider(name) for name in self.providers}
        results = {}
        for name, task in tasks.items():
            results[name] = await task
        return results

    def is_healthy(self, provider_name: str) -> bool:
        return self._status.get(provider_name, True)

    def get_status(self) -> dict[str, bool]:
        return {name: self._status.get(name, True) for name in self.providers}
