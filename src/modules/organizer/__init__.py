"""Document organizer module (Phase 3).

This module provides document organization and cataloging functionality.
It parses PDFs, classifies documents automatically, and indexes them
in a SQLite database for easy searching.

Example usage:
    from src.modules.organizer import DocumentIndexer

    indexer = DocumentIndexer()

    # Index all documents in data directory
    result = indexer.index_directory()

    # Search for documents
    results = indexer.search(query="EDP", document_type=DocumentType.INVOICE)

    for doc in results.documents:
        print(f"{doc.file_name}: {doc.amount}€")
"""

from .classifier import ClassificationResult, DocumentClassifier, classify_document
from .file_organizer import InvoiceOrganizer, OrganizedInvoice
from .indexer import DocumentIndexer, IndexResult, SearchResult
from .invoice_database import InvoiceDatabase
from .models import (
    Document,
    DocumentStatus,
    DocumentType,
    ProcessingLog,
    Provider,
    Tag,
    get_session,
    init_db,
)
from .parser import ParsedDocument, PDFParser, parse_pdf

__all__ = [
    # Models
    "Document",
    "DocumentType",
    "DocumentStatus",
    "Provider",
    "Tag",
    "ProcessingLog",
    "init_db",
    "get_session",
    # Parser
    "PDFParser",
    "ParsedDocument",
    "parse_pdf",
    # Classifier
    "DocumentClassifier",
    "ClassificationResult",
    "classify_document",
    # Indexer
    "DocumentIndexer",
    "IndexResult",
    "SearchResult",
    # File organizer
    "InvoiceOrganizer",
    "OrganizedInvoice",
    # Invoice database
    "InvoiceDatabase",
]
