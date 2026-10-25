"""BYOK model editor with provider presets and live /models fetching."""

from __future__ import annotations

from typing import Any, Callable, Optional

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from neow.core.config import Config, ConfigError
from neow.models.factory import PROVIDERS, build_model_client, resolve_provider
from neow.models.management import (
    PROVIDER_PRESETS,
    fetch_endpoint_models,
    get_preset_by_id,
    is_local_endpoint,
    sync_gateway_models,
    validate_model_entry,
)


class ModelEditorScreen(ModalScreen):
    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ModelEditorScreen .dialog { width: 88; }
    ModelEditorScreen Label { margin-top: 1; }
    ModelEditorScreen Input, ModelEditorScreen Select { width: 100%; }
    ModelEditorScreen .model-actions { height: 1; margin-top: 1; }
    ModelEditorScreen Button { margin-right: 1; }
    ModelEditorScreen #model-error { height: auto; color: $error; }
    ModelEditorScreen #model-fetched-select { display: none; margin-top: 1; }
    ModelEditorScreen #model-fetched-select.visible { display: block; }
    """

    def __init__(
        self,
        *,
        config: Config,
        on_saved: Callable[[], None],
        name: str = "",
        on_activate: Optional[Callable[[str], None]] = None,
    ):
        super().__init__()
        self.config = config
        self.on_saved = on_saved
        self.on_activate = on_activate
        self.entry_name = name
        self.entry = config.stored_model_entry(name) if name else {}
        self._activation_pending = False
        self._test_pending = False
        self._fetch_pending = False
        self._last_preset_name = ""

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = (
            "◆ 编辑模型" if self.entry_name else "◆ 添加 / 自定义模型 (BYOK)"
        )
        try:
            provider = (
                resolve_provider(self.entry, self.entry_name)
                if self.entry_name
                else "openai-compatible"
            )
        except Exception:
            provider = "openai-compatible"
        with box:
            with VerticalScroll():
                yield Label("快速预设模板 (选择常见厂商一键填入地址与协议)")
                yield Select(
                    [(p["label"], p["id"]) for p in PROVIDER_PRESETS],
                    value="custom",
                    allow_blank=False,
                    id="model-preset",
                )
                yield Label("配置名称")
                yield Input(
                    value=self.entry_name,
                    placeholder="例如: deepseek / siliconflow / ollama",
                    id="model-name",
                    disabled=bool(self.entry_name),
                )
                yield Label("API 协议")
                yield Select(
                    [(p, p) for p in PROVIDERS],
                    value=provider,
                    allow_blank=False,
                    id="model-provider",
                )
                yield Label("API 地址")
                yield Input(
                    value=self.entry.get("base_url", ""),
                    placeholder=(
                        "https://api.example.com/v1 " "(本地支持 http://127.0.0.1:...)"
                    ),
                    id="model-url",
                )
                yield Label("模型 ID")
                yield Input(
                    value=self.entry.get("model", ""),
                    placeholder="例如: deepseek-chat / gpt-4o / qwen-max (或点击下方「拉取模型」)",
                    id="model-id",
                )
                yield Select(
                    [("从远端列表选择模型...", "")],
                    value="",
                    allow_blank=False,
                    id="model-fetched-select",
                )
                yield Label("API Key")
                # Never render a stored or environment-resolved credential.
                yield Input(
                    password=True,
                    placeholder=(
                        "保持现有 Key"
                        if self.entry_name
                        else "粘贴 API Key（本地 Ollama/Magpie 可留空）"
                    ),
                    id="model-key",
                )
                yield Label("Key 环境变量")
                yield Input(
                    value=self.entry.get("api_key_env", ""),
                    placeholder="可选，例如: DEEPSEEK_API_KEY / OPENROUTER_API_KEY",
                    id="model-key-env",
                )
                yield Static("", id="model-error", markup=False)
                with Horizontal(classes="model-actions"):
                    yield Button("保存", id="model-save", variant="primary")
                    yield Button("测试连接", id="model-test")
                    yield Button("取消", id="model-cancel")
                    yield Button("拉取模型", id="model-fetch")
                    yield Button("批量导入网关", id="model-import-gw")

    def on_mount(self) -> None:
        self.query_one("#model-id" if self.entry_name else "#model-name", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "model-preset":
            preset_id = str(event.value or "")
            preset = get_preset_by_id(preset_id)
            if not preset or preset_id == "custom":
                return
            self._apply_preset(preset)
        elif event.select.id == "model-fetched-select":
            chosen = str(event.value or "").strip()
            if chosen:
                self.query_one("#model-id", Input).value = chosen
                name_input = self.query_one("#model-name", Input)
                if not self.entry_name and not name_input.value.strip():
                    safe_name = chosen.split("/")[-1].replace(" ", "-")
                    name_input.value = safe_name

    def _apply_preset(self, preset: dict[str, str]) -> None:
        name_input = self.query_one("#model-name", Input)
        if not self.entry_name:
            current_name = name_input.value.strip()
            if not current_name or current_name == self._last_preset_name:
                base_name = preset.get("default_name", "")
                if base_name:
                    candidate = base_name
                    suffix = 2
                    while candidate in self.config.models and candidate not in (
                        "deepseek",
                        "openai",
                        "anthropic",
                    ):
                        candidate = f"{base_name}-{suffix}"
                        suffix += 1
                    name_input.value = candidate
                    self._last_preset_name = candidate

        provider_select = self.query_one("#model-provider", Select)
        if preset.get("provider") in PROVIDERS:
            provider_select.value = preset["provider"]

        self.query_one("#model-url", Input).value = preset.get("base_url", "")
        self.query_one("#model-id", Input).value = preset.get("default_model", "")
        self.query_one("#model-key-env", Input).value = preset.get("api_key_env", "")
        if preset.get("default_key") and not self.query_one("#model-key", Input).value:
            self.query_one("#model-key", Input).value = preset["default_key"]

        self.query_one("#model-error", Static).update(
            f"已套用「{preset['label']}」预设，请填写 API Key 后保存或点击「拉取模型」"
        )

    def _values(self) -> tuple[str, dict[str, Any]]:
        def value(selector: str) -> str:
            return self.query_one(selector, Input).value.strip()

        name = value("#model-name")
        entry = dict(self.entry)
        base_url = value("#model-url")
        entry.update(
            provider=str(self.query_one("#model-provider", Select).value),
            base_url=base_url,
            model=value("#model-id"),
        )
        key = value("#model-key")
        env_name = value("#model-key-env")
        if key:
            entry.update(api_key=key, api_key_env="")
        elif env_name:
            entry.update(api_key="", api_key_env=env_name)
        elif self.entry.get("api_key_env"):
            entry.update(api_key="", api_key_env="")
        elif (
            not entry.get("api_key")
            and not entry.get("api_key_env")
            and is_local_endpoint(base_url)
        ):
            entry.update(api_key="local", api_key_env="")
        validate_model_entry(name, entry)
        return name, entry

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "model-cancel":
            self.app.pop_screen()
            return
        if event.button.id == "model-fetch":
            self._fetch_models()
            return
        if event.button.id == "model-import-gw":
            self._import_gateway_models()
            return
        error = self.query_one("#model-error", Static)
        try:
            name, entry = self._values()
            if event.button.id == "model-save":
                if not self.entry_name and name in self.config.models:
                    # Allow overwriting unconfigured built-in placeholders
                    existing = self.config.models.get(name, {})
                    if existing.get("api_key") or existing.get("api_key_env"):
                        error.update("配置名称已存在")
                        return
                self.config.save_model(name, entry)
                # Retain this saved entry so a failed first-run probe can be retried.
                self.entry_name = name
                self.entry = entry
                self.query_one("#model-name", Input).disabled = True
                self.on_saved()
                if self.on_activate is not None:
                    self.set_activation_pending(True, "配置已保存，正在连接…")
                    self.on_activate(name)
                else:
                    self.app.pop_screen()
            elif event.button.id == "model-test":
                self._test_connection(name, entry)
        except Exception as exc:
            # Validation errors are controlled locally; never show an SDK body.
            self.set_activation_pending(
                False,
                str(exc) if isinstance(exc, ConfigError) else "无法保存模型配置",
            )

    def _fetch_models(self) -> None:
        if self._fetch_pending or self._activation_pending:
            return
        base_url = self.query_one("#model-url", Input).value.strip()
        key = self.query_one("#model-key", Input).value.strip() or str(
            self.entry.get("api_key", "")
        )
        key_env = self.query_one("#model-key-env", Input).value.strip() or str(
            self.entry.get("api_key_env", "")
        )
        self._fetch_pending = True
        self.query_one("#model-fetch", Button).disabled = True
        self.query_one("#model-error", Static).update("正在拉取可用模型列表...")
        self.run_worker(
            lambda: self._probe_fetch_models(base_url, key, key_env),
            thread=True,
            exclusive=True,
        )

    def _probe_fetch_models(self, base_url: str, key: str, key_env: str) -> None:
        try:
            items = fetch_endpoint_models(base_url, api_key=key, api_key_env=key_env)
            model_ids = [item["id"] for item in items]
            err = ""
        except ConfigError as exc:
            model_ids = []
            err = str(exc)
        except Exception:
            model_ids = []
            err = "无法拉取模型列表，请检查地址和 Key"
        self.app.call_from_thread(self._on_models_fetched, model_ids, err)

    def _on_models_fetched(self, model_ids: list[str], err: str) -> None:
        self._fetch_pending = False
        if not self.is_mounted:
            return
        self.query_one("#model-fetch", Button).disabled = self._activation_pending
        if err:
            self.query_one("#model-error", Static).update(err)
            return
        fetched_select = self.query_one("#model-fetched-select", Select)
        options = [(f"选用远端模型: {mid}", mid) for mid in model_ids]
        fetched_select.set_options(options)
        fetched_select.add_class("visible")
        if model_ids:
            fetched_select.value = model_ids[0]
            self.query_one("#model-id", Input).value = model_ids[0]
        self.query_one("#model-error", Static).update(
            f"已拉取 {len(model_ids)} 个可用模型，可在下拉框中切换选择"
        )

    def _import_gateway_models(self) -> None:
        if self._fetch_pending or self._activation_pending:
            return
        base_url = self.query_one("#model-url", Input).value.strip()
        key = self.query_one("#model-key", Input).value.strip() or str(
            self.entry.get("api_key", "")
        )
        key_env = self.query_one("#model-key-env", Input).value.strip() or str(
            self.entry.get("api_key_env", "")
        )
        prefix = self.query_one("#model-name", Input).value.strip() or "gw"
        self._fetch_pending = True
        self.query_one("#model-import-gw", Button).disabled = True
        self.query_one("#model-error", Static).update("正在批量导入网关模型...")
        self.run_worker(
            lambda: self._probe_import_gateway(base_url, key, key_env, prefix),
            thread=True,
            exclusive=True,
        )

    def _probe_import_gateway(
        self, base_url: str, key: str, key_env: str, prefix: str
    ) -> None:
        try:
            count = sync_gateway_models(
                self.config,
                base_url=base_url,
                api_key=key,
                api_key_env=key_env,
                prefix=prefix,
            )
            err = ""
        except ConfigError as exc:
            count = 0
            err = str(exc)
        except Exception:
            count = 0
            err = "批量导入网关模型失败，请检查地址和 Key"
        self.app.call_from_thread(self._on_gateway_imported, count, prefix, err)

    def _on_gateway_imported(self, count: int, prefix: str, err: str) -> None:
        self._fetch_pending = False
        if not self.is_mounted:
            return
        self.query_one("#model-import-gw", Button).disabled = self._activation_pending
        if err:
            self.query_one("#model-error", Static).update(err)
            return
        self.on_saved()
        self.app.notify(f"已批量导入 {count} 个模型 (前缀: {prefix}/)")
        self.app.pop_screen()

    def set_activation_pending(self, pending: bool, message: str = "") -> None:
        self._activation_pending = pending
        self.query_one("#model-save", Button).disabled = pending
        self.query_one("#model-test", Button).disabled = pending or self._test_pending
        for control in self.query("Input, Select"):
            control.disabled = pending or (
                control.id == "model-name" and bool(self.entry_name)
            )
        self.query_one("#model-error", Static).update(message)

    def _test_connection(self, name: str, entry: dict[str, Any]) -> None:
        self._test_pending = True
        self.query_one("#model-test", Button).disabled = True
        self.query_one("#model-error", Static).update("连接中...")
        self.run_worker(lambda: self._probe(name, entry), thread=True, exclusive=True)

    def _probe(self, name: str, entry: dict[str, Any]) -> None:
        try:
            client = build_model_client(entry, name)
            client.client = client.client.with_options(timeout=5, max_retries=0)
            connected = client.validate_connection()
            client.client.close()
        except Exception:
            connected = False
        self.app.call_from_thread(self._tested, connected)

    def _tested(self, connected: bool) -> None:
        self._test_pending = False
        if not self.is_mounted:
            return
        self.query_one("#model-test", Button).disabled = self._activation_pending
        if self._activation_pending:
            return
        self.query_one("#model-error", Static).update(
            "连接成功" if connected else "连接失败，请检查地址和 Key"
        )
