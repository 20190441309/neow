# Neow 任意服务商（BYOK）设计规格

- 日期：2026-10-07
- 状态：对话内设计已获用户批准（"没问题"）；本文件待用户书面审查
- 范围：支持任意 OpenAI 兼容服务商与自定义 `base_url`（含三家内置客户端的 base_url 覆盖），配置 schema、密钥解析、连接校验、展示与测试
- 关联：`docs/design/2026-10-07-neow-tui-design.md`（TUI）、`README.md` 配置章节

## 1. 背景与目标

现状：neow 只支持 deepseek / anthropic / openai 三家，provider 由模型名猜测（`neow/cli/main.py:create_model_client`），`base_url` 不可配（DeepSeek 写死 `https://api.deepseek.com`），密钥只认三个固定环境变量。用户无法接入 OpenRouter、硅基流动、Moonshot、vLLM、Ollama 等 OpenAI 兼容服务商。

目标：让用户通过配置接入任意 OpenAI 兼容端点，并让三家内置客户端支持自定义 `base_url`；旧配置行为零变化。

## 2. 范围

**In scope**

- 模型条目新增 `provider` / `api_key_env` / `base_url` / `validate` 字段
- provider 解析（显式优先，名字启发式兜底）
- 三家客户端构造函数支持 `base_url` 与 `validate`
- 密钥解析顺序（config → 指定 env → 通用 env → 内置 env）
- 连接校验降级（不支持 `/models` 的端点）
- `/model`（REPL）与 TUI ModelPicker 的 provider 展示
- README 与 `.neow.json.example` 文档、测试

**Out of scope**

- Azure OpenAI（`api-version` / deployment 路径）、Google Gemini 原生协议等非兼容协议适配
- OpenRouter `HTTP-Referer` 等 `extra_headers`
- provider 注册表/类层次重构（对话中评估过的方案 2）
- 交互式 `/key` 向导或首次启动密钥录入（用户选择后续再做）
- 代理（HTTP proxy）与证书配置

## 3. 配置 schema

模型条目 (`config.models.<name>`) 字段：

| 字段 | 必填 | 取值 | 默认 | 说明 |
|------|------|------|------|------|
| `provider` | 否 | `openai` / `openai-compatible` / `anthropic` / `deepseek` | 名字启发式 | 显式指定客户端类型 |
| `model` | 是 | 任意字符串 | 无 | 发给服务商的模型名；缺失报 `ConfigError` |
| `api_key` | 否 | 字符串 | 无 | 直填密钥（兼容现状） |
| `api_key_env` | 否 | 环境变量名 | 无 | 引用任意环境变量 |
| `base_url` | 否 | URL 字符串 | 各 provider 默认 | 自定义端点 |
| `validate` | 否 | `auto` / `skip` | `auto` | `skip` 跳过启动连接校验；其它值报 `ConfigError` |

示例：

```json
{
  "default_model": "openrouter",
  "models": {
    "openrouter": {
      "provider": "openai-compatible",
      "api_key_env": "OPENROUTER_API_KEY",
      "model": "anthropic/claude-sonnet-4",
      "base_url": "https://openrouter.ai/api/v1"
    },
    "ollama": {
      "provider": "openai-compatible",
      "api_key": "ollama",
      "model": "qwen2.5:14b",
      "base_url": "http://localhost:11434/v1",
      "validate": "skip"
    },
    "anthropic-gw": {
      "provider": "anthropic",
      "api_key_env": "CORP_ANTHROPIC_KEY",
      "model": "claude-sonnet-4-6",
      "base_url": "https://llm-gateway.corp.example"
    }
  }
}
```

### 3.1 配置校验规则

- `provider` 非法 → `ConfigError("Unknown provider 'x' for model 'y'. Available: openai, openai-compatible, anthropic, deepseek")`
- `model` 缺失或空 → `ConfigError("Model entry 'y' is missing \"model\"")`
- `validate` 非 `auto|skip` → `ConfigError("Invalid validate value 'z' for model 'y'. Use 'auto' or 'skip'")`
- 校验发生在 `create_model_client()` 调用时（启动或 `/model` 切换），不改变 `Config` 加载期行为

## 4. Provider 解析

新模块 `neow/models/factory.py`：

```python
PROVIDERS = ("openai", "openai-compatible", "anthropic", "deepseek")

def resolve_provider(entry: Mapping[str, Any], model_name: str) -> str
```

规则（顺序）：

1. `entry["provider"]` 非空：规范化为小写并校验在 `PROVIDERS` 内，否则 `ConfigError`（见 3.1）
2. 否则按名字启发式（与现状完全一致，向后兼容）：
   - 含 `deepseek` → `deepseek`
   - 含 `anthropic` 或 `claude` → `anthropic`
   - 含 `openai` 或 `gpt` → `openai`
3. 都不匹配 → `ConfigError("Cannot infer provider for model 'y'. Set \"provider\" to one of: ...")`

`openai-compatible` 与 `openai` 使用同一个客户端类 `OpenAIClient`；前者只是语义标记（便于文档与展示）。

## 5. 客户端构造与 base_url 透传

三个客户端构造函数统一扩为：

```python
OpenAIClient(api_key: str, model: str = "gpt-4o", base_url: str | None = None, validate: bool = True)
DeepSeekClient(api_key: str, model: str = "deepseek-v4-flash", base_url: str | None = None, validate: bool = True)
AnthropicClient(api_key: str, model: str = "claude-sonnet-4-6", base_url: str | None = None, validate: bool = True)
```

- 构造时把 `base_url` 与 `validate` 存为实例属性（`self.base_url`、`self.validate_enabled`）
- SDK 构造：
  - OpenAI：`openai.OpenAI(api_key=api_key)`；`base_url` 非空时 `openai.OpenAI(api_key=api_key, base_url=base_url)`
  - DeepSeek：`openai.OpenAI(api_key=api_key, base_url=base_url or "https://api.deepseek.com")`
  - Anthropic：`anthropic.Anthropic(api_key=api_key)`；`base_url` 非空时附 `base_url=base_url`
- 现有位置参数调用（`create_model_client`、测试）不受影响

`create_model_client(config, model_name)` 迁移到 `neow/models/factory.py`，`neow/cli/main.py` 顶部 re-export（`from neow.models.factory import create_model_client`），保证 `neow/cli/repl.py` 与 TUI 的既有延迟 import 不破坏。

构造逻辑：

```python
entry = config.get_model_config(model_name)
provider = resolve_provider(entry, model_name)
api_key = resolve_api_key(entry, model_name)
model = entry.get("model"); if not model: raise ConfigError(...)
base_url = entry.get("base_url") or None
validate_enabled = validate != "skip"
return client_for(provider)(api_key=api_key, model=model, base_url=base_url, validate=validate_enabled)
```

## 6. 密钥解析顺序

```python
def resolve_api_key(entry: Mapping[str, Any], model_name: str, *, env: Mapping[str, str] | None = None) -> str
```

按顺序取第一个非空（`strip()` 后）：

1. `entry["api_key"]`
2. `os.environ[entry["api_key_env"]]`（字段存在且非空时）
3. `os.environ[f"NEOW_{normalize_env_name(model_name)}_API_KEY"]`
   - `normalize_env_name`：非字母数字转 `_`，去首尾 `_`，转大写；例：`my-openrouter` → `MY_OPENROUTER`
4. 内置变量（维持现状）：`NEOW_DEEPSEEK_API_KEY`、`NEOW_ANTHROPIC_API_KEY`、`NEOW_OPENAI_API_KEY`
5. 全空 → `ConfigError("No API key for model 'y'. Set models.y.api_key, models.y.api_key_env, or NEOW_<NAME>_API_KEY")`

约束：密钥仅存内存；不写日志、不在 `/model` 输出回显；`env` 参数用于测试注入。

## 7. 连接校验策略

`validate: auto`（默认）：

- OpenAI / DeepSeek / openai-compatible：调用 `client.models.list()`；`neow/models/base.py` 新增共用助手：

```python
def validate_openai_compatible(client: Any, label: str) -> bool:
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

- Anthropic：维持现有 `messages.create(max_tokens=10)` 探针（兼容自定义网关）
- `validate: skip`：`validate_connection()` 直接 `return True`，不发请求

`validate_enabled=False` 优先于任何探针逻辑。

## 8. 展示与错误提示

- REPL `/model` 无参：每个模型一行，附显式 provider 与 base_url：
  `openrouter (openai-compatible @ https://openrouter.ai/api/v1)`
  未写 `provider` 的条目显示 `(auto)`；不回显密钥
- TUI ModelPicker：`ModelPickerScreen` 增加可选 `labels: dict[str, str] | None`，选项 prompt 用 `labels.get(name, name)`；`ChatScreen._open_model_picker` 生成带 provider 的标签
- 启动失败：配置错误（provider 非法/缺 model/缺密钥/validate 非法）以 `ConfigError` 文案直接提示修复；连接失败维持现有 `Failed to connect to <model> API` 文案

## 9. 文件改动清单

| 文件 | 改动 |
|------|------|
| 新建 `neow/models/factory.py` | `PROVIDERS`、`normalize_env_name`、`resolve_provider`、`resolve_api_key`、`client_for`、`create_model_client` |
| `neow/models/base.py` | 新增 `validate_openai_compatible()`；`BaseModelClient` 增 `base_url`/`validate_enabled` 默认属性 |
| `neow/models/openai.py` | 构造函数扩展；`validate_connection` 接助手并支持 skip |
| `neow/models/deepseek.py` | 同上（默认 base_url 不变） |
| `neow/models/anthropic.py` | 构造函数扩展；`validate_connection` 支持 skip |
| `neow/cli/main.py` | 删除本地 `create_model_client`，改为从 factory re-export；`main()` 行为不变 |
| `neow/cli/repl.py` | `/model` 无参输出增加 provider/endpoint（仅展示） |
| `neow/tui/screens/model_picker.py` | 可选 `labels` |
| `neow/tui/screens/chat.py` | ModelPicker 标签带 provider（仅展示） |
| `.neow.json.example` | 增加一个 openai-compatible 示例条目 |
| `README.md` | "任意 OpenAI 兼容服务商" 一节：OpenRouter/Ollama/vLLM 示例、密钥约定、`validate` 说明、自定义模型的 `token.prices` 说明 |
| 新建 `tests/test_providers.py` | 下列测试 |

## 10. 测试计划（TDD，全部离线、monkeypatch SDK）

`tests/test_providers.py`：

1. `test_resolve_explicit_provider`：四种 provider 值逐一返回自身
2. `test_resolve_heuristic_backward_compat`：`deepseek`/`claude-x`/`gpt-4o` 无 provider 字段时分别解析为 deepseek/anthropic/openai
3. `test_resolve_unknown_provider_raises`：`provider="foo"` → `ConfigError`，文案含可用列表
4. `test_resolve_uninferable_name_raises`：`name="mystery"` → `ConfigError`，文案含 `provider`
5. `test_api_key_prefers_config_value`：`api_key` 与 env 同时存在时取 `api_key`
6. `test_api_key_env_reference`：`api_key_env="MY_KEY"` + monkeypatch env
7. `test_api_key_generic_convention`：仅设 `NEOW_MY_ROUTER_API_KEY` 时可用（条目名 `my-router`）
8. `test_api_key_legacy_env`：仅设 `NEOW_ANTHROPIC_API_KEY` 时 anthropic 条目可用
9. `test_api_key_missing_raises_with_hint`：无任何来源 → `ConfigError`，文案含 `api_key_env` 与 `NEOW_`
10. `test_missing_model_field_raises`
11. `test_invalid_validate_value_raises`
12. `test_create_client_passes_base_url`：monkeypatch `neow.models.factory.OpenAIClient` 捕获 kwargs，断言 `base_url` 与 `validate=False` 透传
13. `test_create_client_provider_mapping`：`openai-compatible` → `OpenAIClient`；`anthropic` → `AnthropicClient`；`deepseek` → `DeepSeekClient`
14. `test_legacy_config_behavior_unchanged`：无 provider/base_url 的旧式 deepseek 条目仍得到 `DeepSeekClient` 且 base_url 默认
15. `test_validate_openai_compatible_404_is_ok`：伪造 `status_code=404` 的异常 → True
16. `test_validate_openai_compatible_401_fails`：`status_code=401` → False
17. `test_validate_skip_returns_true_without_call`：伪造 client，`validate_enabled=False` 时 `models.list` 不被调用
18. `test_model_picker_labels`（Pilot）：带 labels 的 ModelPicker 显示 `openrouter (openai-compatible)` 且选择回调仍返回模型名

验收：以上测试 RED→GREEN；全量 `pytest` 0 失败；`flake8 neow/models neow/cli neow/tui tests`（仓库 `.flake8` 配置）无新增问题；README 示例可被 `Config` 正常解析。

## 11. 兼容性与迁移

- 不写新字段的旧配置：provider 解析、密钥来源、客户端类型、校验行为逐项不变
- 三个内置环境变量与 `models` 默认三条目不变
- `create_model_client` 的公开导入路径（`neow.cli.main`）保留
- 新增字段均可选，无迁移步骤；`.neow.json.example` 更新不强制

## 12. 风险

| 风险 | 缓解 |
|------|------|
| 自定义条目名含 `openai/gpt/claude/deepseek` 被启发式误判 | 文档明确"自定义条目请显式写 provider"；错误文案引导 |
| 兼容端点无 `/models` 且返回其它错误码（如 400） | `validate: skip` 兜底；文档给 Ollama/内网示例 |
| 自定义模型价格缺失显示 $0 | README 说明在 `token.prices` 按模型名配置 |
| `get_model_config` 的子串回退可能匹配到非预期条目 | 自定义条目使用唯一命名；本设计不改该逻辑（超范围） |

## 13. 未决问题

无。实现中发现的歧义需回到本文件更新并经用户确认。
