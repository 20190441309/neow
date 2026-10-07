# Neow 任意服务商（BYOK）实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 支持任意 OpenAI 兼容服务商（含自定义 `base_url`）与三家内置客户端的 base_url 覆盖；密钥支持配置直填/环境变量引用/通用约定；旧配置行为零回归。

**架构：** 新建 `neow/models/factory.py`（provider 解析、密钥解析、客户端构造，原 `neow/cli/main.py:create_model_client` 迁入并 re-export）；三个客户端构造函数扩为 `(api_key, model, base_url=None, validate=True)`；`neow/models/base.py` 提供兼容端点校验助手；REPL `/model` 与 TUI ModelPicker 增加 provider/base_url 展示；README 与示例更新。

**技术栈：** Python 3.10+、既有 openai/anthropic SDK、pytest + monkeypatch（全部测试离线）。无新依赖。

**规格：** `docs/design/2026-10-07-neow-any-provider-design.md`（契约副本 `docs/superpowers/specs/`）。执行者必须两份材料都读；取值以规格为准。

**工作目录与命令约定：** 仓库 `/home/neow`；虚拟环境 `/home/neow/.venv`；pytest 统一用 `PATH="/home/neow/.venv/bin:$PATH" .venv/bin/python -m pytest ...`。

## 全局约束

- **向后兼容**：无 `provider` 字段时名字启发式必须与现状逐项一致（`neow/cli/main.py` 迁移前逻辑）。
- **公开导入路径**：`from neow.cli.main import create_model_client` 必须继续可用（re-export）。
- **密钥纪律**：密钥只进内存；不进日志、不回显、不出现在错误文案。
- 校验降级只放宽 HTTP 404/405/501；401/403/其它错误必须判失败。
- `validate: skip` 时不发任何网络请求。
- 无新运行时依赖；错误统一用 `ConfigError`（`neow.core.config`）。
- 仓库级 `.flake8`（max-line-length 88 / E203）对新增与改动文件保持 clean；新文件 black 格式化。
- 每个任务独立 commit；TDD 顺序：写失败测试 → 看它失败 → 实现 → 看它通过 → 提交。
- 现有 538 个测试保持全绿。

## 审查重点（Review Focus）

1. **密钥泄漏**：任何错误/日志/展示路径不得出现密钥值；缺失密钥的错误只允许出现环境变量名。→ 任务 2 `test_error_messages_never_include_key`、任务 5 `test_end_to_end_offline`。
2. **旧配置回归**：无新字段的 deepseek/anthropic/openai 条目 + 旧环境变量行为不变。→ 任务 2 `test_resolve_heuristic_backward_compat`、任务 3 `test_legacy_config_behavior_unchanged`。
3. **降级误判**：只有 404/405/501 放行，401/403/500 必须失败。→ 任务 1 参数化测试。
4. **base_url 透传**：三家 SDK 构造收到的 base_url 正确，DeepSeek 默认值不变，空值不传多余参数。→ 任务 1 的 `test_*_base_url*`。
5. **skip 零请求**：`validate=False` 时 `models.list` / `messages.create` 都不被调用。→ 任务 1 `test_validate_skip_returns_true_without_call`。

---

## 文件结构

**创建：**

| 文件 | 职责 |
|------|------|
| `neow/models/factory.py` | `PROVIDERS`、`normalize_env_name`、`resolve_provider`、`resolve_api_key`、`client_for`、`create_model_client`、`describe_models` |
| `tests/test_providers.py` | 本计划全部单测 |

**修改：**

| 文件 | 改动 |
|------|------|
| `neow/models/base.py` | `validate_openai_compatible()`；`BaseModelClient` 增 `base_url`/`validate_enabled` 默认属性 |
| `neow/models/openai.py` | 构造函数加 `base_url`/`validate`；`validate_connection` 接助手 + skip |
| `neow/models/deepseek.py` | 同上；默认 base_url 保持 `https://api.deepseek.com` |
| `neow/models/anthropic.py` | 构造函数加 `base_url`/`validate`；`validate_connection` 支持 skip |
| `neow/cli/main.py` | 删除本地 `create_model_client`，改为 re-export；清理不再使用的 client 导入 |
| `neow/cli/repl.py` | `/model` 无参输出改用 `describe_models()`（仅展示） |
| `neow/tui/screens/model_picker.py` | 可选 `labels: dict[str, str] \| None` |
| `neow/tui/screens/chat.py` | ModelPicker 标签带 provider（仅展示） |
| `.neow.json.example` | 增加 openai-compatible 示例 |
| `README.md` | "任意 OpenAI 兼容服务商" 一节（OpenRouter/Ollama/vLLM、密钥约定、validate、prices） |

---

### 任务 1：客户端 base_url/validate + 共享校验助手

**文件：**
- 修改：`neow/models/base.py`、`neow/models/openai.py`、`neow/models/deepseek.py`、`neow/models/anthropic.py`
- 创建：`tests/test_providers.py`

- [ ] **步骤 1：编写失败的测试 `tests/test_providers.py`**

```python
"""任意服务商（BYOK）测试。"""

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
```

- [ ] **步骤 2：运行确认失败**

运行：`... -m pytest tests/test_providers.py -q`
预期：FAIL（`ImportError: cannot import name 'validate_openai_compatible'` 或构造函数 TypeError）

- [ ] **步骤 3：实现**

`neow/models/base.py`：

```python
def validate_openai_compatible(client: Any, label: str) -> bool:
    """Validate an OpenAI-compatible endpoint; tolerate missing /models."""
    try:
        client.models.list()
        return True
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in (404, 405, 501):
            logger.debug(f"{label}: endpoint has no /models (HTTP {status}); assuming compatible")
            return True
        logger.error(f"{label} connection validation failed: {exc}")
        return False
```

`BaseModelClient.__init__` 追加：`self.base_url: Optional[str] = None`、`self.validate_enabled: bool = True`。

`OpenAIClient.__init__(self, api_key, model="gpt-4o", base_url=None, validate=True)`：
- `super().__init__(api_key, model)`；`self.base_url = base_url`；`self.validate_enabled = validate`
- `kwargs = {"api_key": api_key}`；`if base_url: kwargs["base_url"] = base_url`；`self.client = openai.OpenAI(**kwargs)`
- `validate_connection()`：`if not self.validate_enabled: return True`；`return validate_openai_compatible(self.client, "OpenAI")`

`DeepSeekClient`：同上，构造 `openai.OpenAI(api_key=api_key, base_url=base_url or "https://api.deepseek.com")`；`validate_connection` 用 `validate_openai_compatible(self.client, "DeepSeek")`。

`AnthropicClient`：签名扩展；`validate_connection()` 开头 `if not self.validate_enabled: return True`；其余探测逻辑不变。

- [ ] **步骤 4：运行确认通过 + 回归**

运行：`... -m pytest tests/test_providers.py tests/test_models.py -q` → PASS
运行：`... -m pytest -q` → 538 + 新增全绿

- [ ] **步骤 5：Commit**

```bash
git add neow/models/base.py neow/models/openai.py neow/models/deepseek.py neow/models/anthropic.py tests/test_providers.py
git commit -m "feat(models): client base_url, validate flag and compatible-endpoint probe"
```

---

### 任务 2：factory 纯函数（provider/密钥解析）

**文件：**
- 创建：`neow/models/factory.py`（纯函数部分）
- 修改：`tests/test_providers.py`

- [ ] **步骤 1：追加失败测试**

```python
from neow.core.config import ConfigError
from neow.models.factory import (
    PROVIDERS,
    normalize_env_name,
    resolve_api_key,
    resolve_provider,
)


def test_normalize_env_name():
    assert normalize_env_name("my-router.v2") == "MY_ROUTER_V2"
    assert normalize_env_name("openrouter") == "OPENROUTER"


@pytest.mark.parametrize("provider", PROVIDERS)
def test_resolve_explicit_provider(provider):
    assert resolve_provider({"provider": provider, "model": "m"}, "whatever") == provider


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
```

- [ ] **步骤 2：运行确认失败** → `ModuleNotFoundError: neow.models.factory`

- [ ] **步骤 3：实现 `neow/models/factory.py`（纯函数）**

```python
PROVIDERS = ("openai", "openai-compatible", "anthropic", "deepseek")

def normalize_env_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()

def resolve_provider(entry: Mapping[str, Any], model_name: str) -> str:
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
        f"Cannot infer provider for model {model_name!r}. Set \"provider\" to one of: "
        "openai, openai-compatible, anthropic, deepseek"
    )

def resolve_api_key(
    entry: Mapping[str, Any],
    model_name: str,
    *,
    env: Mapping[str, str] | None = None,
) -> str:
    environment = os.environ if env is None else env
    candidates = [
        entry.get("api_key"),
        environment.get(entry.get("api_key_env", "")) if entry.get("api_key_env") else None,
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
```

- [ ] **步骤 4：运行确认通过** → 本任务测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add neow/models/factory.py tests/test_providers.py
git commit -m "feat(models): provider and api-key resolution"
```

---

### 任务 3：`create_model_client` 迁移 + main 接线

**文件：**
- 修改：`neow/models/factory.py`、`neow/cli/main.py`
- 修改：`tests/test_providers.py`

- [ ] **步骤 1：追加失败测试**

```python
import json

from neow.models.factory import create_model_client


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
        {"x": {"provider": "openai", "api_key": "k", "model": "m", "validate": "maybe"}},
    )
    with pytest.raises(ConfigError) as exc:
        create_model_client(config, "x")
    assert "validate" in str(exc.value)


def test_main_reexports_create_model_client():
    from neow.cli.main import create_model_client as from_main
    from neow.models.factory import create_model_client as from_factory

    assert from_main is from_factory
```

- [ ] **步骤 2：运行确认失败**（factory 无 `create_model_client`）

- [ ] **步骤 3：实现**

`neow/models/factory.py` 追加：

```python
def client_for(provider: str):
    if provider in ("openai", "openai-compatible"):
        return OpenAIClient
    if provider == "deepseek":
        return DeepSeekClient
    if provider == "anthropic":
        return AnthropicClient
    raise ConfigError(f"Unsupported provider: {provider!r}")

def create_model_client(config: Config, model_name: str):
    entry = config.get_model_config(model_name)
    provider = resolve_provider(entry, model_name)
    model = entry.get("model")
    if not model:
        raise ConfigError(f"Model entry {model_name!r} is missing \"model\"")
    validate_value = str(entry.get("validate", "auto") or "auto").strip().lower()
    if validate_value not in ("auto", "skip"):
        raise ConfigError(
            f"Invalid validate value {validate_value!r} for model {model_name!r}. "
            "Use 'auto' or 'skip'"
        )
    return client_for(provider)(
        api_key=resolve_api_key(entry, model_name),
        model=model,
        base_url=entry.get("base_url") or None,
        validate=validate_value == "auto",
    )
```

`neow/cli/main.py`：
- 删除本地 `create_model_client` 函数（含 docstring）
- 顶部加 `from neow.models.factory import create_model_client`
- 删除因此不再使用的 `DeepSeekClient/AnthropicClient/OpenAIClient` 导入（以 flake8 为准）

- [ ] **步骤 4：运行确认通过 + 回归**

运行：`... -m pytest tests/test_providers.py tests/tui -q` → PASS
运行：`... -m pytest -q` → 全绿（`_fake_launcher` 对 `main_mod.create_model_client` 的 patch 依赖 re-export，必须仍然可用）

- [ ] **步骤 5：Commit**

```bash
git add neow/models/factory.py neow/cli/main.py tests/test_providers.py
git commit -m "feat(models): create_model_client factory with provider/base_url support"
```

---

### 任务 4：展示（REPL `/model` + TUI ModelPicker 标签）

**文件：**
- 修改：`neow/models/factory.py`、`neow/cli/repl.py`、`neow/tui/screens/model_picker.py`、`neow/tui/screens/chat.py`
- 修改：`tests/test_providers.py`、`tests/tui/test_screens.py`

- [ ] **步骤 1：追加失败测试**

```python
# tests/test_providers.py
from neow.models.factory import describe_models


def test_describe_models_shows_provider_and_endpoint(tmp_path):
    config = _config(
        tmp_path,
        {
            "openrouter": {
                "provider": "openai-compatible",
                "api_key": "k",
                "model": "m",
                "base_url": "https://openrouter.ai/api/v1",
            },
            "deepseek": {"api_key": "k", "model": "deepseek-v4-flash"},
        },
    )
    lines = describe_models(config)
    assert "openrouter (openai-compatible @ https://openrouter.ai/api/v1)" in lines[0]
    assert "deepseek (auto)" in lines[1]
```

```python
# tests/tui/test_screens.py
async def test_model_picker_labels_shown_and_selection_returns_name():
    switched = []
    app = _screen_app(
        ModelPickerScreen(
            models=["openrouter"],
            labels={"openrouter": "openrouter (openai-compatible)"},
            on_select=switched.append,
        )
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "openai-compatible" in _app_text(app)
        await pilot.press("enter")
        await pilot.pause()
        assert switched == ["openrouter"]
```

- [ ] **步骤 2：运行确认失败**（`describe_models` 缺失 / ModelPicker 不接受 `labels`）

- [ ] **步骤 3：实现**

`factory.py`：

```python
def describe_models(config: Config) -> list[str]:
    lines = []
    for name, entry in config.models.items():
        provider = entry.get("provider") or "auto"
        base_url = entry.get("base_url")
        suffix = f" @ {base_url}" if base_url else ""
        lines.append(f"{name} ({provider}{suffix})")
    return lines
```

`neow/cli/repl.py` 的 `Command.MODEL` 无参分支：把可用模型列表改为遍历 `describe_models(self.config)` 输出（保留 current model 与 aliases 两行）。

`ModelPickerScreen.__init__(..., labels: dict[str, str] | None = None)`；选项构造改为
`SelectionList(*[((labels or {}).get(m, m), m) for m in models], id="model-list")`。

`ChatScreen._open_model_picker`：由 `config.models` 构建
`labels = {name: f"{name} ({entry.get('provider')})" if entry.get("provider") else name for name, entry in models.items()}` 并传入；`on_select` 仍返回模型名，行为不变。

- [ ] **步骤 4：运行确认通过 + 回归**

运行：`... -m pytest tests/test_providers.py tests/tui/test_screens.py -q` → PASS
运行：`... -m pytest -q` → 全绿

- [ ] **步骤 5：Commit**

```bash
git add neow/models/factory.py neow/cli/repl.py neow/tui/screens/model_picker.py neow/tui/screens/chat.py tests/test_providers.py tests/tui/test_screens.py
git commit -m "feat: show provider and endpoint in /model and the TUI picker"
```

---

### 任务 5：文档、离线端到端验收

**文件：**
- 修改：`README.md`、`.neow.json.example`
- 修改：`tests/test_providers.py`

- [ ] **步骤 1：追加失败/验收测试**

```python
def test_end_to_end_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(
        "openai.OpenAI",
        lambda **kwargs: SimpleNamespace(models=SimpleNamespace(list=lambda: [])),
    )
    config = _config(
        tmp_path,
        {
            "openrouter": {
                "provider": "openai-compatible",
                "api_key_env": "OPENROUTER_API_KEY",
                "model": "anthropic/claude-sonnet-4",
                "base_url": "http://localhost:9/v1",
                "validate": "skip",
            }
        },
        default="openrouter",
    )
    client = create_model_client(config, "openrouter")
    assert client.validate_connection() is True
    assert client.base_url == "http://localhost:9/v1"
    assert client.model == "anthropic/claude-sonnet-4"
```

- [ ] **步骤 2：实现文档**

`.neow.json.example` 增加：

```json
{
  "default_model": "deepseek",
  "models": {
    "deepseek": {
      "api_key_env": "NEOW_DEEPSEEK_API_KEY",
      "model": "deepseek-v4-flash"
    },
    "openrouter": {
      "provider": "openai-compatible",
      "api_key_env": "OPENROUTER_API_KEY",
      "model": "anthropic/claude-sonnet-4",
      "base_url": "https://openrouter.ai/api/v1"
    }
  }
}
```

README 新增 "任意 OpenAI 兼容服务商（BYOK）" 小节：OpenRouter / Ollama / vLLM 三个配置示例；密钥三种来源与解析顺序；`validate: skip` 的用途；自定义模型在 `token.prices` 配置价格（不配则成本按 0 计）。

- [ ] **步骤 3：全量验收**

```bash
PATH="/home/neow/.venv/bin:$PATH" .venv/bin/python -m pytest -q          # 0 failed
.venv/bin/flake8 neow/models/factory.py tests/test_providers.py neow/tui/screens/model_picker.py  # clean
.venv/bin/black --check neow/models/factory.py tests/test_providers.py    # clean
```

注：`neow/cli/main.py` 与 `neow/cli/repl.py` 仅做最小改动（re-export / 展示），两文件存在既有 lint 债务（E402/E501 等，见 TUI 验收报告 §3 补记），不在本计划范围内处理。

- [ ] **步骤 4：Commit**

```bash
git add README.md .neow.json.example tests/test_providers.py
git commit -m "docs: any-provider (BYOK) usage and examples; offline acceptance"
```

---

## 规格覆盖对照（编写时自检）

| 规格章节 | 覆盖任务 |
|---------|---------|
| §3 配置 schema 与校验 | 2、3 |
| §4 provider 解析 | 2 |
| §5 客户端构造与 base_url | 1、3 |
| §6 密钥解析顺序 | 2 |
| §7 连接校验策略 | 1 |
| §8 展示与错误提示 | 3、4 |
| §9 文件改动清单 | 1–5 |
| §10 测试计划 | 1–5（18 项对号入座） |
| §11 兼容性 | 2、3、5 |
| §12 风险（文档引导） | 4、5 |

**类型一致性检查（编写时已核对）：** `PROVIDERS`/`normalize_env_name`/`resolve_provider`/`resolve_api_key`/`client_for`/`create_model_client`/`describe_models`；三个客户端统一 `(api_key, model, base_url=None, validate=True)`；`validate_openai_compatible(client, label)`；错误一律 `ConfigError`。

**步骤扫描：** 每个任务均为「失败测试 → 确认失败 → 实现 → 确认通过 → 提交」，测试给出确切断言，代码步骤只给签名与规格定值，不重复实现体。
