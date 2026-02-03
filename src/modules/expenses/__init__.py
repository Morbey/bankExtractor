"""Expense tracker module (Phase 5).

This module provides expense tracking, budgeting, and analysis functionality.
It can import expenses from indexed documents, categorize them automatically,
and provide insights through alerts and trends.

Example usage:
    from src.modules.expenses import ExpenseTracker

    tracker = ExpenseTracker()

    # Import expenses from documents
    tracker.import_from_documents()

    # Set a budget
    from src.modules.expenses import ExpenseCategory
    tracker.set_budget(ExpenseCategory.UTILITIES, 200.0)

    # Analyze current month
    analysis = tracker.analyze_current_month()
    print(f"Total: {analysis.total_expenses}€")

    # Check budget status
    status = tracker.get_budget_status(2024, 1)
    for s in status:
        print(f"{s['category_name']}: {s['percentage']:.0f}%")
"""

from .analyzer import ExpenseAnalyzer
from .categorizer import ExpenseCategorizer, categorize_expense
from .models import (
    Alert,
    AlertSeverity,
    AlertType,
    Budget,
    CATEGORY_NAMES,
    CategorySummary,
    Expense,
    ExpenseCategory,
    MonthlyAnalysis,
    PROVIDER_CATEGORIES,
    RecurringExpense,
    get_session,
    init_db,
)
from .tracker import ExpenseTracker

__all__ = [
    # Models
    "Expense",
    "ExpenseCategory",
    "Budget",
    "Alert",
    "AlertType",
    "AlertSeverity",
    "RecurringExpense",
    "CategorySummary",
    "MonthlyAnalysis",
    "CATEGORY_NAMES",
    "PROVIDER_CATEGORIES",
    "init_db",
    "get_session",
    # Categorizer
    "ExpenseCategorizer",
    "categorize_expense",
    # Analyzer
    "ExpenseAnalyzer",
    # Tracker
    "ExpenseTracker",
]
