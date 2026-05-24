from dataclasses import dataclass, field

from code_review_agent.llm.base import BaseLLMProvider
from code_review_agent.llm.providers.claude import ClaudeProvider
from code_review_agent.llm.providers.custom import CustomProvider
from code_review_agent.llm.providers.ollama import OllamaProvider
from code_review_agent.llm.providers.openai import OpenAIProvider


@dataclass
class ResolvedModel:
    provider_name: str
    model_id: str
    alias: str
    max_tokens: int = 4096
    supports_tools: bool = False
    supports_vision: bool = False


class ModelRouter:
    TASK_ALIAS_MAP: dict[str, str] = {
        "review": "smart",
        "intent_classify": "fast",
        "explain": "smart",
        "suggest_fix": "smart",
        "refactor": "smart",
        "search": "fast",
        "chat": "smart",
        "summary": "fast",
    }

    def __init__(self, llm_config: dict):
        self.providers: dict[str, BaseLLMProvider] = {}
        self.model_registry: dict[str, list[ResolvedModel]] = {}
        self._init_from_config(llm_config)

    def _init_from_config(self, config: dict) -> None:
        providers_cfg = config.get("providers", {})
        pricing = config.get("pricing", {})
        task_map_override = config.get("task_model_map", {})
        self.TASK_ALIAS_MAP.update(task_map_override)

        for provider_name, cfg in providers_cfg.items():
            if provider_name == "custom":
                self._init_custom_providers(cfg, pricing)
                continue
            if isinstance(cfg, dict) and not cfg.get("enabled", True):
                continue
            self._init_provider(provider_name, cfg, pricing)

    def _init_provider(self, name: str, cfg: dict, pricing: dict) -> None:
        api_key = cfg.get("api_key", "")
        base_url = cfg.get("base_url") or None

        provider_map = {
            "claude": ClaudeProvider,
            "openai": OpenAIProvider,
            "ollama": OllamaProvider,
        }
        provider_cls = provider_map.get(name)
        if provider_cls is None:
            # Unknown providers (deepseek, groq, together, etc.) use CustomProvider
            # which implements the OpenAI-compatible API protocol.
            provider = CustomProvider(
                name=name, api_key=api_key, base_url=base_url or "",
            )
        else:
            provider = provider_cls(api_key=api_key, base_url=base_url)

        self.providers[name] = provider

        for model_cfg in cfg.get("models", []):
            for alias in model_cfg.get("alias", []):
                rm = ResolvedModel(
                    provider_name=name,
                    model_id=model_cfg["id"],
                    alias=alias,
                    max_tokens=model_cfg.get("max_tokens", 4096),
                    supports_tools=model_cfg.get("supports_tools", False),
                    supports_vision=model_cfg.get("supports_vision", False),
                )
                self.model_registry.setdefault(alias, []).append(rm)

    def _init_custom_providers(self, custom_list: list, pricing: dict) -> None:
        for cfg in custom_list:
            if not isinstance(cfg, dict):
                continue
            name = cfg.get("name", "")
            if not name:
                continue
            provider = CustomProvider(
                name=name,
                api_key=cfg.get("api_key", ""),
                base_url=cfg.get("base_url", ""),
            )
            self.providers[name] = provider
            for model_cfg in cfg.get("models", []):
                for alias in model_cfg.get("alias", []):
                    rm = ResolvedModel(
                        provider_name=name,
                        model_id=model_cfg["id"],
                        alias=alias,
                        max_tokens=model_cfg.get("max_tokens", 4096),
                    )
                    self.model_registry.setdefault(alias, []).append(rm)

    def resolve(self, task: str = "chat", force_alias: str | None = None) -> ResolvedModel:
        alias = force_alias or self.TASK_ALIAS_MAP.get(task, "smart")
        candidates = self.model_registry.get(alias, [])
        if not candidates:
            raise ValueError(f"No model registered for alias '{alias}'")
        return candidates[0]

    def get_provider(self, provider_name: str) -> BaseLLMProvider:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ValueError(f"Provider '{provider_name}' not found")
        return provider

    async def chat(
        self,
        task: str,
        messages: list[dict],
        *,
        force_alias: str | None = None,
        force_model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ):
        resolved = self.resolve(task, force_alias)
        provider = self.get_provider(resolved.provider_name)
        model = force_model or resolved.model_id
        return await provider.chat(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def list_models(self) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {}
        for alias, models in self.model_registry.items():
            result[alias] = [
                {"provider": m.provider_name, "model_id": m.model_id, "max_tokens": m.max_tokens}
                for m in models
            ]
        return result

    def list_providers(self) -> list[str]:
        return list(self.providers.keys())
