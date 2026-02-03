"""Invoice downloader - orchestrates downloads from multiple email providers."""

from datetime import date
from typing import Optional

from src.core import get_logger

from .base import COMMON_INVOICE_SENDERS, DownloadedInvoice, EmailFilter, EmailProviderBase
from .gmail import GmailProvider
from .hotmail import HotmailProvider


# Registry of available email providers
EMAIL_PROVIDERS: dict[str, type[EmailProviderBase]] = {
    "gmail": GmailProvider,
    "hotmail": HotmailProvider,
}


class InvoiceDownloader:
    """Orchestrates invoice downloads from multiple email providers.

    Example usage:
        downloader = InvoiceDownloader()

        # Download from all configured providers
        invoices = downloader.download_all()

        # Download from specific provider
        invoices = downloader.download_from("gmail")

        # Download with custom filter
        from datetime import date
        filter = EmailFilter(
            start_date=date(2024, 1, 1),
            senders=["noreply@edp.pt"]
        )
        invoices = downloader.download_from("gmail", filter)
    """

    def __init__(self):
        self.logger = get_logger("invoices.downloader")

    def download_from(
        self,
        provider_id: str,
        email_filter: Optional[EmailFilter] = None,
        account: Optional[str] = None,
    ) -> list[DownloadedInvoice]:
        """Download invoices from a specific email provider.

        Args:
            provider_id: Email provider identifier (gmail, hotmail)
            email_filter: Optional filter criteria. If None, uses default filter
                         with common invoice senders.
            account: Optional account name for multiple accounts (e.g., 'pessoal', 'empresa')

        Returns:
            List of downloaded invoices
        """
        if provider_id not in EMAIL_PROVIDERS:
            self.logger.error(f"Provider desconhecido: {provider_id}")
            self.logger.info(f"Providers disponíveis: {', '.join(EMAIL_PROVIDERS.keys())}")
            return []

        provider_class = EMAIL_PROVIDERS[provider_id]

        # Use default filter with common senders if not specified
        if email_filter is None:
            email_filter = EmailFilter(
                senders=COMMON_INVOICE_SENDERS,
            )

        account_display = f"{provider_id} ({account})" if account else provider_id
        self.logger.info(f"A iniciar download de faturas via {account_display}...")

        with provider_class(account=account) as provider:
            return provider.run(email_filter)

    def download_all(
        self,
        email_filter: Optional[EmailFilter] = None,
    ) -> list[DownloadedInvoice]:
        """Download invoices from all available email providers.

        Args:
            email_filter: Optional filter criteria. If None, uses default filter
                         with common invoice senders.

        Returns:
            List of downloaded invoices from all providers
        """
        all_invoices = []

        for provider_id in EMAIL_PROVIDERS:
            try:
                invoices = self.download_from(provider_id, email_filter)
                all_invoices.extend(invoices)
            except Exception as e:
                self.logger.error(f"Erro no provider {provider_id}: {e}")
                continue

        return all_invoices

    def download_recent(
        self,
        provider_id: Optional[str] = None,
        days: int = 30,
    ) -> list[DownloadedInvoice]:
        """Download invoices from the last N days.

        Args:
            provider_id: Optional provider ID. If None, downloads from all providers.
            days: Number of days to look back (default: 30)

        Returns:
            List of downloaded invoices
        """
        from datetime import timedelta

        today = date.today()
        start_date = today - timedelta(days=days)

        email_filter = EmailFilter(
            senders=COMMON_INVOICE_SENDERS,
            start_date=start_date,
            end_date=today,
        )

        self.logger.info(f"A procurar faturas dos últimos {days} dias...")

        if provider_id:
            return self.download_from(provider_id, email_filter)
        else:
            return self.download_all(email_filter)

    def download_by_sender(
        self,
        senders: list[str],
        provider_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[DownloadedInvoice]:
        """Download invoices from specific senders.

        Args:
            senders: List of sender email addresses
            provider_id: Optional provider ID. If None, downloads from all providers.
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of downloaded invoices
        """
        email_filter = EmailFilter(
            senders=senders,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(f"A procurar faturas de {len(senders)} remetentes...")

        if provider_id:
            return self.download_from(provider_id, email_filter)
        else:
            return self.download_all(email_filter)

    def download_month(
        self,
        year: int,
        month: int,
        provider_id: Optional[str] = None,
    ) -> list[DownloadedInvoice]:
        """Download invoices for a specific month.

        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)
            provider_id: Optional provider ID. If None, downloads from all providers.

        Returns:
            List of downloaded invoices
        """
        from calendar import monthrange

        start_date = date(year, month, 1)
        _, last_day = monthrange(year, month)
        end_date = date(year, month, last_day)

        email_filter = EmailFilter(
            senders=COMMON_INVOICE_SENDERS,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(f"A procurar faturas de {month:02d}/{year}...")

        if provider_id:
            return self.download_from(provider_id, email_filter)
        else:
            return self.download_all(email_filter)
