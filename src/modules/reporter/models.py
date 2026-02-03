"""Data models and structures for monthly reports."""

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional


class ReportFormat(str, Enum):
    """Available report output formats."""

    CONSOLE = "console"
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"


class ReportPeriod(str, Enum):
    """Report period types."""

    MONTHLY = "mensal"
    QUARTERLY = "trimestral"
    YEARLY = "anual"


@dataclass
class ExpenseCategory:
    """Expense category with total amount."""

    name: str
    amount: float
    count: int
    percentage: float = 0.0
    subcategories: list["ExpenseCategory"] = field(default_factory=list)

    def __post_init__(self):
        # Calculate percentages for subcategories
        if self.subcategories and self.amount > 0:
            for sub in self.subcategories:
                sub.percentage = (sub.amount / self.amount) * 100


@dataclass
class ProviderSummary:
    """Summary of expenses per provider."""

    name: str
    category: Optional[str]
    total_amount: float
    document_count: int
    average_amount: float = 0.0

    def __post_init__(self):
        if self.document_count > 0:
            self.average_amount = self.total_amount / self.document_count


@dataclass
class DocumentSummary:
    """Summary of a document for the report."""

    id: int
    file_name: str
    document_type: str
    provider: Optional[str]
    document_date: Optional[date]
    amount: Optional[float]
    reference: Optional[str]


@dataclass
class MonthlyComparison:
    """Comparison with previous month."""

    current_total: float
    previous_total: float
    difference: float
    percentage_change: float
    trend: str  # "up", "down", "stable"

    @classmethod
    def calculate(cls, current: float, previous: float) -> "MonthlyComparison":
        """Calculate comparison between two periods."""
        difference = current - previous
        if previous > 0:
            percentage_change = ((current - previous) / previous) * 100
        else:
            percentage_change = 100.0 if current > 0 else 0.0

        if percentage_change > 5:
            trend = "up"
        elif percentage_change < -5:
            trend = "down"
        else:
            trend = "stable"

        return cls(
            current_total=current,
            previous_total=previous,
            difference=difference,
            percentage_change=percentage_change,
            trend=trend,
        )


@dataclass
class ReportData:
    """Complete data for a monthly report."""

    # Period information
    year: int
    month: int
    period_start: date
    period_end: date
    report_type: ReportPeriod = ReportPeriod.MONTHLY

    # Summary statistics
    total_documents: int = 0
    total_amount: float = 0.0
    total_invoices: int = 0
    total_statements: int = 0
    total_receipts: int = 0

    # Categorized data
    by_category: list[ExpenseCategory] = field(default_factory=list)
    by_provider: list[ProviderSummary] = field(default_factory=list)
    documents: list[DocumentSummary] = field(default_factory=list)

    # Comparison with previous period
    comparison: Optional[MonthlyComparison] = None

    # Metadata
    generated_at: Optional[date] = None
    notes: list[str] = field(default_factory=list)

    @property
    def period_name(self) -> str:
        """Get human-readable period name."""
        months_pt = [
            "",
            "Janeiro",
            "Fevereiro",
            "Março",
            "Abril",
            "Maio",
            "Junho",
            "Julho",
            "Agosto",
            "Setembro",
            "Outubro",
            "Novembro",
            "Dezembro",
        ]
        return f"{months_pt[self.month]} {self.year}"

    @property
    def has_data(self) -> bool:
        """Check if report has any data."""
        return self.total_documents > 0


@dataclass
class ReportConfig:
    """Configuration for report generation."""

    # Period
    year: int
    month: int

    # Output settings
    format: ReportFormat = ReportFormat.CONSOLE
    output_path: Optional[Path] = None

    # Content options
    include_documents_list: bool = True
    include_comparison: bool = True
    include_charts: bool = False
    max_documents_shown: int = 50

    # Email settings
    send_email: bool = False
    recipient_email: Optional[str] = None
    email_subject: Optional[str] = None


# Category mappings for expense classification
EXPENSE_CATEGORIES = {
    "utilities": {
        "name": "Serviços Essenciais",
        "subcategories": ["eletricidade", "água", "gás", "energia"],
    },
    "telecomunicacoes": {
        "name": "Telecomunicações",
        "subcategories": ["internet", "telefone", "tv", "telemóvel"],
    },
    "transportes": {
        "name": "Transportes",
        "subcategories": ["portagens", "combustível", "transporte público"],
    },
    "seguros": {
        "name": "Seguros",
        "subcategories": ["automóvel", "saúde", "vida", "casa"],
    },
    "banco": {
        "name": "Serviços Bancários",
        "subcategories": ["comissões", "juros"],
    },
    "governo": {
        "name": "Impostos e Taxas",
        "subcategories": ["IRS", "IMI", "IUC", "taxas"],
    },
    "outros": {
        "name": "Outros",
        "subcategories": [],
    },
}
