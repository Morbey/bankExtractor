"""Document Processor - Unified document processing and organization.

This module integrates:
- PDF parsing for data extraction
- Document type detection
- Entity identification
- Automatic organization or pending queue
"""

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

from src.core.config import settings
from src.core.document_registry import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    get_document_registry,
)
from src.core.logger import get_logger
from src.core.transfer_manager import get_transfer_manager
from src.modules.invoices.pdf_parser import PDFInvoiceParser

console = Console()
logger = get_logger(__name__)


@dataclass
class ProcessedDocument:
    """Result of processing a document."""

    file_path: Path
    document_type: DocumentType
    success: bool
    destination_path: Optional[Path] = None
    entity_name: Optional[str] = None
    amount: Optional[str] = None
    document_date: Optional[str] = None
    pending_reason: Optional[str] = None
    error: Optional[str] = None


class DocumentProcessor:
    """Processes documents for classification and organization."""

    # Document type detection patterns
    FATURA_PATTERNS = [
        r"fatura",
        r"factura",
        r"invoice",
        r"n\.?\s*de\s*contribuinte",
        r"nif\s*[:.]?\s*\d",
        r"valor\s*a\s*pagar",
        r"total\s*com\s*iva",
    ]

    COMPROVATIVO_PATTERNS = [
        r"comprovativo\s*de\s*transfer[eê]ncia",
        r"transfer[eê]ncia\s*banc[aá]ria",
        r"sepa",
        r"iban\s*de\s*origem",
        r"iban\s*destino",
        r"benefici[aá]rio",
        r"ordenante",
    ]

    NOTA_CREDITO_PATTERNS = [
        r"nota\s*de\s*cr[eé]dito",
        r"credit\s*note",
    ]

    EXTRATO_PATTERNS = [
        r"extrato",
        r"movimentos\s*da\s*conta",
        r"saldo\s*inicial",
        r"saldo\s*final",
    ]

    RECIBO_PATTERNS = [
        r"recibo",
        r"receipt",
        r"comprovativo\s*de\s*pagamento",
    ]

    # NIF pattern (Portuguese tax number)
    NIF_PATTERN = re.compile(r"\b(\d{9})\b")

    # IBAN pattern
    IBAN_PATTERN = re.compile(r"(PT50[\s\d]{21,30})", re.IGNORECASE)

    # Amount patterns
    AMOUNT_PATTERNS = [
        re.compile(r"total[:\s]*(\d+[.,]\d{2})\s*€?", re.IGNORECASE),
        re.compile(r"montante[:\s]*(\d+[.,]\d{2})\s*EUR", re.IGNORECASE),
        re.compile(r"valor[:\s]*(\d+[.,]\d{2})\s*€?", re.IGNORECASE),
        re.compile(r"(\d+[.,]\d{2})\s*EUR", re.IGNORECASE),
    ]

    # Date patterns
    DATE_PATTERNS = [
        re.compile(r"(\d{2}/\d{2}/\d{4})"),
        re.compile(r"(\d{4}-\d{2}-\d{2})"),
        re.compile(r"(\d{2}-\d{2}-\d{4})"),
    ]

    def __init__(self):
        """Initialize the document processor."""
        self.pdf_parser = PDFInvoiceParser()
        self.transfer_manager = get_transfer_manager()
        self.registry = get_document_registry()

    def detect_document_type(self, text: str) -> DocumentType:
        """Detect document type from text content.

        Args:
            text: Raw text from PDF.

        Returns:
            Detected DocumentType.
        """
        text_lower = text.lower()

        # Check each type in order of specificity
        for pattern in self.NOTA_CREDITO_PATTERNS:
            if re.search(pattern, text_lower):
                return DocumentType.NOTA_CREDITO

        for pattern in self.COMPROVATIVO_PATTERNS:
            if re.search(pattern, text_lower):
                return DocumentType.COMPROVATIVO_TRANSFERENCIA

        for pattern in self.EXTRATO_PATTERNS:
            if re.search(pattern, text_lower):
                return DocumentType.EXTRATO_BANCARIO

        for pattern in self.RECIBO_PATTERNS:
            if re.search(pattern, text_lower):
                return DocumentType.RECIBO

        for pattern in self.FATURA_PATTERNS:
            if re.search(pattern, text_lower):
                return DocumentType.FATURA

        return DocumentType.OUTRO

    def extract_nifs(self, text: str) -> list[str]:
        """Extract NIFs from text.

        Args:
            text: Raw text.

        Returns:
            List of unique NIFs found.
        """
        matches = self.NIF_PATTERN.findall(text)
        # Filter likely NIFs (avoid dates, codes, etc.)
        nifs = []
        for match in matches:
            # Basic validation - should start with 1-3, 5, or 9
            if match[0] in "12359":
                nifs.append(match)
        return list(set(nifs))

    def extract_ibans(self, text: str) -> list[str]:
        """Extract IBANs from text.

        Args:
            text: Raw text.

        Returns:
            List of normalized IBANs.
        """
        matches = self.IBAN_PATTERN.findall(text)
        return [re.sub(r"\s+", "", m).upper() for m in matches]

    def extract_amount(self, text: str) -> Optional[str]:
        """Extract monetary amount from text.

        Args:
            text: Raw text.

        Returns:
            Amount string or None.
        """
        for pattern in self.AMOUNT_PATTERNS:
            match = pattern.search(text)
            if match:
                amount = match.group(1).replace(",", ".")
                return f"{amount} EUR"
        return None

    def extract_date(self, text: str) -> Optional[str]:
        """Extract date from text.

        Args:
            text: Raw text.

        Returns:
            Date string or None.
        """
        for pattern in self.DATE_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1)
        return None

    def identify_entity(
        self,
        nifs: list[str],
        ibans: list[str],
        name_hints: list[str],
    ) -> tuple[Optional[Entity], Optional[str]]:
        """Try to identify an entity from extracted data.

        Args:
            nifs: List of NIFs found.
            ibans: List of IBANs found.
            name_hints: Possible entity names.

        Returns:
            Tuple of (Entity if found, identifier used to match).
        """
        # Try by NIF first
        for nif in nifs:
            entity = self.registry.find_entity(nif=nif)
            if entity:
                return entity, f"NIF: {nif}"

        # Try by IBAN
        for iban in ibans:
            entity = self.registry.find_entity(iban=iban)
            if entity:
                return entity, f"IBAN: {iban[:8]}...{iban[-4:]}"

        # Try by name
        for name in name_hints:
            if name and len(name) > 3:
                entity = self.registry.find_entity(name=name)
                if entity:
                    return entity, f"Nome: {name}"

        return None, None

    def process_document(
        self,
        file_path: Path,
        interactive: bool = True,
        move: bool = False,
    ) -> ProcessedDocument:
        """Process a single document.

        Args:
            file_path: Path to PDF file.
            interactive: If True, prompt for unknown entities.
            move: If True, move file instead of copy.

        Returns:
            ProcessedDocument with result.
        """
        try:
            if not file_path.exists():
                return ProcessedDocument(
                    file_path=file_path,
                    document_type=DocumentType.OUTRO,
                    success=False,
                    error="Ficheiro não encontrado",
                )

            # Parse PDF
            metadata = self.pdf_parser.parse(file_path)
            text = metadata.raw_text or ""

            # Detect document type
            doc_type = self.detect_document_type(text)

            # Extract identifiers
            nifs = self.extract_nifs(text)
            ibans = self.extract_ibans(text)
            amount = self.extract_amount(text)
            doc_date = self.extract_date(text)

            # Special handling for transfer documents
            if doc_type == DocumentType.COMPROVATIVO_TRANSFERENCIA:
                return self._process_transfer(
                    file_path=file_path,
                    text=text,
                    amount=amount,
                    doc_date=doc_date,
                    interactive=interactive,
                    move=move,
                )

            # For other documents, try to identify counterparty
            name_hints = []
            if metadata.vendor:
                name_hints.append(metadata.vendor)

            entity, match_reason = self.identify_entity(nifs, ibans, name_hints)

            if entity:
                # Known entity - organize document
                return self._organize_with_entity(
                    file_path=file_path,
                    doc_type=doc_type,
                    entity=entity,
                    amount=amount,
                    doc_date=doc_date,
                    nifs=nifs,
                    ibans=ibans,
                    text=text,
                    move=move,
                )
            else:
                # Unknown entity
                if interactive:
                    return self._handle_unknown_entity(
                        file_path=file_path,
                        doc_type=doc_type,
                        nifs=nifs,
                        ibans=ibans,
                        amount=amount,
                        doc_date=doc_date,
                        text=text,
                        move=move,
                    )
                else:
                    # Add to pending queue
                    self._add_to_pending(
                        file_path=file_path,
                        doc_type=doc_type,
                        nifs=nifs,
                        ibans=ibans,
                        amount=amount,
                        doc_date=doc_date,
                    )
                    return ProcessedDocument(
                        file_path=file_path,
                        document_type=doc_type,
                        success=False,
                        pending_reason="Entidade desconhecida",
                        amount=amount,
                        document_date=doc_date,
                    )

        except Exception as e:
            logger.error(f"Erro ao processar {file_path}: {e}")
            return ProcessedDocument(
                file_path=file_path,
                document_type=DocumentType.OUTRO,
                success=False,
                error=str(e),
            )

    def _process_transfer(
        self,
        file_path: Path,
        text: str,
        amount: Optional[str],
        doc_date: Optional[str],
        interactive: bool,
        move: bool,
    ) -> ProcessedDocument:
        """Process a bank transfer document."""
        transfer_info = self.transfer_manager.extract_transfer_info(text)
        direction = self.transfer_manager.determine_transfer_direction(transfer_info)

        if direction is None:
            # Need to identify which IBANs are ours
            if interactive and transfer_info.iban_origem:
                if not self.transfer_manager.is_my_iban(transfer_info.iban_origem):
                    self.transfer_manager.prompt_for_my_iban(transfer_info.iban_origem)
                    direction = self.transfer_manager.determine_transfer_direction(transfer_info)

            if direction is None and transfer_info.iban_destino:
                if not self.transfer_manager.is_my_iban(transfer_info.iban_destino):
                    self.transfer_manager.prompt_for_my_iban(transfer_info.iban_destino)
                    direction = self.transfer_manager.determine_transfer_direction(transfer_info)

        if direction is None:
            # Still unknown - add to pending
            self._add_to_pending(
                file_path=file_path,
                doc_type=DocumentType.COMPROVATIVO_TRANSFERENCIA,
                nifs=[],
                ibans=[transfer_info.iban_origem, transfer_info.iban_destino],
                amount=amount,
                doc_date=doc_date,
                extra_info={"direction": "desconhecida"},
            )
            return ProcessedDocument(
                file_path=file_path,
                document_type=DocumentType.COMPROVATIVO_TRANSFERENCIA,
                success=False,
                pending_reason="Direção da transferência desconhecida",
                amount=amount,
                document_date=doc_date,
            )

        # Get destination folder
        dest_folder, counterparty = self.transfer_manager.get_destination_folder(transfer_info)

        if dest_folder is None:
            # Need to create mapping for counterparty
            if interactive:
                counterparty = self.transfer_manager.prompt_for_mapping(transfer_info, direction)
                dest_folder, _ = self.transfer_manager.get_destination_folder(transfer_info)

        if dest_folder:
            dest_folder.mkdir(parents=True, exist_ok=True)

            # Build filename with date
            date_prefix = ""
            if transfer_info.data_hora:
                try:
                    dt = datetime.strptime(transfer_info.data_hora, "%d/%m/%Y %H:%M:%S")
                    date_prefix = dt.strftime("%Y%m%d_")
                except ValueError:
                    pass
            if not date_prefix and doc_date:
                date_prefix = doc_date.replace("/", "").replace("-", "")[:8] + "_"

            dest_filename = f"{date_prefix}{file_path.name}" if date_prefix else file_path.name
            dest_path = dest_folder / dest_filename

            # Handle duplicates
            counter = 1
            while dest_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                dest_path = dest_folder / f"{date_prefix}{stem}_{counter}{suffix}"
                counter += 1

            # Move or copy
            if move:
                shutil.move(str(file_path), str(dest_path))
            else:
                shutil.copy2(str(file_path), str(dest_path))

            logger.info(
                f"{'Movido' if move else 'Copiado'}: {file_path.name} -> {dest_path.parent.name}/"
            )

            return ProcessedDocument(
                file_path=file_path,
                document_type=DocumentType.COMPROVATIVO_TRANSFERENCIA,
                success=True,
                destination_path=dest_path,
                entity_name=counterparty,
                amount=transfer_info.montante or amount,
                document_date=transfer_info.data_hora or doc_date,
            )

        # Could not determine destination
        self._add_to_pending(
            file_path=file_path,
            doc_type=DocumentType.COMPROVATIVO_TRANSFERENCIA,
            nifs=[],
            ibans=[transfer_info.iban_origem, transfer_info.iban_destino],
            amount=amount,
            doc_date=doc_date,
        )
        return ProcessedDocument(
            file_path=file_path,
            document_type=DocumentType.COMPROVATIVO_TRANSFERENCIA,
            success=False,
            pending_reason="Não foi possível determinar destino",
            amount=amount,
            document_date=doc_date,
        )

    def _organize_with_entity(
        self,
        file_path: Path,
        doc_type: DocumentType,
        entity: Entity,
        amount: Optional[str],
        doc_date: Optional[str],
        nifs: list[str],
        ibans: list[str],
        text: str,
        move: bool,
    ) -> ProcessedDocument:
        """Organize a document with a known entity."""
        # Determine base folder based on document type
        if doc_type == DocumentType.FATURA:
            base_folder = settings.data_dir / "faturas"
        elif doc_type == DocumentType.NOTA_CREDITO:
            base_folder = settings.data_dir / "notas_credito"
        elif doc_type == DocumentType.RECIBO:
            base_folder = settings.data_dir / "recibos"
        elif doc_type == DocumentType.EXTRATO_BANCARIO:
            base_folder = settings.data_dir / "extratos"
        else:
            base_folder = settings.data_dir / "outros"

        # Add year and entity folder
        year = datetime.now().year
        if doc_date:
            try:
                if "/" in doc_date:
                    year = int(doc_date.split("/")[-1][:4])
                elif "-" in doc_date:
                    year = int(doc_date.split("-")[0])
            except (ValueError, IndexError):
                pass

        dest_folder = base_folder / str(year) / entity.folder_name
        dest_folder.mkdir(parents=True, exist_ok=True)

        # Build filename
        date_prefix = doc_date.replace("/", "").replace("-", "")[:8] + "_" if doc_date else ""
        dest_filename = f"{date_prefix}{file_path.name}" if date_prefix else file_path.name
        dest_path = dest_folder / dest_filename

        # Handle duplicates
        counter = 1
        while dest_path.exists():
            stem = file_path.stem
            suffix = file_path.suffix
            dest_path = dest_folder / f"{date_prefix}{stem}_{counter}{suffix}"
            counter += 1

        # Move or copy
        if move:
            shutil.move(str(file_path), str(dest_path))
        else:
            shutil.copy2(str(file_path), str(dest_path))

        logger.info(f"{'Movido' if move else 'Copiado'}: {file_path.name} -> {entity.folder_name}/")

        # Record document in registry
        doc_record = DocumentRecord(
            id="",
            file_path=str(dest_path),
            file_name=dest_filename,
            document_type=doc_type,
            status=DocumentStatus.CLASSIFICADO,
            amount=float(amount.replace(" EUR", "").replace(",", ".")) if amount else None,
            document_date=doc_date,
            emitter_entity_id=entity.id,
        )
        self.registry.add_document(doc_record)

        return ProcessedDocument(
            file_path=file_path,
            document_type=doc_type,
            success=True,
            destination_path=dest_path,
            entity_name=entity.name,
            amount=amount,
            document_date=doc_date,
        )

    def _handle_unknown_entity(
        self,
        file_path: Path,
        doc_type: DocumentType,
        nifs: list[str],
        ibans: list[str],
        amount: Optional[str],
        doc_date: Optional[str],
        text: str,
        move: bool,
    ) -> ProcessedDocument:
        """Handle a document with unknown entity interactively."""
        # Show document summary
        self._show_document_summary(
            file_path=file_path,
            doc_type=doc_type,
            nifs=nifs,
            ibans=ibans,
            amount=amount,
            doc_date=doc_date,
        )

        # Ask user what to do
        console.print("\n[yellow]Entidade desconhecida encontrada![/yellow]")
        console.print("Opções:")
        console.print("  1. Criar nova entidade")
        console.print("  2. Adicionar a entidade existente")
        console.print("  3. Deixar pendente para depois")

        choice = Prompt.ask("Escolha", choices=["1", "2", "3"], default="3")

        if choice == "1":
            # Create new entity
            entity = self._prompt_create_entity(nifs, ibans)
            if entity:
                return self._organize_with_entity(
                    file_path=file_path,
                    doc_type=doc_type,
                    entity=entity,
                    amount=amount,
                    doc_date=doc_date,
                    nifs=nifs,
                    ibans=ibans,
                    text=text,
                    move=move,
                )

        elif choice == "2":
            # Add to existing entity
            entity = self._prompt_select_entity()
            if entity:
                # Add new identifiers to entity
                for nif in nifs:
                    self.registry.add_nif_to_entity(entity.id, nif)
                for iban in ibans:
                    self.registry.add_iban_to_entity(entity.id, iban)

                return self._organize_with_entity(
                    file_path=file_path,
                    doc_type=doc_type,
                    entity=entity,
                    amount=amount,
                    doc_date=doc_date,
                    nifs=nifs,
                    ibans=ibans,
                    text=text,
                    move=move,
                )

        # Add to pending queue
        self._add_to_pending(
            file_path=file_path,
            doc_type=doc_type,
            nifs=nifs,
            ibans=ibans,
            amount=amount,
            doc_date=doc_date,
        )
        return ProcessedDocument(
            file_path=file_path,
            document_type=doc_type,
            success=False,
            pending_reason="Deixado pendente pelo utilizador",
            amount=amount,
            document_date=doc_date,
        )

    def _show_document_summary(
        self,
        file_path: Path,
        doc_type: DocumentType,
        nifs: list[str],
        ibans: list[str],
        amount: Optional[str],
        doc_date: Optional[str],
    ) -> None:
        """Display a summary of the document."""
        type_display = {
            DocumentType.FATURA: "[cyan]FATURA[/cyan]",
            DocumentType.COMPROVATIVO_TRANSFERENCIA: "[blue]COMPROVATIVO TRANSFERÊNCIA[/blue]",
            DocumentType.NOTA_CREDITO: "[green]NOTA DE CRÉDITO[/green]",
            DocumentType.EXTRATO_BANCARIO: "[yellow]EXTRATO BANCÁRIO[/yellow]",
            DocumentType.RECIBO: "[magenta]RECIBO[/magenta]",
            DocumentType.OUTRO: "[dim]OUTRO[/dim]",
        }.get(doc_type, str(doc_type.value))

        table = Table(title="Resumo do Documento", show_header=False)
        table.add_column("Campo", style="cyan")
        table.add_column("Valor", style="white")

        table.add_row("Ficheiro", file_path.name)
        table.add_row("Tipo", type_display)
        table.add_row("Data", doc_date or "N/A")
        table.add_row("Valor", amount or "N/A")
        table.add_row("NIFs", ", ".join(nifs) if nifs else "N/A")

        if ibans:
            iban_display = []
            for iban in ibans:
                masked = f"{iban[:8]}...{iban[-4:]}"
                if self.registry.is_my_iban(iban):
                    masked += " [green](meu)[/green]"
                iban_display.append(masked)
            table.add_row("IBANs", "\n".join(iban_display))
        else:
            table.add_row("IBANs", "N/A")

        console.print(table)

    def _prompt_create_entity(
        self,
        nifs: list[str],
        ibans: list[str],
    ) -> Optional[Entity]:
        """Prompt user to create a new entity."""
        console.print("\n[bold]Criar nova entidade[/bold]")

        name = Prompt.ask("Nome da entidade")
        if not name:
            return None

        # Suggest folder name from entity name
        default_folder = re.sub(r"[<>:\"/\\|?*]", "_", name)
        default_folder = default_folder.replace(" ", "_")[:30]
        folder_name = Prompt.ask("Nome da pasta", default=default_folder)

        # Entity type
        console.print("Tipos: empresa, pessoa, banco")
        type_str = Prompt.ask("Tipo", default="empresa")
        try:
            entity_type = EntityType(type_str)
        except ValueError:
            entity_type = EntityType.DESCONHECIDO

        # Create entity
        entity = self.registry.create_entity(
            name=name,
            folder_name=folder_name,
            entity_type=entity_type,
            nifs=nifs,
            ibans=ibans,
        )

        console.print(f"[green]Entidade '{name}' criada com sucesso![/green]")
        return entity

    def _prompt_select_entity(self) -> Optional[Entity]:
        """Prompt user to select an existing entity."""
        entities = self.registry.get_all_entities()

        if not entities:
            console.print("[yellow]Não existem entidades registadas.[/yellow]")
            return None

        console.print("\n[bold]Entidades existentes:[/bold]")
        for i, entity in enumerate(entities, 1):
            console.print(f"  {i}. {entity.name} ({entity.folder_name})")

        choice = Prompt.ask("Número da entidade (0 para cancelar)", default="0")
        try:
            idx = int(choice)
            if 1 <= idx <= len(entities):
                return entities[idx - 1]
        except ValueError:
            pass

        return None

    def _add_to_pending(
        self,
        file_path: Path,
        doc_type: DocumentType,
        nifs: list[str],
        ibans: list[str],
        amount: Optional[str],
        doc_date: Optional[str],
        extra_info: Optional[dict] = None,
    ) -> None:
        """Add a document to the pending queue."""
        pending_doc = {
            "file_path": str(file_path),
            "file_name": file_path.name,
            "detected_type": doc_type.value,
            "nifs": nifs,
            "ibans": [iban for iban in ibans if iban],
            "amount": amount,
            "document_date": doc_date,
            "pending_reason": "Entidade desconhecida",
        }
        if extra_info:
            pending_doc.update(extra_info)

        self.registry.add_to_pending(pending_doc)

    def process_directory(
        self,
        source_dir: Path,
        interactive: bool = True,
        move: bool = False,
        recursive: bool = False,
    ) -> list[ProcessedDocument]:
        """Process all PDF files in a directory.

        Args:
            source_dir: Directory to process.
            interactive: If True, prompt for unknown entities.
            move: If True, move files instead of copy.
            recursive: If True, process subdirectories.

        Returns:
            List of ProcessedDocument results.
        """
        results = []

        if recursive:
            pdf_files = list(source_dir.rglob("*.pdf"))
        else:
            pdf_files = list(source_dir.glob("*.pdf"))

        console.print(f"[bold]Encontrados {len(pdf_files)} ficheiros PDF[/bold]")

        for pdf_file in pdf_files:
            console.print(f"\nA processar: [cyan]{pdf_file.name}[/cyan]")
            result = self.process_document(pdf_file, interactive=interactive, move=move)
            results.append(result)

            if result.success:
                console.print(
                    f"  [green]✓[/green] -> {result.destination_path.parent.name if result.destination_path else 'OK'}/"
                )
            elif result.pending_reason:
                console.print(f"  [yellow]⏳[/yellow] Pendente: {result.pending_reason}")
            else:
                console.print(f"  [red]✗[/red] Erro: {result.error}")

        # Summary
        successful = sum(1 for r in results if r.success)
        pending = sum(1 for r in results if r.pending_reason)
        failed = sum(1 for r in results if r.error)

        console.print("\n[bold]Resumo:[/bold]")
        console.print(f"  [green]Sucesso: {successful}[/green]")
        console.print(f"  [yellow]Pendente: {pending}[/yellow]")
        console.print(f"  [red]Erro: {failed}[/red]")

        return results

    def process_pending_queue(self, interactive: bool = True) -> list[ProcessedDocument]:
        """Process documents in the pending queue.

        Args:
            interactive: If True, prompt for each document.

        Returns:
            List of ProcessedDocument results.
        """
        pending = self.registry.get_pending_documents()

        if not pending:
            console.print("[green]Não há documentos pendentes.[/green]")
            return []

        console.print(f"[bold]Processar {len(pending)} documentos pendentes[/bold]")

        results = []

        for doc in pending:
            file_path = Path(doc["file_path"])

            if not file_path.exists():
                console.print(f"[red]Ficheiro não encontrado: {doc['file_name']}[/red]")
                self.registry.remove_from_pending(doc["id"])
                continue

            console.print(f"\nA processar: [cyan]{doc['file_name']}[/cyan]")

            result = self.process_document(file_path, interactive=interactive)
            results.append(result)

            if result.success:
                # Remove from pending
                self.registry.remove_from_pending(doc["id"])
                console.print("  [green]✓[/green] Processado com sucesso")

        return results
