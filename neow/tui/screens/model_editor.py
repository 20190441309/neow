"""BYOK model editor."""

from __future__ import annotations

from typing import Any, Callable, Optional

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from neow.core.config import Config
from neow.models.factory import PROVIDERS, build_model_client, resolve_provider
from neow.models.management import validate_model_entry


class ModelEditorScreen(ModalScreen):
    DEFAULT_CLASSES = "dialog-backdrop"
    BINDINGS = [("escape", "app.pop_screen", "返回")]
    DEFAULT_CSS = """
    ModelEditorScreen .dialog { width: 84; }
    ModelEditorScreen Label { margin-top: 1; }
    ModelEditorScreen Input, ModelEditorScreen Select { width: 100%; }
    ModelEditorScreen .model-actions { height: 3; margin-top: 1; }
    ModelEditorScreen Button { margin-right: 1; }
    ModelEditorScreen #model-error { height: auto; color: $error; }
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

    def compose(self):
        box = Vertical(classes="dialog")
        box.border_title = "编辑模型" if self.entry_name else "添加 BYOK 模型"
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
                yield Label("配置名称")
                yield Input(
                    value=self.entry_name,
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
                    placeholder="https://api.example.com/v1",
                    id="model-url",
                )
                yield Label("模型 ID")
                yield Input(value=self.entry.get("model", ""), id="model-id")
                yield Label("API Key")
                # Never render a stored or environment-resolved credential.
                yield Input(
                    password=True,
                    placeholder="保持现有 Key" if self.entry_name else "",
                    id="model-key",
                )
                yield Label("Key 环境变量")
                yield Input(value=self.entry.get("api_key_env", ""), id="model-key-env")
                yield Static("", id="model-error", markup=False)
                with Horizontal(classes="model-actions"):
                    yield Button("保存", id="model-save", variant="primary")
                    yield Button("测试连接", id="model-test")
                    yield Button("取消", id="model-cancel")

    def on_mount(self) -> None:
        self.query_one("#model-id" if self.entry_name else "#model-name", Input).focus()

    def _values(self) -> tuple[str, dict[str, Any]]:
        def value(selector: str) -> str:
            return self.query_one(selector, Input).value.strip()

        name = value("#model-name")
        entry = dict(self.entry)
        entry.update(
            provider=str(self.query_one("#model-provider", Select).value),
            base_url=value("#model-url"),
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
        validate_model_entry(name, entry)
        return name, entry

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id == "model-cancel":
            self.app.pop_screen()
            return
        error = self.query_one("#model-error", Static)
        try:
            name, entry = self._values()
            if event.button.id == "model-save":
                if not self.entry_name and name in self.config.models:
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
            from neow.core.config import ConfigError

            self.set_activation_pending(
                False,
                str(exc) if isinstance(exc, ConfigError) else "无法保存模型配置",
            )

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
