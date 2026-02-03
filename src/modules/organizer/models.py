"""Database models for document organization."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

from src.core import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""

    pass


class DocumentType(str, Enum):
    """Types of financial documents."""

    INVOICE = "fatura"
    STATEMENT = "extrato"
    RECEIPT = "recibo"
    CONTRACT = "contrato"
    TAX = "imposto"
    OTHER = "outro"


class DocumentStatus(str, Enum):
    """Document processing status."""

    PENDING = "pendente"
    PROCESSED = "processado"
    ERROR = "erro"


# Association table for document tags
document_tags = Table(
    "document_tags",
    Base.metadata,
    Column("document_id", Integer, ForeignKey("documents.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)


class Tag(Base):
    """Tag for categorizing documents."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)  # Hex color

    documents: Mapped[list["Document"]] = relationship(
        "Document",
        secondary=document_tags,
        back_populates="tags",
    )

    def __repr__(self) -> str:
        return f"Tag(name={self.name!r})"


class Provider(Base):
    """Provider/vendor of documents (e.g., EDP, NOS, CGD)."""

    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    email_pattern: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    documents: Mapped[list["Document"]] = relationship("Document", back_populates="provider")

    def __repr__(self) -> str:
        return f"Provider(name={self.name!r})"


class Document(Base):
    """Represents a financial document (invoice, statement, receipt)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)

    # File information
    file_path: Mapped[str] = mapped_column(String(500), unique=True, index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_size: Mapped[int] = mapped_column(Integer)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # SHA-256

    # Document metadata
    document_type: Mapped[str] = mapped_column(String(20), default=DocumentType.OTHER.value)
    status: Mapped[str] = mapped_column(String(20), default=DocumentStatus.PENDING.value)

    # Extracted information
    document_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Full text content for search
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provider relationship
    provider_id: Mapped[Optional[int]] = mapped_column(ForeignKey("providers.id"), nullable=True)
    provider: Mapped[Optional["Provider"]] = relationship("Provider", back_populates="documents")

    # Tags
    tags: Mapped[list["Tag"]] = relationship(
        "Tag",
        secondary=document_tags,
        back_populates="documents",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Source information
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # gmail, hotmail, manual
    source_email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    def __repr__(self) -> str:
        return f"Document(file_name={self.file_name!r}, type={self.document_type!r})"

    @property
    def path(self) -> Path:
        """Get the file path as a Path object."""
        return Path(self.file_path)


class ProcessingLog(Base):
    """Log of document processing attempts."""

    __tablename__ = "processing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    action: Mapped[str] = mapped_column(String(50))
    success: Mapped[bool] = mapped_column(default=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    document: Mapped["Document"] = relationship("Document")

    def __repr__(self) -> str:
        return f"ProcessingLog(document_id={self.document_id}, action={self.action!r})"


def get_engine():
    """Get SQLAlchemy engine for the document database."""
    db_path = settings.data_dir / "catalogo" / "documents.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db():
    """Initialize the database, creating all tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    """Get a new database session."""
    engine = get_engine()
    return Session(engine)
