"""Database operations for bank transaction management."""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from src.core import get_logger

from .models import (
    BankTransaction,
    MatchStatus,
    TransactionType,
    get_engine,
    init_db,
)

logger = get_logger(__name__)

# Default tolerance for amount matching (in EUR)
AMOUNT_TOLERANCE = Decimal("0.01")


@dataclass
class MatchResult:
    """Result of a payment matching operation.

    Attributes:
        found: Whether a matching transaction was found.
        transaction: The matching transaction (if found).
        match_type: How the match was made (iban, reference, description).
        confidence: Confidence level (high, medium, low).
    """

    found: bool
    transaction: Optional[BankTransaction] = None
    match_type: Optional[str] = None
    confidence: str = "low"


class TransactionDatabase:
    """Database operations for bank transactions.

    Provides methods for:
    - Adding transactions from bank statements
    - Avoiding duplicate imports
    - Finding matching payments for invoices
    - Querying transactions by various criteria

    Example usage:
        db = TransactionDatabase()

        # Import transactions from statement
        db.import_from_statement("cgd", statement_data)

        # Find payment for an invoice
        result = db.find_matching_payment(
            amount=Decimal("59.99"),
            iban="PT50123456789012345678901",
            date_range_days=30,
        )
        if result.found:
            print(f"Found payment: {result.transaction}")
    """

    def __init__(self):
        """Initialize the transaction database."""
        init_db()
        self._engine = get_engine()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return Session(self._engine)

    # ==================== Add/Import ====================

    def add_transaction(
        self,
        bank: str,
        account_iban: str,
        transaction_date: date,
        value_date: date,
        description: str,
        amount: Decimal,
        balance: Optional[Decimal] = None,
        counterpart_iban: Optional[str] = None,
        counterpart_name: Optional[str] = None,
        reference: Optional[str] = None,
        transaction_type: str = TransactionType.OTHER.value,
        raw_data: Optional[dict] = None,
    ) -> Optional[int]:
        """Add a new transaction to the database.

        Args:
            bank: Bank identifier (cgd, ctt).
            account_iban: IBAN of the account.
            transaction_date: Date of the transaction.
            value_date: Value/settlement date.
            description: Transaction description.
            amount: Transaction amount (negative for outgoing).
            balance: Account balance after transaction.
            counterpart_iban: IBAN of the counterparty.
            counterpart_name: Name of the counterparty.
            reference: Payment reference.
            transaction_type: Type of transaction.
            raw_data: Original data from statement.

        Returns:
            ID of the created transaction, or None if duplicate.
        """
        # Check for duplicate first
        if self.transaction_exists(bank, account_iban, transaction_date, amount, description):
            logger.debug(f"Transaction already exists: {description[:50]}")
            return None

        with self._get_session() as session:
            transaction = BankTransaction(
                bank=bank,
                account_iban=account_iban,
                transaction_date=transaction_date,
                value_date=value_date,
                description=description,
                amount=amount,
                balance=balance,
                counterpart_iban=counterpart_iban,
                counterpart_name=counterpart_name,
                reference=reference,
                transaction_type=transaction_type,
                raw_data=raw_data,
            )
            session.add(transaction)
            session.commit()
            logger.debug(f"Added transaction: {description[:50]}")
            return transaction.id

    def transaction_exists(
        self,
        bank: str,
        account_iban: str,
        transaction_date: date,
        amount: Decimal,
        description: str,
    ) -> bool:
        """Check if a transaction already exists (for deduplication).

        Args:
            bank: Bank identifier.
            account_iban: Account IBAN.
            transaction_date: Date of transaction.
            amount: Transaction amount.
            description: Transaction description.

        Returns:
            True if transaction exists, False otherwise.
        """
        with self._get_session() as session:
            stmt = select(BankTransaction.id).where(
                and_(
                    BankTransaction.bank == bank,
                    BankTransaction.account_iban == account_iban,
                    BankTransaction.transaction_date == transaction_date,
                    BankTransaction.amount == amount,
                    BankTransaction.description == description,
                )
            )
            result = session.execute(stmt).first()
            return result is not None

    def import_from_statement(
        self,
        bank: str,
        account_iban: str,
        transactions: list[dict],
    ) -> tuple[int, int]:
        """Import multiple transactions from a bank statement.

        Expected transaction dict format:
        {
            "transaction_date": date,
            "value_date": date,
            "description": str,
            "amount": Decimal,
            "balance": Decimal (optional),
            "counterpart_iban": str (optional),
            "counterpart_name": str (optional),
            "reference": str (optional),
            "transaction_type": str (optional),
            "raw_data": dict (optional),
        }

        Args:
            bank: Bank identifier (cgd, ctt).
            account_iban: IBAN of the account.
            transactions: List of transaction dictionaries.

        Returns:
            Tuple of (imported_count, skipped_count).
        """
        imported = 0
        skipped = 0

        for tx_data in transactions:
            result = self.add_transaction(
                bank=bank,
                account_iban=account_iban,
                transaction_date=tx_data["transaction_date"],
                value_date=tx_data.get("value_date", tx_data["transaction_date"]),
                description=tx_data["description"],
                amount=tx_data["amount"],
                balance=tx_data.get("balance"),
                counterpart_iban=tx_data.get("counterpart_iban"),
                counterpart_name=tx_data.get("counterpart_name"),
                reference=tx_data.get("reference"),
                transaction_type=tx_data.get("transaction_type", TransactionType.OTHER.value),
                raw_data=tx_data.get("raw_data"),
            )

            if result is not None:
                imported += 1
            else:
                skipped += 1

        logger.info(f"Imported {imported} transactions, skipped {skipped} duplicates")
        return imported, skipped

    # ==================== Payment Matching ====================

    def find_matching_payment(
        self,
        amount: Decimal,
        iban: Optional[str] = None,
        reference: Optional[str] = None,
        description_keywords: Optional[list[str]] = None,
        date_range_days: int = 30,
        from_date: Optional[date] = None,
        tolerance: Decimal = AMOUNT_TOLERANCE,
    ) -> MatchResult:
        """Find a matching payment for an invoice/fatura.

        Searches for outgoing transactions (negative amounts) that match
        the given criteria. The search prioritizes matches by:
        1. Exact IBAN match + amount
        2. Reference match + amount
        3. Description keywords + amount

        Args:
            amount: Invoice amount (positive value, will be negated for search).
            iban: IBAN of the entity/supplier to match.
            reference: Payment reference to match.
            description_keywords: Keywords to search in description.
            date_range_days: Number of days to search (default 30).
            from_date: Start date for search (default: today - date_range_days).
            tolerance: Amount tolerance for matching (default 0.01).

        Returns:
            MatchResult with the matching transaction if found.
        """
        if from_date is None:
            from_date = date.today() - timedelta(days=date_range_days)

        end_date = date.today()

        # The payment amount is negative (outgoing)
        target_amount = -abs(amount)
        min_amount = target_amount - tolerance
        max_amount = target_amount + tolerance

        with self._get_session() as session:
            # Base query: outgoing transactions in date range with matching amount
            base_conditions = [
                BankTransaction.amount >= min_amount,
                BankTransaction.amount <= max_amount,
                BankTransaction.transaction_date >= from_date,
                BankTransaction.transaction_date <= end_date,
            ]

            # Try matching by IBAN first (highest confidence)
            if iban:
                stmt = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            BankTransaction.counterpart_iban == iban,
                        )
                    )
                    .order_by(BankTransaction.transaction_date.desc())
                    .limit(1)
                )
                result = session.execute(stmt).scalar_one_or_none()

                if result:
                    return MatchResult(
                        found=True,
                        transaction=self._detach_transaction(result),
                        match_type="iban",
                        confidence="high",
                    )

            # Try matching by reference (high confidence)
            if reference:
                stmt = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            or_(
                                BankTransaction.reference == reference,
                                BankTransaction.description.contains(reference),
                            ),
                        )
                    )
                    .order_by(BankTransaction.transaction_date.desc())
                    .limit(1)
                )
                result = session.execute(stmt).scalar_one_or_none()

                if result:
                    return MatchResult(
                        found=True,
                        transaction=self._detach_transaction(result),
                        match_type="reference",
                        confidence="high",
                    )

            # Try matching by description keywords (medium confidence)
            if description_keywords:
                # Build OR conditions for keywords
                keyword_conditions = [
                    BankTransaction.description.ilike(f"%{kw}%") for kw in description_keywords
                ]

                stmt = (
                    select(BankTransaction)
                    .where(
                        and_(
                            *base_conditions,
                            or_(*keyword_conditions),
                        )
                    )
                    .order_by(BankTransaction.transaction_date.desc())
                    .limit(1)
                )
                result = session.execute(stmt).scalar_one_or_none()

                if result:
                    return MatchResult(
                        found=True,
                        transaction=self._detach_transaction(result),
                        match_type="description",
                        confidence="medium",
                    )

            # Try matching by counterpart name containing entity name
            if iban:
                # If we have IBAN, try to find by partial match on counterpart name
                # This is low confidence
                stmt = (
                    select(BankTransaction)
                    .where(and_(*base_conditions))
                    .order_by(BankTransaction.transaction_date.desc())
                    .limit(5)
                )
                results = session.execute(stmt).scalars().all()

                # Return first match with amount only (low confidence)
                if results:
                    return MatchResult(
                        found=True,
                        transaction=self._detach_transaction(results[0]),
                        match_type="amount_only",
                        confidence="low",
                    )

            return MatchResult(found=False)

    def _detach_transaction(self, tx: BankTransaction) -> BankTransaction:
        """Create a detached copy of a transaction for use outside session.

        Args:
            tx: Transaction to detach.

        Returns:
            Detached transaction object.
        """
        # Access all attributes to load them before session closes
        _ = (
            tx.id,
            tx.bank,
            tx.account_iban,
            tx.transaction_date,
            tx.value_date,
            tx.description,
            tx.amount,
            tx.balance,
            tx.counterpart_iban,
            tx.counterpart_name,
            tx.reference,
            tx.transaction_type,
            tx.raw_data,
            tx.match_status,
            tx.matched_document_id,
            tx.created_at,
        )
        return tx

    # ==================== Update ====================

    def mark_matched(
        self,
        transaction_id: int,
        document_id: int,
        manual: bool = False,
    ) -> bool:
        """Mark a transaction as matched to a document/invoice.

        Args:
            transaction_id: ID of the transaction.
            document_id: ID of the matched document.
            manual: Whether this was a manual match.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(BankTransaction).where(BankTransaction.id == transaction_id)
            tx = session.execute(stmt).scalar_one_or_none()

            if not tx:
                return False

            tx.match_status = MatchStatus.MANUAL.value if manual else MatchStatus.MATCHED.value
            tx.matched_document_id = document_id
            session.commit()
            logger.debug(f"Marked transaction {transaction_id} matched to doc {document_id}")
            return True

    def unmatch(self, transaction_id: int) -> bool:
        """Remove match status from a transaction.

        Args:
            transaction_id: ID of the transaction.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(BankTransaction).where(BankTransaction.id == transaction_id)
            tx = session.execute(stmt).scalar_one_or_none()

            if not tx:
                return False

            tx.match_status = MatchStatus.UNMATCHED.value
            tx.matched_document_id = None
            session.commit()
            logger.debug(f"Unmatched transaction {transaction_id}")
            return True

    # ==================== Query ====================

    def get_transaction_by_id(self, transaction_id: int) -> Optional[BankTransaction]:
        """Get a transaction by ID.

        Args:
            transaction_id: The transaction ID.

        Returns:
            BankTransaction or None.
        """
        with self._get_session() as session:
            stmt = select(BankTransaction).where(BankTransaction.id == transaction_id)
            result = session.execute(stmt).scalar_one_or_none()

            if result:
                return self._detach_transaction(result)
            return None

    def get_transactions(
        self,
        bank: Optional[str] = None,
        account_iban: Optional[str] = None,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        transaction_type: Optional[str] = None,
        match_status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BankTransaction]:
        """Get transactions with optional filters.

        Args:
            bank: Filter by bank.
            account_iban: Filter by account IBAN.
            from_date: Filter from this date.
            to_date: Filter to this date.
            transaction_type: Filter by transaction type.
            match_status: Filter by match status.
            limit: Maximum results to return.
            offset: Number of results to skip.

        Returns:
            List of matching BankTransaction objects.
        """
        with self._get_session() as session:
            stmt = select(BankTransaction)

            conditions = []
            if bank:
                conditions.append(BankTransaction.bank == bank)
            if account_iban:
                conditions.append(BankTransaction.account_iban == account_iban)
            if from_date:
                conditions.append(BankTransaction.transaction_date >= from_date)
            if to_date:
                conditions.append(BankTransaction.transaction_date <= to_date)
            if transaction_type:
                conditions.append(BankTransaction.transaction_type == transaction_type)
            if match_status:
                conditions.append(BankTransaction.match_status == match_status)

            if conditions:
                stmt = stmt.where(and_(*conditions))

            stmt = (
                stmt.order_by(BankTransaction.transaction_date.desc()).offset(offset).limit(limit)
            )

            results = session.execute(stmt).scalars().all()
            return [self._detach_transaction(tx) for tx in results]

    def get_unmatched_outgoing(
        self,
        from_date: Optional[date] = None,
        min_amount: Optional[Decimal] = None,
        limit: int = 100,
    ) -> list[BankTransaction]:
        """Get unmatched outgoing transactions (potential invoice payments).

        Args:
            from_date: Filter from this date.
            min_amount: Minimum absolute amount.
            limit: Maximum results to return.

        Returns:
            List of unmatched outgoing BankTransaction objects.
        """
        with self._get_session() as session:
            conditions = [
                BankTransaction.amount < 0,  # Outgoing
                BankTransaction.match_status == MatchStatus.UNMATCHED.value,
            ]

            if from_date:
                conditions.append(BankTransaction.transaction_date >= from_date)

            if min_amount:
                conditions.append(BankTransaction.amount <= -abs(min_amount))

            stmt = (
                select(BankTransaction)
                .where(and_(*conditions))
                .order_by(BankTransaction.transaction_date.desc())
                .limit(limit)
            )

            results = session.execute(stmt).scalars().all()
            return [self._detach_transaction(tx) for tx in results]

    def search_by_description(
        self,
        pattern: str,
        limit: int = 50,
    ) -> list[BankTransaction]:
        """Search transactions by description pattern.

        Args:
            pattern: Search pattern (supports % wildcard).
            limit: Maximum results.

        Returns:
            List of matching BankTransaction objects.
        """
        with self._get_session() as session:
            stmt = (
                select(BankTransaction)
                .where(BankTransaction.description.ilike(f"%{pattern}%"))
                .order_by(BankTransaction.transaction_date.desc())
                .limit(limit)
            )

            results = session.execute(stmt).scalars().all()
            return [self._detach_transaction(tx) for tx in results]

    def search_by_counterpart(
        self,
        name: Optional[str] = None,
        iban: Optional[str] = None,
        limit: int = 50,
    ) -> list[BankTransaction]:
        """Search transactions by counterpart name or IBAN.

        Args:
            name: Counterpart name pattern.
            iban: Counterpart IBAN.
            limit: Maximum results.

        Returns:
            List of matching BankTransaction objects.
        """
        with self._get_session() as session:
            conditions = []

            if name:
                conditions.append(BankTransaction.counterpart_name.ilike(f"%{name}%"))

            if iban:
                conditions.append(BankTransaction.counterpart_iban == iban)

            if not conditions:
                return []

            stmt = (
                select(BankTransaction)
                .where(or_(*conditions))
                .order_by(BankTransaction.transaction_date.desc())
                .limit(limit)
            )

            results = session.execute(stmt).scalars().all()
            return [self._detach_transaction(tx) for tx in results]

    # ==================== Statistics ====================

    def get_statistics(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
    ) -> dict:
        """Get transaction statistics.

        Args:
            from_date: Start date for statistics.
            to_date: End date for statistics.

        Returns:
            Dictionary with various statistics.
        """
        with self._get_session() as session:
            conditions = []
            if from_date:
                conditions.append(BankTransaction.transaction_date >= from_date)
            if to_date:
                conditions.append(BankTransaction.transaction_date <= to_date)

            base_query = select(BankTransaction)
            if conditions:
                base_query = base_query.where(and_(*conditions))

            # Total count
            total_count = (
                session.execute(
                    select(func.count(BankTransaction.id)).where(
                        and_(*conditions) if conditions else True
                    )
                ).scalar()
                or 0
            )

            # Outgoing sum
            outgoing_sum = session.execute(
                select(func.sum(BankTransaction.amount)).where(
                    and_(
                        BankTransaction.amount < 0,
                        *conditions,
                    )
                )
            ).scalar() or Decimal("0")

            # Incoming sum
            incoming_sum = session.execute(
                select(func.sum(BankTransaction.amount)).where(
                    and_(
                        BankTransaction.amount > 0,
                        *conditions,
                    )
                )
            ).scalar() or Decimal("0")

            # By bank
            bank_counts = session.execute(
                select(BankTransaction.bank, func.count(BankTransaction.id))
                .where(and_(*conditions) if conditions else True)
                .group_by(BankTransaction.bank)
            ).all()

            # By match status
            match_counts = session.execute(
                select(BankTransaction.match_status, func.count(BankTransaction.id))
                .where(and_(*conditions) if conditions else True)
                .group_by(BankTransaction.match_status)
            ).all()

            # By transaction type
            type_counts = session.execute(
                select(BankTransaction.transaction_type, func.count(BankTransaction.id))
                .where(and_(*conditions) if conditions else True)
                .group_by(BankTransaction.transaction_type)
            ).all()

            return {
                "total_transactions": total_count,
                "total_outgoing": float(outgoing_sum),
                "total_incoming": float(incoming_sum),
                "net_flow": float(incoming_sum + outgoing_sum),
                "by_bank": dict(bank_counts),
                "by_match_status": dict(match_counts),
                "by_type": dict(type_counts),
            }

    def get_monthly_summary(
        self,
        year: int,
        month: int,
    ) -> dict:
        """Get monthly transaction summary.

        Args:
            year: Year.
            month: Month (1-12).

        Returns:
            Dictionary with monthly summary.
        """
        from_date = date(year, month, 1)
        if month == 12:
            to_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(year, month + 1, 1) - timedelta(days=1)

        return self.get_statistics(from_date, to_date)
