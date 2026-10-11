"""Configuration management for Neow CLI."""

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from neow.utils.logger import logger


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
                "grep",
                "glob",
                "list_dir",
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
            "warn_at_tokens": 1000000,
            "max_tokens": 5000000,
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
        "tui": {
            "effects": "full",
            "sidebar_default": False,
            "theme": "midnight",
        },
        "agent": {
            "max_turns": 50,
            "max_tool_output_chars": 30000,
            "subagent_max_turns": 25,
            "subagent_approval": "inherit",
        },
    }

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize configuration.

        Args:
            config_path: Path to configuration file. If None, uses default location.
        """
        self._config: Dict[str, Any] = deepcopy(self.DEFAULT_CONFIG)
        # File the settings came from, and whether the user (not a cloned
        # repository) controls it: ~/.neow/config.json or an explicit --config.
        self.source_path: Optional[Path] = None
        self.user_owned = config_path is not None
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
                self.user_owned = True
            elif local_config.exists():
                config_path = local_config
            else:
                return

        self.source_path = config_path
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
    def hooks(self) -> Dict[str, Any]:
        """Hook commands by event (see neow.core.hooks)."""
        return self._config.get("hooks") or {}

    @property
    def mcp(self) -> Dict[str, Any]:
        """MCP client configuration (``servers``: name -> server entry)."""
        return self._config.get("mcp") or {}

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

    @property
    def tui(self) -> Dict[str, Any]:
        """Get validated TUI configuration."""
        cfg = self._config.get("tui", {})
        effects = cfg.get("effects", "full")
        if effects not in ("full", "subtle", "off"):
            logger.warning("Unknown tui.effects %r; falling back to 'full'", effects)
            effects = "full"
        theme = cfg.get("theme", "midnight")
        if theme not in ("midnight", "light"):
            logger.warning("Unknown tui.theme %r; falling back to 'midnight'", theme)
            theme = "midnight"
        return {
            "effects": effects,
            "sidebar_default": bool(cfg.get("sidebar_default", False)),
            "theme": theme,
        }

    @property
    def agent(self) -> Dict[str, Any]:
        """Get validated agent-loop configuration."""
        cfg = self._config.get("agent", {})

        def positive(key: str, default: int) -> int:
            value = cfg.get(key, default)
            valid = isinstance(value, int) and not isinstance(value, bool)
            if not valid or value < 1:
                logger.warning(
                    "Invalid agent.%s %r; falling back to %d", key, value, default
                )
                return default
            return value

        approval = cfg.get("subagent_approval", "inherit")
        if approval not in ("inherit", "yolo"):
            logger.warning(
                "Invalid agent.subagent_approval %r; using 'inherit'", approval
            )
            approval = "inherit"
        return {
            "max_turns": positive("max_turns", 50),
            "max_tool_output_chars": positive("max_tool_output_chars", 30000),
            "subagent_max_turns": positive("subagent_max_turns", 25),
            "subagent_approval": approval,
        }

    def resolve_model_alias(self, alias: str) -> str:
        """Resolve model alias to canonical name. Returns input if no alias found."""
        if alias in self.models:
            return alias
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
        return self.models[self.resolve_model_name(model_name)]

    def resolve_model_name(self, model_name: str) -> str:
        """Resolve a model selector to its stored entry, keeping exact names first."""
        name = self.resolve_model_alias(model_name)
        if name in self.models:
            return name

        # Preserve legacy selectors such as "DeepSeek" or "deepseek-v4-flash".
        model_lower = name.lower()
        for key in self.models:
            if model_lower.startswith(key.lower()) or key.lower() in model_lower:
                return key
        raise ConfigError(f"Model '{model_name}' not found in configuration")

    def persist_updates(self, updates: Dict[str, Any]) -> Path:
        """Atomically save explicit changes without copying resolved env secrets."""
        path = self.source_path or Path.home() / ".neow" / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        is_yaml = path.suffix in (".yml", ".yaml")
        try:
            raw = path.read_text(encoding="utf-8") if path.exists() else "{}"
            data = (yaml.safe_load(raw) if is_yaml else json.loads(raw)) or {}
            if not isinstance(data, dict):
                raise ConfigError("Configuration must be an object")
            self._merge_config(data, deepcopy(updates))
            text = (
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
                if is_yaml else json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            )
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=path.parent, delete=False
                ) as stream:
                    temporary = stream.name
                    os.chmod(temporary, 0o600)
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                if temporary and os.path.exists(temporary):
                    os.unlink(temporary)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise ConfigError("Could not save model configuration") from exc
        self._merge_config(self._config, deepcopy(updates))
        self.source_path = path
        return path

    def save_model(self, name: str, entry: Dict[str, Any]) -> Path:
        """Save one model entry, retaining all unrelated on-disk settings."""
        # Empty auth fields deliberately clear a previous credential reference.
        return self.persist_updates({"models": {name: entry}})

    def set_default_model(self, name: str) -> Path:
        """Remember an explicitly selected model for the next launch."""
        return self.persist_updates({"default_model": self.resolve_model_name(name)})

    def stored_model_entry(self, name: str) -> Dict[str, Any]:
        """Read editable fields without environment-resolved credentials."""
        entry = deepcopy(self.DEFAULT_CONFIG["models"].get(name, {}))
        if self.source_path and self.source_path.exists():
            raw = self.source_path.read_text(encoding="utf-8")
            data = (
                yaml.safe_load(raw) if self.source_path.suffix in (".yml", ".yaml")
                else json.loads(raw)
            ) or {}
            self._merge_config(entry, data.get("models", {}).get(name, {}))
        return entry
