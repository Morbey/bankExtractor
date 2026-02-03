"""Invoice downloader - orchestrates downloads from multiple email providers."""

import threading
from datetime import date
from queue import Queue
from typing import Callable, Optional

from src.core import get_logger

from .base import (
    COMMON_INVOICE_SENDERS,
    DownloadedInvoice,
    EmailFilter,
    EmailProviderBase,
    ProgressCallback,
)
from .gmail import GmailProvider
from .hotmail import HotmailProvider
from .inbox_db import InboxDatabase

# Registry of available email providers
EMAIL_PROVIDERS: dict[str, type[EmailProviderBase]] = {
    "gmail": GmailProvider,
    "hotmail": HotmailProvider,
}

# Type alias for invoice callback
InvoiceCallback = Callable[[DownloadedInvoice], None]

# Sentinel to signal end of queue
_DOWNLOAD_COMPLETE = object()


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
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[DownloadedInvoice]:
        """Download invoices from a specific email provider.

        Args:
            provider_id: Email provider identifier (gmail, hotmail)
            email_filter: Optional filter criteria. If None, uses default filter
                         with common invoice senders.
            account: Optional account name for multiple accounts (e.g., 'pessoal', 'empresa')
            progress_callback: Optional callback for progress updates.
                              Called with (stage, current, total, message)

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
            return provider.run(email_filter, progress_callback)

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

    def download_streaming(
        self,
        provider_id: str,
        email_filter: Optional[EmailFilter] = None,
        account: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[Queue, threading.Thread]:
        """Download invoices with streaming - returns queue that receives invoices as downloaded.

        This allows processing invoices while download is still in progress.

        Args:
            provider_id: Email provider identifier (gmail, hotmail)
            email_filter: Optional filter criteria
            account: Optional account name
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (invoice_queue, download_thread).
            Queue receives DownloadedInvoice objects, then _DOWNLOAD_COMPLETE sentinel when done.
            Thread can be joined to wait for completion.

        Example:
            queue, thread = downloader.download_streaming("gmail", filter)

            while True:
                item = queue.get()
                if item is _DOWNLOAD_COMPLETE:
                    break
                # Process invoice
                process(item)

            thread.join()  # Ensure thread is cleaned up
        """
        invoice_queue: Queue = Queue()

        def download_worker():
            try:
                if provider_id not in EMAIL_PROVIDERS:
                    self.logger.error(f"Provider desconhecido: {provider_id}")
                    return

                provider_class = EMAIL_PROVIDERS[provider_id]
                filter_to_use = email_filter or EmailFilter(senders=COMMON_INVOICE_SENDERS)

                # Don't use context manager - manually control connect/disconnect
                # to allow proper progress feedback
                provider = provider_class(account=account)

                if progress_callback:
                    progress_callback("connect", 0, 1, "A ligar ao servidor...")

                if not provider.connect():
                    self.logger.error("Falha na ligação ao servidor de email.")
                    return

                if progress_callback:
                    progress_callback("connect", 1, 1, "Ligado com sucesso")

                try:
                    # Search emails
                    messages = provider.search_emails(filter_to_use, progress_callback)
                    self.logger.info(f"Encontrados {len(messages)} emails com faturas.")

                    if progress_callback:
                        progress_callback(
                            "download", 0, len(messages), f"A processar {len(messages)} emails..."
                        )

                    # Download and stream each invoice
                    for i, msg in enumerate(messages):
                        if progress_callback:
                            subject = msg.get("Subject", "")[:40]
                            progress_callback(
                                "download", i + 1, len(messages), f"A processar: {subject}..."
                            )

                        invoices = provider.download_attachments(
                            msg, filter_to_use.attachment_extensions
                        )

                        # Put each invoice in queue immediately
                        for invoice in invoices:
                            invoice_queue.put(invoice)

                    self.logger.info("Download concluído.")
                finally:
                    provider.disconnect()

            except Exception as e:
                self.logger.error(f"Erro no download: {e}")
            finally:
                # Signal completion
                invoice_queue.put(_DOWNLOAD_COMPLETE)

        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()

        return invoice_queue, thread

    def download_streaming_multi(
        self,
        providers: list[str],
        email_filter: Optional[EmailFilter] = None,
        account: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[Queue, threading.Thread]:
        """Download from multiple providers with streaming.

        Args:
            providers: List of provider IDs
            email_filter: Optional filter criteria
            account: Optional account name
            progress_callback: Optional callback for progress updates

        Returns:
            Tuple of (invoice_queue, download_thread)
        """
        invoice_queue: Queue = Queue()

        def download_worker():
            try:
                filter_to_use = email_filter or EmailFilter(senders=COMMON_INVOICE_SENDERS)

                for provider_id in providers:
                    if provider_id not in EMAIL_PROVIDERS:
                        self.logger.error(f"Provider desconhecido: {provider_id}")
                        continue

                    provider_class = EMAIL_PROVIDERS[provider_id]

                    # Don't use context manager - manually control connect/disconnect
                    provider = provider_class(account=account)

                    try:
                        if progress_callback:
                            progress_callback("connect", 0, 1, f"A ligar a {provider_id}...")

                        if not provider.connect():
                            self.logger.error(f"Falha na ligação a {provider_id}.")
                            continue

                        if progress_callback:
                            progress_callback("connect", 1, 1, f"Ligado a {provider_id}")

                        # Use streaming method - processes each email immediately
                        def on_invoice(invoice):
                            invoice_queue.put(invoice)

                        provider.run_streaming(
                            email_filter=filter_to_use,
                            invoice_callback=on_invoice,
                            progress_callback=progress_callback,
                        )

                    except Exception as e:
                        self.logger.error(f"Erro em {provider_id}: {e}")
                    finally:
                        provider.disconnect()

            finally:
                invoice_queue.put(_DOWNLOAD_COMPLETE)

        thread = threading.Thread(target=download_worker, daemon=True)
        thread.start()

        return invoice_queue, thread

    def scrape_to_inbox(
        self,
        provider_id: str,
        email_filter: Optional[EmailFilter] = None,
        account: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[int, int, int, int]:
        """Scrape emails and store in inbox database (without processing).

        Downloads attachments and stores them in the inbox database for later
        processing. Performs deduplication by message_id (emails) and
        content hash (attachments).

        Args:
            provider_id: Email provider identifier (gmail, hotmail).
            email_filter: Optional filter criteria. If None, uses default.
            account: Optional account name (e.g., 'pessoal', 'empresa').
            progress_callback: Optional callback for progress updates.

        Returns:
            Tuple of (emails_added, emails_skipped, attachments_added, attachments_skipped).
        """
        if provider_id not in EMAIL_PROVIDERS:
            self.logger.error(f"Provider desconhecido: {provider_id}")
            return (0, 0, 0, 0)

        provider_class = EMAIL_PROVIDERS[provider_id]

        # Use default filter with common senders if not specified
        if email_filter is None:
            email_filter = EmailFilter(senders=COMMON_INVOICE_SENDERS)

        account_display = f"{provider_id} ({account})" if account else provider_id
        self.logger.info(f"A iniciar scrape para inbox via {account_display}...")

        # Initialize inbox database
        inbox_db = InboxDatabase()

        emails_added = 0
        emails_skipped = 0
        attachments_added = 0
        attachments_skipped = 0

        with provider_class(account=account) as provider:
            if progress_callback:
                progress_callback("connect", 0, 1, "A ligar ao servidor...")

            if not provider.connect():
                self.logger.error("Falha na ligação ao servidor de email.")
                return (0, 0, 0, 0)

            if progress_callback:
                progress_callback("connect", 1, 1, "Ligado com sucesso")

            try:
                # Search for emails
                messages = provider.search_emails(email_filter, progress_callback)
                self.logger.info(f"Encontrados {len(messages)} emails.")

                if progress_callback:
                    progress_callback(
                        "download",
                        0,
                        len(messages),
                        f"A processar {len(messages)} emails...",
                    )

                for i, msg in enumerate(messages):
                    try:
                        # Extract message metadata FIRST (before downloading anything)
                        message_id = provider._get_message_id(msg)
                        sender = provider._decode_header_value(msg.get("From", ""))
                        subject = provider._decode_header_value(msg.get("Subject", ""))
                        email_date = provider._get_email_date(msg)

                        if progress_callback:
                            progress_callback(
                                "download",
                                i + 1,
                                len(messages),
                                f"Email {i + 1}/{len(messages)}: {subject[:30]}...",
                            )

                        # Check if email already exists BEFORE downloading
                        if inbox_db.email_exists(message_id):
                            emails_skipped += 1
                            self.logger.debug(f"Email já existe: {subject[:30]}")
                            continue

                        # Check if email has valid attachments BEFORE downloading
                        if email_filter.has_attachment:
                            if not provider._has_matching_attachment(
                                msg, email_filter.attachment_extensions
                            ):
                                continue

                        # Extract email body (only when we know we'll use it)
                        email_body = provider._extract_email_body(msg)

                        # Download attachments
                        invoices = provider.download_attachments(
                            msg, email_filter.attachment_extensions
                        )

                        if not invoices:
                            # No valid attachments, skip this email
                            continue

                        # Check if any attachment is new (by content hash)
                        new_invoices = []
                        for invoice in invoices:
                            if invoice.file_path.exists():
                                file_hash = inbox_db.compute_file_hash(invoice.file_path)
                                if not inbox_db.attachment_exists_by_hash(file_hash):
                                    new_invoices.append((invoice, file_hash))
                                else:
                                    # Attachment already exists (duplicate content), delete the file
                                    self.logger.debug(
                                        f"Anexo duplicado (hash): {invoice.file_name}"
                                    )
                                    invoice.file_path.unlink()
                                    attachments_skipped += 1

                        if not new_invoices:
                            # All attachments already existed (by content)
                            emails_skipped += 1
                            continue

                        # Add email to database
                        email_id = inbox_db.add_email(
                            provider=provider_id,
                            message_id=message_id,
                            sender=sender,
                            subject=subject,
                            email_date=email_date,
                            account=account,
                            body=email_body,
                        )
                        emails_added += 1

                        # Add new attachments
                        for invoice, file_hash in new_invoices:
                            inbox_db.add_attachment(
                                email_id=email_id,
                                file_name=invoice.file_name,
                                file_path=str(invoice.file_path),
                                file_size=invoice.file_size,
                                content_hash=file_hash,
                            )
                            attachments_added += 1
                            self.logger.debug(f"Adicionado: {invoice.file_name}")

                    except Exception as e:
                        self.logger.error(f"Erro ao processar email: {e}")
                        continue

            finally:
                provider.disconnect()

        self.logger.info(
            f"Scrape concluído: {emails_added} emails novos "
            f"({emails_skipped} existiam), "
            f"{attachments_added} anexos novos "
            f"({attachments_skipped} existiam)"
        )

        return (emails_added, emails_skipped, attachments_added, attachments_skipped)

    def scrape_all_to_inbox(
        self,
        email_filter: Optional[EmailFilter] = None,
        account: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> tuple[int, int, int, int]:
        """Scrape from all providers and store in inbox database.

        Args:
            email_filter: Optional filter criteria.
            account: Optional account name.
            progress_callback: Optional callback for progress updates.

        Returns:
            Tuple of total (emails_added, emails_skipped, attachments_added, attachments_skipped).
        """
        total_emails_added = 0
        total_emails_skipped = 0
        total_attachments_added = 0
        total_attachments_skipped = 0

        for provider_id in EMAIL_PROVIDERS:
            try:
                ea, es, aa, as_ = self.scrape_to_inbox(
                    provider_id,
                    email_filter,
                    account,
                    progress_callback,
                )
                total_emails_added += ea
                total_emails_skipped += es
                total_attachments_added += aa
                total_attachments_skipped += as_
            except Exception as e:
                self.logger.error(f"Erro no provider {provider_id}: {e}")
                continue

        return (
            total_emails_added,
            total_emails_skipped,
            total_attachments_added,
            total_attachments_skipped,
        )
