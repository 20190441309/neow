"""Slash-command dispatcher for the TUI (REPL parity, plan task 13).

Inline commands call the same core APIs as ``REPL._handle_command``
(``neow/cli/repl.py:625-931``); screen-backed commands are delegated to
``hooks`` registered by ``ChatScreen`` (plan task 14).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from neow.cli.commands import ParsedCommand
from neow.utils.logger import logger


@dataclass
class CommandResult:
    text: str = ""
    should_exit: bool = False
    kind: str = "info"  # info | warn | error


def describe_memory(memory: Any) -> str:
    """One line per loaded memory file, plus any warnings."""
    files = getattr(memory, "files", None) or []
    if not files:
        return (
            "没有加载记忆文件。在项目根目录放 AGENTS.md / NEOW.md，"
            "或用 /init 生成、/memory add <text> 追加。"
        )
    lines = ["已加载的记忆文件（后面的优先）："]
    lines += [f"  {f.path}  ({f.chars:,} chars)" for f in files]
    lines += [f"  ⚠ {w}" for w in getattr(memory, "warnings", [])]
    return "\n".join(lines)


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
        hooks: Optional[Dict[str, Callable[..., Any]]] = None,
    ):
        self.conversation = conversation
        self.config = config
        self.session_manager = session_manager
        self.token_tracker = token_tracker
        self.approval_policy = approval_policy
        self.web_fetcher = web_fetcher
        self.event_bus = event_bus
        self.plugin_api = plugin_api
        self.hooks: Dict[str, Callable[..., Any]] = hooks or {}
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
        if not args and "clear" in self.hooks:
            return self._hook("clear")
        self.conversation.clear_history()
        return CommandResult("Conversation history cleared")

    def _cmd_exit(self, args: str) -> CommandResult:
        return CommandResult("Goodbye!", should_exit=True)

    def _cmd_model(self, args: str) -> CommandResult:
        if args == "magpie":
            if "model_sync" in self.hooks:
                return self._hook("model_sync")
            from neow.models.management import sync_magpie

            try:
                count = sync_magpie(self.config)
                return CommandResult(f"Imported {count} Magpie models")
            except Exception as exc:
                return CommandResult(str(exc), kind="error")
        if args == "add":
            return self._hook("model_add")
        if args:
            from neow.cli.main import create_model_client

            try:
                name = self.config.resolve_model_alias(args)
                if "model_switch" in self.hooks:
                    return self.hooks["model_switch"](name)
                client = create_model_client(self.config, name)
                if not client.validate_connection():
                    return CommandResult(f"Failed to connect to {name}", kind="error")
                self.config.set_default_model(name)
                self.conversation.model_client = client
                return CommandResult(f"Switched to model: {name}")
            except Exception as exc:
                return CommandResult(str(exc), kind="error")
        return self._hook("model")

    def _cmd_effort(self, args: str) -> CommandResult:
        from neow.models.base import EFFORT_LEVELS

        client = self.conversation.model_client
        if client is None:
            return CommandResult("No model configured", kind="error")
        name = getattr(client, "config_name", None)
        if not args:
            if "effort" in self.hooks:
                return self._hook("effort")
            level = getattr(client, "effort", None) or "off"
            return CommandResult(
                f"Effort: {level}\nAvailable: off, {', '.join(EFFORT_LEVELS)}"
            )
        level = args.strip().lower()
        if level not in ("off",) + EFFORT_LEVELS:
            return CommandResult(
                f"Unknown effort: {level}. Use: off, {', '.join(EFFORT_LEVELS)}",
                kind="error",
            )
        client.effort = None if level == "off" else level
        if name and self.config is not None:
            try:
                self.config.save_model(name, {"effort": level})
            except Exception as exc:
                return CommandResult(
                    f"Set for this session, but failed to persist: {exc}",
                    kind="error",
                )
        return CommandResult(f"Effort set to: {level}")

    def _cmd_diff(self, args: str) -> CommandResult:
        return self._hook("diff")

    def _cmd_commit(self, args: str) -> CommandResult:
        if not args and "commit" in self.hooks:
            return self._hook("commit")
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
            if "add" in self.hooks:
                return self._hook("add")
            return CommandResult("Usage: /add <file_path>", kind="error")
        try:
            return CommandResult(self.conversation.add_context_file(args))
        except FileNotFoundError as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_drop(self, args: str) -> CommandResult:
        if not args:
            if "drop" in self.hooks:
                return self._hook("drop")
            return CommandResult("Usage: /drop <file_path>", kind="error")
        try:
            return CommandResult(self.conversation.drop_context_file(args))
        except KeyError as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_imgdiff(self, args: str) -> CommandResult:
        if not args and "imgdiff" in self.hooks:
            return self._hook("imgdiff")
        parts = args.split()
        if len(parts) != 2:
            return CommandResult("Usage: /imgdiff <before> <after>", kind="error")
        import time

        from neow.tools.imgdiff import ImageDiffError, diff_images

        out_path = str(Path.home() / ".neow" / "imgdiff" / f"{int(time.time())}.png")
        try:
            result = diff_images(parts[0], parts[1], out_path)
        except ImageDiffError as exc:
            return CommandResult(str(exc), kind="error")
        status = "differs" if result.changed else "no visual difference"
        self.conversation.queue_image(result.out_path)
        return CommandResult(
            f"Diff ({status}, {result.size[0]}x{result.size[1]}): {result.out_path} — "
            "queued for the next message (no inline preview in the TUI)"
        )

    def _cmd_ls(self, args: str) -> CommandResult:
        if not args and "ls" in self.hooks:
            return self._hook("ls")
        files = self.conversation.list_context_files()
        if not files:
            return CommandResult("No files in context")
        return CommandResult("Context files:\n" + "\n".join(f"  {f}" for f in files))

    def _cmd_lint(self, args: str) -> CommandResult:
        if not args and "lint" in self.hooks:
            return self._hook("lint")
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
        if not args and "test" in self.hooks:
            return self._hook("test")
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
        if not args and "architect" in self.hooks:
            return self._hook("architect")
        self.architect_mode = True
        return CommandResult(
            "Architect mode enabled. The planner model turns each request "
            "into a task list that the agent then works through. Use /code "
            "to return to normal coding mode."
        )

    def _cmd_code(self, args: str) -> CommandResult:
        if not args and "code" in self.hooks:
            return self._hook("code")
        self.architect_mode = False
        return CommandResult("Normal coding mode restored.")

    def _cmd_mode(self, args: str) -> CommandResult:
        if "mode" in self.hooks:
            return self._hook("mode")
        mode = "architect" if self.architect_mode else "code"
        return CommandResult(f"Current mode: {mode}")

    def _cmd_save(self, args: str) -> CommandResult:
        if not args and "save" in self.hooks:
            return self._hook("save")
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
            if "web" in self.hooks:
                return self._hook("web")
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
        if not args:
            if "thinking" in self.hooks:
                return self._hook("thinking")
            if "think" in self.hooks:
                return self._hook("think")
        return self._cmd_thinking(args or "view")

    def _cmd_thinking(self, args: str) -> CommandResult:
        arg = args.strip().lower()
        if not arg and "thinking" in self.hooks:
            return self._hook("thinking")
        if arg in ("view", "detail", "trace", "show", "history"):
            if "think" in self.hooks:
                return self._hook("think")
            return CommandResult(
                "No thinking content available. Reasoning is captured during "
                "AI responses that use thinking mode."
            )
        if arg in ("on", "1", "true", "enable"):
            enabled = True
        elif arg in ("off", "0", "false", "hide", "disable"):
            enabled = False
        elif not arg:
            current = getattr(self.conversation, "show_thinking", True)
            enabled = not current
        else:
            return CommandResult(
                "Usage: /thinking [on|off|view] - 控制思考过程显示开关或查看详情",
                kind="warn",
            )
        self.conversation.show_thinking = enabled
        self._set_config("tui", "show_thinking", enabled)
        status = "开启 (显示)" if enabled else "关闭 (隐藏)"
        return CommandResult(f"思考过程显示已{status}。")

    def _cmd_compact(self, args: str) -> CommandResult:
        if not args and "compact" in self.hooks:
            return self._hook("compact")
        if args.startswith("--keep-tokens"):
            parts = args.split()
            try:
                keep = int(parts[1]) if len(parts) > 1 else 4000
            except (ValueError, IndexError):
                keep = 4000
            return CommandResult(
                str(self.conversation.compact_incremental(keep_recent_tokens=keep)),
                kind="compaction",
            )
        if "incremental" in args.lower():
            return CommandResult(
                str(self.conversation.compact_incremental()), kind="compaction"
            )
        if "handoff" in args.lower():
            handoff = self.conversation.compact_with_handoff()
            if handoff:
                self.conversation.add_message(
                    "user", "[Session handoff from previous conversation]"
                )
                self.conversation.add_message("assistant", handoff)
            return CommandResult(
                f"Handoff complete: {len(handoff)} char summary injected",
                kind="compaction",
            )
        return CommandResult(str(self.conversation.compact()), kind="compaction")

    def _cmd_export(self, args: str) -> CommandResult:
        if not args and "export" in self.hooks:
            return self._hook("export")
        if self.session_manager is None:
            return CommandResult("Session manager not available", kind="error")
        path = self.session_manager.export_markdown(self.conversation, args or None)
        return CommandResult(f"Exported to: {path}")

    def _cmd_image(self, args: str) -> CommandResult:
        if not args:
            if "image" in self.hooks:
                return self._hook("image")
            return CommandResult("Usage: /image <file_path>", kind="error")
        try:
            return CommandResult(str(self.conversation.queue_image(args)))
        except (FileNotFoundError, ValueError) as exc:
            return CommandResult(str(exc), kind="error")

    def _cmd_approval(self, args: str) -> CommandResult:
        if not args and "approval" in self.hooks:
            return self._hook("approval")
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
                f"Unknown mode: {args}. Use: always-ask, write, yolo",
                kind="error",
            )
        self.approval_policy.set_mode(new_mode)
        self._set_config("approval", "mode", new_mode.value)
        return CommandResult(f"Approval mode set to: {new_mode.value}")

    def _cmd_tree(self, args: str) -> CommandResult:
        return self._hook("tree")

    def _cmd_branch(self, args: str) -> CommandResult:
        return self._hook("branch")

    def _cmd_memory(self, args: str) -> CommandResult:
        if not args and "memory" in self.hooks:
            return self._hook("memory")
        from neow.core.memory import add_memory_note, load_memory

        if args.startswith("add"):
            note = args[3:].strip()
            if not note:
                return CommandResult("Usage: /memory add <text>", kind="error")
            path = add_memory_note(Path.cwd(), note)
            self.conversation.memory = load_memory(Path.cwd())
            return CommandResult(f"已写入 {path}")
        if args.startswith("reload"):
            self.conversation.memory = load_memory(Path.cwd())
        return CommandResult(describe_memory(self.conversation.memory))

    def _cmd_mcp(self, args: str) -> CommandResult:
        if not args and "mcp" in self.hooks:
            return self._hook("mcp")
        from neow.core.mcp_client import mcp_command

        manager = getattr(self.conversation, "mcp", None)
        text, kind = mcp_command(manager, args.strip(), wait=False)
        return CommandResult(text, kind=kind)

    def _cmd_rewind(self, args: str) -> CommandResult:
        if not args and "rewind" in self.hooks:
            return self._hook("rewind")
        from neow.core.checkpoints import rewind_command

        store = getattr(self.conversation, "checkpoints", None)
        if store is not None:
            store.last_result = None
        text, kind = rewind_command(store, args.strip(), self.conversation)
        result = getattr(store, "last_result", None)
        hook = self.hooks.get("rewound")
        if hook is not None and result is not None and result.cut_index is not None:
            hook(result.cut_index)
        return CommandResult(text, kind=kind)

    def _cmd_init(self, args: str) -> CommandResult:
        from neow.core.memory import INIT_PROMPT

        submit = self.hooks.get("submit")
        if submit is None:
            return CommandResult("/init is not available here", kind="warn")
        submit(INIT_PROMPT)
        return CommandResult("正在分析仓库并生成 AGENTS.md…")

    def _cmd_verbose(self, args: str) -> CommandResult:
        if not args and "verbose" in self.hooks:
            return self._hook("verbose")
        self.verbose = not self.verbose
        state = (
            "expanded (all parameters shown)"
            if self.verbose
            else "collapsed (one-line summary)"
        )
        return CommandResult(f"Tool call display: {state}")

    def _cmd_goal(self, args: str) -> CommandResult:
        arg = args.strip()
        if not arg:
            if "goal" in self.hooks:
                return self._hook("goal")
            state = getattr(self.conversation, "goal_state", None)
            if state and getattr(state, "active", False):
                return CommandResult(
                    (
                        f"正在执行目标 (第 {state.current_round}/{state.max_rounds} 轮): "
                        f"{state.goal}"
                    )
                )
            return CommandResult("Usage: /goal <目标描述> | /goal stop | /goal status")

        low = arg.lower()
        if low in ("stop", "off", "cancel", "clear"):
            stop_hook = self.hooks.get("goal_stop")
            if stop_hook is not None:
                stop_hook()
                return CommandResult("")
            state = getattr(self.conversation, "goal_state", None)
            if state is not None:
                state.active = False
            return CommandResult("已停止当前目标模式。")

        if low == "status":
            state = getattr(self.conversation, "goal_state", None)
            if state and getattr(state, "active", False):
                return CommandResult(
                    (
                        f"正在执行目标 (第 {state.current_round}/{state.max_rounds} 轮): "
                        f"{state.goal}"
                    )
                )
            return CommandResult("当前没有正在运行的目标。")

        start_hook = self.hooks.get("goal_start")
        if start_hook is not None:
            start_hook(arg)
            return CommandResult("")

        from neow.core.goal import GoalState, build_goal_initial_prompt

        self.conversation.goal_state = GoalState(goal=arg, active=True)
        submit = self.hooks.get("submit")
        if submit is not None:
            submit(build_goal_initial_prompt(arg))
        return CommandResult(f"◆ 已启动目标模式: {arg}")

    def _cmd_plan(self, args: str) -> CommandResult:
        arg = args.strip()
        if not arg:
            if "plan" in self.hooks:
                return self._hook("plan")
            return CommandResult("Usage: /plan <任务描述> | /plan approve")

        if arg.lower() in ("approve", "run", "go", "execute"):
            approve_hook = self.hooks.get("plan_approve")
            if approve_hook is not None:
                approve_hook("")
                return CommandResult("")
            submit = self.hooks.get("submit")
            if submit is not None:
                submit("请按照已制定的计划清单依次执行所有步骤。")
            return CommandResult("◆ 已批准计划并开始执行。")

        plan_start = self.hooks.get("plan_start")
        if plan_start is not None:
            plan_start(arg)
            return CommandResult("")

        plan_prompt = (
            f"请先为以下任务制定详细的分步执行计划，调用 `todo_write` 记录步骤，"
            f"如有不明确之处请调用 `ask_user` 询问，在用户确认前暂不修改代码：\n\n{arg}"
        )
        submit = self.hooks.get("submit")
        if submit is not None:
            submit(plan_prompt)
        return CommandResult(f"◆ 正在生成执行计划: {arg}")

    def _cmd_tasks(self, args: str) -> CommandResult:
        arg = args.strip()
        if not arg and "tasks" in self.hooks:
            return self._hook("tasks")
        from neow.core.background_tasks import background_task

        parts = arg.split(maxsplit=1)
        action = parts[0].lower() if parts else "list"
        rest = parts[1] if len(parts) > 1 else ""
        if action == "start":
            return CommandResult(background_task("start", command=rest))
        if action in ("stop", "status", "output"):
            return CommandResult(background_task(action, task_id=rest))
        return CommandResult(background_task("list"))

    def _cmd_skills(self, args: str) -> CommandResult:
        arg = args.strip()
        if not arg and "skills" in self.hooks:
            return self._hook("skills")
        from neow.core.skills import discover_skills, load_skill_content

        if arg:
            content = load_skill_content(arg)
            if content.startswith("Error:"):
                return CommandResult(content, kind="error")
            self.conversation.add_message(
                "user", f'<skill name="{arg}">\n{content}\n</skill>'
            )
            return CommandResult(f"◆ 已加载技能到上下文: {arg}")

        skills = discover_skills()
        if not skills:
            return CommandResult(
                "未发现技能文件 (.neow/skills/<name>/SKILL.md "
                "或 ~/.neow/skills/<name>/SKILL.md)。"
            )
        lines = ["已发现的技能："]
        for s in skills:
            lines.append(f"  ◆ {s.name} [{s.scope}] — {s.description}")
        return CommandResult("\n".join(lines))


__all__ = ["CommandDispatcher", "CommandResult"]
