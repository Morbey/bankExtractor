"""Document indexer for organizing and searching documents."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.core import get_logger, settings

from .classifier import ClassificationResult, classify_document
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
from .parser import PDFParser, ParsedDocument

logger = get_logger("organizer.indexer")


@dataclass
class IndexResult:
    """Result of indexing operation."""

    total_files: int
    indexed: int
    skipped: int
    errors: int
    documents: list[Document]


@dataclass
class SearchResult:
    """Result of a document search."""

    documents: list[Document]
    total_count: int
    query: str


class DocumentIndexer:
    """Indexer for organizing and cataloging documents."""

    def __init__(self):
        self.logger = logger
        self.parser = PDFParser()
        init_db()

    def index_directory(
        self,
        directory: Optional[Path] = None,
        recursive: bool = True,
    ) -> IndexResult:
        """Index all PDF documents in a directory.

        Args:
            directory: Directory to scan. Defaults to data_dir.
            recursive: Whether to scan subdirectories.

        Returns:
            IndexResult with statistics
        """
        if directory is None:
            directory = settings.data_dir

        if not directory.exists():
            self.logger.error(f"Diretório não encontrado: {directory}")
            return IndexResult(0, 0, 0, 0, [])

        # Find all PDF files
        if recursive:
            pdf_files = list(directory.rglob("*.pdf"))
        else:
            pdf_files = list(directory.glob("*.pdf"))

        self.logger.info(f"Encontrados {len(pdf_files)} ficheiros PDF em {directory}")

        indexed = 0
        skipped = 0
        errors = 0
        documents = []

        with get_session() as session:
            for pdf_path in pdf_files:
                try:
                    result = self._index_file(session, pdf_path)
                    if result is None:
                        skipped += 1
                    else:
                        indexed += 1
                        documents.append(result)
                except Exception as e:
                    self.logger.error(f"Erro ao indexar {pdf_path}: {e}")
                    errors += 1

            session.commit()

        self.logger.info(
            f"Indexação completa: {indexed} indexados, {skipped} ignorados, {errors} erros"
        )

        return IndexResult(
            total_files=len(pdf_files),
            indexed=indexed,
            skipped=skipped,
            errors=errors,
            documents=documents,
        )

    def index_file(self, file_path: Path) -> Optional[Document]:
        """Index a single PDF file.

        Args:
            file_path: Path to the PDF file

        Returns:
            Document if indexed successfully, None if skipped/error
        """
        with get_session() as session:
            result = self._index_file(session, file_path)
            session.commit()
            return result

    def _index_file(self, session: Session, file_path: Path) -> Optional[Document]:
        """Internal method to index a file within a session."""
        # Parse the PDF
        parsed = self.parser.parse(file_path)
        if parsed is None:
            return None

        # Check if already indexed (by hash)
        existing = session.execute(
            select(Document).where(Document.file_hash == parsed.file_hash)
        ).scalar_one_or_none()

        if existing:
            self.logger.debug(f"Já indexado: {file_path.name}")
            return None

        # Classify the document
        classification = classify_document(parsed)

        # Get or create provider
        provider = None
        if classification.provider_name:
            provider = self._get_or_create_provider(
                session,
                classification.provider_name,
                classification.provider_category,
            )

        # Create document record
        doc = Document(
            file_path=str(file_path.absolute()),
            file_name=parsed.file_name,
            file_size=parsed.file_size,
            file_hash=parsed.file_hash,
            document_type=classification.document_type.value,
            status=DocumentStatus.PROCESSED.value,
            document_date=datetime.combine(parsed.document_date, datetime.min.time())
            if parsed.document_date
            else None,
            due_date=datetime.combine(parsed.due_date, datetime.min.time())
            if parsed.due_date
            else None,
            amount=parsed.amount,
            reference=parsed.reference,
            text_content=parsed.text_content[:50000] if parsed.text_content else None,  # Limit size
            provider=provider,
        )

        # Add tags
        for tag_name in classification.tags:
            tag = self._get_or_create_tag(session, tag_name)
            doc.tags.append(tag)

        session.add(doc)

        # Log processing
        log = ProcessingLog(
            document=doc,
            action="index",
            success=True,
            message=f"Indexed as {classification.document_type.value}",
        )
        session.add(log)

        self.logger.info(f"Indexado: {file_path.name} ({classification.document_type.value})")
        return doc

    def _get_or_create_provider(
        self,
        session: Session,
        name: str,
        category: Optional[str],
    ) -> Provider:
        """Get existing provider or create new one."""
        provider = session.execute(
            select(Provider).where(Provider.name == name)
        ).scalar_one_or_none()

        if not provider:
            provider = Provider(name=name, category=category)
            session.add(provider)
            session.flush()

        return provider

    def _get_or_create_tag(self, session: Session, name: str) -> Tag:
        """Get existing tag or create new one."""
        tag = session.execute(
            select(Tag).where(Tag.name == name)
        ).scalar_one_or_none()

        if not tag:
            tag = Tag(name=name)
            session.add(tag)
            session.flush()

        return tag

    def search(
        self,
        query: Optional[str] = None,
        document_type: Optional[DocumentType] = None,
        provider_name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        tags: Optional[list[str]] = None,
        limit: int = 50,
    ) -> SearchResult:
        """Search for documents matching criteria.

        Args:
            query: Full-text search query
            document_type: Filter by document type
            provider_name: Filter by provider name
            start_date: Filter documents from this date
            end_date: Filter documents until this date
            tags: Filter by tag names
            limit: Maximum number of results

        Returns:
            SearchResult with matching documents
        """
        with get_session() as session:
            stmt = select(Document)

            # Full-text search
            if query:
                search_pattern = f"%{query}%"
                stmt = stmt.where(
                    or_(
                        Document.text_content.ilike(search_pattern),
                        Document.file_name.ilike(search_pattern),
                        Document.reference.ilike(search_pattern),
                    )
                )

            # Document type filter
            if document_type:
                stmt = stmt.where(Document.document_type == document_type.value)

            # Provider filter
            if provider_name:
                stmt = stmt.join(Document.provider).where(
                    Provider.name.ilike(f"%{provider_name}%")
                )

            # Date filters
            if start_date:
                start_dt = datetime.combine(start_date, datetime.min.time())
                stmt = stmt.where(Document.document_date >= start_dt)

            if end_date:
                end_dt = datetime.combine(end_date, datetime.max.time())
                stmt = stmt.where(Document.document_date <= end_dt)

            # Tag filter
            if tags:
                for tag_name in tags:
                    stmt = stmt.join(Document.tags).where(Tag.name == tag_name)

            # Order by date descending
            stmt = stmt.order_by(Document.document_date.desc().nulls_last())
            stmt = stmt.limit(limit)

            documents = list(session.execute(stmt).scalars().all())

            return SearchResult(
                documents=documents,
                total_count=len(documents),
                query=query or "",
            )

    def get_statistics(self) -> dict:
        """Get statistics about indexed documents.

        Returns:
            Dictionary with statistics
        """
        with get_session() as session:
            total_docs = session.query(Document).count()
            total_providers = session.query(Provider).count()
            total_tags = session.query(Tag).count()

            # Count by type
            by_type = {}
            for doc_type in DocumentType:
                count = session.query(Document).filter(
                    Document.document_type == doc_type.value
                ).count()
                if count > 0:
                    by_type[doc_type.value] = count

            # Count by provider
            by_provider = {}
            providers = session.query(Provider).all()
            for provider in providers:
                count = len(provider.documents)
                if count > 0:
                    by_provider[provider.name] = count

            # Total amount
            total_amount = session.query(Document).with_entities(
                Document.amount
            ).filter(Document.amount.isnot(None)).all()
            sum_amount = sum(a[0] for a in total_amount if a[0])

            return {
                "total_documents": total_docs,
                "total_providers": total_providers,
                "total_tags": total_tags,
                "by_type": by_type,
                "by_provider": by_provider,
                "total_amount": sum_amount,
            }

    def get_document_by_id(self, doc_id: int) -> Optional[Document]:
        """Get a document by its ID."""
        with get_session() as session:
            return session.get(Document, doc_id)

    def delete_document(self, doc_id: int) -> bool:
        """Delete a document from the index.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted, False if not found
        """
        with get_session() as session:
            doc = session.get(Document, doc_id)
            if doc:
                session.delete(doc)
                session.commit()
                self.logger.info(f"Eliminado documento ID {doc_id}")
                return True
            return False

    def reindex_all(self) -> IndexResult:
        """Clear index and reindex all documents.

        Returns:
            IndexResult with statistics
        """
        with get_session() as session:
            # Clear all documents
            session.query(ProcessingLog).delete()
            session.query(Document).delete()
            session.commit()

        self.logger.info("Índice limpo, a reindexar...")
        return self.index_directory()
