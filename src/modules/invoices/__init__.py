"""Invoice download module (Phase 2).

This module provides email-based invoice downloading functionality.
It supports multiple email providers (Gmail, Hotmail/Outlook) and
automatically searches for invoices from common Portuguese providers.

Example usage:
    from src.modules.invoices import InvoiceDownloader

    downloader = InvoiceDownloader()
    invoices = downloader.download_recent(days=30)

    for invoice in invoices:
        print(f"Downloaded: {invoice.file_path}")

Inbox System (scrape & process later):
    from src.modules.invoices import InboxDatabase

    # Scrape emails to inbox database
    downloader = InvoiceDownloader()
    emails_added, _, attachments_added, _ = downloader.scrape_to_inbox("gmail")

    # Process pending attachments later
    inbox_db = InboxDatabase()
    pending = inbox_db.get_pending_attachments()
"""

from .base import (
    COMMON_INVOICE_SENDERS,
    DownloadedInvoice,
    EmailFilter,
    EmailProviderBase,
    ProgressCallback,
)
from .downloader import EMAIL_PROVIDERS, InvoiceDownloader, _DOWNLOAD_COMPLETE
from .email_client import EmailAttachment, EmailClient, InvoiceEmail
from .gmail import GmailProvider
from .hotmail import HotmailProvider
from .inbox_db import InboxDatabase
from .inbox_models import Attachment, AttachmentStatus, Email, get_session, init_db
from .invoice_processor import InvoiceProcessor, ProcessedInvoice
from .pdf_parser import InvoiceMetadata, PDFInvoiceParser

__all__ = [
    # Base classes and data types
    "EmailProviderBase",
    "EmailFilter",
    "DownloadedInvoice",
    "COMMON_INVOICE_SENDERS",
    "ProgressCallback",
    # Providers
    "GmailProvider",
    "HotmailProvider",
    "EMAIL_PROVIDERS",
    # Main downloader
    "InvoiceDownloader",
    # Invoice processor
    "InvoiceProcessor",
    "ProcessedInvoice",
    # Inbox system
    "InboxDatabase",
    "Email",
    "Attachment",
    "AttachmentStatus",
    "init_db",
    "get_session",
    # Legacy email client (for backward compatibility)
    "EmailClient",
    "InvoiceEmail",
    "EmailAttachment",
    # PDF parsing
    "PDFInvoiceParser",
    "InvoiceMetadata",
]
