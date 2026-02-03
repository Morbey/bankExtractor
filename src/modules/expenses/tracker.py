"""Expense tracker - main interface for expense management."""

from datetime import date
from typing import Optional

from sqlalchemy import select

from src.core import get_logger
from src.modules.organizer import Document, get_session as get_doc_session

from .analyzer import ExpenseAnalyzer
from .categorizer import ExpenseCategorizer
from .models import (
    Budget,
    CATEGORY_NAMES,
    Expense,
    ExpenseCategory,
    RecurringExpense,
    get_session,
    init_db,
)

logger = get_logger("expenses.tracker")


class ExpenseTracker:
    """Main expense tracking interface.

    Provides methods for:
    - Importing expenses from indexed documents
    - Managing budgets
    - Tracking recurring expenses
    - Running analysis
    """

    def __init__(self):
        self.logger = logger
        self.categorizer = ExpenseCategorizer()
        self.analyzer = ExpenseAnalyzer()
        init_db()

    def import_from_documents(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> int:
        """Import expenses from indexed documents.

        Args:
            year: Optional year filter
            month: Optional month filter

        Returns:
            Number of expenses imported
        """
        self.logger.info("A importar despesas dos documentos indexados...")

        imported = 0

        with get_doc_session() as doc_session, get_session() as exp_session:
            # Build query
            stmt = select(Document).where(Document.amount.isnot(None))

            if year and month:
                from calendar import monthrange
                from datetime import datetime
                start = datetime(year, month, 1)
                _, last = monthrange(year, month)
                end = datetime(year, month, last, 23, 59, 59)
                stmt = stmt.where(Document.document_date >= start)
                stmt = stmt.where(Document.document_date <= end)

            documents = doc_session.execute(stmt).scalars().all()

            for doc in documents:
                # Check if already imported
                existing = exp_session.execute(
                    select(Expense).where(Expense.document_id == doc.id)
                ).scalar_one_or_none()

                if existing:
                    continue

                # Categorize
                provider_name = doc.provider.name if doc.provider else None
                category, confidence = self.categorizer.categorize(
                    provider_name=provider_name,
                    description=doc.text_content[:500] if doc.text_content else None,
                    amount=doc.amount,
                )

                # Create expense
                expense = Expense(
                    document_id=doc.id,
                    amount=doc.amount,
                    description=doc.file_name,
                    category=category.value,
                    provider_name=provider_name,
                    expense_date=doc.document_date.date() if doc.document_date else date.today(),
                    due_date=doc.due_date.date() if doc.due_date else None,
                    is_recurring=self.categorizer.is_recurring(category, provider_name),
                    is_essential=self.categorizer.is_essential(category, provider_name),
                    is_tax_deductible=self.categorizer.is_tax_deductible(category),
                )

                exp_session.add(expense)
                imported += 1

            exp_session.commit()

        self.logger.info(f"Importadas {imported} despesas.")
        return imported

    def add_expense(
        self,
        amount: float,
        category: ExpenseCategory,
        description: str,
        expense_date: Optional[date] = None,
        provider_name: Optional[str] = None,
        is_recurring: bool = False,
        notes: Optional[str] = None,
    ) -> Expense:
        """Manually add an expense.

        Args:
            amount: Expense amount
            category: Expense category
            description: Description
            expense_date: Date of expense (default: today)
            provider_name: Provider/vendor name
            is_recurring: Whether expense recurs
            notes: Additional notes

        Returns:
            Created Expense object
        """
        with get_session() as session:
            expense = Expense(
                amount=amount,
                category=category.value,
                description=description,
                expense_date=expense_date or date.today(),
                provider_name=provider_name,
                is_recurring=is_recurring,
                is_essential=self.categorizer.is_essential(category),
                is_tax_deductible=self.categorizer.is_tax_deductible(category),
                notes=notes,
            )
            session.add(expense)
            session.commit()
            session.refresh(expense)

            self.logger.info(f"Adicionada despesa: {amount}€ em {category.value}")
            return expense

    def get_expenses(
        self,
        year: Optional[int] = None,
        month: Optional[int] = None,
        category: Optional[ExpenseCategory] = None,
        provider: Optional[str] = None,
        limit: int = 100,
    ) -> list[Expense]:
        """Get expenses with optional filters.

        Args:
            year: Filter by year
            month: Filter by month
            category: Filter by category
            provider: Filter by provider name
            limit: Maximum results

        Returns:
            List of expenses
        """
        with get_session() as session:
            stmt = select(Expense)

            if year:
                stmt = stmt.where(
                    Expense.expense_date >= date(year, 1, 1)
                ).where(
                    Expense.expense_date <= date(year, 12, 31)
                )

            if year and month:
                from calendar import monthrange
                _, last = monthrange(year, month)
                stmt = stmt.where(Expense.expense_date >= date(year, month, 1))
                stmt = stmt.where(Expense.expense_date <= date(year, month, last))

            if category:
                stmt = stmt.where(Expense.category == category.value)

            if provider:
                stmt = stmt.where(Expense.provider_name.ilike(f"%{provider}%"))

            stmt = stmt.order_by(Expense.expense_date.desc()).limit(limit)

            return list(session.execute(stmt).scalars().all())

    # Budget management

    def set_budget(
        self,
        category: ExpenseCategory,
        monthly_limit: float,
        warning_threshold: float = 0.8,
    ) -> Budget:
        """Set or update a budget for a category.

        Args:
            category: Category to budget
            monthly_limit: Monthly spending limit
            warning_threshold: Percentage at which to warn (0.0-1.0)

        Returns:
            Budget object
        """
        with get_session() as session:
            # Check for existing budget
            existing = session.execute(
                select(Budget).where(Budget.category == category.value)
            ).scalar_one_or_none()

            if existing:
                existing.monthly_limit = monthly_limit
                existing.warning_threshold = warning_threshold
                existing.is_active = True
                session.commit()
                self.logger.info(f"Orçamento atualizado: {category.value} = {monthly_limit}€")
                return existing
            else:
                budget = Budget(
                    category=category.value,
                    monthly_limit=monthly_limit,
                    warning_threshold=warning_threshold,
                )
                session.add(budget)
                session.commit()
                session.refresh(budget)
                self.logger.info(f"Orçamento criado: {category.value} = {monthly_limit}€")
                return budget

    def get_budgets(self, active_only: bool = True) -> list[Budget]:
        """Get all budgets.

        Args:
            active_only: Only return active budgets

        Returns:
            List of budgets
        """
        with get_session() as session:
            stmt = select(Budget)
            if active_only:
                stmt = stmt.where(Budget.is_active == True)
            return list(session.execute(stmt).scalars().all())

    def delete_budget(self, category: ExpenseCategory) -> bool:
        """Delete a budget (deactivate it).

        Args:
            category: Category to remove budget for

        Returns:
            True if deleted
        """
        with get_session() as session:
            budget = session.execute(
                select(Budget).where(Budget.category == category.value)
            ).scalar_one_or_none()

            if budget:
                budget.is_active = False
                session.commit()
                return True
            return False

    def get_budget_status(self, year: int, month: int) -> list[dict]:
        """Get budget status for a month.

        Args:
            year: Year
            month: Month

        Returns:
            List of budget status dictionaries
        """
        from calendar import monthrange
        from sqlalchemy import func

        status = []

        with get_session() as session:
            budgets = session.execute(
                select(Budget).where(Budget.is_active == True)
            ).scalars().all()

            _, last = monthrange(year, month)
            start = date(year, month, 1)
            end = date(year, month, last)

            for budget in budgets:
                # Get spent amount
                spent = session.execute(
                    select(func.sum(Expense.amount))
                    .where(Expense.category == budget.category)
                    .where(Expense.expense_date >= start)
                    .where(Expense.expense_date <= end)
                ).scalar() or 0.0

                remaining = budget.monthly_limit - spent
                percentage = (spent / budget.monthly_limit * 100) if budget.monthly_limit > 0 else 0

                try:
                    cat_name = CATEGORY_NAMES.get(
                        ExpenseCategory(budget.category),
                        budget.category.title()
                    )
                except ValueError:
                    cat_name = budget.category.title()

                status.append({
                    "category": budget.category,
                    "category_name": cat_name,
                    "limit": budget.monthly_limit,
                    "spent": spent,
                    "remaining": remaining,
                    "percentage": percentage,
                    "is_exceeded": percentage >= 100,
                    "is_warning": percentage >= budget.warning_threshold * 100,
                })

        return sorted(status, key=lambda x: x["percentage"], reverse=True)

    # Recurring expenses

    def add_recurring(
        self,
        name: str,
        provider_name: str,
        category: ExpenseCategory,
        expected_amount: float,
        frequency: str = "monthly",
    ) -> RecurringExpense:
        """Add a recurring expense definition.

        Args:
            name: Name for the recurring expense
            provider_name: Provider name
            category: Category
            expected_amount: Expected monthly amount
            frequency: monthly, quarterly, yearly

        Returns:
            RecurringExpense object
        """
        with get_session() as session:
            recurring = RecurringExpense(
                name=name,
                provider_name=provider_name,
                category=category.value,
                expected_amount=expected_amount,
                frequency=frequency,
            )
            session.add(recurring)
            session.commit()
            session.refresh(recurring)
            return recurring

    def get_recurring(self, active_only: bool = True) -> list[RecurringExpense]:
        """Get recurring expense definitions."""
        with get_session() as session:
            stmt = select(RecurringExpense)
            if active_only:
                stmt = stmt.where(RecurringExpense.is_active == True)
            return list(session.execute(stmt).scalars().all())

    # Analysis shortcuts

    def analyze_current_month(self):
        """Analyze the current month."""
        today = date.today()
        return self.analyzer.analyze_month(today.year, today.month)

    def check_all_budgets(self):
        """Check budgets for current month."""
        today = date.today()
        return self.analyzer.check_budgets(today.year, today.month)

    def get_alerts(self):
        """Get pending alerts."""
        return self.analyzer.get_pending_alerts()

    def get_trends(self, months: int = 6):
        """Get expense trends."""
        return self.analyzer.get_trends(months)
