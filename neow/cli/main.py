"""Main entry point for Neow CLI."""

import logging
import sys
from pathlib import Path

import click

from neow.core.config import Config
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.core.security import SecurityGuard
from neow.core.prompts import get_system_prompt, get_tool_definitions
from neow.models.deepseek import DeepSeekClient
from neow.models.anthropic import AnthropicClient
from neow.models.openai import OpenAIClient
from neow.tools.file_ops import read_file, write_file, edit_file, create_file, delete_file
from neow.tools.command import execute_command
from neow.tools.search import search_code
from neow.tools.git import git_status, git_diff, git_commit, git_log, auto_commit, GitError
from neow.cli.repl import REPL
from neow.utils.logger import setup_logger, logger
from neow.utils.formatter import print_error, print_info
from neow.core.token_tracker import TokenTracker
from neow.core.session import SessionManager


def create_model_client(config: Config, model_name: str):
    """Create model client based on configuration.

    Args:
        config: Configuration object.
        model_name: Name of the model to create.

    Returns:
        Model client instance.
    """
    model_config = config.get_model_config(model_name)

    # Determine client type based on model name prefix
    model_lower = model_name.lower()
    if "deepseek" in model_lower:
        return DeepSeekClient(
            api_key=model_config["api_key"], model=model_config["model"]
        )
    elif "anthropic" in model_lower or "claude" in model_lower:
        return AnthropicClient(
            api_key=model_config["api_key"], model=model_config["model"]
        )
    elif "openai" in model_lower or "gpt" in model_lower:
        return OpenAIClient(
            api_key=model_config["api_key"], model=model_config["model"]
        )
    else:
        raise ValueError(f"Unknown model: {model_name}")


def setup_tools(executor: ToolExecutor) -> None:
    """Register tools with executor.

    Args:
        executor: ToolExecutor instance.
    """
    executor.register_tool("read_file", read_file)
    executor.register_tool("write_file", write_file)
    executor.register_tool("edit_file", edit_file)
    executor.register_tool("create_file", create_file)
    executor.register_tool("delete_file", delete_file)
    executor.register_tool("execute_command", execute_command)
    executor.register_tool("search_code", search_code)
    executor.register_tool("git_status", git_status)
    executor.register_tool("git_diff", git_diff)
    executor.register_tool("git_commit", git_commit)
    executor.register_tool("git_log", git_log)


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("prompt", required=False, default=None)
@click.option("--file", "-f", multiple=True, type=click.Path(exists=True),
              help="Files to add to context")
@click.option("--message-file", type=click.Path(exists=True),
              help="Read prompt from file")
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--model", "-m", type=str, help="AI model to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(prompt, file, message_file, config, model, verbose):
    """Neow - A lightweight, general-purpose AI CLI assistant."""
    # Detect pipe input
    piped_input = ""
    if not sys.stdin.isatty():
        piped_input = sys.stdin.read().strip()

    # Merge piped input into prompt
    if piped_input:
        if prompt:
            prompt = f"{piped_input}\n\n{prompt}"
        else:
            prompt = piped_input

    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    setup_logger(level=log_level)

    try:
        # Load configuration
        config_path = Path(config) if config else None
        cfg = Config(config_path)

        # Determine model to use
        model_name = model or cfg.default_model
        print_info(f"Using model: {model_name}")

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

        # Wire git auto-commit callback
        if cfg.git.get("auto_commit", True):
            def _on_file_change(tool_name: str, file_path: str):
                try:
                    auto_commit(file_path, action=tool_name)
                except GitError as e:
                    logger.warning(f"Auto-commit failed: {e}")

                # Auto-lint
                if cfg.lint_test.get("auto_lint"):
                    from neow.tools.lint_test import run_lint
                    from pathlib import Path as P
                    lint_result = run_lint(P.cwd())
                    if not lint_result.success:
                        conversation.pending_lint_feedback = (
                            f"Lint errors after editing {file_path}:\n{lint_result.output}"
                        )

                # Auto-test
                if cfg.lint_test.get("auto_test"):
                    from neow.tools.lint_test import run_tests
                    from pathlib import Path as P
                    test_result = run_tests(P.cwd())
                    if not test_result.success:
                        conversation.pending_lint_feedback = (
                            f"Test failures after editing {file_path}:\n{test_result.output}"
                        )

            executor.on_file_change = _on_file_change

        # Setup conversation manager
        token_tracker = TokenTracker(cfg)
        conversation = ConversationManager(model_client, executor, token_tracker=token_tracker)

        # Set system prompt and tools
        conversation.set_system_prompt(get_system_prompt())
        conversation.set_tools(get_tool_definitions())

        # Read message from file if specified
        if message_file:
            file_content = Path(message_file).read_text(encoding="utf-8")
            prompt = f"{file_content}\n\n{prompt}" if prompt else file_content

        # Add --file arguments to context
        for f in file:
            conversation.add_context_file(f)

        # Non-interactive mode
        if prompt:
            response = conversation.get_response(prompt)
            if response.content:
                print(response.content)
            # Auto-save
            session_manager = SessionManager(Path.home() / ".neow" / "sessions")
            session_manager.save(conversation)
            sys.exit(0)

        # Start REPL
        streaming_enabled = cfg.streaming.get("enabled", True)
        session_manager = SessionManager(Path.home() / ".neow" / "sessions")
        repl = REPL(conversation, config=cfg, streaming=streaming_enabled,
                    token_tracker=token_tracker, session_manager=session_manager)
        repl.start()

    except Exception as e:
        print_error(f"Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
