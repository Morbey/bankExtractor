"""Monthly reporter module (Phase 4).

This module provides report generation and delivery functionality.
It aggregates financial data from indexed documents and generates
reports in multiple formats (console, HTML, Excel).

Example usage:
    from src.modules.reporter import ReportGenerator, ReportConfig

    # Generate a monthly report
    config = ReportConfig(year=2024, month=1)
    generator = ReportGenerator()
    report = generator.generate(config)

    # Display in console
    from src.modules.reporter import ConsoleFormatter
    formatter = ConsoleFormatter()
    formatter.render(report)

    # Send via email
    from src.modules.reporter import ReportMailer
    mailer = ReportMailer(provider="gmail")
    mailer.send_report(report, "contabilista@example.com")
"""

from .formatters import (
    ConsoleFormatter,
    ExcelFormatter,
    HTMLFormatter,
    ReportFormatter,
    get_formatter,
)
from .generator import ReportGenerator
from .mailer import ReportMailer
from .models import (
    DocumentSummary,
    EXPENSE_CATEGORIES,
    ExpenseCategory,
    MonthlyComparison,
    ProviderSummary,
    ReportConfig,
    ReportData,
    ReportFormat,
    ReportPeriod,
)

__all__ = [
    # Models
    "ReportData",
    "ReportConfig",
    "ReportFormat",
    "ReportPeriod",
    "ExpenseCategory",
    "ProviderSummary",
    "DocumentSummary",
    "MonthlyComparison",
    "EXPENSE_CATEGORIES",
    # Generator
    "ReportGenerator",
    # Formatters
    "ReportFormatter",
    "ConsoleFormatter",
    "HTMLFormatter",
    "ExcelFormatter",
    "get_formatter",
    # Mailer
    "ReportMailer",
]

