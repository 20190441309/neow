"""Configuration management for Neow CLI."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigError(Exception):
    """Configuration error."""

    pass


class Config:
    """Manages Neow configuration."""

    MODEL_ALIASES = {
        "sonnet": "anthropic",
        "claude": "anthropic",
        "deep": "deepseek",
        "gpt": "openai",
    }

    DEFAULT_CONFIG = {
        "default_model": "deepseek",
        "models": {
            "anthropic": {"api_key": "", "model": "claude-sonnet-4-6"},
            "openai": {"api_key": "", "model": "gpt-4o"},
            "deepseek": {"api_key": "", "model": "deepseek-v4-flash"},
        },
        "tools": {
            "enabled": [
                "read_file",
                "write_file",
                "edit_file",
                "create_file",
                "delete_file",
                "execute_command",
                "search_code",
            ],
            "allowed_commands": ["ls", "cat", "grep", "find", "python", "npm"],
        },
        "approval": {
            "mode": "write",
            "overrides": {},
        },
        "git": {
            "auto_commit": True,
        },
        "streaming": {
            "enabled": True,
        },
        "lint_test": {
            "auto_lint": False,
            "auto_test": False,
            "lint_command": None,
            "test_command": None,
        },
        "architect": {
            "planner": "anthropic",
            "executor": "deepseek",
        },
        "token": {
            "show_usage": True,
            "warn_at_tokens": 100000,
            "max_tokens": 500000,
            "prices": {
                "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
                "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
                "gpt-4o": {"input": 2.5, "output": 10.0},
            },
        },
        "web": {
            "enabled": True,
            "auto_detect": True,
            "max_content_length": 10000,
            "timeout": 10,
        },
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        self._config: Dict[str, Any] = self.DEFAULT_CONFIG.copy()
        self._load_config(config_path)
        self._load_env_vars()

    def _load_config(self, config_path: Optional[Path]) -> None:
        """Load configuration from file."""
        if config_path is None:
            # Try default locations
            home_config = Path.home() / ".neow" / "config.json"
            local_config = Path(".neow.json")

            if home_config.exists():
                config_path = home_config
            elif local_config.exists():
                config_path = local_config
            else:
                return

        if not config_path.exists():
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix in (".yml", ".yaml"):
                    file_config = yaml.safe_load(f)
                else:
                    file_config = json.load(f)

            if file_config:
                self._merge_config(self._config, file_config)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise ConfigError(f"Invalid config file: {e}")

    def _merge_config(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Merge override config into base config.

        Only overrides keys that are explicitly provided in *override*.
        Nested dicts are merged recursively so that providing a partial
        sub-dict (e.g. only one model's api_key) preserves other siblings.
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def _load_env_vars(self) -> None:
        """Load API keys from environment variables."""
        env_mapping = {
            "NEOW_DEEPSEEK_API_KEY": ("deepseek", "api_key"),
            "NEOW_ANTHROPIC_API_KEY": ("anthropic", "api_key"),
            "NEOW_OPENAI_API_KEY": ("openai", "api_key"),
        }

        for env_var, (model, key) in env_mapping.items():
            value = os.environ.get(env_var)
            if value:
                self._config["models"][model][key] = value

    @property
    def default_model(self) -> str:
        """Get default model name."""
        return self._config["default_model"]

    @property
    def models(self) -> Dict[str, Dict[str, str]]:
        """Get models configuration."""
        return self._config["models"]

    @property
    def tools(self) -> Dict[str, Any]:
        """Get tools configuration."""
        return self._config["tools"]

    @property
    def git(self) -> Dict[str, Any]:
        """Get git configuration."""
        return self._config.get("git", {"auto_commit": True})

    @property
    def streaming(self) -> Dict[str, Any]:
        """Get streaming configuration."""
        return self._config.get("streaming", {"enabled": True})

    @property
    def lint_test(self) -> Dict[str, Any]:
        """Get lint/test configuration."""
        return self._config.get("lint_test", {
            "auto_lint": False, "auto_test": False,
            "lint_command": None, "test_command": None,
        })

    @property
    def architect(self) -> Dict[str, Any]:
        """Get architect mode configuration."""
        return self._config.get("architect", {
            "planner": "anthropic", "executor": "deepseek",
        })

    @property
    def token(self) -> Dict[str, Any]:
        """Get token usage configuration."""
        return self._config.get("token", {
            "show_usage": True,
            "warn_at_tokens": 100000,
            "max_tokens": 500000,
            "prices": {},
        })

    @property
    def web(self) -> Dict[str, Any]:
        """Get web context configuration."""
        return self._config.get("web", {
            "enabled": True,
            "auto_detect": True,
            "max_content_length": 10000,
            "timeout": 10,
        })

    @property
    def approval(self) -> Dict[str, Any]:
        """Get approval mode configuration."""
        return self._config.get("approval", {
            "mode": "write",
            "overrides": {},
        })

    def resolve_model_alias(self, alias: str) -> str:
        """Resolve model alias to canonical name. Returns input if no alias found."""
        return self.MODEL_ALIASES.get(alias.lower(), alias)

    def get_model_config(self, model_name: str) -> Dict[str, str]:
        """Get configuration for specific model.

        Args:
            model_name: Name of the model (anthropic, openai, deepseek).

        Returns:
            Model configuration dictionary.

        Raises:
            ConfigError: If model not found.
        """
        # Try exact match first
        if model_name in self._config["models"]:
            return self._config["models"][model_name]

        # Try prefix match (e.g., "deepseek-v4-flash" matches "deepseek")
        model_lower = model_name.lower()
        for key in self._config["models"]:
            if model_lower.startswith(key.lower()) or key.lower() in model_lower:
                return self._config["models"][key]

        raise ConfigError(f"Model '{model_name}' not found in configuration")
