"""Database models for email inbox management."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from src.core import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for inbox models."""

    pass


class AttachmentStatus(str, Enum):
    """Status of an attachment in the inbox."""

    PENDING = "pending"
    PROCESSED = "processed"
    IGNORED = "ignored"
    DELETED = "deleted"


class Email(Base):
    """Represents an email in the inbox."""

    __tablename__ = "emails"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Email provider and account
    provider: Mapped[str] = mapped_column(String(50), index=True)  # gmail, hotmail
    account: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # pessoal, empresa

    # Unique identifier for deduplication
    message_id: Mapped[str] = mapped_column(String(500), unique=True, index=True)

    # Email metadata
    sender: Mapped[str] = mapped_column(String(500))
    subject: Mapped[str] = mapped_column(String(1000))
    email_date: Mapped[datetime] = mapped_column(DateTime)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relationships
    attachments: Mapped[list["Attachment"]] = relationship(
        "Attachment",
        back_populates="email",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"Email(id={self.id}, sender={self.sender!r}, subject={self.subject[:30]!r})"


class Attachment(Base):
    """Represents an attachment/file in the inbox."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Foreign key to email
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)

    # File information
    file_name: Mapped[str] = mapped_column(String(500))
    file_path: Mapped[str] = mapped_column(String(1000))  # Path in _pendentes/
    file_size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)  # SHA-256

    # Status tracking
    status: Mapped[str] = mapped_column(
        String(20),
        default=AttachmentStatus.PENDING.value,
        index=True,
    )

    # Destination information (after processing)
    destination_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    entity_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Ignore/delete reason
    ignore_reason: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    ignore_reason_label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    email: Mapped["Email"] = relationship("Email", back_populates="attachments")

    def __repr__(self) -> str:
        return f"Attachment(id={self.id}, file_name={self.file_name!r}, status={self.status})"

    @property
    def path(self) -> Path:
        """Get the file path as a Path object."""
        return Path(self.file_path)


def get_engine():
    """Get SQLAlchemy engine for the inbox database."""
    db_path = settings.data_dir / "inbox" / "inbox.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    """Initialize the inbox database, creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    """Get a new database session."""
    engine = get_engine()
    return Session(engine)
