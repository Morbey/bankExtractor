"""Document Registry - Central system for document and entity management.

This module provides:
- Document type classification
- Entity (actor) management
- Document-entity relationships
- Pending document queue for unknown entities
- Invoice-payment reconciliation support
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.config import settings
from src.core.logger import get_logger

console = Console()
logger = get_logger(__name__)


class DocumentType(str, Enum):
    """Types of financial documents."""
    FATURA = "fatura"
    COMPROVATIVO_TRANSFERENCIA = "comprovativo_transferencia"
    NOTA_CREDITO = "nota_credito"
    EXTRATO_BANCARIO = "extrato_bancario"
    RECIBO = "recibo"
    OUTRO = "outro"


class DocumentStatus(str, Enum):
    """Document processing status."""
    PENDENTE = "pendente"  # Awaiting classification
    CLASSIFICADO = "classificado"  # Classified but not linked
    PAGO = "pago"  # Invoice marked as paid
    POR_PAGAR = "por_pagar"  # Invoice pending payment
    ARQUIVADO = "arquivado"  # Archived/completed


class EntityType(str, Enum):
    """Types of entities/actors."""
    EMPRESA = "empresa"
    PESSOA = "pessoa"
    BANCO = "banco"
    PROPRIO = "proprio"  # My own accounts/entities
    DESCONHECIDO = "desconhecido"


class AccountingScope(str, Enum):
    """Accounting scope for document organization."""
    PESSOAL = "pessoal"  # Personal accounting
    EMPRESA = "empresa"  # Business accounting


@dataclass
class Entity:
    """Represents an actor/entity in the system."""
    id: str
    name: str
    folder_name: str
    entity_type: EntityType = EntityType.DESCONHECIDO
    scope: AccountingScope = AccountingScope.EMPRESA  # Default to business
    nifs: list[str] = field(default_factory=list)
    ibans: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)  # Contact emails
    sender_emails: list[str] = field(default_factory=list)  # Email addresses that send invoices
    aliases: list[str] = field(default_factory=list)  # Alternative names
    notes: str = ""
    created_at: str = ""

    def matches(self, nif: Optional[str] = None, iban: Optional[str] = None,
                email: Optional[str] = None, name: Optional[str] = None,
                sender_email: Optional[str] = None) -> bool:
        """Check if entity matches any of the provided identifiers."""
        if nif and nif in self.nifs:
            return True
        if iban:
            normalized_iban = re.sub(r"\s+", "", iban).upper()
            if normalized_iban in [re.sub(r"\s+", "", i).upper() for i in self.ibans]:
                return True
        if email and email.lower() in [e.lower() for e in self.emails]:
            return True
        if sender_email and sender_email.lower() in [e.lower() for e in self.sender_emails]:
            return True
        if name:
            name_lower = name.lower()
            if name_lower == self.name.lower():
                return True
            if name_lower in [a.lower() for a in self.aliases]:
                return True
        return False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "folder_name": self.folder_name,
            "entity_type": self.entity_type.value,
            "scope": self.scope.value,
            "nifs": self.nifs,
            "ibans": self.ibans,
            "emails": self.emails,
            "sender_emails": self.sender_emails,
            "aliases": self.aliases,
            "notes": self.notes,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        return cls(
            id=data.get("id", str(uuid4())),
            name=data["name"],
            folder_name=data["folder_name"],
            entity_type=EntityType(data.get("entity_type", "desconhecido")),
            scope=AccountingScope(data.get("scope", "empresa")),
            nifs=data.get("nifs", []),
            ibans=data.get("ibans", []),
            emails=data.get("emails", []),
            sender_emails=data.get("sender_emails", []),
            aliases=data.get("aliases", []),
            notes=data.get("notes", ""),
            created_at=data.get("created_at", ""),
        )


@dataclass
class DocumentRecord:
    """Record of a processed document."""
    id: str
    file_path: str
    file_name: str
    document_type: DocumentType
    status: DocumentStatus

    # Financial info
    amount: Optional[float] = None
    currency: str = "EUR"
    document_date: Optional[str] = None
    due_date: Optional[str] = None
    reference: Optional[str] = None

    # Entity relationships
    emitter_entity_id: Optional[str] = None  # Who issued the document
    receiver_entity_id: Optional[str] = None  # Who received/paid

    # For transfers
    source_iban: Optional[str] = None
    destination_iban: Optional[str] = None

    # Reconciliation
    linked_document_ids: list[str] = field(default_factory=list)  # Related docs (e.g., invoice linked to payment)

    # Metadata
    raw_text: Optional[str] = None
    extraction_notes: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "file_name": self.file_name,
            "document_type": self.document_type.value,
            "status": self.status.value,
            "amount": self.amount,
            "currency": self.currency,
            "document_date": self.document_date,
            "due_date": self.due_date,
            "reference": self.reference,
            "emitter_entity_id": self.emitter_entity_id,
            "receiver_entity_id": self.receiver_entity_id,
            "source_iban": self.source_iban,
            "destination_iban": self.destination_iban,
            "linked_document_ids": self.linked_document_ids,
            "extraction_notes": self.extraction_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DocumentRecord":
        return cls(
            id=data.get("id", str(uuid4())),
            file_path=data["file_path"],
            file_name=data["file_name"],
            document_type=DocumentType(data.get("document_type", "outro")),
            status=DocumentStatus(data.get("status", "pendente")),
            amount=data.get("amount"),
            currency=data.get("currency", "EUR"),
            document_date=data.get("document_date"),
            due_date=data.get("due_date"),
            reference=data.get("reference"),
            emitter_entity_id=data.get("emitter_entity_id"),
            receiver_entity_id=data.get("receiver_entity_id"),
            source_iban=data.get("source_iban"),
            destination_iban=data.get("destination_iban"),
            linked_document_ids=data.get("linked_document_ids", []),
            extraction_notes=data.get("extraction_notes"),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class DocumentRegistry:
    """Central registry for documents and entities."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize document registry.

        Args:
            config_dir: Directory for configuration files.
        """
        self.config_dir = config_dir or settings.data_dir
        self.entities_path = self.config_dir / "entities.json"
        self.documents_path = self.config_dir / "documents.json"
        self.pending_path = self.config_dir / "pending_documents.json"

        self._entities: dict[str, Entity] = {}
        self._documents: dict[str, DocumentRecord] = {}
        self._pending: list[dict] = []  # Docs awaiting classification

        self._load_data()

    def _load_data(self) -> None:
        """Load all data from files."""
        # Load entities
        if self.entities_path.exists():
            try:
                with open(self.entities_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for entity_data in data.get("entities", []):
                        entity = Entity.from_dict(entity_data)
                        self._entities[entity.id] = entity
                logger.debug(f"Loaded {len(self._entities)} entities")
            except Exception as e:
                logger.error(f"Error loading entities: {e}")

        # Load documents
        if self.documents_path.exists():
            try:
                with open(self.documents_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for doc_data in data.get("documents", []):
                        doc = DocumentRecord.from_dict(doc_data)
                        self._documents[doc.id] = doc
                logger.debug(f"Loaded {len(self._documents)} documents")
            except Exception as e:
                logger.error(f"Error loading documents: {e}")

        # Load pending
        if self.pending_path.exists():
            try:
                with open(self.pending_path, "r", encoding="utf-8") as f:
                    self._pending = json.load(f).get("pending", [])
                logger.debug(f"Loaded {len(self._pending)} pending documents")
            except Exception as e:
                logger.error(f"Error loading pending: {e}")

    def _save_entities(self) -> None:
        """Save entities to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            data = {"entities": [e.to_dict() for e in self._entities.values()]}
            with open(self.entities_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving entities: {e}")

    def _save_documents(self) -> None:
        """Save documents to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            data = {"documents": [d.to_dict() for d in self._documents.values()]}
            with open(self.documents_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving documents: {e}")

    def _save_pending(self) -> None:
        """Save pending documents to file."""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            data = {"pending": self._pending}
            with open(self.pending_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving pending: {e}")

    # =========================================================================
    # Entity Management
    # =========================================================================

    def add_entity(self, entity: Entity) -> Entity:
        """Add a new entity."""
        if not entity.id:
            entity.id = str(uuid4())
        if not entity.created_at:
            entity.created_at = datetime.now().isoformat()

        self._entities[entity.id] = entity
        self._save_entities()
        logger.info(f"Added entity: {entity.name}")
        return entity

    def create_entity(
        self,
        name: str,
        folder_name: str,
        entity_type: EntityType = EntityType.DESCONHECIDO,
        scope: AccountingScope = AccountingScope.EMPRESA,
        nifs: Optional[list[str]] = None,
        ibans: Optional[list[str]] = None,
        emails: Optional[list[str]] = None,
        sender_emails: Optional[list[str]] = None,
    ) -> Entity:
        """Create and add a new entity."""
        entity = Entity(
            id=str(uuid4()),
            name=name,
            folder_name=folder_name,
            entity_type=entity_type,
            scope=scope,
            nifs=nifs or [],
            ibans=[re.sub(r"\s+", "", i).upper() for i in (ibans or [])],
            emails=emails or [],
            sender_emails=[e.lower() for e in (sender_emails or [])],
            created_at=datetime.now().isoformat(),
        )
        return self.add_entity(entity)

    def find_entity(
        self,
        nif: Optional[str] = None,
        iban: Optional[str] = None,
        email: Optional[str] = None,
        name: Optional[str] = None,
        sender_email: Optional[str] = None,
    ) -> Optional[Entity]:
        """Find an entity by any identifier."""
        for entity in self._entities.values():
            if entity.matches(nif=nif, iban=iban, email=email, name=name, sender_email=sender_email):
                return entity
        return None

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID."""
        return self._entities.get(entity_id)

    def get_all_entities(self) -> list[Entity]:
        """Get all entities."""
        return list(self._entities.values())

    def update_entity(self, entity: Entity) -> None:
        """Update an existing entity."""
        if entity.id in self._entities:
            self._entities[entity.id] = entity
            self._save_entities()

    def add_iban_to_entity(self, entity_id: str, iban: str) -> bool:
        """Add an IBAN to an entity."""
        entity = self.get_entity(entity_id)
        if entity:
            normalized = re.sub(r"\s+", "", iban).upper()
            if normalized not in entity.ibans:
                entity.ibans.append(normalized)
                self._save_entities()
            return True
        return False

    def add_nif_to_entity(self, entity_id: str, nif: str) -> bool:
        """Add a NIF to an entity."""
        entity = self.get_entity(entity_id)
        if entity:
            if nif not in entity.nifs:
                entity.nifs.append(nif)
                self._save_entities()
            return True
        return False

    def add_sender_email_to_entity(self, entity_id: str, sender_email: str) -> bool:
        """Add a sender email to an entity for automatic matching."""
        entity = self.get_entity(entity_id)
        if entity:
            normalized = sender_email.lower()
            if normalized not in entity.sender_emails:
                entity.sender_emails.append(normalized)
                self._save_entities()
                logger.info(f"Sender email '{sender_email}' added to entity '{entity.name}'")
            return True
        return False

    def get_my_entities(self) -> list[Entity]:
        """Get all entities marked as my own."""
        return [e for e in self._entities.values() if e.entity_type == EntityType.PROPRIO]

    def is_my_iban(self, iban: str) -> bool:
        """Check if IBAN belongs to one of my entities."""
        normalized = re.sub(r"\s+", "", iban).upper()
        for entity in self.get_my_entities():
            if normalized in [re.sub(r"\s+", "", i).upper() for i in entity.ibans]:
                return True
        return False

    # =========================================================================
    # Document Management
    # =========================================================================

    def add_document(self, doc: DocumentRecord) -> DocumentRecord:
        """Add a document record."""
        if not doc.id:
            doc.id = str(uuid4())
        if not doc.created_at:
            doc.created_at = datetime.now().isoformat()
        doc.updated_at = datetime.now().isoformat()

        self._documents[doc.id] = doc
        self._save_documents()
        logger.info(f"Added document: {doc.file_name}")
        return doc

    def get_document(self, doc_id: str) -> Optional[DocumentRecord]:
        """Get document by ID."""
        return self._documents.get(doc_id)

    def get_documents_by_entity(self, entity_id: str) -> list[DocumentRecord]:
        """Get all documents related to an entity."""
        return [
            d for d in self._documents.values()
            if d.emitter_entity_id == entity_id or d.receiver_entity_id == entity_id
        ]

    def get_unpaid_invoices(self) -> list[DocumentRecord]:
        """Get all unpaid invoices."""
        return [
            d for d in self._documents.values()
            if d.document_type == DocumentType.FATURA and d.status == DocumentStatus.POR_PAGAR
        ]

    def get_documents_by_type(self, doc_type: DocumentType) -> list[DocumentRecord]:
        """Get all documents of a specific type."""
        return [d for d in self._documents.values() if d.document_type == doc_type]

    def link_documents(self, doc_id_1: str, doc_id_2: str) -> bool:
        """Link two documents (e.g., invoice to payment)."""
        doc1 = self.get_document(doc_id_1)
        doc2 = self.get_document(doc_id_2)

        if doc1 and doc2:
            if doc_id_2 not in doc1.linked_document_ids:
                doc1.linked_document_ids.append(doc_id_2)
            if doc_id_1 not in doc2.linked_document_ids:
                doc2.linked_document_ids.append(doc_id_1)
            self._save_documents()
            return True
        return False

    def mark_invoice_paid(self, invoice_id: str, payment_id: Optional[str] = None) -> bool:
        """Mark an invoice as paid, optionally linking to payment."""
        invoice = self.get_document(invoice_id)
        if invoice and invoice.document_type == DocumentType.FATURA:
            invoice.status = DocumentStatus.PAGO
            invoice.updated_at = datetime.now().isoformat()
            if payment_id:
                self.link_documents(invoice_id, payment_id)
            self._save_documents()
            return True
        return False

    # =========================================================================
    # Pending Documents Queue
    # =========================================================================

    def add_to_pending(self, pending_doc: dict) -> None:
        """Add a document to the pending queue."""
        pending_doc["id"] = str(uuid4())
        pending_doc["added_at"] = datetime.now().isoformat()
        self._pending.append(pending_doc)
        self._save_pending()
        logger.info(f"Added to pending queue: {pending_doc.get('file_name', 'unknown')}")

    def get_pending_documents(self) -> list[dict]:
        """Get all pending documents."""
        return self._pending.copy()

    def remove_from_pending(self, pending_id: str) -> bool:
        """Remove a document from pending queue."""
        for i, doc in enumerate(self._pending):
            if doc.get("id") == pending_id:
                self._pending.pop(i)
                self._save_pending()
                return True
        return False

    def get_pending_count(self) -> int:
        """Get count of pending documents."""
        return len(self._pending)

    # =========================================================================
    # Display Methods
    # =========================================================================

    def show_pending_summary(self) -> None:
        """Display summary of pending documents."""
        if not self._pending:
            console.print("[green]Não há documentos pendentes.[/green]")
            return

        table = Table(title=f"Documentos Pendentes ({len(self._pending)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Ficheiro", style="white")
        table.add_column("Tipo", style="cyan")
        table.add_column("Valor", style="green", justify="right")
        table.add_column("Problema", style="yellow")

        for doc in self._pending:
            table.add_row(
                doc.get("id", "")[:8],
                doc.get("file_name", "N/A")[:40],
                doc.get("detected_type", "?"),
                doc.get("amount", "N/A"),
                doc.get("pending_reason", "Entidade desconhecida"),
            )

        console.print(table)

    def show_entity_summary(self, entity_id: str) -> None:
        """Display summary of an entity and its documents."""
        entity = self.get_entity(entity_id)
        if not entity:
            console.print(f"[red]Entidade não encontrada: {entity_id}[/red]")
            return

        table = Table(title=f"Entidade: {entity.name}", show_header=False)
        table.add_column("Campo", style="cyan")
        table.add_column("Valor", style="white")

        table.add_row("ID", entity.id[:8])
        table.add_row("Nome", entity.name)
        table.add_row("Pasta", entity.folder_name)
        table.add_row("Tipo", entity.entity_type.value)
        table.add_row("NIFs", ", ".join(entity.nifs) or "N/A")
        table.add_row("IBANs", ", ".join(entity.ibans) or "N/A")
        table.add_row("Emails", ", ".join(entity.emails) or "N/A")

        console.print(table)

        # Show related documents
        docs = self.get_documents_by_entity(entity_id)
        if docs:
            console.print(f"\n[bold]Documentos relacionados ({len(docs)}):[/bold]")
            for doc in docs[:10]:
                status_color = {"pago": "green", "por_pagar": "red"}.get(doc.status.value, "yellow")
                console.print(f"  • {doc.file_name[:50]} [{status_color}]{doc.status.value}[/{status_color}]")


# Global instance
_registry: Optional[DocumentRegistry] = None


def get_document_registry() -> DocumentRegistry:
    """Get the global document registry instance."""
    global _registry
    if _registry is None:
        _registry = DocumentRegistry()
    return _registry
