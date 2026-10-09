"""Request retries (plan task 1.4).

The OpenAI and Anthropic SDKs already retry 408/409/429/5xx and
connection errors (2 retries, exponential backoff, honouring
retry-after), so neow does not add its own layer; it only lets each
model entry tune ``max_retries``.
"""

import json
from unittest.mock import patch

import pytest

from neow.core.config import Config, ConfigError
from neow.models.factory import create_model_client

PROVIDERS = [
    ("anthropic", "claude-sonnet-4-6", "neow.models.anthropic.anthropic.Anthropic"),
    ("openai", "gpt-4o", "neow.models.openai.openai.OpenAI"),
    ("deepseek", "deepseek-chat", "neow.models.deepseek.openai.OpenAI"),
]


def _config(tmp_path, entry):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"models": {"m": {"api_key": "k", **entry}}}))
    return Config(path)


@pytest.mark.parametrize("provider, model, sdk_path", PROVIDERS)
def test_max_retries_reaches_the_sdk(tmp_path, provider, model, sdk_path):
    config = _config(tmp_path, {"provider": provider, "model": model, "max_retries": 5})
    with patch(sdk_path) as sdk:
        create_model_client(config, "m")
    assert sdk.call_args.kwargs["max_retries"] == 5


@pytest.mark.parametrize("provider, model, sdk_path", PROVIDERS)
def test_sdk_default_retries_kept_when_unset(tmp_path, provider, model, sdk_path):
    config = _config(tmp_path, {"provider": provider, "model": model})
    with patch(sdk_path) as sdk:
        create_model_client(config, "m")
    assert "max_retries" not in sdk.call_args.kwargs


def test_zero_retries_allowed_and_negative_rejected(tmp_path):
    zero = _config(
        tmp_path, {"provider": "openai", "model": "gpt-4o", "max_retries": 0}
    )
    with patch("neow.models.openai.openai.OpenAI") as sdk:
        create_model_client(zero, "m")
    assert sdk.call_args.kwargs["max_retries"] == 0

    negative = _config(
        tmp_path, {"provider": "openai", "model": "gpt-4o", "max_retries": -1}
    )
    with pytest.raises(ConfigError, match="max_retries"):
        create_model_client(negative, "m")
