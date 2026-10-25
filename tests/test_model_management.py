"""Model persistence, credential isolation, and gateway catalog tests."""

import json
import sys
from unittest.mock import MagicMock

import pytest
import yaml

from neow.core.config import Config, ConfigError
from neow.models.factory import resolve_api_key
from neow.models.management import (
    PROVIDER_PRESETS,
    auto_discover_magpie,
    fetch_endpoint_models,
    get_preferred_magpie_model,
    get_preset_by_id,
    sync_gateway_models,
    sync_magpie,
    validate_model_entry,
)


def configured(tmp_path, data=None, suffix=".json"):
    path = tmp_path / ("config" + suffix)
    data = data or {"models": {}, "tools": {"enabled": ["read_file"]}}
    path.write_text(yaml.safe_dump(data) if suffix == ".yaml" else json.dumps(data))
    return Config(path)


@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_save_preserves_settings_without_persisting_environment(
    tmp_path, monkeypatch, suffix
):
    monkeypatch.setenv("NEOW_DEEPSEEK_API_KEY", "env-secret")
    config = configured(tmp_path, suffix=suffix)
    path = config.save_model(
        "router",
        {
            "provider": "openai-compatible",
            "api_key_env": "ROUTER_KEY",
            "model": "m",
            "base_url": "https://example.com/v1",
        },
    )
    raw = path.read_text()
    assert "env-secret" not in raw
    data = yaml.safe_load(raw)
    assert data["tools"]["enabled"] == ["read_file"]
    if sys.platform != "win32":
        # save_model chmods the temp file to 0600 before replacing the config.
        # Windows has no POSIX mode bits (chmod only toggles the read-only
        # flag), so this can only be asserted on POSIX.
        assert path.stat().st_mode & 0o777 == 0o600
    reloaded = Config(path)
    assert reloaded.models["router"]["model"] == "m"


def test_editor_reads_original_key_not_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("NEOW_OPENAI_API_KEY", "environment-secret")
    config = configured(tmp_path, {"models": {"openai": {"api_key": "original"}}})
    assert config.models["openai"]["api_key"] == "environment-secret"
    assert config.stored_model_entry("openai")["api_key"] == "original"


def test_save_failure_leaves_memory_and_file_unchanged(tmp_path, monkeypatch):
    config = configured(tmp_path)
    original = config.source_path.read_text()
    monkeypatch.setattr("neow.core.config.os.replace", MagicMock(side_effect=OSError))
    with pytest.raises(ConfigError):
        config.save_model("router", {"model": "m"})
    assert "router" not in config.models
    assert config.source_path.read_text() == original
    assert len(list(tmp_path.iterdir())) == 1


def test_custom_model_does_not_use_other_provider_secret():
    with pytest.raises(ConfigError):
        resolve_api_key({}, "custom", env={"NEOW_ANTHROPIC_API_KEY": "wrong-secret"})


def test_explicit_missing_config_is_persistence_target(tmp_path):
    path = tmp_path / "new-config.json"
    config = Config(path)
    assert config.save_model("router", {"model": "m"}) == path


def test_config_name_has_priority_over_builtin_alias(tmp_path):
    config = configured(tmp_path, {"models": {"gpt": {"model": "my-model"}}})
    assert config.resolve_model_alias("gpt") == "gpt"


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "https://key@example.com", "https://example.com?key=secret"],
)
def test_model_url_validation_rejects_credentials(url):
    with pytest.raises(ConfigError) as error:
        validate_model_entry(
            "custom",
            {
                "provider": "openai-compatible",
                "model": "m",
                "api_key": "secret",
                "base_url": url,
            },
        )
    assert "secret" not in str(error.value)


def test_magpie_sync_uses_routed_ids_and_metadata(tmp_path, monkeypatch):
    config = configured(tmp_path)
    response = MagicMock()
    response.json.return_value = {
        "data": [
            {"id": "vendor/model", "display_name": "Model", "context_window": 100000},
            {"id": "vendor/another"},
            {"no_id": "ignored"},
        ]
    }
    get = MagicMock(return_value=response)
    monkeypatch.setattr("neow.models.management.requests.get", get)
    assert sync_magpie(config) == 2
    entry = config.models["magpie/vendor/model"]
    assert entry["model"] == "vendor/model"
    assert entry["context_window"] == 100000
    assert entry["display_name"] == "Model"
    assert entry["provider"] == "openai-compatible"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer magpie"}
    assert sync_magpie(config) == 2
    assert len([k for k in config.models if k.startswith("magpie/")]) == 2


def test_magpie_remote_key_reference_is_not_saved(tmp_path, monkeypatch):
    monkeypatch.setenv("GW_KEY", "gateway-secret")
    config = configured(
        tmp_path,
        {"magpie": {"base_url": "https://gw.example/v1", "api_key_env": "GW_KEY"}},
    )
    response = MagicMock()
    response.json.return_value = {"data": [{"id": "vendor/m"}]}
    get = MagicMock(return_value=response)
    monkeypatch.setattr("neow.models.management.requests.get", get)
    sync_magpie(config)
    assert "gateway-secret" not in config.source_path.read_text()
    assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer gateway-secret"


def test_invalid_catalog_does_not_write(tmp_path, monkeypatch):
    config = configured(tmp_path)
    original = config.source_path.read_text()
    response = MagicMock()
    response.json.return_value = {"data": "not a list"}
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: response)
    with pytest.raises(ConfigError):
        sync_magpie(config)
    assert config.source_path.read_text() == original


def test_magpie_sync_prunes_deleted_models(tmp_path, monkeypatch):
    config = configured(tmp_path)
    res1 = MagicMock()
    res1.json.return_value = {
        "data": [
            {"id": "xiaomi/mimo"},
            {"id": "deepseek/chat"},
        ]
    }
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: res1)
    assert sync_magpie(config) == 2
    assert "magpie/xiaomi/mimo" in config.models
    assert "magpie/deepseek/chat" in config.models

    # Turn 2: xiaomi removed from upstream gateway
    res2 = MagicMock()
    res2.json.return_value = {
        "data": [
            {"id": "deepseek/chat"},
        ]
    }
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: res2)
    assert sync_magpie(config) == 1
    assert "magpie/xiaomi/mimo" not in config.models
    assert "magpie/deepseek/chat" in config.models

    # Verify persisted on disk as well
    reloaded = Config(config.source_path)
    assert "magpie/xiaomi/mimo" not in reloaded.models
    assert "magpie/deepseek/chat" in reloaded.models


def test_provider_presets_and_fetch_endpoint_models(monkeypatch):
    assert len(PROVIDER_PRESETS) >= 10
    sf = get_preset_by_id("siliconflow")
    assert sf is not None
    assert sf["provider"] == "openai-compatible"
    assert "siliconflow.cn" in sf["base_url"]

    ollama = get_preset_by_id("ollama")
    assert ollama is not None
    assert "11434" in ollama["base_url"]

    res = MagicMock()
    res.json.return_value = {"data": [{"id": "qwen2.5-coder:7b"}, {"id": "llama3.2"}]}
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: res)
    models = fetch_endpoint_models("http://127.0.0.1:11434/v1")
    assert [m["id"] for m in models] == ["qwen2.5-coder:7b", "llama3.2"]


def test_sync_custom_gateway_and_delete_model(tmp_path, monkeypatch):
    config = configured(tmp_path)
    res = MagicMock()
    res.json.return_value = {"data": [{"id": "deepseek-ai/DeepSeek-V3"}]}
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: res)
    count = sync_gateway_models(
        config,
        base_url="https://api.siliconflow.cn/v1",
        api_key="sf-key",
        prefix="sf",
    )
    assert count == 1
    assert "sf/deepseek-ai/DeepSeek-V3" in config.models
    assert config.models["sf/deepseek-ai/DeepSeek-V3"]["source"] == "gateway"

    # Delete model from config and verify persistence
    config.delete_model("sf/deepseek-ai/DeepSeek-V3")
    assert "sf/deepseek-ai/DeepSeek-V3" not in config.models
    reloaded = Config(config.source_path)
    assert "sf/deepseek-ai/DeepSeek-V3" not in reloaded.models


def test_auto_discover_magpie_reads_applied_json(tmp_path, monkeypatch):
    config = configured(tmp_path)
    fake_home = tmp_path / "fake_home"
    magpie_dir = fake_home / ".config" / "magpie"
    magpie_dir.mkdir(parents=True)
    (magpie_dir / "applied.json").write_text(
        json.dumps(
            {
                "claude": {
                    "at": "2026-10-06T18:00:00+08:00",
                    "fields": {"model": "cursor/auto"},
                },
                "codex": {
                    "at": "2026-10-23T19:00:00+08:00",
                    "fields": {"model": "gpt20x/gpt-6-astra"},
                },
            }
        ),
        encoding="utf-8",
    )

    res = MagicMock()
    res.json.return_value = {
        "data": [
            {"id": "cursor/auto"},
            {"id": "gpt20x/gpt-6-astra"},
        ]
    }
    monkeypatch.setattr("neow.models.management.requests.get", lambda *a, **k: res)

    discovered = auto_discover_magpie(config, home=fake_home)
    assert discovered == "magpie/gpt20x/gpt-6-astra"
    assert config.default_model == "magpie/gpt20x/gpt-6-astra"
    assert get_preferred_magpie_model(config, home=fake_home) == (
        "magpie/gpt20x/gpt-6-astra"
    )
