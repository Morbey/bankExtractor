"""Logging configuration with Rich formatting."""

import logging
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

from .config import settings


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get a configured logger instance.

    Args:
        name: Logger name. If None, returns root logger.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(name or "bank-extractor")

    if not logger.handlers:
        console = Console(stderr=True)
        handler = RichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.log_level))

    return logger
