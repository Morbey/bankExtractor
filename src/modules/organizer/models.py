"""Database models for invoice cataloging."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.core.categories import InvoiceCategory
from src.core.config import settings


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Invoice(Base):
    """Model for cataloged invoices."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # File information
    file_path = Column(String(500), nullable=False, unique=True)
    file_name = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=True)  # SHA256 hash for deduplication

    # Categorization
    category = Column(Enum(InvoiceCategory), nullable=False, default=InvoiceCategory.OUTROS)

    # Extracted metadata
    nif_emitente = Column(String(9), nullable=True, index=True)
    nif_cliente = Column(String(9), nullable=True)
    vendor_name = Column(String(255), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    invoice_date = Column(Date, nullable=True, index=True)
    due_date = Column(Date, nullable=True)
    total_amount = Column(Numeric(12, 2), nullable=True)
    currency = Column(String(3), default="EUR")

    # Email source information (if from email)
    email_sender = Column(String(255), nullable=True)
    email_subject = Column(String(500), nullable=True)
    email_date = Column(DateTime, nullable=True)
    email_message_id = Column(String(255), nullable=True)

    # Processing information
    processed_at = Column(DateTime, default=datetime.utcnow)
    manually_categorized = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    # Status
    is_paid = Column(Boolean, default=False)
    paid_date = Column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<Invoice {self.id}: {self.file_name} ({self.category.value})>"


class EmailAccount(Base):
    """Model for configured email accounts."""

    __tablename__ = "email_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    email_address = Column(String(255), nullable=False, unique=True)
    imap_server = Column(String(255), nullable=False)
    imap_port = Column(Integer, default=993)
    use_ssl = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<EmailAccount {self.name}: {self.email_address}>"


class InvoiceDatabase:
    """Database manager for invoice catalog."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file. Uses default if not provided.
        """
        if db_path is None:
            db_path = settings.data_dir / "invoices.db"

        db_path.parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create tables
        Base.metadata.create_all(self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def add_invoice(
        self,
        file_path: Path,
        category: InvoiceCategory,
        nif_emitente: Optional[str] = None,
        nif_cliente: Optional[str] = None,
        vendor_name: Optional[str] = None,
        invoice_number: Optional[str] = None,
        invoice_date: Optional[date] = None,
        total_amount: Optional[Decimal] = None,
        email_sender: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_date: Optional[datetime] = None,
        email_message_id: Optional[str] = None,
    ) -> Invoice:
        """Add a new invoice to the catalog.

        Args:
            file_path: Path to invoice file.
            category: Invoice category.
            ... (other metadata fields)

        Returns:
            Created Invoice object.
        """
        with self.get_session() as session:
            invoice = Invoice(
                file_path=str(file_path),
                file_name=file_path.name,
                category=category,
                nif_emitente=nif_emitente,
                nif_cliente=nif_cliente,
                vendor_name=vendor_name,
                invoice_number=invoice_number,
                invoice_date=invoice_date,
                total_amount=total_amount,
                email_sender=email_sender,
                email_subject=email_subject,
                email_date=email_date,
                email_message_id=email_message_id,
            )
            session.add(invoice)
            session.commit()
            session.refresh(invoice)
            return invoice

    def get_invoice_by_path(self, file_path: Path) -> Optional[Invoice]:
        """Get invoice by file path.

        Args:
            file_path: Path to invoice file.

        Returns:
            Invoice if found, None otherwise.
        """
        with self.get_session() as session:
            return session.query(Invoice).filter(Invoice.file_path == str(file_path)).first()

    def get_invoices_by_category(self, category: InvoiceCategory) -> list[Invoice]:
        """Get all invoices in a category.

        Args:
            category: Invoice category.

        Returns:
            List of invoices.
        """
        with self.get_session() as session:
            return session.query(Invoice).filter(Invoice.category == category).all()

    def get_invoices_by_nif(self, nif: str) -> list[Invoice]:
        """Get all invoices from a specific NIF.

        Args:
            nif: NIF to search for.

        Returns:
            List of invoices.
        """
        with self.get_session() as session:
            return session.query(Invoice).filter(Invoice.nif_emitente == nif).all()

    def get_invoices_by_date_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[Invoice]:
        """Get invoices within a date range.

        Args:
            start_date: Start of period.
            end_date: End of period.

        Returns:
            List of invoices.
        """
        with self.get_session() as session:
            return (
                session.query(Invoice)
                .filter(Invoice.invoice_date >= start_date)
                .filter(Invoice.invoice_date <= end_date)
                .order_by(Invoice.invoice_date)
                .all()
            )

    def get_total_by_category(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict[InvoiceCategory, Decimal]:
        """Get total amount per category.

        Args:
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Dictionary mapping category to total amount.
        """
        with self.get_session() as session:
            query = session.query(Invoice).filter(Invoice.total_amount.isnot(None))

            if start_date:
                query = query.filter(Invoice.invoice_date >= start_date)
            if end_date:
                query = query.filter(Invoice.invoice_date <= end_date)

            invoices = query.all()

            totals: dict[InvoiceCategory, Decimal] = {}
            for inv in invoices:
                if inv.category not in totals:
                    totals[inv.category] = Decimal("0")
                totals[inv.category] += inv.total_amount or Decimal("0")

            return totals

    def update_category(
        self,
        invoice_id: int,
        new_category: InvoiceCategory,
        manual: bool = True,
    ) -> bool:
        """Update invoice category.

        Args:
            invoice_id: Invoice ID.
            new_category: New category.
            manual: Mark as manually categorized.

        Returns:
            True if updated successfully.
        """
        with self.get_session() as session:
            invoice = session.query(Invoice).filter(Invoice.id == invoice_id).first()
            if invoice:
                invoice.category = new_category
                invoice.manually_categorized = manual
                session.commit()
                return True
            return False

    def mark_as_paid(self, invoice_id: int, paid_date: Optional[date] = None) -> bool:
        """Mark invoice as paid.

        Args:
            invoice_id: Invoice ID.
            paid_date: Date when paid (defaults to today).

        Returns:
            True if updated successfully.
        """
        with self.get_session() as session:
            invoice = session.query(Invoice).filter(Invoice.id == invoice_id).first()
            if invoice:
                invoice.is_paid = True
                invoice.paid_date = paid_date or date.today()
                session.commit()
                return True
            return False

    def search_invoices(
        self,
        search_term: str,
        limit: int = 50,
    ) -> list[Invoice]:
        """Search invoices by various fields.

        Args:
            search_term: Term to search for.
            limit: Maximum results.

        Returns:
            List of matching invoices.
        """
        with self.get_session() as session:
            search_pattern = f"%{search_term}%"
            return (
                session.query(Invoice)
                .filter(
                    (Invoice.file_name.ilike(search_pattern))
                    | (Invoice.vendor_name.ilike(search_pattern))
                    | (Invoice.invoice_number.ilike(search_pattern))
                    | (Invoice.email_subject.ilike(search_pattern))
                    | (Invoice.nif_emitente.ilike(search_pattern))
                )
                .order_by(Invoice.invoice_date.desc())
                .limit(limit)
                .all()
            )

    def get_statistics(self) -> dict:
        """Get overall statistics.

        Returns:
            Dictionary with statistics.
        """
        with self.get_session() as session:
            total_count = session.query(Invoice).count()
            total_amount = sum(
                (inv.total_amount or Decimal("0"))
                for inv in session.query(Invoice).filter(Invoice.total_amount.isnot(None)).all()
            )
            paid_count = session.query(Invoice).filter(Invoice.is_paid == True).count()
            unpaid_count = total_count - paid_count

            categories = {}
            for category in InvoiceCategory:
                count = session.query(Invoice).filter(Invoice.category == category).count()
                if count > 0:
                    categories[category.value] = count

            return {
                "total_invoices": total_count,
                "total_amount": total_amount,
                "paid_count": paid_count,
                "unpaid_count": unpaid_count,
                "by_category": categories,
            }

    def invoice_exists(self, file_path: Path) -> bool:
        """Check if invoice already exists in database.

        Args:
            file_path: Path to check.

        Returns:
            True if exists.
        """
        return self.get_invoice_by_path(file_path) is not None
