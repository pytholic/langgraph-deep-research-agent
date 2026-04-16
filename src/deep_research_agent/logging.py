"""Shared logging configuration with Rich handler.

Created by @pytholic on 2026.04.16
"""

import logging

from rich.console import Console
from rich.logging import RichHandler

console = Console()

handler = RichHandler(
    console=console,
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    show_path=False,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%m/%d/%Y %I:%M:%S %p]",
    handlers=[handler],
)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger with the shared Rich configuration.

    Args:
        name: Logger name, typically ``__name__`` from the calling module.
    """
    return logging.getLogger(name)
