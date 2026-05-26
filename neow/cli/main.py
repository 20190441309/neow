"""Main entry point for Neow CLI."""

import logging
import sys
from pathlib import Path

import click

from neow.core.config import Config
from neow.core.conversation import ConversationManager
from neow.core.executor import ToolExecutor
from neow.models.deepseek import DeepSeekClient
from neow.models.anthropic import AnthropicClient
from neow.models.openai import OpenAIClient
from neow.tools.file_ops import read_file, write_file, edit_file
from neow.tools.command import execute_command
from neow.tools.search import search_code
from neow.cli.repl import REPL
from neow.utils.logger import setup_logger, logger
from neow.utils.formatter import print_error, print_info


def create_model_client(config: Config, model_name: str):
    """Create model client based on configuration.

    Args:
        config: Configuration object.
        model_name: Name of the model to create.

    Returns:
        Model client instance.
    """
    model_config = config.get_model_config(model_name)

    if model_name == "deepseek":
        return DeepSeekClient(
            api_key=model_config["api_key"], model=model_config["model"]
        )
    elif model_name == "anthropic":
        return AnthropicClient(
            api_key=model_config["api_key"], model=model_config["model"]
        )
    elif model_name == "openai":
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
    executor.register_tool("execute_command", execute_command)
    executor.register_tool("search_code", search_code)


@click.command()
@click.option("--config", "-c", type=click.Path(exists=True), help="Config file path")
@click.option("--model", "-m", type=str, help="AI model to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def main(config: str, model: str, verbose: bool):
    """Neow - A lightweight, general-purpose AI CLI assistant."""
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

        # Setup conversation manager
        conversation = ConversationManager(model_client)

        # Setup tool executor
        executor = ToolExecutor()
        setup_tools(executor)

        # Start REPL
        repl = REPL(conversation)
        repl.start()

    except Exception as e:
        print_error(f"Fatal error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
