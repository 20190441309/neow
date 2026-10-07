"""Slash-command dispatcher for the TUI (REPL parity, plan task 13).

Inline commands call the same core APIs as ``REPL._handle_command``
(``neow/cli/repl.py:625-931``); screen-backed commands are delegated to
``hooks`` registered by ``ChatScreen`` (plan task 14).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from neow.cli.commands import Command, ParsedCommand
from neow.utils.logger import logger


@dataclass
class CommandResult:
    text: str = ""
    should_exit: bool = False
    kind: str = "info"  # info | warn | error


class CommandDispatcher:
    """Maps parsed slash commands to core actions or UI hooks."""

    def __init__(
        self,
        *,
        conversation: Any,
        config: Any = None,
        session_manager: Any = None,
        token_tracker: Any = None,
        approval_policy: Any = None,
        web_fetcher: Any = None,
        event_bus: Any = None,
        plugin_api: Any = None,
        hooks: Optional[Dict[str, Callable[[], Any]]] = None,
    ):
        self.conversation = conversation
        self.config = config
        self.session_manager = session_manager
        self.token_tracker = token_tracker
        self.approval_policy = approval_policy
        self.web_fetcher = web_fetcher
        self.event_bus = event_bus
        self.plugin_api = plugin_api
        self.hooks: Dict[str, Callable[[], Any]] = hooks or {}
        self.verbose = False
        self.architect_mode = False

    # -- entry point ---------------------------------------------------

    def dispatch(self, parsed: ParsedCommand) -> CommandResult:
        if parsed.command is None:
            return self._unknown(parsed)
        method = getattr(self, f"_cmd_{parsed.command.value}", None)
        args = (parsed.args or "").strip()
        if method is None:
            return self._hook(parsed.command.value)
        return method(args)

    # -- helpers -------------------------------------------------------

    def _hook(self, name: str, fallback: str = "") -> CommandResult:
        hook = self.hooks.get(name)
        if hook is None:
            return CommandResult(
                fallback or f"/{name} is not available in the TUI yet",
                kind="warn",
            )
        result = hook()
        if isinstance(result, CommandResult):
            return result
        if result is None:
            return CommandResult("")
        return CommandResult(str(result))

    def _unknown(self, parsed: ParsedCommand) -> CommandResult:
        raw = parsed.raw_command or ""
        plugin_commands = getattr(self.plugin_api, "plugin_commands", None) or {}
        if raw in plugin_commands:
            try:
                plugin_commands[raw](parsed.args)
                return CommandResult(f"Plugin command executed: {raw}")
            except Exception as exc:  # noqa: BLE001
                return CommandResult(str(exc), kind="error")
        return CommandResult(f"Unknown command: {raw}", kind="error")

    def _set_config(self, section: str, key: str, value: Any) -> bool:
        if self.config is None:
            return False
        try:
            self.config._config.setdefault(section, {})[key] = value
            return True
        except Exception:
            return False

    # -- inline commands ----------------------------------------------

    def _cmd_help(self, args: str) -> CommandResult:
        return self._hook("help")

    def _cmd_clear(self, args: str) -> CommandResult:
        self.conversation.clear_history()
        return CommandResult("Conversation history cleared")

    def _cmd_exit(self, args: str) -> CommandResult:
        return CommandResult("Goodbye!", should_exit=True)

    def _cmd_model(self, args: str) -> CommandResult:
        return self._hook("model")

    def _cmd_diff(self, args: str) -> CommandResult:
        return self._hook("diff")

    def _cmd_commit(self, args: str) -> CommandResult:
        if args:
            from neow.tools.git import GitError, git_commit

            try:
                return CommandResult(git_commit(args))
            except GitError as exc:
                return CommandResult(str(exc), kind="error")
        return self._hook("commit_ai")

    def _cmd_undo(self, args: str) -> CommandResult:
        return self._hook("undo")

    def _cmd_add(self, args: str) -> CommandResult:
        if not args:
            return CommandResult("Usage: /add <file_path>", kind="error")
        try:
            return CommandResult(self.conversation.add_context_file(args))
        except FileNotFoundError as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_drop(self, args: str) -> CommandResult:
        if not args:
            return CommandResult("Usage: /drop <file_path>", kind="error")
        try:
            return CommandResult(self.conversation.drop_context_file(args))
        except KeyError as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_ls(self, args: str) -> CommandResult:
        files = self.conversation.list_context_files()
        if not files:
            return CommandResult("No files in context")
        return CommandResult("Context files:\n" + "\n".join(f"  {f}" for f in files))

    def _cmd_lint(self, args: str) -> CommandResult:
        from neow.tools.lint_test import run_lint

        if args == "on":
            self._set_config("lint_test", "auto_lint", True)
            return CommandResult("Auto-lint enabled")
        if args == "off":
            self._set_config("lint_test", "auto_lint", False)
            return CommandResult("Auto-lint disabled")
        result = run_lint(Path.cwd())
        if not result.success:
            self.conversation.pending_lint_feedback = (
                f"Please fix the following lint errors:\n{result.output}"
            )
            return CommandResult(result.output or "Lint failed", kind="warn")
        return CommandResult(result.output or "Lint passed")

    def _cmd_test(self, args: str) -> CommandResult:
        from neow.tools.lint_test import run_tests

        if args == "on":
            self._set_config("lint_test", "auto_test", True)
            return CommandResult("Auto-test enabled")
        if args == "off":
            self._set_config("lint_test", "auto_test", False)
            return CommandResult("Auto-test disabled")
        result = run_tests(Path.cwd())
        if not result.success:
            self.conversation.pending_lint_feedback = (
                f"Please fix the following test failures:\n{result.output}"
            )
            return CommandResult(result.output or "Tests failed", kind="warn")
        return CommandResult(result.output or "Tests passed")

    def _cmd_architect(self, args: str) -> CommandResult:
        self.architect_mode = True
        return CommandResult(
            "Architect mode enabled. Tasks will be planned and dispatched to sub-agents. "
            "Use /code to return to normal coding mode."
        )

    def _cmd_code(self, args: str) -> CommandResult:
        self.architect_mode = False
        return CommandResult("Normal coding mode restored.")

    def _cmd_save(self, args: str) -> CommandResult:
        if self.session_manager is None:
            return CommandResult("Session manager not available", kind="error")
        name = self.session_manager.save(self.conversation, args or None)
        try:
            tree_mgr = self.session_manager.session_tree
            model = getattr(
                getattr(self.conversation, "model_client", None), "model", "unknown"
            )
            tree_mgr.create(name, model)
            for message in self.conversation.messages:
                meta_keys = {"tool_call_id", "tool_calls", "type", "name"}
                meta = {k: message[k] for k in meta_keys if k in message}
                tree_mgr.append(
                    name,
                    message.get("role", "user"),
                    message.get("content", ""),
                    metadata=meta if meta else None,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"JSONL save failed: {exc}")
        return CommandResult(f"Session saved: {name}")

    def _cmd_load(self, args: str) -> CommandResult:
        return self._hook("load")

    def _cmd_history(self, args: str) -> CommandResult:
        return self._hook("history")

    def _cmd_cost(self, args: str) -> CommandResult:
        if "cost" in self.hooks:
            return self._hook("cost")
        if self.token_tracker is None:
            return CommandResult("Token tracker not available", kind="error")
        return CommandResult(str(self.token_tracker.get_session_summary()))

    def _cmd_web(self, args: str) -> CommandResult:
        if not args:
            return CommandResult("Usage: /web <url>", kind="error")
        if self.web_fetcher is None:
            return CommandResult("Web fetcher not available", kind="error")
        try:
            content = self.web_fetcher.fetch(args)
            self.conversation.add_web_content(args, content)
            return CommandResult(
                f"Fetched: {content.title} ({len(content.text)} chars)"
            )
        except Exception as exc:  # noqa: BLE001
            return CommandResult(f"Failed to fetch URL: {exc}", kind="error")

    def _cmd_think(self, args: str) -> CommandResult:
        if "think" in self.hooks:
            return self._hook("think")
        return CommandResult(
            "No thinking content available. Reasoning is captured during "
            "AI responses that use thinking mode."
        )

    def _cmd_compact(self, args: str) -> CommandResult:
        if args.startswith("--keep-tokens"):
            parts = args.split()
            try:
                keep = int(parts[1]) if len(parts) > 1 else 4000
            except (ValueError, IndexError):
                keep = 4000
            return CommandResult(
                str(self.conversation.compact_incremental(keep_recent_tokens=keep))
            )
        if "incremental" in args.lower():
            return CommandResult(str(self.conversation.compact_incremental()))
        if "handoff" in args.lower():
            handoff = self.conversation.compact_with_handoff()
            if handoff:
                self.conversation.add_message(
                    "user", "[Session handoff from previous conversation]"
                )
                self.conversation.add_message("assistant", handoff)
            return CommandResult(
                f"Handoff complete: {len(handoff)} char summary injected"
            )
        return CommandResult(str(self.conversation.compact()))

    def _cmd_export(self, args: str) -> CommandResult:
        if self.session_manager is None:
            return CommandResult("Session manager not available", kind="error")
        path = self.session_manager.export_markdown(self.conversation, args or None)
        return CommandResult(f"Exported to: {path}")

    def _cmd_image(self, args: str) -> CommandResult:
        if not args:
            return CommandResult("Usage: /image <file_path>", kind="error")
        try:
            return CommandResult(str(self.conversation.queue_image(args)))
        except (FileNotFoundError, ValueError) as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_approval(self, args: str) -> CommandResult:
        from neow.core.approval import ApprovalMode

        if self.approval_policy is None:
            return CommandResult("Approval mode not configured")
        if not args:
            lines = [
                f"Approval mode: {self.approval_policy.mode.value}",
                "Available: always-ask | write | yolo",
            ]
            if self.approval_policy.tool_overrides:
                lines.append(f"Overrides: {self.approval_policy.tool_overrides}")
            return CommandResult("\n".join(lines))
        mode_map = {
            "always-ask": ApprovalMode.ALWAYS_ASK,
            "always_ask": ApprovalMode.ALWAYS_ASK,
            "ask": ApprovalMode.ALWAYS_ASK,
            "write": ApprovalMode.WRITE,
            "w": ApprovalMode.WRITE,
            "yolo": ApprovalMode.YOLO,
            "y": ApprovalMode.YOLO,
        }
        new_mode = mode_map.get(args.lower())
        if new_mode is None:
            return CommandResult(
                f"Unknown mode: {args}. Use: always-ask, write, yolo", kind="error"
            )
        self.approval_policy.set_mode(new_mode)
        self._set_config("approval", "mode", new_mode.value)
        return CommandResult(f"Approval mode set to: {new_mode.value}")

    def _cmd_tree(self, args: str) -> CommandResult:
        return self._hook("tree")

    def _cmd_branch(self, args: str) -> CommandResult:
        return self._hook("branch")

    def _cmd_verbose(self, args: str) -> CommandResult:
        self.verbose = not self.verbose
        state = (
            "expanded (all parameters shown)"
            if self.verbose
            else "collapsed (one-line summary)"
        )
        return CommandResult(f"Tool call display: {state}")


__all__ = ["CommandDispatcher", "CommandResult"]
