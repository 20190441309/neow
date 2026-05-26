"""REPL (Read-Eval-Print Loop) for Neow CLI."""

import sys
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from neow.cli.commands import Command, parse_command
from neow.core.conversation import ConversationManager
from neow.tools.git import git_diff, git_commit, git_undo, GitError
from neow.utils.formatter import (
    print_welcome,
    print_assistant_message,
    print_error,
    print_info,
)
from neow.utils.logger import logger
from neow.core.config import Config


class REPL:
    """Interactive REPL for Neow CLI."""

    def __init__(
        self,
        conversation: ConversationManager,
        config: Optional[Config] = None,
        streaming: bool = True,
    ):
        """Initialize REPL.

        Args:
            conversation: ConversationManager instance.
            config: Optional Config instance for lint/test toggles.
            streaming: Whether to use streaming output.
        """
        self.conversation = conversation
        self.config = config
        self.streaming = streaming
        self.architect_mode = False
        self.session: Optional[PromptSession] = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup prompt session with history."""
        try:
            # Try to create a simple prompt session without history first
            # to test if prompt-toolkit works in this terminal
            test_session = PromptSession()
            # If successful, setup with history
            try:
                history = FileHistory(".neow_history")
                self.session = PromptSession(history=history)
            except Exception:
                self.session = test_session
        except Exception as e:
            logger.warning(f"Failed to setup prompt-toolkit: {e}")
            self.session = None

    def start(self) -> None:
        """Start the REPL loop."""
        print_welcome()

        while True:
            try:
                user_input = self._get_input()
                if not user_input or not user_input.strip():
                    continue

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
                return input("You: ")
            return self.session.prompt("You: ")
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
                    print_info(diff)
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

        return False

    def _process_input(self, user_input: str) -> None:
        """Process user input with AI.

        Args:
            user_input: User input string.
        """
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

        # Process pending lint/test feedback
        if self.conversation.pending_lint_feedback:
            feedback = self.conversation.pending_lint_feedback
            self.conversation.pending_lint_feedback = None
            print_info("Auto-fixing lint/test errors...")
            self._process_input(feedback)

    def _process_input_stream(self, user_input: str) -> None:
        """Process user input with streaming output.

        Args:
            user_input: User input string.
        """
        try:
            sys.stdout.write("\033[1;32mAssistant:\033[0m ")
            sys.stdout.flush()

            for chunk in self.conversation.get_response_stream(user_input):
                if chunk.content_delta:
                    sys.stdout.write(chunk.content_delta)
                    sys.stdout.flush()

            sys.stdout.write("\n")
            sys.stdout.flush()
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
