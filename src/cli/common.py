"""Common utilities shared across CLI commands."""

from datetime import date, datetime

from rich.console import Console

from src import __version__
from src.modules.banks import BancoCTTBank, CGDEmpresasBank

# Shared console instance
console = Console()

# Bank registry
BANKS = {
    "cgd": CGDEmpresasBank,
    "ctt": BancoCTTBank,
}


def parse_date(date_str: str) -> date:
    """Parse date string in DD-MM-YYYY format.

    Args:
        date_str: Date string in DD-MM-YYYY format

    Returns:
        Parsed date object

    Raises:
        ValueError: If date string is invalid
    """
    return datetime.strptime(date_str, "%d-%m-%Y").date()


def version_banner(title: str = "Bank Extractor", color: str = "blue") -> str:
    """Return formatted version banner text.

    Args:
        title: Title text to display
        color: Color for the version text

    Returns:
        Formatted banner string
    """
    return f"[bold {color}]Bank Extractor v{__version__}[/bold {color}]\n{title}"
