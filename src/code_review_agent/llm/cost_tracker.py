import time
from collections import defaultdict

from code_review_agent.llm.base import Usage


class CostTracker:
    """Tracks token usage and cost per provider/model/task dimension."""

    def __init__(self, pricing: dict | None = None):
        self.pricing: dict[str, dict[str, tuple[float, float]]] = pricing or {}
        self.records: list[dict] = []
        self._totals: dict[str, dict[str, dict[str, float]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(float))
        )

    def record(
        self,
        task: str,
        provider: str,
        model: str,
        usage: Usage,
    ) -> None:
        cost = self._calculate_cost(provider, model, usage)
        usage.cost_usd = cost

        self.records.append({
            "timestamp": time.time(),
            "task": task,
            "provider": provider,
            "model": model,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost_usd": cost,
        })

        totals = self._totals[provider][model]
        totals["prompt_tokens"] += usage.prompt_tokens
        totals["completion_tokens"] += usage.completion_tokens
        totals["total_tokens"] += usage.total_tokens
        totals["cost_usd"] += cost

    def _calculate_cost(self, provider: str, model: str, usage: Usage) -> float:
        provider_pricing = self.pricing.get(provider, {})
        rates = provider_pricing.get(model) or provider_pricing.get("*")
        if not rates:
            return 0.0
        input_price, output_price = rates
        input_cost = (usage.prompt_tokens / 1_000_000) * input_price
        output_cost = (usage.completion_tokens / 1_000_000) * output_price
        return input_cost + output_cost

    def get_summary(self) -> dict:
        result: dict[str, dict[str, dict[str, float]]] = {}
        for provider, models in self._totals.items():
            result[provider] = {}
            for model, metrics in models.items():
                result[provider][model] = dict(metrics)
        return result

    def get_total_cost(self) -> float:
        return sum(
            metrics["cost_usd"]
            for models in self._totals.values()
            for metrics in models.values()
        )
