"""Expense analyzer for trends, alerts, and insights."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func, select

from src.core import get_logger

from .models import (
    Alert,
    AlertSeverity,
    AlertType,
    Budget,
    CategorySummary,
    CATEGORY_NAMES,
    Expense,
    ExpenseCategory,
    MonthlyAnalysis,
    get_session,
    init_db,
)

logger = get_logger("expenses.analyzer")


class ExpenseAnalyzer:
    """Analyzer for expense trends, budgets, and alerts."""

    def __init__(self):
        self.logger = logger
        init_db()

    def analyze_month(self, year: int, month: int) -> MonthlyAnalysis:
        """Analyze expenses for a specific month.

        Args:
            year: Year to analyze
            month: Month to analyze (1-12)

        Returns:
            MonthlyAnalysis with aggregated data
        """
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        with get_session() as session:
            # Get expenses for the month
            expenses = session.execute(
                select(Expense)
                .where(Expense.expense_date >= start_date)
                .where(Expense.expense_date <= end_date)
                .order_by(Expense.expense_date.desc())
            ).scalars().all()

            # Calculate totals
            total_amount = sum(e.amount for e in expenses)

            # Group by category
            by_category = self._analyze_by_category(session, expenses, year, month)

            # Top providers
            top_providers = self._get_top_providers(expenses)

            # Get alerts for the month
            alerts = self._get_month_alerts(session, year, month)

            # Compare with previous month
            comparison, comparison_pct = self._compare_with_previous(
                session, year, month, total_amount
            )

            return MonthlyAnalysis(
                year=year,
                month=month,
                total_expenses=total_amount,
                expense_count=len(expenses),
                by_category=by_category,
                top_providers=top_providers,
                alerts=alerts,
                comparison_previous=comparison,
                comparison_percentage=comparison_pct,
            )

    def _analyze_by_category(
        self,
        session,
        expenses: list[Expense],
        year: int,
        month: int,
    ) -> list[CategorySummary]:
        """Analyze expenses grouped by category."""
        # Group expenses
        category_data = defaultdict(lambda: {"amount": 0.0, "count": 0})
        for expense in expenses:
            category_data[expense.category]["amount"] += expense.amount
            category_data[expense.category]["count"] += 1

        # Get budgets
        budgets = {
            b.category: b for b in
            session.execute(select(Budget).where(Budget.is_active == True)).scalars().all()
        }

        # Get previous month data for trends
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        prev_start = date(prev_year, prev_month, 1)
        _, prev_last = monthrange(prev_year, prev_month)
        prev_end = date(prev_year, prev_month, prev_last)

        prev_expenses = session.execute(
            select(Expense)
            .where(Expense.expense_date >= prev_start)
            .where(Expense.expense_date <= prev_end)
        ).scalars().all()

        prev_by_category = defaultdict(float)
        for exp in prev_expenses:
            prev_by_category[exp.category] += exp.amount

        # Build summaries
        summaries = []
        for category, data in sorted(category_data.items(), key=lambda x: -x[1]["amount"]):
            # Get category display name
            try:
                cat_enum = ExpenseCategory(category)
                cat_name = CATEGORY_NAMES.get(cat_enum, category.title())
            except ValueError:
                cat_name = category.title()

            # Calculate average
            avg = data["amount"] / data["count"] if data["count"] > 0 else 0

            # Budget info
            budget = budgets.get(category)
            budget_limit = budget.monthly_limit if budget else None
            budget_pct = (data["amount"] / budget_limit * 100) if budget_limit else None

            # Trend calculation
            prev_amount = prev_by_category.get(category, 0)
            if prev_amount > 0:
                trend_pct = ((data["amount"] - prev_amount) / prev_amount) * 100
                if trend_pct > 10:
                    trend = "up"
                elif trend_pct < -10:
                    trend = "down"
                else:
                    trend = "stable"
            else:
                trend = "new" if data["amount"] > 0 else "stable"
                trend_pct = 100 if data["amount"] > 0 else 0

            summaries.append(CategorySummary(
                category=category,
                category_name=cat_name,
                total_amount=data["amount"],
                expense_count=data["count"],
                average_amount=avg,
                budget_limit=budget_limit,
                budget_used_percentage=budget_pct,
                trend=trend,
                trend_percentage=trend_pct,
            ))

        return summaries

    def _get_top_providers(self, expenses: list[Expense]) -> list[tuple[str, float]]:
        """Get top providers by total amount."""
        provider_totals = defaultdict(float)
        for expense in expenses:
            provider = expense.provider_name or "Desconhecido"
            provider_totals[provider] += expense.amount

        sorted_providers = sorted(
            provider_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return sorted_providers[:10]

    def _get_month_alerts(self, session, year: int, month: int) -> list[Alert]:
        """Get alerts for the month."""
        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        return list(session.execute(
            select(Alert)
            .where(Alert.created_at >= start_dt)
            .where(Alert.created_at <= end_dt)
            .where(Alert.is_dismissed == False)
            .order_by(Alert.created_at.desc())
        ).scalars().all())

    def _compare_with_previous(
        self,
        session,
        year: int,
        month: int,
        current_total: float,
    ) -> tuple[Optional[float], Optional[float]]:
        """Compare with previous month."""
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        prev_start = date(prev_year, prev_month, 1)
        _, prev_last = monthrange(prev_year, prev_month)
        prev_end = date(prev_year, prev_month, prev_last)

        result = session.execute(
            select(func.sum(Expense.amount))
            .where(Expense.expense_date >= prev_start)
            .where(Expense.expense_date <= prev_end)
        ).scalar()

        prev_total = result or 0.0

        if prev_total > 0:
            diff = current_total - prev_total
            pct = (diff / prev_total) * 100
            return diff, pct

        return None, None

    def check_budgets(self, year: int, month: int) -> list[Alert]:
        """Check budget limits and create alerts.

        Args:
            year: Year to check
            month: Month to check

        Returns:
            List of generated alerts
        """
        alerts = []

        with get_session() as session:
            # Get active budgets
            budgets = session.execute(
                select(Budget).where(Budget.is_active == True)
            ).scalars().all()

            # Get month expenses by category
            start_date = date(year, month, 1)
            _, last_day = monthrange(year, month)
            end_date = date(year, month, last_day)

            category_totals = dict(session.execute(
                select(Expense.category, func.sum(Expense.amount))
                .where(Expense.expense_date >= start_date)
                .where(Expense.expense_date <= end_date)
                .group_by(Expense.category)
            ).all())

            for budget in budgets:
                spent = category_totals.get(budget.category, 0.0)
                usage_pct = spent / budget.monthly_limit if budget.monthly_limit > 0 else 0

                if usage_pct >= 1.0:
                    # Budget exceeded
                    alert = Alert(
                        alert_type=AlertType.BUDGET_EXCEEDED.value,
                        severity=AlertSeverity.CRITICAL.value,
                        category=budget.category,
                        message=f"Orçamento de {budget.category} excedido: {spent:.2f}€ / {budget.monthly_limit:.2f}€",
                        details=f"Utilização: {usage_pct*100:.1f}%",
                    )
                    session.add(alert)
                    alerts.append(alert)

                elif usage_pct >= budget.warning_threshold:
                    # Budget warning
                    alert = Alert(
                        alert_type=AlertType.BUDGET_WARNING.value,
                        severity=AlertSeverity.WARNING.value,
                        category=budget.category,
                        message=f"Orçamento de {budget.category} em {usage_pct*100:.0f}%: {spent:.2f}€ / {budget.monthly_limit:.2f}€",
                        details=f"Restam {budget.monthly_limit - spent:.2f}€",
                    )
                    session.add(alert)
                    alerts.append(alert)

            session.commit()

        return alerts

    def detect_unusual_expenses(self, year: int, month: int) -> list[Alert]:
        """Detect unusual expenses (significantly higher than average).

        Args:
            year: Year to check
            month: Month to check

        Returns:
            List of alerts for unusual expenses
        """
        alerts = []

        with get_session() as session:
            start_date = date(year, month, 1)
            _, last_day = monthrange(year, month)
            end_date = date(year, month, last_day)

            # Get month expenses
            month_expenses = session.execute(
                select(Expense)
                .where(Expense.expense_date >= start_date)
                .where(Expense.expense_date <= end_date)
            ).scalars().all()

            # Get historical averages (last 6 months)
            hist_start = start_date - timedelta(days=180)
            hist_avg = dict(session.execute(
                select(
                    Expense.category,
                    func.avg(Expense.amount),
                    func.stddev(Expense.amount)
                )
                .where(Expense.expense_date >= hist_start)
                .where(Expense.expense_date < start_date)
                .group_by(Expense.category)
            ).all())

            # Check each expense
            for expense in month_expenses:
                if expense.category in hist_avg:
                    avg, stddev = hist_avg[expense.category]
                    if avg and stddev and expense.amount > avg + (2 * stddev):
                        # Unusually high expense
                        alert = Alert(
                            alert_type=AlertType.UNUSUAL_EXPENSE.value,
                            severity=AlertSeverity.WARNING.value,
                            category=expense.category,
                            message=f"Despesa invulgar em {expense.category}: {expense.amount:.2f}€ (média: {avg:.2f}€)",
                            expense_id=expense.id,
                        )
                        session.add(alert)
                        alerts.append(alert)

            session.commit()

        return alerts

    def get_trends(self, months: int = 6) -> dict:
        """Get expense trends over the last N months.

        Args:
            months: Number of months to analyze

        Returns:
            Dictionary with trend data
        """
        trends = {
            "monthly_totals": [],
            "by_category": defaultdict(list),
            "average_monthly": 0.0,
            "trend_direction": "stable",
        }

        with get_session() as session:
            today = date.today()

            for i in range(months - 1, -1, -1):
                # Calculate month
                year = today.year
                month = today.month - i
                while month <= 0:
                    month += 12
                    year -= 1

                start_date = date(year, month, 1)
                _, last_day = monthrange(year, month)
                end_date = date(year, month, last_day)

                # Get total for month
                total = session.execute(
                    select(func.sum(Expense.amount))
                    .where(Expense.expense_date >= start_date)
                    .where(Expense.expense_date <= end_date)
                ).scalar() or 0.0

                trends["monthly_totals"].append({
                    "year": year,
                    "month": month,
                    "total": total,
                })

                # Get by category
                cat_totals = session.execute(
                    select(Expense.category, func.sum(Expense.amount))
                    .where(Expense.expense_date >= start_date)
                    .where(Expense.expense_date <= end_date)
                    .group_by(Expense.category)
                ).all()

                for cat, amount in cat_totals:
                    trends["by_category"][cat].append(amount)

        # Calculate average and trend
        totals = [m["total"] for m in trends["monthly_totals"]]
        if totals:
            trends["average_monthly"] = sum(totals) / len(totals)

            # Simple trend detection
            if len(totals) >= 3:
                recent_avg = sum(totals[-3:]) / 3
                older_avg = sum(totals[:-3]) / max(len(totals) - 3, 1)

                if recent_avg > older_avg * 1.1:
                    trends["trend_direction"] = "up"
                elif recent_avg < older_avg * 0.9:
                    trends["trend_direction"] = "down"

        return trends

    def get_pending_alerts(self) -> list[Alert]:
        """Get all unread/undismissed alerts."""
        with get_session() as session:
            return list(session.execute(
                select(Alert)
                .where(Alert.is_dismissed == False)
                .order_by(Alert.created_at.desc())
            ).scalars().all())

    def dismiss_alert(self, alert_id: int) -> bool:
        """Dismiss an alert."""
        with get_session() as session:
            alert = session.get(Alert, alert_id)
            if alert:
                alert.is_dismissed = True
                session.commit()
                return True
            return False
