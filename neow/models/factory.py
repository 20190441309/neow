"""Model client factory: provider resolution, key resolution, construction."""

from __future__ import annotations

import os
import re
from typing import Any, Mapping, Optional

from neow.core.config import ConfigError

PROVIDERS = ("openai", "openai-compatible", "anthropic", "deepseek")


def normalize_env_name(name: str) -> str:
    """Turn a model entry name into an environment-variable fragment."""

    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()


def resolve_provider(entry: Mapping[str, Any], model_name: str) -> str:
    """Resolve the provider for a configured model (explicit wins)."""

    provider = str(entry.get("provider", "") or "").strip().lower()
    if provider:
        if provider not in PROVIDERS:
            raise ConfigError(
                f"Unknown provider {provider!r} for model {model_name!r}. "
                "Available: openai, openai-compatible, anthropic, deepseek"
            )
        return provider
    lowered = model_name.lower()
    if "deepseek" in lowered:
        return "deepseek"
    if "anthropic" in lowered or "claude" in lowered:
        return "anthropic"
    if "openai" in lowered or "gpt" in lowered:
        return "openai"
    raise ConfigError(
        f'Cannot infer provider for model {model_name!r}. Set "provider" to one of: '
        "openai, openai-compatible, anthropic, deepseek"
    )


def resolve_api_key(
    entry: Mapping[str, Any],
    model_name: str,
    *,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    """Resolve an API key: config -> api_key_env -> NEOW_<NAME>_API_KEY -> legacy."""

    environment = os.environ if env is None else env
    api_key_env = entry.get("api_key_env")
    candidates = [
        entry.get("api_key"),
        environment.get(api_key_env) if api_key_env else None,
        environment.get(f"NEOW_{normalize_env_name(model_name)}_API_KEY"),
        environment.get("NEOW_DEEPSEEK_API_KEY"),
        environment.get("NEOW_ANTHROPIC_API_KEY"),
        environment.get("NEOW_OPENAI_API_KEY"),
    ]
    for candidate in candidates:
        if candidate and str(candidate).strip():
            return str(candidate).strip()
    raise ConfigError(
        f"No API key for model {model_name!r}. Set models.{model_name}.api_key, "
        f"models.{model_name}.api_key_env, or environment variable "
        f"NEOW_{normalize_env_name(model_name)}_API_KEY"
    )


__all__ = [
    "PROVIDERS",
    "normalize_env_name",
    "resolve_provider",
    "resolve_api_key",
]
