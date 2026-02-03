"""Bank transaction management module.

This module provides functionality for:
- Storing bank transactions extracted from statements
- Deduplication to avoid importing the same transaction twice
- Matching transactions to invoices/faturas for payment verification

Example usage:
    from src.modules.transactions import TransactionDatabase, BankTransaction

    # Initialize database
    db = TransactionDatabase()

    # Import transactions from a statement
    transactions = [
        {
            "transaction_date": date(2025, 1, 15),
            "value_date": date(2025, 1, 15),
            "description": "TRANSF PARA FORNECEDOR X",
            "amount": Decimal("-150.00"),
            "counterpart_iban": "PT50123456789012345678901",
            "counterpart_name": "Fornecedor X",
        },
        ...
    ]
    imported, skipped = db.import_from_statement("cgd", "PT50...", transactions)

    # Find matching payment for an invoice
    result = db.find_matching_payment(
        amount=Decimal("150.00"),
        iban="PT50123456789012345678901",
        date_range_days=30,
    )
    if result.found:
        print(f"Payment found: {result.transaction.description}")
        print(f"Match confidence: {result.confidence}")
"""

from .models import (
    BankTransaction,
    Base,
    MatchStatus,
    TransactionType,
    get_engine,
    get_session,
    init_db,
)
from .transaction_db import (
    AMOUNT_TOLERANCE,
    MatchResult,
    TransactionDatabase,
)

__all__ = [
    # Models
    "BankTransaction",
    "Base",
    "MatchStatus",
    "TransactionType",
    # Database functions
    "get_engine",
    "get_session",
    "init_db",
    # Transaction database class
    "TransactionDatabase",
    "MatchResult",
    "AMOUNT_TOLERANCE",
]
