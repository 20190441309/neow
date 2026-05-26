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

    DEFAULT_CONFIG = {
        "default_model": "deepseek-chat",
        "models": {
            "anthropic": {
                "api_key": "",
                "model": "claude-sonnet-4-6"
            },
            "openai": {
                "api_key": "",
                "model": "gpt-4o"
            },
            "deepseek": {
                "api_key": "",
                "model": "deepseek-chat"
            }
        },
        "tools": {
            "enabled": [
                "read_file",
                "write_file",
                "edit_file",
                "execute_command",
                "search_code"
            ],
            "allowed_commands": [
                "ls",
                "cat",
                "grep",
                "find",
                "python",
                "npm"
            ]
        }
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        self._config = self.DEFAULT_CONFIG.copy()
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
        """Merge override config into base config."""
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

    def get_model_config(self, model_name: str) -> Dict[str, str]:
        """Get configuration for specific model.

        Args:
            model_name: Name of the model (anthropic, openai, deepseek).

        Returns:
            Model configuration dictionary.

        Raises:
            ConfigError: If model not found.
        """
        if model_name not in self._config["models"]:
            raise ConfigError(f"Model '{model_name}' not found in configuration")
        return self._config["models"][model_name]
