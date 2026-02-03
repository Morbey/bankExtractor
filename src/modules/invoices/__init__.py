"""Invoice download and processing module."""

from src.modules.invoices.email_client import EmailAttachment, EmailClient, InvoiceEmail
from src.modules.invoices.pdf_parser import InvoiceMetadata, PDFInvoiceParser

__all__ = [
    "EmailClient",
    "InvoiceEmail",
    "EmailAttachment",
    "PDFInvoiceParser",
    "InvoiceMetadata",
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
"""

from .base import (
    COMMON_INVOICE_SENDERS,
    DownloadedInvoice,
    EmailFilter,
    EmailProviderBase,
)
from .downloader import EMAIL_PROVIDERS, InvoiceDownloader
from .gmail import GmailProvider
from .hotmail import HotmailProvider

__all__ = [
    # Base classes and data types
    "EmailProviderBase",
    "EmailFilter",
    "DownloadedInvoice",
    "COMMON_INVOICE_SENDERS",
    # Providers
    "GmailProvider",
    "HotmailProvider",
    "EMAIL_PROVIDERS",
    # Main downloader
    "InvoiceDownloader",
]
