"""Hotmail/Outlook email provider for invoice downloads."""

import email
import imaplib
from datetime import datetime
from email.header import decode_header
from email.message import Message
from pathlib import Path
from typing import Optional

from src.core import settings

from .base import DownloadedInvoice, EmailFilter, EmailProviderBase, ProgressCallback


class HotmailProvider(EmailProviderBase):
    """Hotmail/Outlook email provider implementation.

    Uses IMAP to connect to Outlook.com/Hotmail.
    Works with both @hotmail.com and @outlook.com accounts.

    Note: If you have 2-Factor Authentication enabled,
    you may need to generate an App Password.
    """

    PROVIDER_ID = "hotmail"
    PROVIDER_NAME = "Hotmail/Outlook"
    IMAP_SERVER = "outlook.office365.com"
    IMAP_PORT = 993

    def __init__(self, account: Optional[str] = None):
        super().__init__(account=account)
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> bool:
        """Connect to Outlook IMAP server.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            email_addr, password = self.get_credentials()

            # Clean credentials (remove extra spaces)
            email_addr = email_addr.strip()
            password = password.replace(" ", "").strip()

            # Mask email for logging (security)
            masked_email = self._mask_email(email_addr)
            self.logger.info(f"A ligar ao Outlook ({masked_email})...")
            self._imap = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
            self._imap.login(email_addr, password)
            self.logger.info("Ligação estabelecida com sucesso.")
            return True
        except imaplib.IMAP4.error as e:
            self.logger.error(f"Erro de autenticação IMAP: {e}")
            self.logger.info(
                "Nota: Se tem 2FA ativada, pode necessitar de uma App Password."
            )
            return False
        except Exception as e:
            self.logger.error(f"Erro ao ligar ao Outlook: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from Outlook IMAP server."""
        if self._imap:
            try:
                self._imap.logout()
                self.logger.info("Desligado do Outlook.")
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

        # Subject filter
        if email_filter.subject_contains:
            for subject in email_filter.subject_contains:
                criteria.append(f'SUBJECT "{subject}"')
                break  # IMAP only allows one SUBJECT criterion

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

    def search_emails(
        self,
        email_filter: EmailFilter,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> list[Message]:
        """Search for emails matching the filter criteria.

        Args:
            email_filter: Filter criteria
            progress_callback: Optional callback for progress updates

        Returns:
            List of email messages matching the criteria
        """
        if not self._imap:
            self.logger.error("Não está ligado ao servidor.")
            return []

        messages = []

        try:
            # Select inbox
            self._imap.select("INBOX")
        except Exception as e:
            self.logger.error(f"Erro ao selecionar INBOX: {e}")
            return []

        base_criteria = self._build_search_criteria(email_filter)

        # If we have sender filters, search for each sender
        senders = email_filter.senders if email_filter.senders else [None]
        total_senders = len(senders)

        for sender_idx, sender in enumerate(senders):
            try:
                if sender:
                    search_criteria = f'{base_criteria} FROM "{sender}"'
                    sender_display = sender.split("@")[0] if "@" in sender else sender
                else:
                    search_criteria = base_criteria
                    sender_display = "todos"

                if progress_callback:
                    progress_callback(
                        "search",
                        sender_idx + 1,
                        total_senders,
                        f"A pesquisar: {sender_display}..."
                    )

                self.logger.debug(f"Critério de pesquisa: {search_criteria}")

                # Search emails
                status, msg_ids = self._imap.search(None, search_criteria)

                if status != "OK":
                    continue

                msg_id_list = msg_ids[0].split()
                num_found = len(msg_id_list)

                if num_found > 0:
                    self.logger.debug(f"Encontrados {num_found} emails de {sender or 'todos'}")

                    if progress_callback:
                        progress_callback(
                            "fetch",
                            0,
                            num_found,
                            f"A obter {num_found} emails de {sender_display}..."
                        )

                # Fetch each message
                for fetch_idx, msg_id in enumerate(msg_id_list):
                    if progress_callback and num_found > 0:
                        progress_callback(
                            "fetch",
                            fetch_idx + 1,
                            num_found,
                            f"A obter email {fetch_idx + 1}/{num_found} de {sender_display}..."
                        )

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

    def _extract_email_body(self, message: Message) -> str:
        """Extract plain text body from email message.

        Args:
            message: Email message

        Returns:
            Plain text body content
        """
        body_parts = []

        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = part.get("Content-Disposition", "")

            # Skip attachments
            if "attachment" in content_disposition:
                continue

            # Get plain text parts
            if content_type == "text/plain":
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        text = payload.decode(charset, errors="replace")
                        body_parts.append(text)
                except Exception:
                    pass

            # Fallback to HTML if no plain text
            elif content_type == "text/html" and not body_parts:
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        html = payload.decode(charset, errors="replace")
                        # Basic HTML to text - remove tags
                        import re
                        text = re.sub(r'<[^>]+>', ' ', html)
                        text = re.sub(r'\s+', ' ', text).strip()
                        body_parts.append(text)
                except Exception:
                    pass

        return "\n".join(body_parts)

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
        email_body = self._extract_email_body(message)

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

            try:
                # Generate unique filename
                date_prefix = email_date.strftime("%Y%m%d")
                safe_filename = self._sanitize_filename(filename)
                final_filename = f"{date_prefix}_{safe_filename}"

                # Ensure we have a valid filename
                if not final_filename or not safe_filename:
                    self.logger.warning(f"Nome de ficheiro inválido ignorado: {filename[:50]}...")
                    continue

                # Save file to temp folder (pending organization)
                file_path = settings.faturas_temp_dir / final_filename

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
                        email_body=email_body,
                    )
                )

            except Exception as e:
                self.logger.warning(f"Erro ao guardar anexo '{filename[:50]}...': {e}")
                continue

        return invoices

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for safe storage.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove newlines and carriage returns first
        filename = filename.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")

        # Remove control characters (ASCII 0-31)
        filename = "".join(c if ord(c) >= 32 else "_" for c in filename)

        # Replace problematic characters for Windows
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, "_")

        # Remove leading/trailing spaces and dots (Windows doesn't like them)
        filename = filename.strip(". ")

        # Collapse multiple spaces/underscores
        while "  " in filename:
            filename = filename.replace("  ", " ")
        while "__" in filename:
            filename = filename.replace("__", "_")

        # Limit length
        if len(filename) > 200:
            stem = Path(filename).stem[:190]
            suffix = Path(filename).suffix
            filename = stem + suffix

        return filename

    def run_streaming(
        self,
        email_filter: Optional[EmailFilter] = None,
        invoice_callback=None,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> int:
        """Execute invoice download with true streaming.

        Each email is fetched and processed immediately, calling invoice_callback
        for each invoice as soon as it's downloaded.

        Args:
            email_filter: Filter criteria for emails.
            invoice_callback: Called immediately for each downloaded invoice.
            progress_callback: Optional callback for progress updates.

        Returns:
            Total number of invoices downloaded.
        """
        from typing import Callable
        from .base import DownloadedInvoice

        if email_filter is None:
            email_filter = EmailFilter()

        if not self._imap:
            self.logger.error("Não está ligado ao servidor.")
            return 0

        total_invoices = 0

        try:
            self._imap.select("INBOX")
        except Exception as e:
            self.logger.error(f"Erro ao selecionar INBOX: {e}")
            return 0

        base_criteria = self._build_search_criteria(email_filter)
        senders = email_filter.senders if email_filter.senders else [None]

        # First, collect all message IDs (fast operation)
        all_msg_ids = []
        for sender in senders:
            try:
                if sender:
                    search_criteria = f'{base_criteria} FROM "{sender}"'
                else:
                    search_criteria = base_criteria

                status, msg_ids = self._imap.search(None, search_criteria)
                if status == "OK":
                    all_msg_ids.extend(msg_ids[0].split())
            except Exception as e:
                self.logger.error(f"Erro na pesquisa: {e}")

        # Remove duplicates while preserving order
        seen = set()
        unique_msg_ids = []
        for mid in all_msg_ids:
            if mid not in seen:
                seen.add(mid)
                unique_msg_ids.append(mid)

        total_emails = len(unique_msg_ids)
        self.logger.info(f"Encontrados {total_emails} emails para processar.")

        if progress_callback:
            progress_callback("fetch", 0, total_emails, f"A processar {total_emails} emails...")

        # Process each email immediately (fetch → download → callback)
        for idx, msg_id in enumerate(unique_msg_ids):
            try:
                if progress_callback:
                    progress_callback(
                        "fetch",
                        idx + 1,
                        total_emails,
                        f"Email {idx + 1}/{total_emails}..."
                    )

                # Fetch this single email
                status, msg_data = self._imap.fetch(msg_id, "(RFC822)")
                if status != "OK" or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)

                # Check if has attachments with desired extensions
                if email_filter.has_attachment:
                    if not self._has_matching_attachment(msg, email_filter.attachment_extensions):
                        continue

                # Download attachments immediately
                invoices = self.download_attachments(msg, email_filter.attachment_extensions)

                # Call callback for each invoice immediately
                for invoice in invoices:
                    total_invoices += 1
                    if invoice_callback:
                        invoice_callback(invoice)

                    if progress_callback:
                        progress_callback(
                            "download",
                            total_invoices,
                            0,  # Unknown total
                            f"Descarregada: {invoice.file_name[:40]}..."
                        )

            except Exception as e:
                self.logger.error(f"Erro ao processar email: {e}")
                continue

        self.logger.info(f"Descarregadas {total_invoices} faturas.")
        return total_invoices
