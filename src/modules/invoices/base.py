"""Base class for email invoice providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import Message
from pathlib import Path
from typing import Optional

from src.core import CredentialManager, get_logger, settings


@dataclass
class DownloadedInvoice:
    """Represents a downloaded invoice."""

    provider: str
    sender: str
    subject: str
    date: datetime
    file_path: Path
    file_name: str
    file_size: int


@dataclass
class EmailFilter:
    """Filter criteria for email search."""

    senders: list[str] = field(default_factory=list)
    subject_contains: list[str] = field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    has_attachment: bool = True
    attachment_extensions: list[str] = field(default_factory=lambda: [".pdf"])


class EmailProviderBase(ABC):
    """Abstract base class for email providers.

    All email provider implementations should inherit from this class
    and implement the abstract methods.
    """

    # Override these in subclasses
    PROVIDER_ID: str = "base"
    PROVIDER_NAME: str = "Base Email"
    IMAP_SERVER: str = ""
    IMAP_PORT: int = 993

    def __init__(self):
        self.logger = get_logger(f"invoices.{self.PROVIDER_ID}")
        self._connection = None

    def __enter__(self):
        """Context manager entry - connects to email server."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnects from email server."""
        self.disconnect()

    def get_credentials(self) -> tuple[str, str]:
        """Get email and password for this provider.

        Returns:
            Tuple of (email, password/app_password)
        """
        email = CredentialManager.get_or_prompt(
            self.PROVIDER_ID,
            "email",
            f"Email {self.PROVIDER_NAME}",
            password=False,
        )
        password = CredentialManager.get_or_prompt(
            self.PROVIDER_ID,
            "password",
            f"Password/App Password {self.PROVIDER_NAME}",
            password=True,
        )
        return email, password

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the email server.

        Should handle:
        1. Establish IMAP connection
        2. Login with credentials
        3. Verify connection success

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the email server."""
        pass

    @abstractmethod
    def search_emails(self, email_filter: EmailFilter) -> list[Message]:
        """Search for emails matching the filter criteria.

        Args:
            email_filter: Filter criteria for searching emails

        Returns:
            List of email messages matching the criteria.
        """
        pass

    @abstractmethod
    def download_attachments(
        self,
        message: Message,
        extensions: list[str],
    ) -> list[DownloadedInvoice]:
        """Download attachments from an email message.

        Args:
            message: Email message to extract attachments from
            extensions: List of file extensions to download (e.g., ['.pdf'])

        Returns:
            List of downloaded invoice information.
        """
        pass

    def run(
        self,
        email_filter: Optional[EmailFilter] = None,
    ) -> list[DownloadedInvoice]:
        """Execute full invoice download workflow.

        Args:
            email_filter: Filter criteria for emails. If None, uses default filter.

        Returns:
            List of downloaded invoices.
        """
        if email_filter is None:
            email_filter = EmailFilter()

        self.logger.info(f"Iniciando download de faturas via {self.PROVIDER_NAME}...")

        if not self.connect():
            self.logger.error("Falha na ligação ao servidor de email.")
            return []

        try:
            messages = self.search_emails(email_filter)
            self.logger.info(f"Encontrados {len(messages)} emails com faturas.")

            all_invoices = []
            for msg in messages:
                invoices = self.download_attachments(msg, email_filter.attachment_extensions)
                all_invoices.extend(invoices)

            self.logger.info(f"Descarregadas {len(all_invoices)} faturas.")
            return all_invoices
        finally:
            self.disconnect()


# Common invoice senders in Portugal
COMMON_INVOICE_SENDERS = [
    # Utilities
    "noreply@edp.pt",
    "facturacao@edp.pt",
    "naoresponder@edpcomercial.pt",
    "galp@comunicacoes.galp.com",
    "comunicacao@nos.pt",
    "factura@nos.pt",
    "fatura@meo.pt",
    "vodafone@vodafone.pt",
    "endurocomunicacao@endesa.pt",
    "noreply@e-redes.pt",
    # Telecommunications
    "noreply@worten.pt",
    "noreply@nowo.pt",
    # Services
    "noreply@via-verde.pt",
    "naoresponda@via-verde.pt",
    # Insurance
    "noreply@fidelidade.pt",
    "comunicacoes@allianz.pt",
    # Government/Tax
    "noreply@portaldasfinancas.gov.pt",
]
