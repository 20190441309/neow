"""任意服务商（BYOK）测试（实现计划任务 1 起）。"""

import json
from types import SimpleNamespace

import pytest

from neow.core.config import ConfigError
from neow.models.anthropic import AnthropicClient
from neow.models.base import validate_openai_compatible
from neow.models.deepseek import DeepSeekClient
from neow.models.factory import (
    PROVIDERS,
    create_model_client,
    normalize_env_name,
    resolve_api_key,
    resolve_provider,
)
from neow.models.openai import OpenAIClient


def _status_error(status: int) -> Exception:
    class _Err(Exception):
        status_code = status

    return _Err("boom")


class _FakeModels:
    def __init__(self, exc=None):
        self.exc = exc
        self.calls = 0

    def list(self):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return []


class _FakeOpenAI:
    def __init__(self, exc=None):
        self.models = _FakeModels(exc)


def test_validate_openai_compatible_ok():
    assert validate_openai_compatible(_FakeOpenAI(), "X") is True


@pytest.mark.parametrize("status", [404, 405, 501])
def test_validate_openai_compatible_missing_models_endpoint(status):
    assert validate_openai_compatible(_FakeOpenAI(_status_error(status)), "X") is True


@pytest.mark.parametrize("status", [401, 403, 500])
def test_validate_openai_compatible_failures(status):
    assert validate_openai_compatible(_FakeOpenAI(_status_error(status)), "X") is False


def test_validate_skip_returns_true_without_call():
    client = OpenAIClient(
        api_key="k", model="m", base_url="http://x/v1", validate=False
    )
    fake = _FakeOpenAI()
    client.client = fake
    assert client.validate_connection() is True
    assert fake.models.calls == 0


def test_openai_base_url_passthrough(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("openai.OpenAI", fake_openai)
    OpenAIClient(api_key="k", model="m", base_url="http://x/v1")
    assert captured["base_url"] == "http://x/v1"


def test_deepseek_default_and_override_base_url(monkeypatch):
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("openai.OpenAI", fake_openai)
    DeepSeekClient(api_key="k", model="m")
    assert captured["base_url"] == "https://api.deepseek.com"
    DeepSeekClient(api_key="k", model="m", base_url="http://gw/v1")
    assert captured["base_url"] == "http://gw/v1"


def test_anthropic_base_url_passthrough(monkeypatch):
    captured = {}

    def fake_anthropic(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr("anthropic.Anthropic", fake_anthropic)
    AnthropicClient(api_key="k", model="m", base_url="http://gw")
    assert captured["base_url"] == "http://gw"


def test_normalize_env_name():
    assert normalize_env_name("my-router.v2") == "MY_ROUTER_V2"
    assert normalize_env_name("openrouter") == "OPENROUTER"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_resolve_explicit_provider(provider):
    assert (
        resolve_provider({"provider": provider, "model": "m"}, "whatever") == provider
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("deepseek", "deepseek"),
        ("claude-sonnet", "anthropic"),
        ("gpt-4o", "openai"),
        ("my-deepseek-proxy", "deepseek"),
    ],
)
def test_resolve_heuristic_backward_compat(name, expected):
    assert resolve_provider({"model": "m"}, name) == expected


def test_resolve_unknown_provider_raises():
    with pytest.raises(ConfigError) as exc:
        resolve_provider({"provider": "foo", "model": "m"}, "x")
    assert "openai-compatible" in str(exc.value)


def test_resolve_uninferable_name_raises():
    with pytest.raises(ConfigError) as exc:
        resolve_provider({}, "mystery")
    assert "provider" in str(exc.value)


def test_error_messages_never_include_key():
    with pytest.raises(ConfigError) as exc:
        resolve_provider({"provider": "foo", "api_key": "sk-super-secret"}, "x")
    assert "sk-super-secret" not in str(exc.value)


def test_api_key_prefers_config_value():
    entry = {"api_key": "direct", "api_key_env": "OTHER"}
    assert resolve_api_key(entry, "x", env={"OTHER": "env"}) == "direct"


def test_api_key_env_reference():
    assert resolve_api_key({"api_key_env": "MY_KEY"}, "x", env={"MY_KEY": "s"}) == "s"


def test_api_key_generic_convention():
    assert (
        resolve_api_key({}, "my-router", env={"NEOW_MY_ROUTER_API_KEY": "gen"}) == "gen"
    )


def test_api_key_legacy_env():
    assert (
        resolve_api_key({}, "anthropic", env={"NEOW_ANTHROPIC_API_KEY": "legacy"})
        == "legacy"
    )


def test_api_key_missing_raises_with_hint():
    with pytest.raises(ConfigError) as exc:
        resolve_api_key({}, "my-router", env={})
    message = str(exc.value)
    assert "api_key_env" in message and "NEOW_MY_ROUTER_API_KEY" in message


def _config(tmp_path, models, default="deepseek"):
    from neow.core.config import Config

    path = tmp_path / ".neow.json"
    path.write_text(json.dumps({"default_model": default, "models": models}))
    return Config(path)


def _fake_clients(monkeypatch, used):
    def make(name):
        class Fake:
            def __init__(self, **kwargs):
                used[name] = kwargs

        return Fake

    monkeypatch.setattr("neow.models.factory.OpenAIClient", make("openai"))
    monkeypatch.setattr("neow.models.factory.AnthropicClient", make("anthropic"))
    monkeypatch.setattr("neow.models.factory.DeepSeekClient", make("deepseek"))


def test_create_client_provider_mapping(monkeypatch, tmp_path):
    used = {}
    _fake_clients(monkeypatch, used)
    config = _config(
        tmp_path,
        {
            "a": {"provider": "openai-compatible", "api_key": "k", "model": "m"},
            "b": {"provider": "anthropic", "api_key": "k", "model": "m"},
            "c": {"provider": "deepseek", "api_key": "k", "model": "m"},
        },
    )
    create_model_client(config, "a")
    create_model_client(config, "b")
    create_model_client(config, "c")
    assert set(used) == {"openai", "anthropic", "deepseek"}


def test_create_client_passes_base_url_and_validate(monkeypatch, tmp_path):
    used = {}
    _fake_clients(monkeypatch, used)
    config = _config(
        tmp_path,
        {
            "ollama": {
                "provider": "openai-compatible",
                "api_key": "ollama",
                "model": "qwen2.5:14b",
                "base_url": "http://localhost:11434/v1",
                "validate": "skip",
            }
        },
    )
    create_model_client(config, "ollama")
    assert used["openai"] == {
        "api_key": "ollama",
        "model": "qwen2.5:14b",
        "base_url": "http://localhost:11434/v1",
        "validate": False,
    }


def test_legacy_config_behavior_unchanged(monkeypatch, tmp_path):
    used = {}
    _fake_clients(monkeypatch, used)
    config = _config(
        tmp_path, {"deepseek": {"api_key": "k", "model": "deepseek-v4-flash"}}
    )
    create_model_client(config, "deepseek")
    assert used["deepseek"] == {
        "api_key": "k",
        "model": "deepseek-v4-flash",
        "base_url": None,
        "validate": True,
    }


def test_missing_model_field_raises(monkeypatch, tmp_path):
    _fake_clients(monkeypatch, {})
    config = _config(tmp_path, {"x": {"provider": "openai", "api_key": "k"}})
    with pytest.raises(ConfigError):
        create_model_client(config, "x")


def test_invalid_validate_value_raises(monkeypatch, tmp_path):
    _fake_clients(monkeypatch, {})
    config = _config(
        tmp_path,
        {
            "x": {
                "provider": "openai",
                "api_key": "k",
                "model": "m",
                "validate": "maybe",
            }
        },
    )
    with pytest.raises(ConfigError) as exc:
        create_model_client(config, "x")
    assert "validate" in str(exc.value)


def test_main_reexports_create_model_client():
    from neow.cli.main import create_model_client as from_main
    from neow.models.factory import create_model_client as from_factory

    assert from_main is from_factory
