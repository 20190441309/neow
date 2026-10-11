"""BYOK model configuration and Magpie gateway catalog integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import requests

from neow.core.config import Config, ConfigError
from neow.models.factory import resolve_api_key, resolve_provider

MAGPIE_URL = "http://127.0.0.1:3425/v1"


def validate_model_entry(name: str, entry: dict[str, Any]) -> None:
    """Check fields without sending a key to an endpoint or echoing it."""
    if not name.strip() or any(c.isspace() for c in name):
        raise ConfigError("Model name must be nonempty and contain no spaces")
    if not isinstance(entry.get("model"), str) or not entry["model"].strip():
        raise ConfigError("Model ID is required")
    provider = resolve_provider(entry, name)
    endpoint = entry.get("base_url")
    if endpoint:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ConfigError("API address must be an http:// or https:// URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ConfigError(
                "API address must not contain credentials or query parameters"
            )
    elif provider == "openai-compatible":
        raise ConfigError("API address is required for an OpenAI-compatible provider")
    resolve_api_key(entry, name)


def sync_magpie(config: Config) -> int:
    """Import routed IDs via /models; never read upstream provider credentials."""
    settings = config._config.get("magpie", {})
    endpoint = str(settings.get("base_url") or MAGPIE_URL).rstrip("/")
    auth = {
        "api_key": settings.get("api_key", ""),
        "api_key_env": settings.get("api_key_env", ""),
    }
    # The local gateway accepts a placeholder; remote gateways require a key.
    if not auth["api_key"] and not auth["api_key_env"]:
        if urlsplit(endpoint).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ConfigError("Set magpie.api_key_env for a remote gateway")
        auth["api_key"] = "magpie"
    probe = {
        "provider": "openai-compatible",
        "model": "catalog",
        "base_url": endpoint,
        **auth,
    }
    validate_model_entry("magpie", probe)
    key = resolve_api_key(auth, "magpie")
    try:
        response = requests.get(
            endpoint + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=5
        )
        response.raise_for_status()
        catalog = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ConfigError(
            "Could not load Magpie models; check gateway address and key"
        ) from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise ConfigError("Magpie returned an invalid model catalog")
    entries = {}
    for model in catalog["data"]:
        if not isinstance(model, dict) or not isinstance(model.get("id"), str):
            continue
        model_id = model["id"].strip()
        if not model_id or any(c.isspace() for c in model_id):
            continue
        name = "magpie/" + model_id
        existing = config.models.get(name, {})
        if existing and existing.get("source") != "magpie":
            continue
        entry = {
            "provider": "openai-compatible",
            "model": model_id,
            "base_url": endpoint,
            "source": "magpie",
            "display_name": model.get("magpie_label")
            or model.get("display_name")
            or model_id,
            **auth,
        }
        context = model.get("context_window") or model.get("context_length")
        if isinstance(context, int) and not isinstance(context, bool) and context > 0:
            entry["context_window"] = context
        entries[name] = entry
    if not entries:
        raise ConfigError("Magpie has no available models")
    config.persist_updates(
        {"models": entries, "magpie": {"enabled": True, "base_url": endpoint}}
    )
    return len(entries)
