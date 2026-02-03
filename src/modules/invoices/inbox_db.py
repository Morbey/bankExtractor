"""Database operations for email inbox management."""

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core import get_logger

from .inbox_models import (
    Attachment,
    AttachmentStatus,
    Email,
    get_engine,
    get_session,
    init_db,
)

logger = get_logger(__name__)


class InboxDatabase:
    """Database operations for the email inbox.

    Provides methods for:
    - Deduplication (by message_id for emails, by hash for attachments)
    - Adding emails and attachments
    - Querying by status, sender, etc.
    - Updating status after processing

    Example usage:
        db = InboxDatabase()

        # Check if email already exists
        if not db.email_exists("some-message-id"):
            email_id = db.add_email(
                provider="gmail",
                message_id="some-message-id",
                sender="noreply@example.com",
                subject="Your Invoice",
                email_date=datetime.now(),
            )

            # Add attachment
            file_hash = db.compute_file_hash(Path("invoice.pdf"))
            if not db.attachment_exists_by_hash(file_hash):
                db.add_attachment(
                    email_id=email_id,
                    file_name="invoice.pdf",
                    file_path="/path/to/invoice.pdf",
                    file_size=1024,
                    content_hash=file_hash,
                )
    """

    def __init__(self):
        """Initialize the inbox database."""
        init_db()
        self._engine = get_engine()

    def _get_session(self) -> Session:
        """Get a new database session."""
        return Session(self._engine)

    # ==================== Deduplication ====================

    def email_exists(self, message_id: str) -> bool:
        """Check if an email with this message_id already exists.

        Args:
            message_id: The Message-ID header value.

        Returns:
            True if email exists, False otherwise.
        """
        with self._get_session() as session:
            stmt = select(Email.id).where(Email.message_id == message_id)
            result = session.execute(stmt).first()
            return result is not None

    def attachment_exists_by_hash(self, content_hash: str) -> bool:
        """Check if an attachment with this hash already exists.

        Args:
            content_hash: SHA-256 hash of file content.

        Returns:
            True if attachment exists, False otherwise.
        """
        with self._get_session() as session:
            stmt = select(Attachment.id).where(Attachment.content_hash == content_hash)
            result = session.execute(stmt).first()
            return result is not None

    @staticmethod
    def compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file.

        Args:
            file_path: Path to the file.

        Returns:
            SHA-256 hash as hex string.
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    # ==================== Add ====================

    def add_email(
        self,
        provider: str,
        message_id: str,
        sender: str,
        subject: str,
        email_date: datetime,
        account: Optional[str] = None,
        body: Optional[str] = None,
    ) -> int:
        """Add a new email to the inbox.

        Args:
            provider: Email provider (gmail, hotmail).
            message_id: Unique Message-ID for deduplication.
            sender: Sender email address.
            subject: Email subject.
            email_date: Date of the email.
            account: Optional account name (pessoal, empresa).
            body: Optional email body text.

        Returns:
            ID of the created email record.
        """
        with self._get_session() as session:
            email = Email(
                provider=provider,
                account=account,
                message_id=message_id,
                sender=sender,
                subject=subject,
                email_date=email_date,
                body=body,
            )
            session.add(email)
            session.commit()
            logger.debug(f"Added email: {subject[:50]}")
            return email.id

    def add_attachment(
        self,
        email_id: int,
        file_name: str,
        file_path: str,
        file_size: int,
        content_hash: str,
    ) -> int:
        """Add a new attachment to an email.

        Args:
            email_id: ID of the parent email.
            file_name: Original file name.
            file_path: Path where file is stored.
            file_size: Size in bytes.
            content_hash: SHA-256 hash for deduplication.

        Returns:
            ID of the created attachment record.
        """
        with self._get_session() as session:
            attachment = Attachment(
                email_id=email_id,
                file_name=file_name,
                file_path=file_path,
                file_size=file_size,
                content_hash=content_hash,
                status=AttachmentStatus.PENDING.value,
            )
            session.add(attachment)
            session.commit()
            logger.debug(f"Added attachment: {file_name}")
            return attachment.id

    # ==================== Query ====================

    def get_pending_attachments(
        self,
        limit: Optional[int] = None,
        sender_pattern: Optional[str] = None,
    ) -> list[Attachment]:
        """Get pending attachments, optionally filtered.

        Args:
            limit: Maximum number to return.
            sender_pattern: Filter by sender (supports % wildcard).

        Returns:
            List of pending Attachment objects with email loaded.
        """
        with self._get_session() as session:
            stmt = (
                select(Attachment)
                .join(Email)
                .where(Attachment.status == AttachmentStatus.PENDING.value)
                .order_by(Attachment.created_at)
            )

            if sender_pattern:
                stmt = stmt.where(Email.sender.like(f"%{sender_pattern}%"))

            if limit:
                stmt = stmt.limit(limit)

            result = session.execute(stmt).scalars().all()

            # Detach from session by accessing attributes
            attachments = []
            for att in result:
                # Access email to load it before session closes
                _ = att.email.sender
                attachments.append(att)

            return attachments

    def get_attachments_by_status(
        self,
        status: AttachmentStatus,
        limit: Optional[int] = None,
    ) -> list[Attachment]:
        """Get attachments by status.

        Args:
            status: Status to filter by.
            limit: Maximum number to return.

        Returns:
            List of Attachment objects.
        """
        with self._get_session() as session:
            stmt = (
                select(Attachment)
                .join(Email)
                .where(Attachment.status == status.value)
                .order_by(Attachment.created_at)
            )

            if limit:
                stmt = stmt.limit(limit)

            result = session.execute(stmt).scalars().all()

            # Detach from session
            attachments = []
            for att in result:
                _ = att.email.sender
                attachments.append(att)

            return attachments

    def get_attachment_by_id(self, attachment_id: int) -> Optional[Attachment]:
        """Get an attachment by ID.

        Args:
            attachment_id: The attachment ID.

        Returns:
            Attachment object or None.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            result = session.execute(stmt).scalar_one_or_none()

            if result:
                # Load email before session closes
                _ = result.email.sender

            return result

    def get_status_counts(self) -> dict[str, int]:
        """Get counts of attachments by status.

        Returns:
            Dictionary mapping status to count.
        """
        with self._get_session() as session:
            stmt = (
                select(Attachment.status, func.count(Attachment.id))
                .group_by(Attachment.status)
            )
            result = session.execute(stmt).all()

            counts = {status.value: 0 for status in AttachmentStatus}
            for status, count in result:
                counts[status] = count

            return counts

    def get_email_count(self) -> int:
        """Get total number of emails in inbox.

        Returns:
            Total email count.
        """
        with self._get_session() as session:
            stmt = select(func.count(Email.id))
            return session.execute(stmt).scalar() or 0

    def search_by_sender(self, pattern: str, limit: int = 50) -> list[Attachment]:
        """Search attachments by sender email pattern.

        Args:
            pattern: Search pattern (supports % wildcard).
            limit: Maximum results.

        Returns:
            List of matching Attachment objects.
        """
        with self._get_session() as session:
            stmt = (
                select(Attachment)
                .join(Email)
                .where(Email.sender.like(f"%{pattern}%"))
                .order_by(Attachment.created_at.desc())
                .limit(limit)
            )

            result = session.execute(stmt).scalars().all()

            attachments = []
            for att in result:
                _ = att.email.sender
                attachments.append(att)

            return attachments

    def search_by_subject(self, pattern: str, limit: int = 50) -> list[Attachment]:
        """Search attachments by email subject pattern.

        Args:
            pattern: Search pattern (supports % wildcard).
            limit: Maximum results.

        Returns:
            List of matching Attachment objects.
        """
        with self._get_session() as session:
            stmt = (
                select(Attachment)
                .join(Email)
                .where(Email.subject.like(f"%{pattern}%"))
                .order_by(Attachment.created_at.desc())
                .limit(limit)
            )

            result = session.execute(stmt).scalars().all()

            attachments = []
            for att in result:
                _ = att.email.sender
                attachments.append(att)

            return attachments

    # ==================== Update ====================

    def mark_processed(
        self,
        attachment_id: int,
        destination_path: str,
        entity_id: Optional[str] = None,
        entity_name: Optional[str] = None,
    ) -> bool:
        """Mark an attachment as processed.

        Args:
            attachment_id: ID of the attachment.
            destination_path: Where the file was moved to.
            entity_id: Optional entity ID.
            entity_name: Optional entity name.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            attachment = session.execute(stmt).scalar_one_or_none()

            if not attachment:
                return False

            attachment.status = AttachmentStatus.PROCESSED.value
            attachment.destination_path = destination_path
            attachment.entity_id = entity_id
            attachment.entity_name = entity_name
            attachment.processed_at = datetime.now()

            session.commit()
            logger.debug(f"Marked attachment {attachment_id} as processed")
            return True

    def mark_ignored(
        self,
        attachment_id: int,
        reason: Optional[str] = None,
        reason_label: Optional[str] = None,
    ) -> bool:
        """Mark an attachment as ignored.

        Args:
            attachment_id: ID of the attachment.
            reason: Optional reason code.
            reason_label: Optional human-readable reason.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            attachment = session.execute(stmt).scalar_one_or_none()

            if not attachment:
                return False

            attachment.status = AttachmentStatus.IGNORED.value
            attachment.ignore_reason = reason
            attachment.ignore_reason_label = reason_label
            attachment.processed_at = datetime.now()

            session.commit()
            logger.debug(f"Marked attachment {attachment_id} as ignored")
            return True

    def mark_deleted(
        self,
        attachment_id: int,
        reason: Optional[str] = None,
        reason_label: Optional[str] = None,
    ) -> bool:
        """Mark an attachment as deleted.

        Args:
            attachment_id: ID of the attachment.
            reason: Optional reason code.
            reason_label: Optional human-readable reason.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            attachment = session.execute(stmt).scalar_one_or_none()

            if not attachment:
                return False

            attachment.status = AttachmentStatus.DELETED.value
            attachment.ignore_reason = reason
            attachment.ignore_reason_label = reason_label
            attachment.processed_at = datetime.now()

            session.commit()
            logger.debug(f"Marked attachment {attachment_id} as deleted")
            return True

    def restore_to_pending(self, attachment_id: int) -> bool:
        """Restore an attachment back to pending status.

        Args:
            attachment_id: ID of the attachment.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            attachment = session.execute(stmt).scalar_one_or_none()

            if not attachment:
                return False

            attachment.status = AttachmentStatus.PENDING.value
            attachment.ignore_reason = None
            attachment.ignore_reason_label = None
            attachment.destination_path = None
            attachment.entity_id = None
            attachment.entity_name = None
            attachment.processed_at = None

            session.commit()
            logger.debug(f"Restored attachment {attachment_id} to pending")
            return True

    def update_file_path(self, attachment_id: int, new_path: str) -> bool:
        """Update the file path for an attachment.

        Args:
            attachment_id: ID of the attachment.
            new_path: New file path.

        Returns:
            True if update was successful.
        """
        with self._get_session() as session:
            stmt = select(Attachment).where(Attachment.id == attachment_id)
            attachment = session.execute(stmt).scalar_one_or_none()

            if not attachment:
                return False

            attachment.file_path = new_path
            session.commit()
            return True

    # ==================== Bulk Operations ====================

    def get_emails_for_provider(
        self,
        provider: str,
        account: Optional[str] = None,
    ) -> list[Email]:
        """Get all emails for a provider/account.

        Args:
            provider: Email provider (gmail, hotmail).
            account: Optional account name.

        Returns:
            List of Email objects.
        """
        with self._get_session() as session:
            stmt = select(Email).where(Email.provider == provider)

            if account:
                stmt = stmt.where(Email.account == account)

            return list(session.execute(stmt).scalars().all())

    def get_statistics(self) -> dict:
        """Get comprehensive inbox statistics.

        Returns:
            Dictionary with various statistics.
        """
        with self._get_session() as session:
            # Total emails
            total_emails = session.execute(
                select(func.count(Email.id))
            ).scalar() or 0

            # Total attachments
            total_attachments = session.execute(
                select(func.count(Attachment.id))
            ).scalar() or 0

            # By status
            status_counts = self.get_status_counts()

            # By provider
            provider_counts = session.execute(
                select(Email.provider, func.count(Email.id))
                .group_by(Email.provider)
            ).all()

            # Total file size
            total_size = session.execute(
                select(func.sum(Attachment.file_size))
            ).scalar() or 0

            return {
                "total_emails": total_emails,
                "total_attachments": total_attachments,
                "by_status": status_counts,
                "by_provider": dict(provider_counts),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
            }
