"""Chat screen: turn lifecycle, cards, queueing and approval wiring."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from rich.text import Text
from textual import work
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static

from neow.cli.commands import Command, parse_command
from neow.tui.bridge.controller import ChatController
from neow.tui.bridge.events import (
    ContentDelta,
    Notice,
    ReasoningDelta,
    ReasoningEnd,
    ReasoningStarted,
    ToolFinished,
    ToolStarted,
    TurnCompleted,
    TurnFailed,
)
from neow.tui.widgets.cards import (
    AssistantCard,
    CardBase,
    CompactionCard,
    ErrorCard,
    SystemCard,
    ThinkingCard,
    ToolCard,
    UserCard,
)
from neow.tui.clipboard import extract_last_code_block
from neow.tui.commands import CommandDispatcher, CommandResult
from neow.tui.screens.cost import CostScreen
from neow.tui.screens.diff_view import DiffScreen
from neow.tui.screens.help import HelpScreen
from neow.tui.screens.model_picker import ModelPickerScreen
from neow.tui.screens.session_picker import SessionPickerScreen
from neow.tui.screens.tree import SessionTreeScreen
from neow.tui.widgets.input_dock import InputDock
from neow.tui.widgets.status_bar import StatusBar, TopBar
from neow.tui.widgets.timeline import TimelineScroll
from neow.tui.theme import get_palette
from neow.utils.logger import logger

SIDEBAR_TABS = ("context", "tree", "git")


class TuiEventMessage(Message):
    """Worker-thread -> UI-thread wrapper for controller events."""

    def __init__(self, event: Any):
        self.event = event
        super().__init__()


class AutoCompacted(Message):
    """Worker-thread -> UI: automatic compaction finished."""

    def __init__(self, result: Optional[str], error: Optional[str]):
        self.result = result
        self.error = error
        super().__init__()


class ChatScreen(Screen):
    """Main screen: top bar, timeline, sidebar, input dock, status bar."""

    BINDINGS = [
        ("escape", "cancel_or_close", "中断"),
        ("ctrl+o", "toggle_card", "折叠"),
        ("ctrl+t", "cycle_sidebar", "侧栏页"),
        ("ctrl+b", "toggle_sidebar", "侧栏"),
        ("f1", "show_help", "帮助"),
        ("ctrl+y", "copy_last_code", "复制代码"),
    ]

    def __init__(self):
        super().__init__()
        self._busy = False
        self._turn_number = 0
        self._turn_started = 0.0
        self._current_assistant: Optional[AssistantCard] = None
        self._segment_started = 0.0
        self._current_thinking: Optional[ThinkingCard] = None
        self._running_tools: Dict[str, ToolCard] = {}
        self._tool_started: Dict[str, float] = {}
        self._controller: Optional[ChatController] = None
        self.commands: Optional[CommandDispatcher] = None
        self.sidebar_tab = "context"

    # -- composition ---------------------------------------------------

    def compose(self):
        yield TopBar(id="topbar")
        with Horizontal(id="body"):
            yield TimelineScroll(id="timeline")
            yield Vertical(id="sidebar")
        yield Static(id="queuestrip")
        yield InputDock(id="inputdock")
        yield StatusBar(id="statusbar")

    def on_mount(self) -> None:
        self.apply_width_classes(self.size.width)
        app = self.app
        self._controller = ChatController(
            app.conversation,
            event_callback=self._post_event,
            approval_bridge=getattr(app, "approval_bridge", None),
            token_tracker=getattr(app, "token_tracker", None),
            event_bus=getattr(app, "event_bus", None),
        )
        self.commands = CommandDispatcher(
            conversation=app.conversation,
            config=getattr(app, "config", None),
            session_manager=getattr(app, "session_manager", None),
            token_tracker=getattr(app, "token_tracker", None),
            approval_policy=getattr(app, "approval_policy", None),
            event_bus=getattr(app, "event_bus", None),
            plugin_api=getattr(app, "plugin_api", None),
        )
        self._last_reasoning = ""
        self.commands.hooks.update(
            {
                "help": self._open_help,
                "model": self._open_model_picker,
                "history": self._open_session_picker,
                "load": self._open_session_picker,
                "tree": self._open_tree,
                "branch": self._open_tree,
                "diff": self._open_diff,
                "commit_ai": self._commit_ai,
                "undo": self._undo_action,
                "cost": self._open_cost,
                "think": self._show_thinking,
            }
        )
        self.refresh_status()
        self._refresh_sidebar()
        if self._sidebar_default():
            self.sidebar.set_class(True, "visible")

    def _sidebar_default(self) -> bool:
        config = getattr(self.app, "config", None)
        if config is None:
            return False
        try:
            return bool(config.tui.get("sidebar_default", False))
        except Exception:
            return False

    # -- responsive breakpoints (spec §4.3) ----------------------------

    def on_resize(self, event) -> None:
        self.apply_width_classes(event.size.width)
        self.set_class(event.size.height < 20, "short")

    def on_unmount(self) -> None:
        """Auto-save the session on exit (parity with the classic REPL)."""

        manager = getattr(self.app, "session_manager", None)
        if manager is None:
            return
        try:
            manager.save(self.app.conversation)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Auto-save failed: {exc}")

    def on_key(self, event) -> None:
        collapse = getattr(self.app, "collapse_splash", None)
        if callable(collapse):
            collapse()

    def apply_width_classes(self, width: int) -> None:
        self.set_class(width < 110, "small-sidebar")
        self.set_class(width < 88, "no-sidebar")
        self.set_class(width < 72, "narrow")

    # -- widgets -------------------------------------------------------

    @property
    def timeline(self) -> TimelineScroll:
        return self.query_one("#timeline", TimelineScroll)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#statusbar", StatusBar)

    @property
    def sidebar(self) -> Vertical:
        return self.query_one("#sidebar", Vertical)

    @property
    def input_dock(self) -> InputDock:
        return self.query_one("#inputdock", InputDock)

    @property
    def sidebar_visible(self) -> bool:
        return self.sidebar.has_class("visible")

    # -- public API ----------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def queued(self) -> List[str]:
        return self.input_dock.queued_texts()

    def submit_prompt(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if self._busy:
            self.input_dock.enqueue(text)
            self._update_queue_strip()
            return
        self._start_turn(text)

    def cancel_turn(self) -> None:
        if self._controller is not None:
            self._controller.cancel()

    # -- turn lifecycle ------------------------------------------------

    def _start_turn(self, text: str) -> None:
        self._busy = True
        self._turn_number += 1
        self._turn_started = time.monotonic()
        self._current_assistant = None
        self._current_thinking = None
        self._segment_started = time.monotonic()
        self._running_tools = {}
        self._tool_started = {}
        self._add_card(
            UserCard(text, number=self._turn_number, timestamp=self._timestamp())
        )
        self.status_bar.set_activity("thinking")
        self.input_dock.set_busy(True)
        self._run_turn(text)

    @work(thread=True, exclusive=True)
    def _run_turn(self, text: str) -> None:
        if self._controller is not None:
            self._controller.run_turn(text)

    def _post_event(self, event: Any) -> None:
        self.post_message(TuiEventMessage(event))

    def on_tui_event_message(self, message: TuiEventMessage) -> None:
        self.handle_event(message.event)

    def handle_event(self, event: Any) -> None:
        if isinstance(event, ReasoningStarted):
            self._ensure_thinking()
        elif isinstance(event, ReasoningDelta):
            self._ensure_thinking().append_reasoning(event.text)
        elif isinstance(event, ReasoningEnd):
            card = self._ensure_thinking()
            card.finish_reasoning(event.duration)
            self._last_reasoning = event.reasoning
            self._current_thinking = None
        elif isinstance(event, ContentDelta):
            card = self._ensure_assistant()
            self.call_later(card.append_content, event.text)
        elif isinstance(event, ToolStarted):
            if self._current_assistant is not None:
                self._current_assistant.finish(time.monotonic() - self._segment_started)
            self._current_assistant = None
            card = ToolCard(effects=self.app.effects)
            card.start(event.name, event.args)
            key = event.call_id or event.name
            self._running_tools[key] = card
            self._tool_started[key] = time.monotonic()
            self._add_card(card)
            self.status_bar.set_activity(f"running {event.name}")
        elif isinstance(event, ToolFinished):
            key = event.call_id or event.name
            card = self._running_tools.pop(key, None)
            started = self._tool_started.pop(key, None)
            if card is not None:
                duration = (time.monotonic() - started) if started else None
                card.finish(
                    event.result, event.is_error, duration=duration, denied=event.denied
                )
            if not self._running_tools:
                self.status_bar.set_activity("thinking")
        elif isinstance(event, Notice):
            level = event.level if event.level in ("info", "warn", "error") else "info"
            self._add_card(SystemCard(event.message, level=level))
        elif isinstance(event, TurnCompleted):
            self._finish_turn(event.content)
        elif isinstance(event, TurnFailed):
            self._add_card(ErrorCard("模型错误", event.message))
            self._finish_turn("")

    def _add_card(self, card: CardBase) -> None:
        """Add a card, playing its entrance animation in full effects mode."""

        if isinstance(card, ToolCard):
            cards = self.timeline.cards()
            previous = cards[-1] if cards else None
            # Consecutive tool calls stack into one tight group.
            card.set_class(isinstance(previous, ToolCard), "follows")
        card.apply_palette(get_palette(self.app))
        self.timeline.add_card(card)
        if getattr(self.app, "effects", "full") == "full":
            card.play_entrance()

    def _ensure_thinking(self) -> ThinkingCard:
        if self._current_thinking is None:
            card = ThinkingCard(effects=self.app.effects)
            self._current_thinking = card
            self._add_card(card)
        return self._current_thinking

    def _ensure_assistant(self) -> AssistantCard:
        if self._current_assistant is None:
            self._segment_started = time.monotonic()
            card = AssistantCard(
                number=self._turn_number,
                timestamp=self._timestamp(),
                effects=getattr(self.app, "effects", "full"),
                label=self._model_label(),
            )
            self._current_assistant = card
            self._add_card(card)
            self.status_bar.set_activity("writing")
        return self._current_assistant

    def _model_label(self) -> str:
        client = getattr(self.app.conversation, "model_client", None)
        return str(getattr(client, "model", "") or "Assistant")

    def _finish_turn(self, content: str) -> None:
        duration = time.monotonic() - self._turn_started
        if self._current_assistant is not None:
            self._current_assistant.finish(time.monotonic() - self._segment_started)
            self._current_assistant = None
        if self._current_thinking is not None:
            self._current_thinking.finish_reasoning(duration)
            self._current_thinking = None
        self._busy = False
        self.status_bar.set_activity("idle")
        self.input_dock.set_busy(False)
        self.refresh_status()
        self._refresh_sidebar()
        if self._should_auto_compact():
            self._start_auto_compact()
            return
        self._continue_after_turn()

    def _continue_after_turn(self) -> None:
        """Run the next queued prompt or a pending lint/test fix."""
        nxt = self.input_dock.pop_first_queued()
        if nxt is not None:
            self._update_queue_strip()
            self._start_turn(nxt)
            return

        feedback = getattr(self.app.conversation, "pending_lint_feedback", None)
        if feedback:
            self.app.conversation.pending_lint_feedback = None
            self._add_card(SystemCard("自动修复 lint/test 错误", level="warn"))
            self._start_turn(feedback)

    # -- auto-compaction -----------------------------------------------

    def _should_auto_compact(self) -> bool:
        check = getattr(self.app.conversation, "should_auto_compact", None)
        try:
            return bool(check and check())
        except Exception:  # noqa: BLE001
            return False

    def _start_auto_compact(self) -> None:
        # Stay busy so new prompts queue instead of racing the compaction.
        self._busy = True
        self.status_bar.set_activity("compacting")
        self.input_dock.set_busy(True)
        self._run_auto_compact()

    @work(thread=True, group="compact")
    def _run_auto_compact(self) -> None:
        try:
            result, error = self.app.conversation.compact_incremental(), None
        except Exception as exc:  # noqa: BLE001
            result, error = None, str(exc)
        self.post_message(AutoCompacted(result, error))

    def on_auto_compacted(self, message: "AutoCompacted") -> None:
        if message.error:
            self._add_card(ErrorCard("自动压缩失败", message.error))
        else:
            self._add_card(CompactionCard(f"上下文接近上限，已自动压缩\n{message.result}"))
        self._busy = False
        self.status_bar.set_activity("idle")
        self.input_dock.set_busy(False)
        self.refresh_status()
        self._continue_after_turn()

    # -- status / queue ------------------------------------------------

    def refresh_status(self) -> None:
        usage = getattr(self.app.conversation, "context_usage", None)
        if callable(usage):
            try:
                self.status_bar.set_context(usage()[2])
            except Exception:  # noqa: BLE001
                pass
        tracker = getattr(self.app, "token_tracker", None)
        if tracker is None:
            return
        try:
            self.status_bar.set_tokens(
                getattr(tracker, "session_input", 0),
                getattr(tracker, "session_output", 0),
                tracker.get_session_cost(),
            )
        except Exception:
            pass

    def _update_queue_strip(self) -> None:
        strip = self.query_one("#queuestrip", Static)
        count = self.input_dock.queued_count()
        if count:
            palette = get_palette(self.app)
            strip.update(
                Text.assemble(
                    ("◷ ", palette["warn"]),
                    (f"已排队 {count} 条", palette["warn"]),
                    ("  ·  ↑ 取回编辑", palette["muted"]),
                )
            )
        strip.set_class(bool(count), "visible")

    def on_input_dock_submitted(self, message: InputDock.Submitted) -> None:
        if message.text.startswith("/"):
            self.dispatch_command(message.text)
            return
        self.submit_prompt(message.text)

    def dispatch_command(self, raw: str) -> CommandResult:
        """Run a slash command and present the result (spec §7.3)."""

        if self.commands is None:
            return CommandResult("Command dispatcher not ready", kind="error")
        parsed = parse_command(raw)
        if self._busy and parsed.command in (
            Command.CLEAR,
            Command.LOAD,
            Command.HISTORY,
            Command.MODEL,
            Command.BRANCH,
            Command.TREE,
            Command.COMPACT,
        ):
            self.notify("请先按 Esc 中断当前生成，再修改会话或模型", severity="warning")
            return CommandResult("Turn in progress", kind="error")
        result = self.commands.dispatch(parsed)
        if parsed.command == Command.CLEAR and result.kind != "error":
            self.timeline.clear_cards()
        if result.should_exit:
            self.app.exit()
            return result
        if result.text:
            if result.kind == "compaction":
                self._add_card(CompactionCard(result.text))
            else:
                level = (
                    result.kind if result.kind in ("info", "warn", "error") else "info"
                )
                self._add_card(SystemCard(result.text, level=level))
        self._maybe_lint_followup()
        self._refresh_sidebar()
        self.query_one(TopBar).refresh_info()
        return result

    def _maybe_lint_followup(self) -> None:
        feedback = getattr(self.app.conversation, "pending_lint_feedback", None)
        if feedback and not self._busy:
            self.app.conversation.pending_lint_feedback = None
            self._add_card(SystemCard("自动修复 lint/test 错误", level="warn"))
            self._start_turn(feedback)

    # -- screen hooks (plan task 14) -----------------------------------

    def _open_help(self):
        self.app.push_screen(HelpScreen())
        return None

    def _open_model_picker(self):
        models = []
        labels = {}
        config = getattr(self.app, "config", None)
        if config is not None:
            try:
                for name, entry in config.models.items():
                    models.append(name)
                    provider = entry.get("provider")
                    if provider:
                        labels[name] = f"{name} ({provider})"
            except Exception:
                models = []
                labels = {}
        self.app.push_screen(
            ModelPickerScreen(
                models=models,
                labels=labels,
                on_select=self._switch_model,
                current=self._model_label(),
            )
        )
        return None

    def _switch_model(self, name: str) -> None:
        try:
            from neow.cli.main import create_model_client

            client = create_model_client(self.app.config, name)
            if client.validate_connection():
                self.app.conversation.model_client = client
                self._add_card(SystemCard(f"Switched to model: {name}"))
                self.query_one(TopBar).refresh_info()
            else:
                self._add_card(ErrorCard("模型切换失败", f"无法连接 {name}"))
        except Exception as exc:  # noqa: BLE001
            self._add_card(ErrorCard("模型切换失败", str(exc)))

    def _open_session_picker(self):
        sessions = []
        manager = getattr(self.app, "session_manager", None)
        if manager is not None:
            try:
                sessions = manager.list_sessions()
            except Exception:
                sessions = []
        self.app.push_screen(
            SessionPickerScreen(sessions=sessions, on_select=self._load_session)
        )
        return None

    def _load_session(self, name: str) -> None:
        manager = getattr(self.app, "session_manager", None)
        if manager is None:
            self._add_card(ErrorCard("会话", "Session manager not available"))
            return
        loaded = False
        try:
            tree_mgr = manager.session_tree
            if tree_mgr.find_session(name):
                conversation = self.app.conversation
                conversation.messages.clear()
                conversation.messages.extend(tree_mgr.get_messages(name))
                loaded = True
                self._add_card(SystemCard(f"Session loaded (JSONL): {name}"))
        except Exception:
            loaded = False
        if not loaded:
            if manager.restore(name, self.app.conversation):
                self._add_card(SystemCard(f"Session loaded: {name}"))
            else:
                self._add_card(ErrorCard("会话", f"Session not found: {name}"))

    def _active_session_name(self):
        manager = getattr(self.app, "session_manager", None)
        if manager is None:
            return None
        try:
            sessions = manager.list_sessions()
        except Exception:
            return None
        return sessions[0]["name"] if sessions else None

    def _open_tree(self):
        tree = {}
        leaf = None
        name = self._active_session_name()
        manager = getattr(self.app, "session_manager", None)
        if manager is not None and name:
            try:
                tree_mgr = manager.session_tree
                tree = tree_mgr.get_tree(name)
                leaf = tree_mgr.get_leaf_id(name)
            except Exception:
                tree = {}
        self.app.push_screen(
            SessionTreeScreen(
                tree=tree,
                leaf_id=leaf,
                on_goto=self._goto_node,
                on_branch=self._branch_at,
            )
        )
        return None

    def _goto_node(self, node_id: str) -> None:
        manager = getattr(self.app, "session_manager", None)
        name = self._active_session_name()
        if manager is None or not name:
            self._add_card(ErrorCard("会话树", "No active session"))
            return
        try:
            tree_mgr = manager.session_tree
            tree_mgr.branch_at(name, node_id)
            conversation = self.app.conversation
            conversation.messages.clear()
            conversation.messages.extend(tree_mgr.get_messages(name))
            self._add_card(SystemCard(f"Navigated to node {node_id[:8]}"))
        except (ValueError, FileNotFoundError) as exc:
            self._add_card(ErrorCard("会话树", str(exc)))

    def _branch_at(self, node_id: str) -> None:
        if not node_id:
            return
        self._goto_node(node_id)

    def _open_diff(self):
        from neow.tools.git import GitError, git_diff

        try:
            diff = git_diff()
        except GitError as exc:
            diff = str(exc)
        self.app.push_screen(
            DiffScreen(
                diff_text=diff,
                on_commit=self._commit_ai,
                on_undo=self._diff_undo,
            )
        )
        return None

    def _diff_undo(self) -> None:
        result = self._undo_action()
        self._add_card(SystemCard(result.text, level=result.kind))

    def _commit_ai(self):
        self.submit_prompt(
            "Please generate a concise commit message for the current changes "
            "and use the git_commit tool to commit them."
        )
        return CommandResult("正在生成 commit message…")

    def _undo_action(self) -> CommandResult:
        from neow.tools.git import GitError, git_undo

        try:
            return CommandResult(git_undo())
        except GitError as exc:
            return CommandResult(str(exc), kind="error")

    def _open_cost(self):
        summary = ""
        tracker = getattr(self.app, "token_tracker", None)
        if tracker is not None:
            try:
                summary = str(tracker.get_session_summary())
            except Exception:
                summary = ""
        self.app.push_screen(CostScreen(summary=summary))
        return None

    def _show_thinking(self) -> CommandResult:
        if self._last_reasoning:
            return CommandResult(self._last_reasoning)
        return CommandResult(
            "No thinking content available. Reasoning is captured during "
            "AI responses that use thinking mode."
        )

    def _refresh_sidebar(self) -> None:
        try:
            sidebar = self.sidebar
        except Exception:
            return
        for child in list(sidebar.children):
            child.remove()
        palette = get_palette(self.app)
        tab = self.sidebar_tab
        out = Text(no_wrap=True, overflow="ellipsis")
        labels = {"context": "Context", "tree": "Sessions", "git": "Git"}
        active = f"bold {palette['bg']} on {palette['accent1']}"
        for index, name in enumerate(SIDEBAR_TABS):
            if index:
                out.append("  ")
            if name == tab:
                out.append(f" {labels[name]} ", active)
            else:
                out.append(f" {labels[name]} ", palette["muted"])
        out.append("\n\n")

        def heading(text: str) -> None:
            out.append(f"{text}\n", f"bold {palette['dim']}")

        def item(icon: str, text: str, color: str, note: str = "") -> None:
            out.append(f" {icon} ", color)
            out.append(text, palette["text"])
            if note:
                out.append(f"  {note}", palette["muted"])
            out.append("\n")

        def empty(text: str) -> None:
            out.append(f" {text}\n", f"italic {palette['muted']}")

        if tab == "context":
            files = []
            try:
                files = self.app.conversation.list_context_files()
            except Exception:
                files = []
            heading(f"FILES IN CONTEXT · {len(files)}")
            for path in files:
                item("▪", str(path), palette["accent1"])
            if not files:
                empty("暂无文件 · /add <file> 或 @ 引用")
        elif tab == "tree":
            heading("RECENT SESSIONS")
            manager = getattr(self.app, "session_manager", None)
            if manager is None:
                empty("(no session manager)")
            else:
                try:
                    sessions = manager.list_sessions()
                    for session in sessions[:8]:
                        item(
                            "◇",
                            str(session.get("name")),
                            palette["accent2"],
                            f"{session.get('message_count', 0)} msgs",
                        )
                    if not sessions:
                        empty("(no sessions)")
                except Exception as exc:  # noqa: BLE001
                    empty(str(exc))
        else:
            heading("STATUS")
            try:
                from neow.tools.git import git_log, git_status

                status = git_status() or "Working tree clean"
                clean = "clean" in status.lower()
                for line in status.splitlines():
                    item(
                        "●",
                        line.strip(),
                        palette["success"] if clean else palette["warn"],
                    )
                log = git_log(5)
                if log:
                    out.append("\n")
                    heading("RECENT COMMITS")
                    for line in log.splitlines():
                        sha, _, subject = line.partition(" ")
                        out.append(f" {sha[:7]} ", palette["accent4"])
                        out.append(f"{subject}\n", palette["dim"])
            except Exception as exc:  # noqa: BLE001
                empty(str(exc))
        out.rstrip()
        sidebar.mount(Static(out))

    def on_input_dock_queue_changed(self, message: InputDock.QueueChanged) -> None:
        self._update_queue_strip()

    def on_input_dock_copy_requested(self, message: InputDock.CopyRequested) -> None:
        self.action_copy_last_code()

    @staticmethod
    def _timestamp() -> str:
        return time.strftime("%H:%M")

    # -- actions -------------------------------------------------------

    def action_cancel_or_close(self) -> None:
        if self._busy:
            self.cancel_turn()

    def action_toggle_card(self) -> None:
        focused = self.focused
        while focused is not None and not isinstance(focused, CardBase):
            focused = focused.parent
        if isinstance(focused, CardBase):
            focused.toggle()
            return
        cards = self.timeline.cards()
        if cards:
            cards[-1].toggle()

    def action_show_help(self) -> None:
        self._open_help()

    def action_copy_last_code(self) -> None:
        """Copy the last code block of the newest assistant card (OSC52)."""

        cards = [
            card for card in self.timeline.cards() if isinstance(card, AssistantCard)
        ]
        text = cards[-1].rendered_markdown() if cards else ""
        code = extract_last_code_block(text)
        if not code:
            self.notify("没有可复制的代码块", severity="warning", timeout=2)
            return
        self.app.copy_to_clipboard(code)
        self.notify("已复制最后一个代码块", timeout=2)

    def action_toggle_sidebar(self) -> None:
        sidebar = self.sidebar
        visible = sidebar.has_class("visible")
        if not visible and self.has_class("no-sidebar"):
            self.notify("终端宽度不足，无法显示侧栏", severity="warning", timeout=2)
            return
        sidebar.set_class(not visible, "visible")
        self._refresh_sidebar()

    def action_cycle_sidebar(self) -> None:
        index = SIDEBAR_TABS.index(self.sidebar_tab)
        self.sidebar_tab = SIDEBAR_TABS[(index + 1) % len(SIDEBAR_TABS)]
        self._refresh_sidebar()
