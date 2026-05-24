"""Auto-start Ollama if configured and not already running.

Called during bootstrap. Does nothing if Ollama is not in config or
already running. Otherwise starts ollama serve in a background process
and waits for it to become ready.
"""

import logging
import os
import subprocess
import time

import httpx

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"


async def ensure_ollama(llm_config: dict) -> bool:
    """Start Ollama if configured and not running. Returns True if Ollama is available."""
    providers = llm_config.get("providers", {})
    ollama_cfg = providers.get("ollama", {})
    if not ollama_cfg or not ollama_cfg.get("enabled"):
        return False

    base_url = ollama_cfg.get("base_url", OLLAMA_BASE)

    # Already running?
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                logger.info("Ollama running: %d models loaded", len(models))
                return True
    except Exception:
        pass

    # Try to start ollama serve
    logger.info("Starting Ollama serve...")
    ollama_bin = _find_ollama()
    if not ollama_bin:
        logger.warning("Ollama not found on PATH — install from https://ollama.com/download")
        return False

    try:
        subprocess.Popen(
            [ollama_bin, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except Exception as e:
        logger.warning("Failed to start ollama serve: %s", e)
        return False

    # Wait up to 15s for Ollama to become ready
    for i in range(15):
        time.sleep(1)
        try:
            async with httpx.AsyncClient(timeout=2) as client:
                resp = await client.get(f"{OLLAMA_BASE}/api/tags")
                if resp.status_code == 200:
                    models = resp.json().get("models", [])
                    logger.info("Ollama started: %d models available", len(models))
                    return True
        except Exception:
            pass

    logger.warning("Ollama did not start within 15 seconds")
    return False


def _find_ollama() -> str | None:
    """Locate the ollama binary."""
    # Check PATH first
    for path in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("ollama", "ollama.exe"):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                return full
    # Common install locations on Windows
    for loc in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]:
        if os.path.isfile(loc):
            return loc
    return None
