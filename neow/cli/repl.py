"""REPL (Read-Eval-Print Loop) for Neow CLI."""

import os
import re
import sys
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory

from neow.cli.commands import Command, parse_command
from neow.core.conversation import ConversationManager
from neow.tools.git import git_diff, git_commit, git_undo, GitError
from neow.tools.web import WebFetcher
from neow.utils.formatter import (
    console,
    print_welcome,
    print_user_message,
    print_assistant_message,
    format_assistant_panel,
    format_streaming_assistant_panel,
    print_diff,
    print_error,
    print_info,
    print_status_bar,
    print_tool_call,
    print_tool_result,
    print_turn_separator,
    format_reasoning_dropdown,
)
from neow.utils.logger import logger
from neow.core.config import Config


def _now_ts() -> str:
    """Return current local time as ``HH:MM:SS`` for panel subtitles."""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")


# ── built-in command descriptions for tab completion ──────────────────────

_BUILTIN_COMMANDS: dict[str, str] = {
    "/help":      "Show help message",
    "/clear":     "Clear conversation history",
    "/exit":      "Exit Neow",
    "/model":     "Switch or show AI model",
    "/diff":      "Show uncommitted git changes",
    "/commit":    "Commit changes with AI-generated message",
    "/undo":      "Undo last AI commit",
    "/add":       "Add file to context",
    "/drop":      "Remove file from context",
    "/ls":        "List context files",
    "/lint":      "Run linter / toggle auto-lint",
    "/test":      "Run tests / toggle auto-test",
    "/architect": "Enter architect mode (plan first, then execute)",
    "/code":      "Return to normal coding mode",
    "/save":      "Save current session",
    "/load":      "Load a saved session",
    "/history":   "List saved sessions",
    "/cost":      "Show token usage and cost",
    "/web":       "Fetch web page content into context",
    "/think":     "View last AI thinking/reasoning content",
    "/compact":   "Summarize conversation to free context window",
    "/export":    "Export conversation as Markdown file",
    "/image":     "Queue an image for the next message (vision)",
    "/approval":  "Show or set approval mode (always-ask/write/yolo)",
    "/tree":      "Visualize session tree and navigate to history nodes",
    "/branch":    "Branch from a specific message in history",
    "/verbose":   "Toggle expanded tool-call parameter display",
}

def _expand_path(prefix: str) -> Path:
    """Expand a user-typed path prefix (handles ~ and relative paths)."""
    if prefix.startswith("~"):
        return Path(os.path.expanduser(prefix))
    return Path(prefix)


def _iter_dir(path: Path) -> list[str]:
    """List directory entries, directories first (with trailing sep), hidden last."""
    try:
        items = sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except (OSError, PermissionError):
        return []
    result = []
    for item in items:
        if item.is_dir():
            result.append(item.name + os.sep)
        else:
            result.append(item.name)
    return result


class NeowCompleter(Completer):
    """Tab-completion for /slash commands and @file references."""

    def __init__(self, plugin_api=None):
        self._plugin_api = plugin_api

    # ── commands ──────────────────────────────────────────────────────────

    def _all_commands(self) -> dict[str, str]:
        cmds = dict(_BUILTIN_COMMANDS)
        if self._plugin_api:
            for name in self._plugin_api.plugin_commands:
                if name not in cmds:
                    cmds[name] = "Plugin command"
        return cmds

    def _complete_command(self, word: str):
        for cmd, desc in self._all_commands().items():
            if cmd.startswith(word):
                yield Completion(
                    cmd,
                    start_position=-len(word),
                    display=cmd,
                    display_meta=desc,
                )

    # ── files ─────────────────────────────────────────────────────────────

    def _complete_file(self, word: str):
        # word is the full @-prefixed text, e.g. "@src/neow/cl"
        prefix = word[1:]  # strip '@'
        base_path = _expand_path(prefix) if prefix else Path(".")

        # Determine search directory and name prefix
        if prefix.endswith(os.sep):
            search_dir = base_path
            name_prefix = ""
        elif prefix == "":
            search_dir = Path(".")
            name_prefix = ""
        else:
            search_dir = base_path.parent
            name_prefix = base_path.name

        if not search_dir.is_dir():
            return

        for entry in _iter_dir(search_dir):
            if not entry.lower().startswith(name_prefix.lower()):
                continue
            # Reconstruct the completion text with @ prefix
            rel = str(search_dir / entry)
            if prefix == "" or prefix == ".":
                completed = "@" + entry if search_dir == Path(".") else "@" + rel
            elif prefix.endswith(os.sep):
                completed = "@" + prefix + entry
            else:
                completed = "@" + str(search_dir / entry)

            display_meta = "dir" if entry.endswith(os.sep) else "file"
            yield Completion(
                completed,
                start_position=-len(word),
                display=completed,
                display_meta=display_meta,
            )

    # ── dispatch ───────────────────────────────────────────────────────────

    def get_completions(self, document, complete_event):
        text_before = document.text_before_cursor
        # Find the current "word" (from last whitespace to cursor)
        last_space = text_before.rfind(" ")
        current_word = text_before[last_space + 1:]

        if current_word.startswith("/"):
            yield from self._complete_command(current_word)
        elif current_word.startswith("@"):
            yield from self._complete_file(current_word)


MODEL_MAX_CONTEXT = {
    "deepseek-v4-flash": 128_000,
    "deepseek-v3": 128_000,
    "claude-sonnet-4-6": 200_000,
    "claude-3-5-sonnet": 200_000,
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
}
DEFAULT_MAX_CONTEXT = 128_000


def _format_toolbar_text(
    model: str, tokens_used: int, cost: float, branch: str
) -> str:
    """Format status bar text for prompt_toolkit bottom toolbar."""
    max_ctx = MODEL_MAX_CONTEXT.get(model, DEFAULT_MAX_CONTEXT)
    pct = (tokens_used / max_ctx * 100) if max_ctx else 0
    parts = [f" {model}", f"ctx: {tokens_used:,}/{pct:.0%}", f"cost: ${cost:.4f}"]
    if branch:
        parts.append(branch)
    parts.append("/help")
    return " | ".join(parts)


class REPL:
    """Interactive REPL for Neow CLI."""

    URL_PATTERN = re.compile(r'https?://[^\s]+')

    def __init__(
        self,
        conversation: ConversationManager,
        config: Optional[Config] = None,
        streaming: bool = True,
        token_tracker=None,
        session_manager=None,
        plugin_api=None,
        event_bus=None,
    ):
        """Initialize REPL.

        Args:
            conversation: ConversationManager instance.
            config: Optional Config instance for lint/test toggles.
            streaming: Whether to use streaming output.
            token_tracker: Optional TokenTracker for cost display.
            session_manager: Optional SessionManager for session persistence.
            plugin_api: Optional PluginAPI for plugin command dispatch.
            event_bus: Optional EventBus for emitting lifecycle events.
        """
        self.conversation = conversation
        self.config = config
        self.streaming = streaming
        self.token_tracker = token_tracker
        self.session_manager = session_manager
        self.plugin_api = plugin_api
        self.event_bus = event_bus
        self.architect_mode = False
        self.session: Optional[PromptSession] = None
        self.web_fetcher = WebFetcher(config.web if config else {})
        self._last_reasoning: Optional[str] = None
        self.approval_policy = None  # ApprovalPolicy, wired from main.py
        self._last_activity_time = 0.0  # monotonic timestamp of last user input
        self._session_name: Optional[str] = None
        self._idle_compact_done = False  # prevent repeated idle compacts
        self._stream_status = None  # Rich Status spinner, set during streaming
        self._msg_counter = 0  # 1-based sequence number for user/assistant panels
        self.verbose_tools = False  # /verbose toggle: expand tool call parameters
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup prompt session with history, completer, and bottom status bar."""
        try:
            test_session = PromptSession()
            try:
                history = FileHistory(".neow_history")
                completer = NeowCompleter(self.plugin_api)
                self.session = PromptSession(
                    history=history,
                    completer=completer,
                    bottom_toolbar=self._bottom_toolbar,
                )
            except Exception:
                self.session = test_session
        except Exception as e:
            logger.warning(f"Failed to setup prompt-toolkit: {e}")
            self.session = None

    def prompt_user_approval(self, tool_name: str, parameters: dict, reason: str) -> bool:
        """Prompt the user to approve a tool execution.

        Uses a single-keystroke prompt: Y to allow, N to deny,
        Enter defaults to deny.  Falls back to plain input() if
        prompt_toolkit is unavailable.
        """
        from neow.utils.formatter import print_approval_request
        # Stop streaming spinner while waiting for user input
        spinner_was_running = False
        if self._stream_status is not None:
            try:
                self._stream_status.stop()
                spinner_was_running = True
            except Exception:
                pass
        print_approval_request(tool_name, parameters, reason)
        try:
            return self._read_approval_key()
        except (EOFError, KeyboardInterrupt):
            return False
        finally:
            if spinner_was_running and self._stream_status is not None:
                try:
                    self._stream_status.start()
                except Exception:
                    pass

    def _read_approval_key(self) -> bool:
        """Read an approval decision with arrow-key navigation.

        Renders a two-option selector (``[Y] 允许`` / ``[N] 拒绝``) and lets
        the user move between them with Up/Down/Left/Right, confirming with
        Enter.  Y/N still work as single-key shortcuts; Esc/Ctrl+C deny.

        Falls back through three layers:
          1. ``prompt_toolkit.Application`` with key bindings (cross-platform,
             supports arrow keys) — primary path.
          2. Platform-native single-key read (``msvcrt``/``termios``) when
             prompt_toolkit is unavailable — Y/N only, no arrow keys.
          3. Plain ``input()`` — last resort.
        """
        import sys

        # ── Layer 1: prompt_toolkit Application with arrow-key nav ──
        if self.session is not None:
            try:
                return self._read_approval_prompt_toolkit()
            except Exception as e:
                logger.debug(f"prompt_toolkit approval selector failed: {e}")

        # ── Layer 2: platform-native single-key read (Y/N only) ───────
        try:
            if sys.platform == "win32":
                import msvcrt
                while True:
                    ch = msvcrt.getwch()
                    if ch in ("y", "Y"):
                        console.print("[sev.success]  ✓ Allowed[/sev.success]")
                        return True
                    if ch in ("n", "N", "\r", "\n"):
                        console.print("[sev.error]  ✗ Denied[/sev.error]")
                        return False
                    if ch in ("\x03", "\x1b"):  # Ctrl+C, Esc
                        console.print("[sev.error]  ✗ Denied[/sev.error]")
                        return False
            else:
                import tty, termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    while True:
                        ch = sys.stdin.read(1)
                        if ch in ("y", "Y"):
                            sys.stdout.write("✓ Allowed\r\n")
                            sys.stdout.flush()
                            return True
                        if ch in ("n", "N", "\r", "\n"):
                            sys.stdout.write("✗ Denied\r\n")
                            sys.stdout.flush()
                            return False
                        if ch in ("\x03", "\x1b"):  # Ctrl+C, Esc
                            sys.stdout.write("✗ Denied\r\n")
                            sys.stdout.flush()
                            return False
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass

        # ── Layer 3: plain input() ──────────────────────────────────
        response = input("  [Y] 允许 / [N] 拒绝 > ").strip().lower()
        return response in ("y", "yes")

    def _read_approval_prompt_toolkit(self) -> bool:
        """Render the arrow-key approval selector via prompt_toolkit.

        Two options (``允许`` default-selected, ``拒绝``) with full key bindings:
        Up/Down/Left/Right move, Enter confirms, Y/N are single-key shortcuts,
        Esc/Ctrl+C deny.

        Returns:
            True if the user approved, False if denied.
        """
        from prompt_toolkit import Application
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import Layout, HSplit, Window, FormattedTextControl
        from prompt_toolkit.formatted_text import FormattedText

        # State: 0 = allow (default), 1 = deny
        state = {"selected": 0, "result": None}

        def _options_fragment():
            """Build the formatted text for the two options with the
            currently-selected one highlighted."""
            sel = state["selected"]
            allow_style = "reverse" if sel == 0 else ""
            deny_style = "reverse" if sel == 1 else ""
            return FormattedText([
                ("", "  "),
                (allow_style, " [Y] 允许 "),
                ("", "   "),
                (deny_style, " [N] 拒绝 "),
                ("", "\n\n"),
                ("", "  ↑/↓/←/→ 切换 · Enter 确认 · Esc 拒绝"),
            ])

        control = FormattedTextControl(text=_options_fragment)
        body = HSplit([Window(content=control, height=3)])

        kb = KeyBindings()

        def _move(direction: int) -> None:
            """Toggle between 0 (allow) and 1 (deny)."""
            state["selected"] = (state["selected"] + direction) % 2

        def _confirm(event) -> None:
            state["result"] = state["selected"] == 0
            event.app.exit()

        def _deny(event) -> None:
            state["result"] = False
            event.app.exit()

        def _allow(event) -> None:
            state["result"] = True
            event.app.exit()

        # Arrow keys — all four directions work; Left maps to allow, Right to deny.
        @kb.add("up")
        @kb.add("left")
        def _up(event):
            _move(-1)

        @kb.add("down")
        @kb.add("right")
        def _down(event):
            _move(1)

        @kb.add("enter")
        def _enter(event):
            _confirm(event)

        @kb.add("y")
        @kb.add("Y")
        def _y(event):
            _allow(event)

        @kb.add("n")
        @kb.add("N")
        def _n(event):
            _deny(event)

        @kb.add("escape")
        @kb.add("c-c")
        def _esc(event):
            _deny(event)

        app = Application(
            layout=Layout(body),
            key_bindings=kb,
            full_screen=False,
            style={
                "reverse": "reverse",
            },
        )
        app.run()

        result = state["result"]
        if result is None:
            return False
        if result:
            console.print("[sev.success]  ✓ Allowed[/sev.success]")
        else:
            console.print("[sev.error]  ✗ Denied[/sev.error]")
        return result

    def _bottom_toolbar(self) -> str:
        """Return status bar text for prompt_toolkit bottom toolbar."""
        model_name = getattr(self.conversation.model_client, "model", "unknown")
        tokens_used = 0
        cost = 0.0
        branch = ""

        if self.token_tracker:
            tokens_used = (
                self.token_tracker.session_input + self.token_tracker.session_output
            )
            cost = self.token_tracker.get_session_cost()

        try:
            from neow.tools.git import git_status

            status = git_status()
            if "On branch" in status:
                branch = status.split("On branch ")[-1].split("\n")[0].strip()
        except Exception:
            pass

        return _format_toolbar_text(
            model_name, tokens_used, cost, f"branch:{branch}" if branch else ""
        )

    def _show_status_bar(self) -> None:
        """Display status bar with model, token, and cost info."""
        model_name = getattr(self.conversation.model_client, "model", "unknown")
        tokens_used = 0
        tokens_max = 128000
        cost = 0.0
        branch = ""

        if self.token_tracker:
            tokens_used = (
                self.token_tracker.session_input + self.token_tracker.session_output
            )
            cost = self.token_tracker.get_session_cost()

        # Get branch info
        try:
            from neow.tools.git import git_status

            status = git_status()
            if "On branch" in status:
                branch = status.split("On branch ")[-1].split("\n")[0].strip()
        except Exception:
            pass

        print_status_bar(
            model_name,
            tokens_used,
            tokens_max,
            cost,
            f"branch:{branch}" if branch else "",
        )

    def _get_recent_sessions(self, limit: int = 3) -> list:
        """Return up to ``limit`` most recent saved sessions for the welcome page.

        Returns an empty list if no session manager is wired or listing fails.
        """
        if not self.session_manager:
            return []
        try:
            sessions = self.session_manager.list_sessions()
            return sessions[:limit]
        except Exception as e:
            logger.debug(f"Failed to list recent sessions: {e}")
            return []

    def start(self) -> None:
        """Start the REPL loop."""
        model_name = getattr(self.conversation.model_client, "model", "")
        print_welcome(
            model=model_name,
            recent_sessions=self._get_recent_sessions(),
        )
        if self.event_bus:
            self.event_bus.emit("session_start", conversation=self.conversation)

        while True:
            try:
                user_input = self._get_input()
                if not user_input or not user_input.strip():
                    continue

                # Clear the raw input line and re-render as panel
                sys.stdout.write("\033[A\033[2K\r")
                sys.stdout.flush()
                # Separate conversation turns with a thin dim rule.
                if self._msg_counter > 0:
                    print_turn_separator()
                self._msg_counter += 1
                user_num = self._msg_counter
                print_user_message(
                    "> " + user_input,
                    msg_num=user_num,
                    timestamp=_now_ts(),
                )

                # Check for commands
                parsed = parse_command(user_input)
                if parsed.command:
                    if self._handle_command(parsed):
                        break
                    continue

                # Process with AI
                self._process_input(user_input)

            except KeyboardInterrupt:
                print_info("\nUse /exit to quit")
            except EOFError:
                break
            except Exception as e:
                print_error(f"Error: {e}")
                logger.error(f"REPL error: {e}")

    def _get_input(self) -> str:
        """Get user input.

        Returns:
            User input string.

        Supports multi-line input: end a line with \\ to continue.
        """
        try:
            if self.session is None:
                first = input("> ")
            else:
                first = self.session.prompt("> ")

            if not first or not first.rstrip().endswith("\\"):
                return first

            # Multi-line mode: collect lines until blank line
            lines = [first.rstrip().rstrip("\\")]
            while True:
                prompt = "... " if self.session is None else "... "
                try:
                    if self.session is None:
                        line = input(prompt)
                    else:
                        line = self.session.prompt(prompt)
                except (KeyboardInterrupt, EOFError):
                    break
                if not line or not line.strip():
                    break
                if line.rstrip().endswith("\\"):
                    lines.append(line.rstrip().rstrip("\\"))
                else:
                    lines.append(line)
                    break
            return "\n".join(lines)
        except KeyboardInterrupt:
            return ""
        except EOFError:
            raise

    def _handle_command(self, parsed) -> bool:
        """Handle parsed command.

        Args:
            parsed: ParsedCommand object.

        Returns:
            True if should exit, False otherwise.
        """
        if parsed.command == Command.HELP:
            print_welcome(
                model=getattr(self.conversation.model_client, "model", ""),
                recent_sessions=self._get_recent_sessions(),
            )
        elif parsed.command == Command.CLEAR:
            self.conversation.clear_history()
            self._msg_counter = 0
            print_info("Conversation history cleared")
        elif parsed.command == Command.EXIT:
            if self.event_bus:
                self.event_bus.emit("session_end", conversation=self.conversation)
            if self.session_manager:
                try:
                    self.session_manager.save(self.conversation)
                except Exception as e:
                    logger.warning(f"Auto-save failed: {e}")
            print_info("Goodbye!")
            return True
        elif parsed.command == Command.MODEL:
            if parsed.args:
                model_name = self.config.resolve_model_alias(parsed.args.strip())
                try:
                    from neow.cli.main import create_model_client
                    new_client = create_model_client(self.config, model_name)
                    if new_client.validate_connection():
                        self.conversation.model_client = new_client
                        print_info(f"Switched to model: {model_name}")
                    else:
                        print_error(f"Failed to connect to {model_name}")
                except Exception as e:
                    print_error(f"Failed to switch model: {e}")
            else:
                current = self.conversation.model_client.model
                available = list(self.config.models.keys())
                print_info(f"Current model: {current}")
                print_info(f"Available models: {', '.join(available)}")
                print_info("Aliases: sonnet->anthropic, claude->anthropic, deep->deepseek, gpt->openai")
        elif parsed.command == Command.DIFF:
            try:
                args_lower = parsed.args.lower() if parsed.args else ""
                staged = "staged" in args_lower
                split = "split" in args_lower or "side" in args_lower
                diff = git_diff(staged=staged)
                if diff:
                    print_diff(diff, split=split)
                else:
                    label = "staged" if staged else "uncommitted"
                    print_info(f"No {label} changes")
            except GitError as e:
                print_error(str(e))
        elif parsed.command == Command.COMMIT:
            try:
                if parsed.args:
                    result = git_commit(parsed.args)
                    print_info(result)
                else:
                    self._process_input(
                        "Please generate a concise commit message for the current changes "
                        "and use the git_commit tool to commit them."
                    )
            except GitError as e:
                print_error(str(e))
        elif parsed.command == Command.UNDO:
            try:
                result = git_undo()
                print_info(result)
            except GitError as e:
                print_error(str(e))
        elif parsed.command == Command.ADD:
            if parsed.args:
                try:
                    result = self.conversation.add_context_file(parsed.args.strip())
                    print_info(result)
                except FileNotFoundError as e:
                    print_error(str(e))
            else:
                print_error("Usage: /add <file_path>")
        elif parsed.command == Command.DROP:
            if parsed.args:
                try:
                    result = self.conversation.drop_context_file(parsed.args.strip())
                    print_info(result)
                except KeyError as e:
                    print_error(str(e))
            else:
                print_error("Usage: /drop <file_path>")
        elif parsed.command == Command.LS:
            files = self.conversation.list_context_files()
            if files:
                print_info("Context files:")
                for f in files:
                    print_info(f"  {f}")
            else:
                print_info("No files in context")
        elif parsed.command == Command.LINT:
            from neow.tools.lint_test import run_lint
            from pathlib import Path

            if parsed.args == "on":
                self.config._config["lint_test"]["auto_lint"] = True
                print_info("Auto-lint enabled")
            elif parsed.args == "off":
                self.config._config["lint_test"]["auto_lint"] = False
                print_info("Auto-lint disabled")
            else:
                result = run_lint(Path.cwd())
                if result.output:
                    print_info(result.output)
                if not result.success:
                    self._process_input(
                        f"Please fix the following lint errors:\n{result.output}"
                    )
        elif parsed.command == Command.TEST:
            from neow.tools.lint_test import run_tests
            from pathlib import Path

            if parsed.args == "on":
                self.config._config["lint_test"]["auto_test"] = True
                print_info("Auto-test enabled")
            elif parsed.args == "off":
                self.config._config["lint_test"]["auto_test"] = False
                print_info("Auto-test disabled")
            else:
                result = run_tests(Path.cwd())
                if result.output:
                    print_info(result.output)
                if not result.success:
                    self._process_input(
                        f"Please fix the following test failures:\n{result.output}"
                    )
        elif parsed.command == Command.ARCHITECT:
            self.architect_mode = True
            print_info("Architect mode enabled. Tasks will be planned and dispatched to sub-agents.")
            print_info("Use /code to return to normal coding mode.")
        elif parsed.command == Command.CODE:
            self.architect_mode = False
            print_info("Normal coding mode restored.")
        elif parsed.command == Command.SAVE:
            if self.session_manager:
                name = self.session_manager.save(self.conversation, parsed.args)
                self._session_name = name
                # Also save as JSONL
                try:
                    tree_mgr = self.session_manager.session_tree
                    tree_mgr.create(name, getattr(self.conversation.model_client, "model", "unknown"))
                    for msg in self.conversation.messages:
                        meta_keys = {"tool_call_id", "tool_calls", "type", "name"}
                        meta = {k: msg[k] for k in meta_keys if k in msg}
                        tree_mgr.append(name, msg.get("role", "user"), msg.get("content", ""), metadata=meta if meta else None)
                except Exception as e:
                    logger.warning(f"JSONL save failed: {e}")
                print_info(f"Session saved: {name}")
            else:
                print_error("Session manager not available")
        elif parsed.command == Command.LOAD:
            if self.session_manager and parsed.args:
                loaded = False
                # Try JSONL first
                try:
                    tree_mgr = self.session_manager.session_tree
                    jsonl_path = tree_mgr.find_session(parsed.args)
                    if jsonl_path:
                        self.conversation.messages.clear()
                        self.conversation.messages.extend(tree_mgr.get_messages(parsed.args))
                        self._session_name = parsed.args
                        loaded = True
                        print_info(f"Session loaded (JSONL): {parsed.args}")
                except Exception as e:
                    logger.debug(f"JSONL load failed, trying JSON: {e}")
                if not loaded:
                    if self.session_manager.restore(parsed.args, self.conversation):
                        self._session_name = parsed.args
                        print_info(f"Session loaded: {parsed.args}")
                    else:
                        print_error(f"Session not found: {parsed.args}")
            else:
                print_error("Usage: /load <session_name>")
        elif parsed.command == Command.HISTORY:
            if self.session_manager:
                sessions = self.session_manager.list_sessions()
                if sessions:
                    print_info("Sessions:")
                    for s in sessions:
                        print_info(f"  {s['name']} ({s['message_count']} msgs, {s['model']}, {s['created_at'][:16]})")
                else:
                    print_info("No saved sessions")
            else:
                print_error("Session manager not available")
        elif parsed.command == Command.COST:
            if self.token_tracker:
                print_info(self.token_tracker.get_session_summary())
            else:
                print_error("Token tracker not available")
        elif parsed.command == Command.WEB:
            if not parsed.args:
                print_error("Usage: /web <url>")
            else:
                try:
                    url = parsed.args.strip()
                    content = self.web_fetcher.fetch(url)
                    self.conversation.add_web_content(url, content)
                    print_info(f"Fetched: {content.title} ({len(content.text)} chars)")
                except Exception as e:
                    print_error(f"Failed to fetch URL: {e}")

        elif parsed.command == Command.THINK:
            if self._last_reasoning:
                from neow.utils.formatter import format_reasoning_expanded
                console.print(format_reasoning_expanded(self._last_reasoning))
            else:
                print_info("No thinking content available. Reasoning is captured during AI responses that use thinking mode.")
        elif parsed.command == Command.COMPACT:
            if parsed.args and parsed.args.strip().startswith("--keep-tokens"):
                try:
                    parts = parsed.args.strip().split()
                    keep = int(parts[1]) if len(parts) > 1 else 4000
                    result = self.conversation.compact_incremental(keep_recent_tokens=keep)
                except (ValueError, IndexError):
                    result = self.conversation.compact_incremental()
            elif parsed.args and "incremental" in parsed.args.lower():
                result = self.conversation.compact_incremental()
            elif parsed.args and "handoff" in parsed.args.lower():
                handoff = self.conversation.compact_with_handoff()
                if handoff:
                    # Inject the handoff as context for the new session
                    self.conversation.add_message("user", "[Session handoff from previous conversation]")
                    self.conversation.add_message("assistant", handoff)
                result = f"Handoff complete: {len(handoff)} char summary injected"
            else:
                result = self.conversation.compact()
            print_info(result)
        elif parsed.command == Command.EXPORT:
            if self.session_manager:
                export_name = parsed.args.strip() if parsed.args else None
                path = self.session_manager.export_markdown(self.conversation, export_name)
                print_info(f"Exported to: {path}")
            else:
                print_error("Session manager not available")
        elif parsed.command == Command.IMAGE:
            if not parsed.args:
                print_error("Usage: /image <file_path>")
            else:
                try:
                    result = self.conversation.queue_image(parsed.args.strip())
                    print_info(result)
                except (FileNotFoundError, ValueError) as e:
                    print_error(str(e))
        elif parsed.command == Command.APPROVAL:
            if not self.approval_policy:
                print_info("Approval mode not configured")
            elif not parsed.args:
                # Show current mode
                from neow.core.approval import ApprovalMode
                mode = self.approval_policy.mode
                print_info(f"Approval mode: {mode.value}")
                print_info("Available: always-ask | write | yolo")
                if self.approval_policy.tool_overrides:
                    print_info(f"Overrides: {self.approval_policy.tool_overrides}")
            else:
                from neow.core.approval import ApprovalMode
                arg = parsed.args.strip().lower()
                mode_map = {
                    "always-ask": ApprovalMode.ALWAYS_ASK,
                    "always_ask": ApprovalMode.ALWAYS_ASK,
                    "ask": ApprovalMode.ALWAYS_ASK,
                    "write": ApprovalMode.WRITE,
                    "w": ApprovalMode.WRITE,
                    "yolo": ApprovalMode.YOLO,
                    "y": ApprovalMode.YOLO,
                }
                new_mode = mode_map.get(arg)
                if new_mode:
                    self.approval_policy.set_mode(new_mode)
                    self.config._config["approval"]["mode"] = new_mode.value
                    print_info(f"Approval mode set to: {new_mode.value}")
                else:
                    print_error(f"Unknown mode: {arg}. Use: always-ask, write, yolo")
        elif parsed.command == Command.TREE:
            self._handle_tree(parsed)
        elif parsed.command == Command.BRANCH:
            self._handle_branch(parsed)
        elif parsed.command == Command.VERBOSE:
            self.verbose_tools = not self.verbose_tools
            state = "expanded (all parameters shown)" if self.verbose_tools else "collapsed (one-line summary)"
            print_info(f"Tool call display: {state}")
        if parsed.command is None and parsed.raw_command:
            if self.plugin_api and parsed.raw_command in self.plugin_api.plugin_commands:
                self.plugin_api.plugin_commands[parsed.raw_command](parsed.args)
            else:
                print_error(f"Unknown command: {parsed.raw_command}")

        return False

    def _get_session_tree_mgr(self):
        """Get a SessionTree instance for the current sessions dir."""
        from neow.core.session_tree import SessionTree
        if self.session_manager:
            return self.session_manager.session_tree
        return SessionTree(Path.home() / ".neow" / "sessions")

    def _get_active_session_name(self) -> Optional[str]:
        """Get the active session name from _session_name or most recent JSONL."""
        if self._session_name:
            return self._session_name
        tree_mgr = self._get_session_tree_mgr()
        sessions = tree_mgr.list_sessions()
        if sessions:
            return sessions[0]["name"]
        return None

    def _handle_tree(self, parsed) -> None:
        """Handle /tree command — visualize session tree or navigate."""
        tree_mgr = self._get_session_tree_mgr()
        session_name = self._get_active_session_name()
        if not session_name:
            print_error("No active session. Use /save or /load first.")
            return

        if parsed.args and parsed.args.strip().startswith("goto "):
            entry_id = parsed.args.strip()[5:].strip()
            try:
                tree_mgr.branch_at(session_name, entry_id)
                self.conversation.messages.clear()
                self.conversation.messages.extend(tree_mgr.get_messages(session_name))
                print_info(f"Navigated to node {entry_id[:8]}")
            except (ValueError, FileNotFoundError) as e:
                print_error(str(e))
        else:
            # Show tree visualization
            try:
                tree = tree_mgr.get_tree(session_name)
                leaf_id = tree_mgr.get_leaf_id(session_name)
                if not tree:
                    print_info("Empty session tree")
                    return
                print_info(f"Session: {session_name}  (leaf: {leaf_id[:8] if leaf_id else 'none'})")
                roots = [nid for nid, n in tree.items() if n["parentId"] is None]
                for root_id in roots:
                    self._print_tree_node(tree, root_id, leaf_id, indent=0)
            except FileNotFoundError:
                print_error(f"Session not found: {session_name}")

    def _print_tree_node(self, tree: dict, node_id: str, leaf_id: Optional[str], indent: int) -> None:
        """Recursively print a tree node."""
        node = tree.get(node_id)
        if not node:
            return
        is_leaf = node_id == leaf_id
        marker = " *" if is_leaf else ""
        prefix = "  " * indent
        preview = node["content_preview"]
        if len(preview) > 60:
            preview = preview[:60] + "..."
        role_tag = node["role"]
        nid_short = node_id[:8]
        print_info(f"{prefix}[{nid_short}] {role_tag}: {preview}{marker}")
        for child_id in node.get("children", []):
            self._print_tree_node(tree, child_id, leaf_id, indent + 1)

    def _handle_branch(self, parsed) -> None:
        """Handle /branch command — branch from a specific message."""
        tree_mgr = self._get_session_tree_mgr()
        session_name = self._get_active_session_name()
        if not session_name:
            print_error("No active session. Use /save or /load first.")
            return

        if parsed.args:
            entry_id = parsed.args.strip()
            try:
                tree_mgr.branch_at(session_name, entry_id)
                self.conversation.messages.clear()
                self.conversation.messages.extend(tree_mgr.get_messages(session_name))
                print_info(f"Branched at {entry_id[:8]}")
            except (ValueError, FileNotFoundError) as e:
                print_error(str(e))
        else:
            # Branch from parent of last message
            leaf_id = tree_mgr.get_leaf_id(session_name)
            if not leaf_id:
                print_error("Session is empty")
                return
            tree = tree_mgr.get_tree(session_name)
            parent_id = tree.get(leaf_id, {}).get("parentId")
            if parent_id:
                tree_mgr.branch_at(session_name, parent_id)
                self.conversation.messages.clear()
                self.conversation.messages.extend(tree_mgr.get_messages(session_name))
                print_info(f"Branched at {parent_id[:8]} (removed last message)")
            else:
                print_info("Cannot branch: at root node")

    def _process_input(self, user_input: str) -> None:
        """Process user input with AI.

        Args:
            user_input: User input string.
        """
        import time
        self._last_activity_time = time.monotonic()
        self._idle_compact_done = False

        # Auto-detect URLs in input
        if self.config and self.config.web.get("auto_detect", True):
            urls = self.URL_PATTERN.findall(user_input)
            for url in urls:
                if url not in self.conversation.web_cache:
                    try:
                        content = self.web_fetcher.fetch(url)
                        self.conversation.add_web_content(url, content)
                        print_info(f"Auto-fetched: {content.title}")
                    except Exception as e:
                        logger.warning(f"Auto-fetch failed for {url}: {e}")

        if self.event_bus:
            self.event_bus.emit("pre_prompt", prompt=user_input, conversation=self.conversation)

        # Token hard limit check
        if self.token_tracker and self.token_tracker.check_max_tokens():
            print_error("Token limit reached. Use /compact to summarize history, or /cost to check usage.")
            return

        try:
            if self.architect_mode:
                self._process_architect(user_input)
            elif self.streaming:
                self._process_input_stream(user_input)
            else:
                response = self.conversation.get_response(user_input)
                if response.content:
                    self._msg_counter += 1
                    print_assistant_message(
                        response.content,
                        msg_num=self._msg_counter,
                        timestamp=_now_ts(),
                    )
        except Exception as e:
            print_error(f"Failed to get response: {e}")
            logger.error(f"Failed to get response: {e}")

        if self.event_bus:
            self.event_bus.emit("post_response", conversation=self.conversation)

        # Token usage warnings
        if self.token_tracker:
            warn = self.token_tracker.check_warn_threshold()
            if warn:
                print_warning(warn)

        # Auto-compact when approaching token limit
        if self.token_tracker:
            max_t = self.config.token.get("max_tokens", 500000) if self.config else 500000
            used = self.token_tracker.session_input + self.token_tracker.session_output
            if used > max_t * 0.8:
                print_warning("Token usage above 80% threshold. Auto-compacting...")
                try:
                    result = self.conversation.compact_incremental()
                    print_info(result)
                except Exception as e:
                    logger.warning(f"Auto-compact failed: {e}")
            elif used > max_t * 0.5 and not self._idle_compact_done:
                # Idle maintenance: compact proactively if usage is moderate
                import time
                idle_secs = time.monotonic() - self._last_activity_time
                if idle_secs > 30 and len(self.conversation.messages) > 8:
                    print_info("Idle maintenance: compacting conversation...")
                    try:
                        result = self.conversation.compact_incremental()
                        print_info(result)
                        self._idle_compact_done = True
                    except Exception as e:
                        logger.warning(f"Idle compact failed: {e}")
        if self.conversation.pending_lint_feedback:
            feedback = self.conversation.pending_lint_feedback
            self.conversation.pending_lint_feedback = None
            print_info("Auto-fixing lint/test errors...")
            self._process_input(feedback)

    def _process_input_stream(self, user_input: str) -> None:
        """Process user input with streaming output + dynamic spinner.

        Uses a Rich ``Live`` region to wrap the assistant's streaming output in
        a Panel (matching the non-streaming assistant panel) instead of writing
        raw text to stdout.  Each contiguous content segment between tool calls
        gets its own Panel; tool calls / results interrupt and print normally.
        """
        from rich.live import Live

        try:
            stream = self.conversation.get_response_stream(user_input)
            all_reasoning: list[str] = []
            spinner_text = "Thinking..."

            status = console.status(spinner_text, spinner="dots")
            self._stream_status = status
            status.start()

            # Per-segment buffer + Live region for the assistant Panel.
            # One assistant turn shares a single message number + timestamp,
            # even when interrupted by tool calls (multiple content segments).
            content_buffer = ""
            live: Optional[Live] = None
            assistant_num: Optional[int] = None
            assistant_ts: Optional[str] = None

            def _finalize_segment() -> None:
                """Render final Markdown for current segment and close its Live."""
                nonlocal live, content_buffer
                if live is not None:
                    if content_buffer:
                        live.update(
                            format_assistant_panel(
                                content_buffer,
                                msg_num=assistant_num,
                                timestamp=assistant_ts,
                            ),
                            refresh=True,
                        )
                    live.stop()
                    live = None
                    content_buffer = ""

            try:
                for chunk in stream:
                    if chunk.progress:
                        ptype = chunk.progress.get("type")
                        name = chunk.progress.get("name", "")
                        if ptype == "tool_start":
                            _finalize_segment()
                            status.stop()
                            print_tool_call(
                                name,
                                chunk.progress.get("args", {}),
                                verbose=self.verbose_tools,
                            )
                            status.start()
                            spinner_text = f"Executing {name}..."
                        elif ptype == "tool_end":
                            tool_result = chunk.progress.get("result", "")
                            _finalize_segment()
                            if tool_result:
                                status.stop()
                                print_tool_result(tool_result)
                                status.start()
                            spinner_text = "Thinking..."
                        elif ptype == "reasoning_start":
                            spinner_text = "Thinking..."
                        elif ptype == "reasoning_end":
                            if all_reasoning:
                                chars = sum(len(r) for r in all_reasoning)
                                spinner_text = f"Thinking... ({chars:,} chars)"
                        status.update(spinner_text)
                        continue

                    if chunk.reasoning_delta:
                        all_reasoning.append(chunk.reasoning_delta)
                        chars = sum(len(r) for r in all_reasoning)
                        spinner_text = f"Thinking... ({chars:,} chars)"
                        if len(all_reasoning) % 4 == 0:
                            status.update(spinner_text)

                    if chunk.content_delta:
                        if live is None:
                            # Start of a new content segment: stop spinner,
                            # show reasoning dropdown, open a Live Panel.
                            # Allocate this assistant turn's number + timestamp
                            # on first content; reused by later segments.
                            if assistant_num is None:
                                self._msg_counter += 1
                                assistant_num = self._msg_counter
                                assistant_ts = _now_ts()
                            status.stop()
                            if all_reasoning:
                                full_reasoning = "".join(all_reasoning)
                                self._last_reasoning = full_reasoning
                                console.print(
                                    format_reasoning_dropdown(full_reasoning)
                                )
                                all_reasoning.clear()
                            content_buffer = ""
                            live = Live(
                                format_streaming_assistant_panel(
                                    "",
                                    msg_num=assistant_num,
                                    timestamp=assistant_ts,
                                ),
                                console=console,
                                refresh_per_second=20,
                                transient=False,
                            )
                            live.start()
                        content_buffer += chunk.content_delta
                        live.update(
                            format_streaming_assistant_panel(
                                content_buffer,
                                msg_num=assistant_num,
                                timestamp=assistant_ts,
                            )
                        )
            finally:
                _finalize_segment()
                try:
                    status.stop()
                except Exception:
                    pass
                self._stream_status = None

            # If reasoning was captured but no content was produced (e.g. tool-only turn)
            if all_reasoning:
                full_reasoning = "".join(all_reasoning)
                self._last_reasoning = full_reasoning
                console.print(format_reasoning_dropdown(full_reasoning))
        except StopIteration:
            pass
        except Exception as e:
            sys.stdout.write("\n")
            sys.stdout.flush()
            raise

    def _process_architect(self, user_input: str) -> None:
        """Process input through architect orchestrator.

        Args:
            user_input: User input string.
        """
        from neow.core.architect import ArchitectOrchestrator
        from neow.cli.main import create_model_client

        try:
            arch_config = self.config.architect
            planner_client = create_model_client(self.config, arch_config["planner"])
            executor_client = create_model_client(self.config, arch_config["executor"])

            orch = ArchitectOrchestrator(
                planner_client, executor_client, self.conversation.tool_executor
            )
            result = orch.run(user_input)
            self._msg_counter += 1
            print_assistant_message(
                result, msg_num=self._msg_counter, timestamp=_now_ts()
            )
        except Exception as e:
            print_error(f"Architect mode error: {e}")
            logger.error(f"Architect mode error: {e}")
