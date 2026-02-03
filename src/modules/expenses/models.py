"""Data models for expense tracking."""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from src.core import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for expenses."""

    pass


class ExpenseCategory(str, Enum):
    """Standard expense categories."""

    UTILITIES = "utilities"
    TELECOM = "telecomunicacoes"
    TRANSPORT = "transportes"
    INSURANCE = "seguros"
    HEALTH = "saude"
    EDUCATION = "educacao"
    FOOD = "alimentacao"
    HOUSING = "habitacao"
    ENTERTAINMENT = "lazer"
    CLOTHING = "vestuario"
    TAXES = "impostos"
    BANK_FEES = "comissoes_bancarias"
    SUBSCRIPTIONS = "subscricoes"
    OTHER = "outros"


class AlertType(str, Enum):
    """Types of expense alerts."""

    BUDGET_EXCEEDED = "orcamento_excedido"
    BUDGET_WARNING = "orcamento_aviso"
    UNUSUAL_EXPENSE = "despesa_invulgar"
    RECURRING_MISSED = "recorrente_faltou"
    NEW_PROVIDER = "novo_fornecedor"
    PRICE_INCREASE = "aumento_preco"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "aviso"
    CRITICAL = "critico"


class Budget(Base):
    """Monthly budget for a category."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    monthly_limit: Mapped[float] = mapped_column(Float)
    warning_threshold: Mapped[float] = mapped_column(Float, default=0.8)  # 80% warning
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"Budget(category={self.category!r}, limit={self.monthly_limit})"


class Expense(Base):
    """Individual expense record."""

    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Source document reference
    document_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Expense details
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(50), index=True)
    subcategory: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Provider/vendor
    provider_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Dates
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Classification
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=True)
    is_tax_deductible: Mapped[bool] = mapped_column(Boolean, default=False)

    # Metadata
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # Comma-separated
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"Expense(amount={self.amount}, category={self.category!r})"

    @property
    def month_key(self) -> str:
        """Get month key for grouping (YYYY-MM)."""
        return self.expense_date.strftime("%Y-%m")


class Alert(Base):
    """Expense alert record."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON data
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    expense_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"Alert(type={self.alert_type!r}, severity={self.severity!r})"


class RecurringExpense(Base):
    """Expected recurring expense definition."""

    __tablename__ = "recurring_expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    provider_name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(50))
    expected_amount: Mapped[float] = mapped_column(Float)
    amount_tolerance: Mapped[float] = mapped_column(Float, default=0.1)  # 10% tolerance
    frequency: Mapped[str] = mapped_column(String(20), default="monthly")  # monthly, quarterly, yearly
    expected_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Day of month
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"RecurringExpense(name={self.name!r}, amount={self.expected_amount})"


# Dataclasses for analysis results
@dataclass
class CategorySummary:
    """Summary of expenses for a category."""

    category: str
    category_name: str
    total_amount: float
    expense_count: int
    average_amount: float
    budget_limit: Optional[float] = None
    budget_used_percentage: Optional[float] = None
    trend: str = "stable"  # up, down, stable
    trend_percentage: float = 0.0


@dataclass
class MonthlyAnalysis:
    """Analysis of expenses for a month."""

    year: int
    month: int
    total_expenses: float
    expense_count: int
    by_category: list[CategorySummary] = field(default_factory=list)
    top_providers: list[tuple[str, float]] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    comparison_previous: Optional[float] = None
    comparison_percentage: Optional[float] = None


@dataclass
class ExpenseAlert:
    """Alert information for display."""

    alert_type: AlertType
    severity: AlertSeverity
    message: str
    category: Optional[str] = None
    amount: Optional[float] = None
    details: Optional[str] = None


# Category display names in Portuguese
CATEGORY_NAMES = {
    ExpenseCategory.UTILITIES: "Serviços Essenciais",
    ExpenseCategory.TELECOM: "Telecomunicações",
    ExpenseCategory.TRANSPORT: "Transportes",
    ExpenseCategory.INSURANCE: "Seguros",
    ExpenseCategory.HEALTH: "Saúde",
    ExpenseCategory.EDUCATION: "Educação",
    ExpenseCategory.FOOD: "Alimentação",
    ExpenseCategory.HOUSING: "Habitação",
    ExpenseCategory.ENTERTAINMENT: "Lazer",
    ExpenseCategory.CLOTHING: "Vestuário",
    ExpenseCategory.TAXES: "Impostos",
    ExpenseCategory.BANK_FEES: "Comissões Bancárias",
    ExpenseCategory.SUBSCRIPTIONS: "Subscrições",
    ExpenseCategory.OTHER: "Outros",
}


# Provider to category mapping
PROVIDER_CATEGORIES = {
    # Utilities
    "EDP": ExpenseCategory.UTILITIES,
    "Endesa": ExpenseCategory.UTILITIES,
    "Galp": ExpenseCategory.UTILITIES,
    "E-Redes": ExpenseCategory.UTILITIES,
    "EPAL": ExpenseCategory.UTILITIES,
    "Águas de Portugal": ExpenseCategory.UTILITIES,
    "Lisboagás": ExpenseCategory.UTILITIES,
    # Telecom
    "NOS": ExpenseCategory.TELECOM,
    "MEO": ExpenseCategory.TELECOM,
    "Vodafone": ExpenseCategory.TELECOM,
    "NOWO": ExpenseCategory.TELECOM,
    # Transport
    "Via Verde": ExpenseCategory.TRANSPORT,
    "CP": ExpenseCategory.TRANSPORT,
    # Insurance
    "Fidelidade": ExpenseCategory.INSURANCE,
    "Allianz": ExpenseCategory.INSURANCE,
    "Tranquilidade": ExpenseCategory.INSURANCE,
    # Government/Taxes
    "Finanças": ExpenseCategory.TAXES,
}


def get_engine():
    """Get SQLAlchemy engine for the expenses database."""
    db_path = settings.data_dir / "expenses" / "expenses.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    """Initialize the expenses database."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    """Get a new database session."""
    engine = get_engine()
    return Session(engine)
