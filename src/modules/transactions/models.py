"""Database models for bank transaction management and payment matching."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    create_engine,
)
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from src.core import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for transaction models."""

    pass


class TransactionType(str, Enum):
    """Types of bank transactions."""

    TRANSFER = "transferencia"
    DIRECT_DEBIT = "debito_direto"
    MULTIBANCO = "multibanco"
    CARD = "cartao"
    CHECK = "cheque"
    FEE = "comissao"
    INTEREST = "juro"
    TAX = "imposto"
    SALARY = "salario"
    REFUND = "reembolso"
    DEPOSIT = "deposito"
    WITHDRAWAL = "levantamento"
    STANDING_ORDER = "ordem_permanente"
    OTHER = "outro"


class MatchStatus(str, Enum):
    """Status of transaction-invoice matching."""

    UNMATCHED = "nao_correspondido"
    MATCHED = "correspondido"
    MANUAL = "manual"  # Manually linked


class BankTransaction(Base):
    """Represents a bank transaction from a statement.

    This model stores transactions extracted from bank statements (CGD, CTT, etc.)
    and enables matching against invoices/faturas for payment verification.

    Attributes:
        id: Primary key.
        bank: Bank identifier (cgd, ctt).
        account_iban: IBAN of the account where transaction occurred.
        transaction_date: Date the transaction was executed.
        value_date: Date the transaction was valued/settled.
        description: Transaction description from the bank.
        amount: Transaction amount (negative=outgoing, positive=incoming).
        balance: Account balance after transaction (optional).
        counterpart_iban: IBAN of the counterparty (if available).
        counterpart_name: Name of the counterparty.
        reference: Payment reference (if available).
        transaction_type: Type of transaction (transfer, debit, etc.).
        raw_data: Original data from the statement (JSON).
        match_status: Whether this transaction has been matched to an invoice.
        matched_document_id: ID of the matched document/invoice.
        created_at: When this record was created.
    """

    __tablename__ = "bank_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Bank and account identification
    bank: Mapped[str] = mapped_column(String(20), index=True)  # cgd, ctt
    account_iban: Mapped[str] = mapped_column(String(34), index=True)  # Full IBAN

    # Transaction dates
    transaction_date: Mapped[date] = mapped_column(Date, index=True)
    value_date: Mapped[date] = mapped_column(Date)

    # Transaction details
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))  # Negative=outgoing
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)

    # Counterparty information
    counterpart_iban: Mapped[Optional[str]] = mapped_column(String(34), nullable=True, index=True)
    counterpart_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # References and classification
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    transaction_type: Mapped[str] = mapped_column(
        String(30),
        default=TransactionType.OTHER.value,
        index=True,
    )

    # Original statement data (for debugging/auditing)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Matching status
    match_status: Mapped[str] = mapped_column(
        String(20),
        default=MatchStatus.UNMATCHED.value,
        index=True,
    )
    matched_document_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Composite indexes for efficient matching queries
    __table_args__ = (
        # Index for matching by amount and counterpart IBAN
        Index("idx_amount_counterpart", "amount", "counterpart_iban"),
        # Index for matching by date range and amount
        Index("idx_date_amount", "transaction_date", "amount"),
        # Unique constraint to prevent duplicate imports
        Index(
            "idx_unique_transaction",
            "bank",
            "account_iban",
            "transaction_date",
            "amount",
            "description",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"BankTransaction(id={self.id}, bank={self.bank!r}, "
            f"date={self.transaction_date}, amount={self.amount})"
        )

    @property
    def is_outgoing(self) -> bool:
        """Check if this is an outgoing transaction (payment)."""
        return self.amount < 0

    @property
    def is_incoming(self) -> bool:
        """Check if this is an incoming transaction (receipt)."""
        return self.amount > 0

    @property
    def absolute_amount(self) -> Decimal:
        """Get the absolute value of the amount."""
        return abs(self.amount)


def get_engine():
    """Get SQLAlchemy engine for the transactions database."""
    db_path = settings.data_dir / "transactions" / "transactions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    """Initialize the transactions database, creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    """Get a new database session."""
    engine = get_engine()
    return Session(engine)
