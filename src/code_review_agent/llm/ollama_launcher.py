"""Check if Ollama is running. No auto-start — managed externally by start_cr.ps1."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"


async def ensure_ollama(llm_config: dict) -> bool:
    """Check if Ollama is running. Returns True if available, False otherwise."""
    providers = llm_config.get("providers", {})
    ollama_cfg = providers.get("ollama", {})
    if not ollama_cfg or not ollama_cfg.get("enabled"):
        return False

    base_url = ollama_cfg.get("base_url", OLLAMA_HOST)
    native_url = base_url.rstrip("/").removesuffix("/v1")

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{native_url}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                logger.info("Ollama running: %d models loaded", len(models))
                return True
    except Exception:
        pass

    logger.info("Ollama not running — intent classification will use remote LLM")
    return False
