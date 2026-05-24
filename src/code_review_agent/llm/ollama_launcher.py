"""Auto-start Ollama — download, install, and serve from project tools/ dir.

Called during bootstrap. If Ollama is configured but not installed,
downloads the portable binary to tools/ollama/ (one-time ~1GB download).
Subsequent starts use the cached binary.

The heavy download runs in a background thread to avoid blocking startup.
"""

import logging
import os
import subprocess
import threading
import time
import zipfile
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_VERSION = "v0.24.0"
OLLAMA_DOWNLOAD = (
    f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}"
    "/ollama-windows-amd64.zip"
)
TOOLS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "tools" / "ollama"


async def ensure_ollama(llm_config: dict) -> bool:
    """Ensure Ollama is running. Downloads + installs if needed. Returns True if ready."""
    providers = llm_config.get("providers", {})
    ollama_cfg = providers.get("ollama", {})
    if not ollama_cfg or not ollama_cfg.get("enabled"):
        return False

    base_url = ollama_cfg.get("base_url", OLLAMA_HOST)
    native_url = base_url.rstrip("/").removesuffix("/v1")

    # Already running? (only 200 counts, 502 etc. means something else on the port)
    if await _check_ollama(native_url):
        return True

    # Kill any stale process on the Ollama port
    _kill_port(11434)

    # Find or install ollama binary (download runs in background thread)
    ollama_bin = _find_ollama()
    if not ollama_bin:
        logger.info("Ollama not found, starting background download to %s ...", TOOLS_DIR)
        threading.Thread(target=_install_ollama_sync, name="ollama-install", daemon=True).start()
        logger.info("Ollama download started in background — will be ready next restart")
        return False

    # Ensure OLLAMA_MODELS is set to project dir
    models_dir = str(TOOLS_DIR / "models")
    os.makedirs(models_dir, exist_ok=True)
    env_models = os.environ.get("OLLAMA_MODELS", "")
    if not env_models:
        os.environ["OLLAMA_MODELS"] = models_dir
        logger.info("OLLAMA_MODELS set to %s", models_dir)

    # Start serve
    logger.info("Starting ollama serve...")
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

    # Wait for readiness
    for _ in range(20):
        time.sleep(1.5)
        if await _check_ollama(OLLAMA_HOST):
            # Pull required models in background
            await _pull_models(ollama_bin, ollama_cfg)
            return True

    logger.warning("Ollama did not start within 30 seconds")
    return False


async def _check_ollama(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                logger.info("Ollama running: %d models loaded", len(models))
                return True
    except Exception:
        pass
    return False


def _install_ollama_sync() -> None:
    """Download and extract Ollama portable zip (runs in background thread)."""
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = TOOLS_DIR / "ollama.zip"
    exe_path = TOOLS_DIR / "ollama.exe"

    try:
        logger.info("Downloading Ollama %s (~1GB, one-time)...", OLLAMA_VERSION)
        with httpx.Client(timeout=600, follow_redirects=True) as client:
            with client.stream("GET", OLLAMA_DOWNLOAD) as resp:
                if resp.status_code != 200:
                    logger.error("Ollama download failed: HTTP %d", resp.status_code)
                    return
                total = 0
                with open(zip_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8 * 1024 * 1024):
                        f.write(chunk)
                        total += len(chunk)
                logger.info("Ollama downloaded: %.0f MB", total / 1024 / 1024)

        logger.info("Extracting Ollama...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(TOOLS_DIR)
        zip_path.unlink()
        if exe_path.exists():
            logger.info("Ollama installed to %s — ready after restart", TOOLS_DIR)
        else:
            logger.error("Ollama extraction failed: ollama.exe not found in zip")
    except Exception as e:
        logger.error("Ollama install failed: %s", e)


async def _pull_models(ollama_bin: str, ollama_cfg: dict) -> None:
    """Pull configured models in background if not already present."""
    models = ollama_cfg.get("models", [])
    for m in models:
        model_id = m.get("id", "")
        if not model_id:
            continue
        # Check if model exists
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{OLLAMA_HOST}/api/show",
                    json={"name": model_id},
                )
                if resp.status_code == 200:
                    continue  # already pulled
        except Exception:
            pass

        # Pull in background
        logger.info("Pulling model %s (background)...", model_id)
        try:
            subprocess.Popen(
                [ollama_bin, "pull", model_id],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
        except Exception as e:
            logger.warning("Failed to pull model %s: %s", model_id, e)


def _kill_port(port: int) -> None:
    """Kill any process listening on the given port (Windows only)."""
    if os.name != "nt":
        return
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port}" | findstr "LISTENING"',
            shell=True, text=True,
        )
        for line in out.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                pid = parts[-1]
                subprocess.run(["TASKKILL", "/F", "/PID", pid],
                               capture_output=True)
                logger.info("Killed PID %s on port %d", pid, port)
    except Exception:
        pass


def _find_ollama() -> str | None:
    """Locate the ollama binary: project tools/ first, then PATH, then common locations."""
    # 1. Project tools dir
    exe = TOOLS_DIR / "ollama.exe"
    if exe.exists():
        return str(exe)

    # 2. PATH
    for path in os.environ.get("PATH", "").split(os.pathsep):
        for name in ("ollama", "ollama.exe"):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                return full

    # 3. Common Windows locations
    for loc in [
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]:
        if os.path.isfile(loc):
            return loc

    return None
