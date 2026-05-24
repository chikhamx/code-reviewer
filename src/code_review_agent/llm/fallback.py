import logging

from code_review_agent.llm.base import BaseLLMProvider
from code_review_agent.llm.router import ModelRouter, ResolvedModel

logger = logging.getLogger(__name__)


class NoAvailableModelError(Exception):
    pass


class FallbackChain:
    """Falls back through providers in registry order when a model is unavailable."""

    def __init__(self, router: ModelRouter):
        self.router = router

    async def call_with_fallback(
        self,
        task: str,
        messages: list[dict],
        *,
        force_alias: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        alias = force_alias or self.router.TASK_ALIAS_MAP.get(task, "smart")
        candidates = self.router.model_registry.get(alias, [])
        if not candidates:
            raise NoAvailableModelError(f"No models for alias '{alias}'")

        errors: list[str] = []

        for candidate in candidates:
            try:
                provider = self.router.get_provider(candidate.provider_name)
                resp = await provider.chat(
                    messages,
                    model=candidate.model_id,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                return resp
            except Exception as e:
                err_msg = f"{candidate.provider_name}/{candidate.model_id}: {e}"
                errors.append(err_msg)
                logger.warning("Fallback: %s", err_msg)
                continue

        raise NoAvailableModelError(
            f"All {len(candidates)} models for alias '{alias}' failed:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
