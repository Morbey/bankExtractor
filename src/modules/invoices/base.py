"""Base class for email invoice providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from email.message import Message
from pathlib import Path
from typing import Optional

from src.core import CredentialManager, get_logger, settings


@dataclass
class EmailAttachmentInfo:
    """Information about an email attachment."""

    filename: str
    content_type: str
    size: int
    index: int  # Position in the email for selective download


@dataclass
class EmailMessage:
    """Represents an email message with body and attachment info."""

    message_id: str
    provider: str
    sender: str
    subject: str
    date: datetime
    body_text: str  # Plain text body
    body_html: str  # HTML body (if available)
    attachments: list[EmailAttachmentInfo]
    _raw_message: Optional[Message] = None  # Internal: raw message for attachment download


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
    email_body: str = ""  # Email body text for reference


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

    def __init__(self, account: Optional[str] = None):
        """Initialize email provider.

        Args:
            account: Optional account name for multiple accounts (e.g., 'pessoal', 'empresa')
        """
        self.account = account
        self._credential_key = f"{self.PROVIDER_ID}_{account}" if account else self.PROVIDER_ID
        self.logger = get_logger(f"invoices.{self._credential_key}")
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
        display_name = f"{self.PROVIDER_NAME} ({self.account})" if self.account else self.PROVIDER_NAME

        email = CredentialManager.get_or_prompt(
            self._credential_key,
            "email",
            f"Email {display_name}",
            password=False,
        )
        password = CredentialManager.get_or_prompt(
            self._credential_key,
            "password",
            f"Password/App Password {display_name}",
            password=True,
        )
        return email, password

    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email address for safe logging.

        Args:
            email: Full email address

        Returns:
            Masked email (e.g., 'us***@gm***.com')
        """
        if not email or "@" not in email:
            return "***"

        local, domain = email.rsplit("@", 1)
        domain_parts = domain.split(".")

        # Mask local part: show first 2 chars
        if len(local) > 2:
            masked_local = local[:2] + "***"
        else:
            masked_local = "***"

        # Mask domain: show first 2 chars of domain name
        if len(domain_parts) >= 2:
            domain_name = domain_parts[0]
            if len(domain_name) > 2:
                masked_domain = domain_name[:2] + "***." + domain_parts[-1]
            else:
                masked_domain = "***." + domain_parts[-1]
        else:
            masked_domain = "***"

        return f"{masked_local}@{masked_domain}"

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

    def get_email_messages(
        self,
        email_filter: Optional[EmailFilter] = None,
    ) -> list[EmailMessage]:
        """Get email messages with body and attachment info (without downloading).

        Args:
            email_filter: Filter criteria for searching emails.

        Returns:
            List of EmailMessage objects with body text and attachment info.
        """
        # Default implementation - subclasses should override for better efficiency
        return []

    def download_attachment(
        self,
        email_message: EmailMessage,
        attachment_index: int,
        dest_dir: Optional[Path] = None,
    ) -> Optional[DownloadedInvoice]:
        """Download a specific attachment from an email.

        Args:
            email_message: The email message containing the attachment.
            attachment_index: Index of the attachment to download.
            dest_dir: Destination directory (defaults to faturas_dir).

        Returns:
            DownloadedInvoice if successful, None otherwise.
        """
        # Default implementation - subclasses should override
        return None

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
