"""REPL (Read-Eval-Print Loop) for Neow CLI."""

import re
import sys
from typing import Optional

from prompt_toolkit import PromptSession
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
    print_diff,
    print_error,
    print_info,
    print_status_bar,
)
from neow.utils.logger import logger
from neow.core.config import Config


def _format_toolbar_text(
    model: str, tokens_used: int, cost: float, branch: str
) -> str:
    """Format status bar text for prompt_toolkit bottom toolbar."""
    parts = [f" {model}", f"ctx: {tokens_used:,}", f"cost: ${cost:.4f}"]
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
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup prompt session with history and bottom status bar."""
        try:
            test_session = PromptSession()
            try:
                history = FileHistory(".neow_history")
                self.session = PromptSession(
                    history=history,
                    bottom_toolbar=self._bottom_toolbar,
                )
            except Exception:
                self.session = test_session
        except Exception as e:
            logger.warning(f"Failed to setup prompt-toolkit: {e}")
            self.session = None

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

    def start(self) -> None:
        """Start the REPL loop."""
        model_name = getattr(self.conversation.model_client, "model", "")
        print_welcome(model=model_name)
        if self.event_bus:
            self.event_bus.emit("session_start", conversation=self.conversation)

        while True:
            try:
                user_input = self._get_input()
                if not user_input or not user_input.strip():
                    continue

                # Show user message in panel
                print_user_message(user_input)

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
        """
        try:
            if self.session is None:
                return input("")
            return self.session.prompt("")
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
            print_welcome()
        elif parsed.command == Command.CLEAR:
            self.conversation.clear_history()
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
                diff = git_diff()
                if diff:
                    print_diff(diff)
                else:
                    print_info("No uncommitted changes")
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
                print_info(f"Session saved: {name}")
            else:
                print_error("Session manager not available")
        elif parsed.command == Command.LOAD:
            if self.session_manager and parsed.args:
                if self.session_manager.restore(parsed.args, self.conversation):
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

        # Plugin command dispatch for unknown /commands
        if parsed.command is None and parsed.raw_command:
            if self.plugin_api and parsed.raw_command in self.plugin_api.plugin_commands:
                self.plugin_api.plugin_commands[parsed.raw_command](parsed.args)
            else:
                print_error(f"Unknown command: {parsed.raw_command}")

        return False

    def _process_input(self, user_input: str) -> None:
        """Process user input with AI.

        Args:
            user_input: User input string.
        """
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

        try:
            if self.architect_mode:
                self._process_architect(user_input)
            elif self.streaming:
                self._process_input_stream(user_input)
            else:
                response = self.conversation.get_response(user_input)
                if response.content:
                    print_assistant_message(response.content)
        except Exception as e:
            print_error(f"Failed to get response: {e}")
            logger.error(f"Failed to get response: {e}")

        if self.event_bus:
            self.event_bus.emit("post_response", conversation=self.conversation)

        # Process pending lint/test feedback
        if self.conversation.pending_lint_feedback:
            feedback = self.conversation.pending_lint_feedback
            self.conversation.pending_lint_feedback = None
            print_info("Auto-fixing lint/test errors...")
            self._process_input(feedback)

    def _process_input_stream(self, user_input: str) -> None:
        """Process user input with streaming output + spinner."""
        try:
            stream = self.conversation.get_response_stream(user_input)

            with console.status("[bold green]Thinking...[/bold green]", spinner="dots"):
                first_chunk = next(stream, None)

            if first_chunk is None:
                return

            content_started = False

            def _ensure_content_header():
                nonlocal content_started
                if not content_started:
                    content_started = True
                    sys.stdout.write("\n\033[1;32mNeow:\033[0m ")
                    sys.stdout.flush()

            # Process first chunk (skip reasoning_delta — hidden by design)
            if first_chunk.content_delta:
                _ensure_content_header()
                sys.stdout.write(first_chunk.content_delta)
                sys.stdout.flush()

            # Process remaining chunks (skip reasoning_delta — hidden by design)
            for chunk in stream:
                if chunk.content_delta:
                    _ensure_content_header()
                    sys.stdout.write(chunk.content_delta)
                    sys.stdout.flush()

            sys.stdout.write("\n")
            sys.stdout.flush()
        except StopIteration:
            pass
        except Exception as e:
            sys.stdout.write("\n")
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
            print_assistant_message(result)
        except Exception as e:
            print_error(f"Architect mode error: {e}")
            logger.error(f"Architect mode error: {e}")
