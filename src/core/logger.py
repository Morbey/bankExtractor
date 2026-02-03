"""Logging configuration with Rich formatting."""

import logging
from contextlib import contextmanager
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

from .config import settings

# Global flag to suppress logging during interactive sessions
_logging_suppressed = False


class SuppressableRichHandler(RichHandler):
    """Rich handler that can be suppressed during interactive sessions."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record, unless logging is suppressed."""
        if _logging_suppressed:
            return
        super().emit(record)


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
        handler = SuppressableRichHandler(
            console=console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, settings.log_level))

    return logger


@contextmanager
def suppress_logging():
    """Context manager to suppress logging during interactive sessions.

    Usage:
        with suppress_logging():
            # Do interactive stuff - no logs will be emitted
            pass
    """
    global _logging_suppressed
    _logging_suppressed = True
    try:
        yield
    finally:
        _logging_suppressed = False


def set_logging_suppressed(suppressed: bool) -> None:
    """Set logging suppression state.

    Args:
        suppressed: True to suppress logging, False to enable.
    """
    global _logging_suppressed
    _logging_suppressed = suppressed


def is_logging_suppressed() -> bool:
    """Check if logging is currently suppressed."""
    return _logging_suppressed
