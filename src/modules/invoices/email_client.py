"""Email client for fetching invoices via IMAP."""

import email
import imaplib
from dataclasses import dataclass
from datetime import date, datetime
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Optional

from src.core.logger import get_logger


@dataclass
class EmailAttachment:
    """Represents an email attachment."""

    filename: str
    content: bytes
    content_type: str


@dataclass
class InvoiceEmail:
    """Represents an email containing invoice(s)."""

    message_id: str
    sender: str
    subject: str
    date: datetime
    attachments: list[EmailAttachment]

    @property
    def has_pdf(self) -> bool:
        """Check if email has PDF attachments."""
        return any(
            att.content_type == "application/pdf" or att.filename.lower().endswith(".pdf")
            for att in self.attachments
        )

    @property
    def pdf_attachments(self) -> list[EmailAttachment]:
        """Get only PDF attachments."""
        return [
            att
            for att in self.attachments
            if att.content_type == "application/pdf" or att.filename.lower().endswith(".pdf")
        ]


class EmailClient:
    """IMAP email client for fetching invoices."""

    # Common invoice senders (domains and patterns)
    INVOICE_SENDERS = [
        "vodafone",
        "nos.pt",
        "meo",
        "edp",
        "galp",
        "viaverde",
        "brisa",
        "fidelidade",
        "allianz",
        "epal",
        "endesa",
        "fatura",
        "invoice",
        "factura",
        "recibo",
        "receipt",
        "billing",
        "pagamento",
    ]

    def __init__(
        self,
        server: str,
        username: str,
        password: str,
        port: int = 993,
        use_ssl: bool = True,
    ):
        """Initialize email client.

        Args:
            server: IMAP server address (e.g., imap.gmail.com)
            username: Email username/address
            password: Email password or app password
            port: IMAP port (default 993 for SSL)
            use_ssl: Use SSL connection (default True)
        """
        self.server = server
        self.username = username
        self.password = password
        self.port = port
        self.use_ssl = use_ssl
        self.logger = get_logger(__name__)
        self._connection: Optional[imaplib.IMAP4_SSL | imaplib.IMAP4] = None

    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email address for safe logging."""
        if not email or "@" not in email:
            return "***"
        local, domain = email.rsplit("@", 1)
        masked_local = local[:2] + "***" if len(local) > 2 else "***"
        domain_parts = domain.split(".")
        if len(domain_parts) >= 2:
            masked_domain = domain_parts[0][:2] + "***." + domain_parts[-1]
        else:
            masked_domain = "***"
        return f"{masked_local}@{masked_domain}"

    def connect(self) -> bool:
        """Connect to the IMAP server.

        Returns:
            True if connection successful.
        """
        try:
            if self.use_ssl:
                self._connection = imaplib.IMAP4_SSL(self.server, self.port)
            else:
                self._connection = imaplib.IMAP4(self.server, self.port)

            self._connection.login(self.username, self.password)
            self.logger.info(f"Conectado a {self.server} como {self._mask_email(self.username)}")
            return True

        except imaplib.IMAP4.error as e:
            self.logger.error(f"Erro de autenticação IMAP: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Erro ao conectar ao servidor de email: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the IMAP server."""
        if self._connection:
            try:
                self._connection.logout()
                self.logger.info("Desconectado do servidor de email")
            except Exception:
                pass
            self._connection = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()

    def _decode_header_value(self, value: str) -> str:
        """Decode email header value (handles encoded headers)."""
        if not value:
            return ""

        decoded_parts = decode_header(value)
        result = []

        for part, encoding in decoded_parts:
            if isinstance(part, bytes):
                result.append(part.decode(encoding or "utf-8", errors="replace"))
            else:
                result.append(part)

        return "".join(result)

    def _parse_date(self, date_str: str) -> datetime:
        """Parse email date string to datetime."""
        # Common email date formats
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
            "%d %b %Y %H:%M:%S",
        ]

        # Remove timezone name in parentheses if present
        if "(" in date_str:
            date_str = date_str[: date_str.index("(")].strip()

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        # Fallback to current datetime
        return datetime.now()

    def _extract_attachments(self, msg: Message) -> list[EmailAttachment]:
        """Extract attachments from email message."""
        attachments = []

        if msg.is_multipart():
            for part in msg.walk():
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = part.get_filename()
                    if filename:
                        filename = self._decode_header_value(filename)
                        content = part.get_payload(decode=True)
                        content_type = part.get_content_type()

                        if content:
                            attachments.append(
                                EmailAttachment(
                                    filename=filename,
                                    content=content,
                                    content_type=content_type,
                                )
                            )
        return attachments

    def _parse_email(self, msg_data: bytes, msg_id: str) -> InvoiceEmail:
        """Parse raw email data into InvoiceEmail object."""
        msg = email.message_from_bytes(msg_data)

        sender = self._decode_header_value(msg.get("From", ""))
        subject = self._decode_header_value(msg.get("Subject", ""))
        date_str = msg.get("Date", "")
        email_date = self._parse_date(date_str)

        attachments = self._extract_attachments(msg)

        return InvoiceEmail(
            message_id=msg_id,
            sender=sender,
            subject=subject,
            date=email_date,
            attachments=attachments,
        )

    def search_invoices(
        self,
        folder: str = "INBOX",
        since_date: Optional[date] = None,
        before_date: Optional[date] = None,
        sender_filter: Optional[str] = None,
        subject_filter: Optional[str] = None,
        only_with_attachments: bool = True,
        limit: Optional[int] = None,
    ) -> list[InvoiceEmail]:
        """Search for invoice emails.

        Args:
            folder: Email folder to search (default INBOX)
            since_date: Only emails after this date
            before_date: Only emails before this date
            sender_filter: Filter by sender (partial match)
            subject_filter: Filter by subject (partial match)
            only_with_attachments: Only return emails with attachments
            limit: Maximum number of emails to return

        Returns:
            List of InvoiceEmail objects.
        """
        if not self._connection:
            self.logger.error("Não conectado ao servidor de email")
            return []

        try:
            # Select folder
            status, _ = self._connection.select(folder, readonly=True)
            if status != "OK":
                self.logger.error(f"Não foi possível selecionar a pasta {folder}")
                return []

            # Build search criteria
            criteria = []

            if since_date:
                criteria.append(f'SINCE {since_date.strftime("%d-%b-%Y")}')

            if before_date:
                criteria.append(f'BEFORE {before_date.strftime("%d-%b-%Y")}')

            if sender_filter:
                criteria.append(f'FROM "{sender_filter}"')

            if subject_filter:
                criteria.append(f'SUBJECT "{subject_filter}"')

            # Default search if no criteria
            search_str = " ".join(criteria) if criteria else "ALL"

            self.logger.info(f"Pesquisando emails: {search_str}")

            status, msg_ids = self._connection.search(None, search_str)

            if status != "OK":
                self.logger.error("Erro na pesquisa de emails")
                return []

            msg_id_list = msg_ids[0].split()

            # Reverse to get newest first
            msg_id_list = list(reversed(msg_id_list))

            if limit:
                msg_id_list = msg_id_list[:limit]

            self.logger.info(f"Encontrados {len(msg_id_list)} emails")

            invoices = []

            for msg_id in msg_id_list:
                status, msg_data = self._connection.fetch(msg_id, "(RFC822)")

                if status != "OK":
                    continue

                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        invoice_email = self._parse_email(response_part[1], msg_id.decode())

                        # Filter by attachments
                        if only_with_attachments and not invoice_email.attachments:
                            continue

                        # Check if likely an invoice
                        if self._is_likely_invoice(invoice_email):
                            invoices.append(invoice_email)

            self.logger.info(f"Identificadas {len(invoices)} faturas potenciais")
            return invoices

        except Exception as e:
            self.logger.error(f"Erro ao pesquisar emails: {e}")
            return []

    def _is_likely_invoice(self, email_obj: InvoiceEmail) -> bool:
        """Check if email is likely an invoice based on sender/subject."""
        text_to_check = f"{email_obj.sender} {email_obj.subject}".lower()

        # Check for invoice-related keywords
        for keyword in self.INVOICE_SENDERS:
            if keyword.lower() in text_to_check:
                return True

        # Has PDF attachment with invoice-like name
        for att in email_obj.attachments:
            filename_lower = att.filename.lower()
            if any(
                kw in filename_lower for kw in ["fatura", "factura", "invoice", "recibo", "receipt"]
            ):
                return True

        return False

    def fetch_all_invoices(
        self,
        since_date: Optional[date] = None,
        before_date: Optional[date] = None,
        folders: Optional[list[str]] = None,
    ) -> list[InvoiceEmail]:
        """Fetch all invoices from multiple folders.

        Args:
            since_date: Only emails after this date
            before_date: Only emails before this date
            folders: List of folders to search (default: INBOX only)

        Returns:
            List of InvoiceEmail objects from all folders.
        """
        folders = folders or ["INBOX"]
        all_invoices = []

        for folder in folders:
            self.logger.info(f"Pesquisando pasta: {folder}")
            invoices = self.search_invoices(
                folder=folder,
                since_date=since_date,
                before_date=before_date,
            )
            all_invoices.extend(invoices)

        return all_invoices

    def save_attachments(
        self,
        invoice_email: InvoiceEmail,
        output_dir: Path,
        only_pdf: bool = True,
    ) -> list[Path]:
        """Save email attachments to disk.

        Args:
            invoice_email: The invoice email object
            output_dir: Directory to save attachments
            only_pdf: Only save PDF files

        Returns:
            List of paths to saved files.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_files = []

        attachments = invoice_email.pdf_attachments if only_pdf else invoice_email.attachments

        for att in attachments:
            # Create safe filename
            safe_filename = "".join(c if c.isalnum() or c in ".-_" else "_" for c in att.filename)

            # Add date prefix for uniqueness
            date_prefix = invoice_email.date.strftime("%Y%m%d")
            final_filename = f"{date_prefix}_{safe_filename}"

            file_path = output_dir / final_filename

            # Handle duplicates
            counter = 1
            while file_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                file_path = output_dir / f"{stem}_{counter}{suffix}"
                counter += 1

            file_path.write_bytes(att.content)
            saved_files.append(file_path)
            self.logger.info(f"Guardado: {file_path.name}")

        return saved_files
