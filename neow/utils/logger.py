"""Logging utilities for Neow CLI."""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str = "neow",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Setup logger with console and optional file handler.

    Args:
        name: Logger name.
        level: Logging level for the FILE handler (console always at WARNING).
        log_file: Optional path to log file.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on re-calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)  # capture everything; handlers filter

    # Console handler — only WARNING+ so users don't see internal noise
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.WARNING)
    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler — always at DEBUG for troubleshooting
    log_file = log_file or Path.home() / ".neow" / "neow.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)

    return logger


# Default logger
logger = setup_logger()
