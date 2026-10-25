"""BYOK model configuration, provider presets, and gateway catalog integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlsplit

import requests

from neow.core.config import Config, ConfigError
from neow.models.factory import resolve_api_key, resolve_provider

MAGPIE_URL = "http://127.0.0.1:3425/v1"

PROVIDER_PRESETS: list[dict[str, str]] = [
    {
        "id": "custom",
        "label": "自定义配置 (Custom BYOK)",
        "provider": "openai-compatible",
        "base_url": "",
        "default_model": "",
        "api_key_env": "",
        "default_key": "",
        "default_name": "",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek 官方 (deepseek-chat / reasoner)",
        "provider": "deepseek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_key": "",
        "default_name": "deepseek",
    },
    {
        "id": "openai",
        "label": "OpenAI 官方 (gpt-4o / o3-mini)",
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "default_key": "",
        "default_name": "openai",
    },
    {
        "id": "anthropic",
        "label": "Anthropic 官方 (claude-sonnet-4-6)",
        "provider": "anthropic",
        "base_url": "https://api.anthropic.com",
        "default_model": "claude-sonnet-4-6",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_key": "",
        "default_name": "anthropic",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter 聚合网关 (openrouter.ai)",
        "provider": "openai-compatible",
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "anthropic/claude-3.7-sonnet",
        "api_key_env": "OPENROUTER_API_KEY",
        "default_key": "",
        "default_name": "openrouter",
    },
    {
        "id": "siliconflow",
        "label": "硅基流动 SiliconFlow (api.siliconflow.cn)",
        "provider": "openai-compatible",
        "base_url": "https://api.siliconflow.cn/v1",
        "default_model": "deepseek-ai/DeepSeek-V3",
        "api_key_env": "SILICONFLOW_API_KEY",
        "default_key": "",
        "default_name": "siliconflow",
    },
    {
        "id": "dashscope",
        "label": "阿里云百炼 DashScope (Qwen 系列)",
        "provider": "openai-compatible",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-max",
        "api_key_env": "DASHSCOPE_API_KEY",
        "default_key": "",
        "default_name": "dashscope",
    },
    {
        "id": "moonshot",
        "label": "Kimi / Moonshot (api.moonshot.cn)",
        "provider": "openai-compatible",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k2-0711-preview",
        "api_key_env": "MOONSHOT_API_KEY",
        "default_key": "",
        "default_name": "kimi",
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM BigModel (open.bigmodel.cn)",
        "provider": "openai-compatible",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-plus",
        "api_key_env": "ZHIPUAI_API_KEY",
        "default_key": "",
        "default_name": "glm",
    },
    {
        "id": "ollama",
        "label": "Ollama 本地模型 (127.0.0.1:11434)",
        "provider": "openai-compatible",
        "base_url": "http://127.0.0.1:11434/v1",
        "default_model": "qwen2.5-coder:7b",
        "api_key_env": "",
        "default_key": "ollama",
        "default_name": "ollama",
    },
    {
        "id": "lmstudio",
        "label": "LM Studio 本地服务 (127.0.0.1:1234)",
        "provider": "openai-compatible",
        "base_url": "http://127.0.0.1:1234/v1",
        "default_model": "local-model",
        "api_key_env": "",
        "default_key": "lm-studio",
        "default_name": "lmstudio",
    },
    {
        "id": "magpie",
        "label": "本地 Magpie 网关 (127.0.0.1:3425)",
        "provider": "openai-compatible",
        "base_url": MAGPIE_URL,
        "default_model": "auto",
        "api_key_env": "",
        "default_key": "magpie",
        "default_name": "magpie",
    },
]


def get_preset_by_id(preset_id: str) -> dict[str, str] | None:
    """Return a preset dictionary by its ID, or None if not found."""
    for preset in PROVIDER_PRESETS:
        if preset["id"] == preset_id:
            return dict(preset)
    return None


def is_local_endpoint(url: str) -> bool:
    """Check if an HTTP(S) URL points to localhost / loopback."""
    if not url:
        return False
    try:
        parsed = urlsplit(url.strip())
        return parsed.hostname in ("localhost", "127.0.0.1", "::1")
    except Exception:
        return False


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


def fetch_endpoint_models(
    base_url: str,
    api_key: str = "",
    api_key_env: str = "",
) -> list[dict[str, Any]]:
    """Query an OpenAI-compatible /models endpoint and return model descriptors."""
    endpoint = (base_url or "").strip().rstrip("/")
    if not endpoint:
        raise ConfigError("请先填写 API 地址 (例如 https://.../v1)")
    parsed = urlsplit(endpoint)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError("API address must be an http:// or https:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigError(
            "API address must not contain credentials or query parameters"
        )
    auth = {"api_key": api_key.strip(), "api_key_env": api_key_env.strip()}
    if not auth["api_key"] and not auth["api_key_env"]:
        if is_local_endpoint(endpoint):
            auth["api_key"] = "local"
        else:
            raise ConfigError("远程网关拉取模型需要提供 API Key 或环境变量")
    key = resolve_api_key(auth, "gateway")
    try:
        response = requests.get(
            endpoint + "/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=5,
        )
        response.raise_for_status()
        catalog = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ConfigError("无法从该地址拉取模型列表，请检查 API 地址和 Key") from exc
    if not isinstance(catalog, dict) or not isinstance(catalog.get("data"), list):
        raise ConfigError("服务端返回的 /models 格式无效")
    results: list[dict[str, Any]] = []
    for item in catalog["data"]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        model_id = item["id"].strip()
        if not model_id or any(c.isspace() for c in model_id):
            continue
        results.append(item)
    if not results:
        raise ConfigError("该网关未返回任何可用模型")
    return results


def sync_gateway_models(
    config: Config,
    *,
    base_url: str = "",
    api_key: str = "",
    api_key_env: str = "",
    prefix: str = "magpie",
) -> int:
    """Import routed model IDs from any OpenAI-compatible /models gateway."""
    settings = config._config.get("magpie", {})
    endpoint = str(base_url or settings.get("base_url") or MAGPIE_URL).rstrip("/")
    auth = {
        "api_key": api_key or settings.get("api_key", ""),
        "api_key_env": api_key_env or settings.get("api_key_env", ""),
    }
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
    clean_prefix = (prefix or "magpie").strip().strip("/")
    validate_model_entry(clean_prefix, probe)
    key = resolve_api_key(auth, clean_prefix)
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
        name = f"{clean_prefix}/{model_id}"
        existing = config.models.get(name, {})
        if existing and existing.get("source") not in ("magpie", "gateway", None):
            continue
        entry = {
            "provider": "openai-compatible",
            "model": model_id,
            "base_url": endpoint,
            "source": "magpie" if clean_prefix == "magpie" else "gateway",
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

    # Prune models previously imported with the same prefix/source that no longer exist
    stale_keys = []
    for name, existing_entry in config.models.items():
        if name.startswith(f"{clean_prefix}/") or (
            clean_prefix == "magpie"
            and isinstance(existing_entry, dict)
            and existing_entry.get("source") == "magpie"
        ):
            if name not in entries:
                stale_keys.append(name)

    remove_keys = {"models": stale_keys} if stale_keys else None
    gw_meta: dict[str, Any] = {"enabled": True, "base_url": endpoint}
    if auth.get("api_key_env"):
        gw_meta["api_key_env"] = auth["api_key_env"]
    config.persist_updates(
        {"models": entries, "magpie": gw_meta},
        remove_keys=remove_keys,
    )
    return len(entries)


def sync_magpie(config: Config) -> int:
    """Import routed IDs via /models; never read upstream provider credentials."""
    return sync_gateway_models(config)


def get_preferred_magpie_model(
    config: Config, home: Optional[Path] = None
) -> Optional[str]:
    """Read ~/.config/magpie/applied.json to find the most recently picked model."""
    base_home = home or Path.home()
    applied_path = base_home / ".config" / "magpie" / "applied.json"
    if applied_path.exists():
        try:
            data = json.loads(applied_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                candidates: list[tuple[str, str]] = []
                for agent_entry in data.values():
                    if not isinstance(agent_entry, dict):
                        continue
                    at = str(agent_entry.get("at") or "")
                    fields = agent_entry.get("fields")
                    if isinstance(fields, dict):
                        raw_model = str(fields.get("model") or "").strip()
                        if raw_model:
                            candidates.append((at, raw_model))
                # Most recently applied in Magpie UI first
                candidates.sort(key=lambda item: item[0], reverse=True)
                for _, raw_model in candidates:
                    clean_id = (
                        raw_model[len("magpie/") :]
                        if raw_model.startswith("magpie/")
                        else raw_model
                    )
                    full_name = f"magpie/{clean_id}"
                    if full_name in config.models:
                        return full_name
        except Exception:
            pass

    for name in config.models:
        if name.startswith("magpie/"):
            return name
    return None


def auto_discover_magpie(config: Config, home: Optional[Path] = None) -> Optional[str]:
    """Auto-discover local Magpie on startup if ~/.config/magpie is present."""
    base_home = home or Path.home()
    magpie_dir = base_home / ".config" / "magpie"
    magpie_cfg = config._config.get("magpie", {})
    if not magpie_dir.exists() and not magpie_cfg.get("enabled"):
        return None
    try:
        sync_magpie(config)
        preferred = get_preferred_magpie_model(config, home=base_home)
        if preferred:
            config.set_default_model(preferred)
            return preferred
    except Exception:
        return None
    return None
