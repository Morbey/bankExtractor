"""Invoice database - tracks downloaded and organized invoices."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, DateTime, Float, Integer, String, Boolean, func
from sqlalchemy.orm import Session

from src.core import get_logger, settings

from .models import get_session, init_db, Base


class InvoiceRecord(Base):
    """Database model for tracking invoices."""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True)
    file_path = Column(String, unique=True, nullable=False)
    file_name = Column(String, nullable=False)
    category = Column(String, nullable=False)
    nif_emitente = Column(String, nullable=True)
    invoice_date = Column(DateTime, nullable=True)
    total_amount = Column(Float, nullable=True)
    email_sender = Column(String, nullable=True)
    email_subject = Column(String, nullable=True)
    email_date = Column(DateTime, nullable=True)
    email_message_id = Column(String, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InvoiceDatabase:
    """Database wrapper for invoice tracking."""

    def __init__(self):
        self.logger = get_logger(__name__)
        init_db()

    def add_invoice(
        self,
        file_path: Path,
        category: str,
        nif_emitente: Optional[str] = None,
        invoice_date: Optional[date] = None,
        total_amount: Optional[float] = None,
        email_sender: Optional[str] = None,
        email_subject: Optional[str] = None,
        email_date: Optional[datetime] = None,
        email_message_id: Optional[str] = None,
    ) -> bool:
        """Add an invoice record to the database.

        Args:
            file_path: Path to the invoice file.
            category: Invoice category.
            nif_emitente: NIF of the invoice issuer.
            invoice_date: Date on the invoice.
            total_amount: Total amount on the invoice.
            email_sender: Email sender (if downloaded from email).
            email_subject: Email subject (if downloaded from email).
            email_date: Email date (if downloaded from email).
            email_message_id: Email message ID (if downloaded from email).

        Returns:
            True if successful, False otherwise.
        """
        try:
            with get_session() as session:
                # Convert category if it's an enum
                cat_value = category.value if hasattr(category, "value") else str(category)

                record = InvoiceRecord(
                    file_path=str(file_path),
                    file_name=file_path.name if isinstance(file_path, Path) else Path(file_path).name,
                    category=cat_value,
                    nif_emitente=nif_emitente,
                    invoice_date=invoice_date,
                    total_amount=total_amount,
                    email_sender=email_sender,
                    email_subject=email_subject,
                    email_date=email_date,
                    email_message_id=email_message_id,
                )
                session.add(record)
                session.commit()
                self.logger.debug(f"Invoice added: {file_path}")
                return True
        except Exception as e:
            self.logger.error(f"Error adding invoice: {e}")
            return False

    def invoice_exists(self, file_path: Path) -> bool:
        """Check if an invoice already exists in the database.

        Args:
            file_path: Path to check.

        Returns:
            True if exists, False otherwise.
        """
        try:
            with get_session() as session:
                count = session.query(InvoiceRecord).filter(
                    InvoiceRecord.file_path == str(file_path)
                ).count()
                return count > 0
        except Exception as e:
            self.logger.error(f"Error checking invoice existence: {e}")
            return False

    def get_invoice(self, file_path: Path) -> Optional[InvoiceRecord]:
        """Get an invoice record by file path.

        Args:
            file_path: Path to the invoice file.

        Returns:
            InvoiceRecord if found, None otherwise.
        """
        try:
            with get_session() as session:
                return session.query(InvoiceRecord).filter(
                    InvoiceRecord.file_path == str(file_path)
                ).first()
        except Exception as e:
            self.logger.error(f"Error getting invoice: {e}")
            return None

    def mark_paid(self, file_path: Path) -> bool:
        """Mark an invoice as paid.

        Args:
            file_path: Path to the invoice file.

        Returns:
            True if successful, False otherwise.
        """
        try:
            with get_session() as session:
                invoice = session.query(InvoiceRecord).filter(
                    InvoiceRecord.file_path == str(file_path)
                ).first()
                if invoice:
                    invoice.is_paid = True
                    session.commit()
                    return True
                return False
        except Exception as e:
            self.logger.error(f"Error marking invoice as paid: {e}")
            return False

    def get_statistics(self) -> dict:
        """Get invoice statistics.

        Returns:
            Dictionary with statistics.
        """
        try:
            with get_session() as session:
                total = session.query(InvoiceRecord).count()
                paid = session.query(InvoiceRecord).filter(
                    InvoiceRecord.is_paid == True
                ).count()
                unpaid = total - paid

                total_amount = session.query(func.sum(InvoiceRecord.total_amount)).scalar() or 0.0

                # By category
                by_category = {}
                category_counts = session.query(
                    InvoiceRecord.category,
                    func.count(InvoiceRecord.id)
                ).group_by(InvoiceRecord.category).all()
                for cat, count in category_counts:
                    by_category[cat] = count

                return {
                    "total_invoices": total,
                    "paid_count": paid,
                    "unpaid_count": unpaid,
                    "total_amount": total_amount,
                    "by_category": by_category,
                }
        except Exception as e:
            self.logger.error(f"Error getting statistics: {e}")
            return {
                "total_invoices": 0,
                "paid_count": 0,
                "unpaid_count": 0,
                "total_amount": 0.0,
                "by_category": {},
            }

    def get_invoices_by_category(self, category: str) -> list[InvoiceRecord]:
        """Get all invoices in a category.

        Args:
            category: Category name.

        Returns:
            List of invoice records.
        """
        try:
            with get_session() as session:
                return session.query(InvoiceRecord).filter(
                    InvoiceRecord.category == category
                ).all()
        except Exception as e:
            self.logger.error(f"Error getting invoices by category: {e}")
            return []

    def get_invoices_by_date_range(
        self,
        start_date: date,
        end_date: date,
    ) -> list[InvoiceRecord]:
        """Get invoices within a date range.

        Args:
            start_date: Start date.
            end_date: End date.

        Returns:
            List of invoice records.
        """
        try:
            with get_session() as session:
                return session.query(InvoiceRecord).filter(
                    InvoiceRecord.invoice_date >= start_date,
                    InvoiceRecord.invoice_date <= end_date,
                ).all()
        except Exception as e:
            self.logger.error(f"Error getting invoices by date range: {e}")
            return []

    def get_unpaid_invoices(self) -> list[InvoiceRecord]:
        """Get all unpaid invoices.

        Returns:
            List of unpaid invoice records.
        """
        try:
            with get_session() as session:
                return session.query(InvoiceRecord).filter(
                    InvoiceRecord.is_paid == False
                ).all()
        except Exception as e:
            self.logger.error(f"Error getting unpaid invoices: {e}")
            return []
