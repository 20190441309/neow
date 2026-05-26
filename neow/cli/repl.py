"""REPL (Read-Eval-Print Loop) for Neow CLI."""

from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory

from neow.cli.commands import Command, parse_command
from neow.core.conversation import ConversationManager
from neow.utils.formatter import (
    print_welcome,
    print_assistant_message,
    print_tool_call,
    print_error,
    print_info,
)
from neow.utils.logger import logger


class REPL:
    """Interactive REPL for Neow CLI."""

    def __init__(self, conversation: ConversationManager):
        """Initialize REPL.

        Args:
            conversation: ConversationManager instance.
        """
        self.conversation = conversation
        self.session: Optional[PromptSession] = None
        self._setup_session()

    def _setup_session(self) -> None:
        """Setup prompt session with history."""
        try:
            history = FileHistory(".neow_history")
            self.session = PromptSession(history=history)
        except Exception as e:
            logger.warning(f"Failed to setup history: {e}")
            self.session = PromptSession()

    def start(self) -> None:
        """Start the REPL loop."""
        print_welcome()

        while True:
            try:
                user_input = self._get_input()
                if not user_input:
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
                print_info(f"Switching to model: {parsed.args}")
                # TODO: Implement model switching
            else:
                print_error("Please specify a model name")

        return False

    def _process_input(self, user_input: str) -> None:
        """Process user input with AI.

        Args:
            user_input: User input string.
        """
        try:
            response = self.conversation.get_response(user_input)

            # Handle tool calls
            if response.has_tool_calls:
                for tool_call in response.tool_calls:
                    print_tool_call(
                        tool_call["function"]["name"],
                        tool_call["function"]["arguments"],
                    )
                    # TODO: Execute tool and add result

            # Print response
            if response.content:
                print_assistant_message(response.content)

        except Exception as e:
            print_error(f"Failed to get response: {e}")
            logger.error(f"Failed to get response: {e}")
