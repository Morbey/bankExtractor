"""Report generator for creating monthly financial reports."""

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func, select

from src.core import get_logger, settings
from src.modules.organizer import Document, DocumentType, Provider, get_session

from .models import (
    DocumentSummary,
    EXPENSE_CATEGORIES,
    ExpenseCategory,
    MonthlyComparison,
    ProviderSummary,
    ReportConfig,
    ReportData,
    ReportPeriod,
)

logger = get_logger("reporter.generator")


class ReportGenerator:
    """Generator for monthly financial reports."""

    def __init__(self):
        self.logger = logger

    def generate(self, config: ReportConfig) -> ReportData:
        """Generate a monthly report based on the configuration.

        Args:
            config: Report configuration with period and options

        Returns:
            ReportData with all aggregated information
        """
        self.logger.info(f"A gerar relatório para {config.month:02d}/{config.year}...")

        # Calculate period dates
        period_start = date(config.year, config.month, 1)
        _, last_day = monthrange(config.year, config.month)
        period_end = date(config.year, config.month, last_day)

        # Create report data structure
        report = ReportData(
            year=config.year,
            month=config.month,
            period_start=period_start,
            period_end=period_end,
            generated_at=date.today(),
        )

        with get_session() as session:
            # Get documents for the period
            documents = self._get_documents_for_period(session, period_start, period_end)

            if not documents:
                self.logger.warning("Nenhum documento encontrado para o período.")
                report.notes.append("Nenhum documento encontrado para este período.")
                return report

            # Populate report data
            report.total_documents = len(documents)
            report.total_amount = sum(d.amount or 0 for d in documents)

            # Count by type
            for doc in documents:
                if doc.document_type == DocumentType.INVOICE.value:
                    report.total_invoices += 1
                elif doc.document_type == DocumentType.STATEMENT.value:
                    report.total_statements += 1
                elif doc.document_type == DocumentType.RECEIPT.value:
                    report.total_receipts += 1

            # Aggregate by category
            report.by_category = self._aggregate_by_category(documents)

            # Aggregate by provider
            report.by_provider = self._aggregate_by_provider(documents)

            # Create document summaries
            if config.include_documents_list:
                report.documents = self._create_document_summaries(
                    documents, config.max_documents_shown
                )

            # Calculate comparison with previous month
            if config.include_comparison:
                report.comparison = self._calculate_comparison(
                    session, config.year, config.month, report.total_amount
                )

        self.logger.info(
            f"Relatório gerado: {report.total_documents} documentos, "
            f"{report.total_amount:.2f}€ total"
        )

        return report

    def _get_documents_for_period(
        self,
        session,
        start_date: date,
        end_date: date,
    ) -> list[Document]:
        """Get all documents within a date range."""
        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        stmt = (
            select(Document)
            .where(Document.document_date >= start_dt)
            .where(Document.document_date <= end_dt)
            .order_by(Document.document_date.desc())
        )

        return list(session.execute(stmt).scalars().all())

    def _aggregate_by_category(self, documents: list[Document]) -> list[ExpenseCategory]:
        """Aggregate documents by expense category."""
        category_totals = defaultdict(lambda: {"amount": 0.0, "count": 0})

        for doc in documents:
            # Determine category from provider
            category = "outros"
            if doc.provider and doc.provider.category:
                category = doc.provider.category

            amount = doc.amount or 0
            category_totals[category]["amount"] += amount
            category_totals[category]["count"] += 1

        # Calculate total for percentages
        total_amount = sum(c["amount"] for c in category_totals.values())

        # Build category list
        categories = []
        for cat_id, data in sorted(category_totals.items(), key=lambda x: -x[1]["amount"]):
            cat_info = EXPENSE_CATEGORIES.get(cat_id, {"name": cat_id.title()})
            percentage = (data["amount"] / total_amount * 100) if total_amount > 0 else 0

            categories.append(
                ExpenseCategory(
                    name=cat_info.get("name", cat_id.title()),
                    amount=data["amount"],
                    count=data["count"],
                    percentage=percentage,
                )
            )

        return categories

    def _aggregate_by_provider(self, documents: list[Document]) -> list[ProviderSummary]:
        """Aggregate documents by provider."""
        provider_totals = defaultdict(
            lambda: {"amount": 0.0, "count": 0, "category": None}
        )

        for doc in documents:
            provider_name = doc.provider.name if doc.provider else "Desconhecido"
            provider_category = doc.provider.category if doc.provider else None

            provider_totals[provider_name]["amount"] += doc.amount or 0
            provider_totals[provider_name]["count"] += 1
            provider_totals[provider_name]["category"] = provider_category

        # Build provider list
        providers = []
        for name, data in sorted(provider_totals.items(), key=lambda x: -x[1]["amount"]):
            providers.append(
                ProviderSummary(
                    name=name,
                    category=data["category"],
                    total_amount=data["amount"],
                    document_count=data["count"],
                )
            )

        return providers

    def _create_document_summaries(
        self,
        documents: list[Document],
        max_count: int,
    ) -> list[DocumentSummary]:
        """Create document summaries for the report."""
        summaries = []

        for doc in documents[:max_count]:
            summaries.append(
                DocumentSummary(
                    id=doc.id,
                    file_name=doc.file_name,
                    document_type=doc.document_type,
                    provider=doc.provider.name if doc.provider else None,
                    document_date=doc.document_date.date() if doc.document_date else None,
                    amount=doc.amount,
                    reference=doc.reference,
                )
            )

        return summaries

    def _calculate_comparison(
        self,
        session,
        year: int,
        month: int,
        current_total: float,
    ) -> Optional[MonthlyComparison]:
        """Calculate comparison with previous month."""
        # Calculate previous month
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1

        prev_start = date(prev_year, prev_month, 1)
        _, prev_last_day = monthrange(prev_year, prev_month)
        prev_end = date(prev_year, prev_month, prev_last_day)

        # Get previous month's total
        prev_start_dt = datetime.combine(prev_start, datetime.min.time())
        prev_end_dt = datetime.combine(prev_end, datetime.max.time())

        result = session.execute(
            select(func.sum(Document.amount))
            .where(Document.document_date >= prev_start_dt)
            .where(Document.document_date <= prev_end_dt)
        ).scalar()

        previous_total = result or 0.0

        return MonthlyComparison.calculate(current_total, previous_total)

    def generate_quarterly(self, year: int, quarter: int) -> ReportData:
        """Generate a quarterly report.

        Args:
            year: Year for the report
            quarter: Quarter number (1-4)

        Returns:
            ReportData with quarterly aggregation
        """
        # Determine months in quarter
        start_month = (quarter - 1) * 3 + 1
        end_month = start_month + 2

        period_start = date(year, start_month, 1)
        _, last_day = monthrange(year, end_month)
        period_end = date(year, end_month, last_day)

        report = ReportData(
            year=year,
            month=start_month,  # First month of quarter
            period_start=period_start,
            period_end=period_end,
            report_type=ReportPeriod.QUARTERLY,
            generated_at=date.today(),
        )

        with get_session() as session:
            documents = self._get_documents_for_period(session, period_start, period_end)

            if documents:
                report.total_documents = len(documents)
                report.total_amount = sum(d.amount or 0 for d in documents)
                report.by_category = self._aggregate_by_category(documents)
                report.by_provider = self._aggregate_by_provider(documents)

        return report

    def generate_yearly(self, year: int) -> ReportData:
        """Generate a yearly report.

        Args:
            year: Year for the report

        Returns:
            ReportData with yearly aggregation
        """
        period_start = date(year, 1, 1)
        period_end = date(year, 12, 31)

        report = ReportData(
            year=year,
            month=1,
            period_start=period_start,
            period_end=period_end,
            report_type=ReportPeriod.YEARLY,
            generated_at=date.today(),
        )

        with get_session() as session:
            documents = self._get_documents_for_period(session, period_start, period_end)

            if documents:
                report.total_documents = len(documents)
                report.total_amount = sum(d.amount or 0 for d in documents)
                report.by_category = self._aggregate_by_category(documents)
                report.by_provider = self._aggregate_by_provider(documents)

        return report
