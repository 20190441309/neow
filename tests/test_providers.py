"""任意服务商（BYOK）测试（实现计划任务 1 起）。"""

from types import SimpleNamespace

import pytest

from neow.models.anthropic import AnthropicClient
from neow.models.base import validate_openai_compatible
from neow.models.deepseek import DeepSeekClient
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
