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
from .email_client import EmailAttachment, EmailClient, InvoiceEmail
from .gmail import GmailProvider
from .hotmail import HotmailProvider
from .pdf_parser import InvoiceMetadata, PDFInvoiceParser

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
    # Legacy email client (for backward compatibility)
    "EmailClient",
    "InvoiceEmail",
    "EmailAttachment",
    # PDF parsing
    "PDFInvoiceParser",
    "InvoiceMetadata",
]
