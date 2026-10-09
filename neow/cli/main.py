"""Main entry point for Neow CLI."""

import logging
import warnings

# Suppress requests/urllib3 version mismatch warning before any imports trigger it
warnings.filterwarnings(
    "ignore",
    message="urllib3 .* or chardet .* doesn't match a supported version",
)
import sys
from pathlib import Path

import click

from neow.core.config import Config
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.security import SecurityGuard
from neow.core.prompts import get_system_prompt
from neow.models.factory import create_model_client
from neow.tools.builtin import builtin_specs
from neow.tools.git import auto_commit, GitError
from neow.cli.mode import ModeError, RunMode, select_run_mode, tui_available
from neow.cli.repl import REPL
from neow.utils.logger import setup_logger, logger
from neow.utils.formatter import print_error, print_info, print_warning, console
from neow.core.token_tracker import TokenTracker
from neow.core.session import SessionManager
from neow.core.plugin import EventBus, PluginAPI, PluginManager
import threading
import time


def _run_non_interactive(conversation, prompt):
    """Run a one-shot prompt in non-interactive mode with a TTY-aware spinner.

    When stdout is a TTY, wraps the blocking model call in a Rich ``status``
    spinner that ticks elapsed seconds so the user can tell the process is
    alive.  When stdout is piped (e.g. ``neow "x" | grep``), runs silently to
    keep the pipe clean.

    Args:
        conversation: ConversationManager instance.
        prompt: User prompt string.

    Returns:
        The assistant's response content (may be empty).
    """
    if not sys.stdout.isatty():
        # Piped output: stay silent during the call, print content only.
        response = conversation.get_response(prompt)
        return response.content or ""

    # TTY: show a spinner with elapsed seconds.
    status = console.status("[dim]Thinking...[/dim]", spinner="dots")
    elapsed = [0]
    stop_flag = threading.Event()

    def _tick():
        while not stop_flag.wait(1.0):
            elapsed[0] += 1
            try:
                status.update(f"[dim]Thinking... ({elapsed[0]}s)[/dim]")
            except Exception:
                pass

    status.start()
    ticker = threading.Thread(target=_tick, daemon=True)
    ticker.start()
    try:
        response = conversation.get_response(prompt)
    finally:
        stop_flag.set()
        try:
            status.stop()
        except Exception:
            pass
    return response.content or ""


def setup_mcp(cfg: Config, executor: ToolExecutor, interactive: bool, wait: bool):
    """Start configured MCP servers; their tools join the executor's registry.

    Project-defined servers (``.mcp.json``, or a repository ``.neow.json``)
    need a one-time confirmation; non-interactive runs skip them.
    """
    from neow.core.mcp_client import load_server_configs, start_manager
    from neow.core.memory import project_root

    servers = load_server_configs(
        cfg.mcp.get("servers"),
        "user" if getattr(cfg, "user_owned", True) else "project",
        str(getattr(cfg, "source_path", None) or "config"),
        project_root(Path.cwd()),
    )
    if not servers:
        return None

    def confirm(server) -> bool:
        sends = sorted(server.env) + sorted(server.headers)
        extra = f"\n    会传入：{', '.join(sends)}" if sends else ""
        print_warning(
            f"项目配置了 MCP 服务器 '{server.name}'（{server.origin}）：\n"
            f"    {server.describe()}{extra}\n"
            "它会以你的权限运行。只在信任这个仓库时启用。"
        )
        return click.confirm("启用这个服务器？", default=False)

    manager = start_manager(servers, confirm if interactive else None, wait=wait)
    manager.attach(executor.registry)
    import atexit

    atexit.register(manager.close)
    return manager


def setup_hooks(cfg: Config, event_bus=None):
    """Hooks from the user's own config, plus the ``session_start`` event.

    A repository ``.neow.json`` (read when there is no user config) cannot
    define hooks: they run arbitrary commands on every tool call.
    """
    import uuid

    from neow.core.hooks import HookRunner

    raw = cfg.hooks
    if raw and not getattr(cfg, "user_owned", True):
        print_warning(
            f"忽略 {cfg.source_path} 中的 hooks：只有 ~/.neow/config.json 或 "
            "--config 指定的配置文件可以定义 hooks"
        )
        raw = {}
    runner = HookRunner(raw, session_id=uuid.uuid4().hex, event_bus=event_bus)
    runner.run("session_start", source="startup")
    return runner


def setup_tools(executor: ToolExecutor) -> None:
    """Bind the real built-in tool implementations.

    Args:
        executor: ToolExecutor instance.
    """
    for spec in builtin_specs():
        executor.register_spec(spec)


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("prompt", required=False, default=None)
@click.option("--file", "-f", multiple=True, type=click.Path(exists=True),
              help="Files to add to context")
@click.option("--message-file", type=click.Path(exists=True),
              help="Read prompt from file")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--model", "-m", type=str, help="AI model to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--plain", is_flag=True, help="Use the classic line REPL")
@click.option("--tui", is_flag=True, help="Force the full-screen TUI")
def main(prompt, file, message_file, config, model, verbose, plain, tui):
    """Neow - A lightweight, general-purpose AI CLI assistant."""
    # Detect pipe input
    stdin_is_tty = sys.stdin.isatty()
    piped_input = ""
    if not stdin_is_tty:
        piped_input = sys.stdin.read().strip()

    # Merge piped input into prompt
    if piped_input:
        if prompt:
            prompt = f"{piped_input}\n\n{prompt}"
        else:
            prompt = piped_input

    # Select entry mode (pure logic; fails fast on bad flag combinations)
    try:
        mode = select_run_mode(
            prompt=prompt,
            plain=plain,
            tui=tui,
            stdin_tty=stdin_is_tty,
            stdout_tty=sys.stdout.isatty(),
        )
    except ModeError as exc:
        raise click.UsageError(str(exc)) from exc

    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logger(level=log_level)

    try:
        # Load configuration
        config_path = Path(config) if config else None
        cfg = Config(config_path)

        # Determine model to use
        model_name = model or cfg.default_model

        # Create model client
        model_client = create_model_client(cfg, model_name)

        # Validate connection
        if not model_client.validate_connection():
            print_error(f"Failed to connect to {model_name} API")
            sys.exit(1)

        # Setup tool executor
        executor = ToolExecutor()
        setup_tools(executor)

        # Wire security guard
        executor.security_guard = SecurityGuard()
        executor.allowed_commands = cfg.tools.get("allowed_commands", [])
        from neow.tools import command as command_tool

        command_tool.configure(
            max_timeout=(cfg.tools.get("command") or {}).get("max_timeout")
        )
        # Wire approval policy
        from neow.core.approval import ApprovalMode, ApprovalPolicy
        approval_cfg = cfg.approval
        approval_policy = ApprovalPolicy(
            mode=ApprovalMode(approval_cfg.get("mode", "write")),
            tool_overrides=approval_cfg.get("overrides", {}),
        )
        executor.approval_policy = approval_policy


        # Setup conversation manager (must be created before on_file_change callback)
        token_tracker = TokenTracker(cfg)
        conversation = ConversationManager(model_client, executor, token_tracker=token_tracker)
        conversation.max_turns = cfg.agent["max_turns"]
        conversation.max_tool_output_chars = cfg.agent["max_tool_output_chars"]
        conversation.subagent_max_turns = cfg.agent["subagent_max_turns"]
        conversation.subagent_approval = cfg.agent["subagent_approval"]

        # Initialize plugin system (must be created before on_file_change callback)
        event_bus = EventBus()
        plugin_api = PluginAPI(executor, event_bus)
        plugin_manager = PluginManager(Path.home() / ".neow" / "plugins", plugin_api)
        loaded_plugins = plugin_manager.discover_and_load()
        if loaded_plugins:
            print_info(f"Loaded plugins: {', '.join(loaded_plugins)}")

        # Wire git auto-commit callback
        if cfg.git.get("auto_commit", True):
            def _on_file_change(tool_name: str, file_path: str):
                event_bus.emit("file_changed", tool_name=tool_name, file_path=file_path)
                try:
                    auto_commit(file_path, action=tool_name)
                except GitError as e:
                    logger.warning(f"Auto-commit failed: {e}")

                # Auto-lint
                if cfg.lint_test.get("auto_lint"):
                    from neow.tools.lint_test import run_lint
                    lint_result = run_lint(Path.cwd())
                    if not lint_result.success:
                        conversation.pending_lint_feedback = (
                            f"Lint errors after editing {file_path}:\n{lint_result.output}"
                        )

                # Auto-test
                if cfg.lint_test.get("auto_test"):
                    from neow.tools.lint_test import run_tests
                    test_result = run_tests(Path.cwd())
                    if not test_result.success:
                        existing = conversation.pending_lint_feedback or ""
                        conversation.pending_lint_feedback = (
                            f"{existing}\nTest failures after editing {file_path}:\n{test_result.output}"
                        ).strip()

            executor.on_file_change = _on_file_change


        # Set system prompt; tools come from the registry on every request so
        # plugin (and later MCP) tools are visible to the model.
        conversation.set_system_prompt(get_system_prompt())
        from neow.core.memory import load_memory

        conversation.memory = load_memory(Path.cwd())
        for warning in conversation.memory.warnings:
            print_warning(f"Memory: {warning}")
        conversation.mcp = setup_mcp(
            cfg,
            executor,
            interactive=stdin_is_tty and sys.stdout.isatty(),
            # One-shot runs need the tools before the first request.
            wait=bool(prompt or message_file),
        )
        conversation.hooks = setup_hooks(cfg, event_bus)
        conversation.tool_provider = executor.get_tool_definitions

        # Read message from file if specified
        if message_file:
            file_content = Path(message_file).read_text(encoding="utf-8")
            prompt = f"{file_content}\n\n{prompt}" if prompt else file_content

        # Add --file arguments to context
        for f in file:
            conversation.add_context_file(f)

        # Non-interactive mode
        if prompt:
            content = _run_non_interactive(conversation, prompt)
            if content:
                print(content)
            # Auto-save
            session_manager = SessionManager(Path.home() / ".neow" / "sessions")
            session_manager.save(conversation)
            sys.exit(0)

        session_manager = SessionManager(Path.home() / ".neow" / "sessions")

        # Full-screen TUI (default on a TTY).  If Textual is unavailable we
        # warn and fall through to the classic REPL (spec §10).
        if mode is RunMode.TUI:
            if tui_available():
                from neow.tui import run_tui

                run_tui(
                    conversation,
                    config=cfg,
                    token_tracker=token_tracker,
                    session_manager=session_manager,
                    approval_policy=approval_policy,
                    event_bus=event_bus,
                    plugin_api=plugin_api,
                    executor=executor,
                )
                return
            print_warning(
                "Textual is not installed; falling back to the classic REPL"
            )

        # Start REPL
        streaming_enabled = cfg.streaming.get("enabled", True)

        repl = REPL(conversation, config=cfg, streaming=streaming_enabled,
                    token_tracker=token_tracker, session_manager=session_manager,
                    plugin_api=plugin_api, event_bus=event_bus)
        repl.approval_policy = approval_policy
        executor.approval_callback = repl.prompt_user_approval
        repl.start()

    except Exception as e:
        print_error(f"Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
