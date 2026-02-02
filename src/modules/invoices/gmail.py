"""Gmail email provider for invoice downloads."""

import email
import imaplib
from datetime import datetime
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Optional

from src.core import settings

from .base import DownloadedInvoice, EmailFilter, EmailProviderBase


class GmailProvider(EmailProviderBase):
    """Gmail email provider implementation.

    Uses IMAP to connect to Gmail. Requires an App Password
    (not regular password) due to Google's security requirements.

    To generate an App Password:
    1. Enable 2-Step Verification in your Google Account
    2. Go to https://myaccount.google.com/apppasswords
    3. Generate a new App Password for "Mail"
    """

    PROVIDER_ID = "gmail"
    PROVIDER_NAME = "Gmail"
    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993

    def __init__(self):
        super().__init__()
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> bool:
        """Connect to Gmail IMAP server.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            email_addr, password = self.get_credentials()

            self.logger.info(f"A ligar ao Gmail ({email_addr})...")
            self._imap = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
            self._imap.login(email_addr, password)
            self.logger.info("Ligação estabelecida com sucesso.")
            return True
        except imaplib.IMAP4.error as e:
            self.logger.error(f"Erro de autenticação IMAP: {e}")
            self.logger.info(
                "Nota: O Gmail requer uma App Password. "
                "Veja https://myaccount.google.com/apppasswords"
            )
            return False
        except Exception as e:
            self.logger.error(f"Erro ao ligar ao Gmail: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Gmail IMAP server."""
        if self._imap:
            try:
                self._imap.logout()
                self.logger.info("Desligado do Gmail.")
            except Exception:
                pass
            self._imap = None

    def _build_search_criteria(self, email_filter: EmailFilter) -> str:
        """Build IMAP search criteria string.

        Args:
            email_filter: Filter criteria

        Returns:
            IMAP search criteria string
        """
        criteria = []

        # Date filters
        if email_filter.start_date:
            date_str = email_filter.start_date.strftime("%d-%b-%Y")
            criteria.append(f'SINCE {date_str}')

        if email_filter.end_date:
            date_str = email_filter.end_date.strftime("%d-%b-%Y")
            criteria.append(f'BEFORE {date_str}')

        # Subject filter - use first subject keyword
        if email_filter.subject_contains:
            for subject in email_filter.subject_contains:
                criteria.append(f'SUBJECT "{subject}"')
                break  # IMAP only allows one SUBJECT criterion per search

        # Sender filter - need to search separately for each sender
        # We'll handle this in search_emails method

        return " ".join(criteria) if criteria else "ALL"

    def _decode_header_value(self, value: str) -> str:
        """Decode email header value.

        Args:
            value: Raw header value

        Returns:
            Decoded string
        """
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

    def _get_email_date(self, msg: Message) -> datetime:
        """Extract date from email message.

        Args:
            msg: Email message

        Returns:
            Datetime of the email
        """
        date_str = msg.get("Date", "")
        if date_str:
            try:
                return email.utils.parsedate_to_datetime(date_str)
            except Exception:
                pass
        return datetime.now()

    def search_emails(self, email_filter: EmailFilter) -> list[Message]:
        """Search for emails matching the filter criteria.

        Args:
            email_filter: Filter criteria

        Returns:
            List of email messages matching the criteria
        """
        if not self._imap:
            self.logger.error("Não está ligado ao servidor.")
            return []

        messages = []

        try:
            # Select inbox (or all mail for better coverage)
            self._imap.select("[Gmail]/All Mail")
        except Exception:
            # Fallback to INBOX if All Mail label doesn't exist
            self._imap.select("INBOX")

        base_criteria = self._build_search_criteria(email_filter)

        # If we have sender filters, search for each sender
        senders = email_filter.senders if email_filter.senders else [None]

        for sender in senders:
            try:
                if sender:
                    search_criteria = f'{base_criteria} FROM "{sender}"'
                else:
                    search_criteria = base_criteria

                self.logger.debug(f"Critério de pesquisa: {search_criteria}")

                # Search emails
                status, msg_ids = self._imap.search(None, search_criteria)

                if status != "OK":
                    continue

                msg_id_list = msg_ids[0].split()
                self.logger.debug(f"Encontrados {len(msg_id_list)} emails de {sender or 'todos'}")

                # Fetch each message
                for msg_id in msg_id_list:
                    status, msg_data = self._imap.fetch(msg_id, "(RFC822)")
                    if status == "OK" and msg_data[0]:
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)

                        # Check if has attachments with desired extensions
                        if email_filter.has_attachment:
                            if self._has_matching_attachment(msg, email_filter.attachment_extensions):
                                messages.append(msg)
                        else:
                            messages.append(msg)

            except Exception as e:
                self.logger.error(f"Erro na pesquisa: {e}")
                continue

        return messages

    def _has_matching_attachment(self, msg: Message, extensions: list[str]) -> bool:
        """Check if email has attachments with matching extensions.

        Args:
            msg: Email message
            extensions: List of file extensions to match

        Returns:
            True if matching attachment found
        """
        for part in msg.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    filename = self._decode_header_value(filename)
                    for ext in extensions:
                        if filename.lower().endswith(ext.lower()):
                            return True
        return False

    def download_attachments(
        self,
        message: Message,
        extensions: list[str],
    ) -> list[DownloadedInvoice]:
        """Download attachments from an email message.

        Args:
            message: Email message
            extensions: List of file extensions to download

        Returns:
            List of downloaded invoice information
        """
        invoices = []

        sender = self._decode_header_value(message.get("From", ""))
        subject = self._decode_header_value(message.get("Subject", ""))
        email_date = self._get_email_date(message)

        for part in message.walk():
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" not in content_disposition:
                continue

            filename = part.get_filename()
            if not filename:
                continue

            filename = self._decode_header_value(filename)

            # Check extension
            has_valid_ext = any(filename.lower().endswith(ext.lower()) for ext in extensions)
            if not has_valid_ext:
                continue

            # Get attachment data
            data = part.get_payload(decode=True)
            if not data:
                continue

            # Generate unique filename
            date_prefix = email_date.strftime("%Y%m%d")
            safe_filename = self._sanitize_filename(filename)
            final_filename = f"{date_prefix}_{safe_filename}"

            # Save file
            file_path = settings.faturas_dir / final_filename

            # Handle duplicates
            counter = 1
            base_path = file_path
            while file_path.exists():
                stem = base_path.stem
                suffix = base_path.suffix
                file_path = base_path.parent / f"{stem}_{counter}{suffix}"
                counter += 1

            file_path.write_bytes(data)
            self.logger.info(f"Guardada fatura: {file_path.name}")

            invoices.append(
                DownloadedInvoice(
                    provider=self.PROVIDER_ID,
                    sender=sender,
                    subject=subject,
                    date=email_date,
                    file_path=file_path,
                    file_name=filename,
                    file_size=len(data),
                )
            )

        return invoices

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Replace problematic characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # Limit length
        if len(filename) > 200:
            stem = Path(filename).stem[:190]
            suffix = Path(filename).suffix
            filename = stem + suffix

        return filename
