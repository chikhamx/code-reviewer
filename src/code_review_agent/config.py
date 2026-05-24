import os
import re
from pathlib import Path
from typing import Any

import yaml


def _expand_env(value: str) -> str:
    """Expand ${VAR} placeholders in a string."""

    def _replacer(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return re.sub(r"\$\{(\w+)\}", _replacer, value)


def _expand_env_recursive(obj: Any) -> Any:
    """Recursively expand env vars in a nested structure."""
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _expand_env_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_recursive(item) for item in obj]
    return obj


class Config:
    """Application configuration with YAML + env var support."""

    def __init__(self, config_dir: str = "config", app_config_path: str | None = None):
        self.config_dir = Path(config_dir)
        self._data: dict[str, Any] = {}
        self._load(app_config_path)

    def _load(self, app_config_path: str | None = None) -> None:
        path = Path(app_config_path) if app_config_path else self.config_dir / "default.yaml"
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            self._data = yaml.safe_load(raw) or {}
        self._data = _expand_env_recursive(self._data)

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._data
        for key in keys:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                return default
            if node is None:
                return default
        return node

    def load_sub_config(self, config_path_key: str | None, *keys: str) -> dict[str, Any]:
        """Load an external YAML sub-config referenced by a path key."""
        path_str = self.get(config_path_key, *keys) if config_path_key else self.get(*keys)
        if not path_str:
            return {}
        path = Path(path_str)
        if not path.is_absolute():
            path = self.config_dir / path
        if not path.exists():
            return {}
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return _expand_env_recursive(data)

    @property
    def raw(self) -> dict[str, Any]:
        return self._data


# Global singleton
_config: Config | None = None


def get_config(config_dir: str = "config") -> Config:
    global _config
    if _config is None:
        _config = Config(config_dir)
    return _config


def reload_config(config_dir: str = "config") -> Config:
    global _config
    _config = Config(config_dir)
    return _config
