import pytest

from code_review_agent.llm.router import ModelRouter


def test_router_parses_config(mock_llm_config):
    router = ModelRouter(mock_llm_config)
    assert "claude" in router.list_providers()
    assert "smart" in router.model_registry
    assert "fast" in router.model_registry


def test_router_resolves_model(mock_llm_config):
    router = ModelRouter(mock_llm_config)
    resolved = router.resolve(task="review")
    assert resolved.alias == "smart"
    assert resolved.provider_name == "claude"
    assert resolved.model_id == "claude-sonnet-4-6"


def test_router_resolves_fast_model(mock_llm_config):
    router = ModelRouter(mock_llm_config)
    resolved = router.resolve(task="intent_classify")
    assert resolved.alias == "fast"
    assert resolved.model_id == "claude-haiku-4-5"


def test_router_list_models(mock_llm_config):
    router = ModelRouter(mock_llm_config)
    models = router.list_models()
    assert "smart" in models
    assert "fast" in models
    assert len(models["smart"]) == 1


def test_router_unknown_alias_raises(mock_llm_config):
    router = ModelRouter(mock_llm_config)
    with pytest.raises(ValueError):
        router.resolve(task="review", force_alias="nonexistent")
