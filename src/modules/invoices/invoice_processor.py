"""Invoice Processor - Post-download processing and organization.

This module handles:
- Processing downloaded invoices
- Extracting information from PDFs
- Interactive entity identification
- Automatic organization based on mappings
"""

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.config import settings
from src.core.classification_rules import (
    ClassificationRulesEngine,
    MatchSource,
    MatchType,
    RuleAction,
    RuleCondition,
    get_rules_engine,
)
from src.core.document_registry import (
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    get_document_registry,
)
from src.core.logger import get_logger
from src.modules.invoices.base import DownloadedInvoice

console = Console()
logger = get_logger(__name__)


@dataclass
class ProcessedInvoice:
    """Result of processing an invoice."""

    original: DownloadedInvoice
    success: bool
    destination_path: Optional[Path] = None
    entity_name: Optional[str] = None
    document_type: Optional[DocumentType] = None
    amount: Optional[str] = None
    nif: Optional[str] = None
    error: Optional[str] = None


class InvoiceProcessor:
    """Processes downloaded invoices with interactive organization."""

    # Patterns for PDF content extraction
    NIF_PATTERN = re.compile(r"\b(\d{9})\b")
    AMOUNT_PATTERNS = [
        re.compile(r"total[:\s]*(\d+[.,]\d{2})\s*€?", re.IGNORECASE),
        re.compile(r"montante[:\s]*(\d+[.,]\d{2})\s*EUR", re.IGNORECASE),
        re.compile(r"valor[:\s]*a\s*pagar[:\s]*(\d+[.,]\d{2})", re.IGNORECASE),
        re.compile(r"(\d+[.,]\d{2})\s*EUR", re.IGNORECASE),
    ]
    DATE_PATTERNS = [
        re.compile(r"(\d{2}/\d{2}/\d{4})"),
        re.compile(r"(\d{4}-\d{2}-\d{2})"),
        re.compile(r"(\d{2}-\d{2}-\d{4})"),
    ]

    def __init__(self):
        """Initialize the invoice processor."""
        self.registry = get_document_registry()
        self.rules_engine = get_rules_engine()
        self._pdf_parser = None

    @property
    def pdf_parser(self):
        """Lazy load PDF parser."""
        if self._pdf_parser is None:
            from src.modules.invoices.pdf_parser import PDFInvoiceParser
            self._pdf_parser = PDFInvoiceParser()
        return self._pdf_parser

    def extract_pdf_info(self, file_path: Path) -> dict:
        """Extract information from PDF.

        Args:
            file_path: Path to PDF file.

        Returns:
            Dictionary with extracted information.
        """
        info = {
            "raw_text": "",
            "nifs": [],
            "amount": None,
            "date": None,
            "vendor": None,
        }

        try:
            metadata = self.pdf_parser.parse(file_path)
            info["raw_text"] = metadata.raw_text or ""
            info["vendor"] = metadata.vendor

            if metadata.total_amount:
                info["amount"] = f"{metadata.total_amount:.2f} EUR"

            if metadata.invoice_date:
                info["date"] = metadata.invoice_date.strftime("%d/%m/%Y")

            # Extract NIFs
            if info["raw_text"]:
                matches = self.NIF_PATTERN.findall(info["raw_text"])
                # Filter likely NIFs
                for match in matches:
                    if match[0] in "12359":
                        info["nifs"].append(match)
                info["nifs"] = list(set(info["nifs"]))

                # Try to extract amount if not found
                if not info["amount"]:
                    for pattern in self.AMOUNT_PATTERNS:
                        match = pattern.search(info["raw_text"])
                        if match:
                            amount = match.group(1).replace(",", ".")
                            info["amount"] = f"{amount} EUR"
                            break

                # Try to extract date if not found
                if not info["date"]:
                    for pattern in self.DATE_PATTERNS:
                        match = pattern.search(info["raw_text"])
                        if match:
                            info["date"] = match.group(1)
                            break

        except Exception as e:
            logger.error(f"Error extracting PDF info: {e}")

        return info

    def show_invoice_summary(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
    ) -> None:
        """Display comprehensive invoice summary.

        Args:
            invoice: Downloaded invoice information.
            pdf_info: Extracted PDF information.
        """
        # Email information panel
        email_table = Table(title="Informação do Email", show_header=False, box=None)
        email_table.add_column("Campo", style="cyan", width=15)
        email_table.add_column("Valor", style="white")

        email_table.add_row("Remetente", invoice.sender)
        email_table.add_row("Assunto", invoice.subject)
        email_table.add_row("Data Email", invoice.date.strftime("%d/%m/%Y %H:%M"))
        email_table.add_row("Ficheiro", invoice.file_name)
        email_table.add_row("Tamanho", f"{invoice.file_size / 1024:.1f} KB")

        console.print(Panel(email_table, border_style="blue"))

        # PDF extracted information panel
        pdf_table = Table(title="Informação Extraída do PDF", show_header=False, box=None)
        pdf_table.add_column("Campo", style="cyan", width=15)
        pdf_table.add_column("Valor", style="white")

        pdf_table.add_row("Fornecedor", pdf_info.get("vendor") or "[dim]Não detectado[/dim]")
        pdf_table.add_row("Valor", pdf_info.get("amount") or "[dim]Não detectado[/dim]")
        pdf_table.add_row("Data Doc.", pdf_info.get("date") or "[dim]Não detectado[/dim]")

        nifs = pdf_info.get("nifs", [])
        if nifs:
            pdf_table.add_row("NIFs", ", ".join(nifs))
        else:
            pdf_table.add_row("NIFs", "[dim]Não detectado[/dim]")

        console.print(Panel(pdf_table, border_style="green"))

    def build_rule_data(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> dict:
        """Build data dictionary for rule matching.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Dictionary with all matchable fields.
        """
        return {
            MatchSource.SENDER_EMAIL.value: invoice.sender,
            MatchSource.SUBJECT.value: invoice.subject,
            MatchSource.BODY.value: email_body or "",
            MatchSource.FILENAME.value: invoice.file_name,
            MatchSource.PDF_CONTENT.value: pdf_info.get("raw_text", ""),
            MatchSource.PDF_NIF.value: ",".join(pdf_info.get("nifs", [])),
            MatchSource.PDF_VENDOR.value: pdf_info.get("vendor", ""),
        }

    def find_entity_for_invoice(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> tuple[Optional[Entity], Optional[str]]:
        """Try to find a matching entity for the invoice.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Tuple of (matching entity, match reason) or (None, None).
        """
        # 1. Try classification rules first (most flexible)
        rule_data = self.build_rule_data(invoice, pdf_info, email_body)
        rule_match = self.rules_engine.get_best_match(rule_data)

        if rule_match and rule_match.action == RuleAction.ASSIGN_ENTITY:
            entity = self.registry.get_entity(rule_match.action_value)
            if entity:
                reason = f"Regra: {rule_match.rule.name}"
                return entity, reason

        # 2. Try by sender email (legacy method)
        entity = self.registry.find_entity(sender_email=invoice.sender)
        if entity:
            return entity, f"Email remetente: {invoice.sender}"

        # 3. Try by NIF
        for nif in pdf_info.get("nifs", []):
            entity = self.registry.find_entity(nif=nif)
            if entity:
                return entity, f"NIF: {nif}"

        # 4. Try by vendor name
        vendor = pdf_info.get("vendor")
        if vendor:
            entity = self.registry.find_entity(name=vendor)
            if entity:
                return entity, f"Fornecedor: {vendor}"

        return None, None

    def prompt_for_entity(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> Optional[Entity]:
        """Prompt user to create or select an entity.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Selected or created entity, or None to skip.
        """
        while True:
            console.print("\n[yellow]Entidade desconhecida![/yellow]")
            console.print("Opções:")
            console.print("  1. Criar nova entidade (com regra)")
            console.print("  2. Associar a entidade existente")
            console.print("  3. Ver mais informação (body/PDF)")
            console.print("  4. Ignorar (deixar pendente)")

            choice = Prompt.ask("Escolha", choices=["1", "2", "3", "4"], default="1")

            if choice == "1":
                return self._create_entity_with_rule(invoice, pdf_info, email_body)
            elif choice == "2":
                entity = self._select_existing_entity(invoice, pdf_info, email_body)
                if entity:
                    return entity
                # If cancelled, show menu again
            elif choice == "3":
                self._show_extended_info(invoice, pdf_info, email_body)
                # Show menu again after displaying info
            else:
                return None

    def _show_extended_info(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> None:
        """Show extended information for manual identification.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.
        """
        console.print("\n[bold cyan]Informação Adicional[/bold cyan]")

        # Show email body if available
        if email_body:
            console.print("\n[bold]Body do Email:[/bold]")
            # Show first 1000 chars
            body_preview = email_body[:1000]
            if len(email_body) > 1000:
                body_preview += f"\n[dim]... ({len(email_body) - 1000} caracteres omitidos)[/dim]"
            console.print(Panel(body_preview, border_style="blue"))
        else:
            console.print("[dim]Body do email não disponível[/dim]")

        # Show PDF content preview
        raw_text = pdf_info.get("raw_text", "")
        if raw_text:
            console.print("\n[bold]Conteúdo do PDF (primeiros 1500 chars):[/bold]")
            pdf_preview = raw_text[:1500]
            if len(raw_text) > 1500:
                pdf_preview += f"\n[dim]... ({len(raw_text) - 1500} caracteres omitidos)[/dim]"
            console.print(Panel(pdf_preview, border_style="green"))

        # Ask if user wants to open the file
        if Confirm.ask("\nAbrir o ficheiro PDF?", default=False):
            self._open_file(invoice.file_path)

    def _open_file(self, file_path: Path) -> None:
        """Open a file with the system default application."""
        import subprocess
        import sys

        try:
            if sys.platform == "win32":
                subprocess.run(["start", "", str(file_path)], shell=True)
            elif sys.platform == "darwin":
                subprocess.run(["open", str(file_path)])
            else:
                subprocess.run(["xdg-open", str(file_path)])
        except Exception as e:
            console.print(f"[red]Erro ao abrir ficheiro: {e}[/red]")

    def _create_entity_with_rule(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> Optional[Entity]:
        """Create a new entity with classification rule.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Created entity or None.
        """
        console.print("\n[bold]Criar nova entidade[/bold]")

        # Suggest name from vendor or sender
        suggested_name = pdf_info.get("vendor") or ""
        if not suggested_name:
            # Try to extract from sender email
            sender_parts = invoice.sender.split("@")[0].replace(".", " ").replace("-", " ")
            suggested_name = sender_parts.title()

        name = Prompt.ask("Nome da entidade", default=suggested_name)
        if not name:
            return None

        # Suggest folder name
        default_folder = re.sub(r"[<>:\"/\\|?*]", "_", name)
        default_folder = default_folder.replace(" ", "_")[:30]
        folder_name = Prompt.ask("Nome da pasta", default=default_folder)

        # Entity type
        console.print("Tipos: empresa, pessoa, banco")
        type_str = Prompt.ask("Tipo", default="empresa")
        try:
            entity_type = EntityType(type_str)
        except ValueError:
            entity_type = EntityType.EMPRESA

        # Create entity
        entity = self.registry.create_entity(
            name=name,
            folder_name=folder_name,
            entity_type=entity_type,
            nifs=pdf_info.get("nifs", []),
            sender_emails=[invoice.sender],
        )

        console.print(f"[green]Entidade '{name}' criada![/green]")

        # Ask about creating classification rule
        console.print("\n[bold]Criar regra de classificação[/bold]")
        console.print("Que critérios usar para identificar automaticamente futuras faturas?")

        rule_conditions = []

        # Option 1: Sender email (always suggested)
        console.print(f"\n1. Email remetente: [cyan]{invoice.sender}[/cyan]")
        if Confirm.ask("   Usar email do remetente?", default=True):
            rule_conditions.append(RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.EXACT,
                pattern=invoice.sender,
            ))

        # Option 2: NIF from PDF
        nifs = pdf_info.get("nifs", [])
        if nifs:
            console.print(f"\n2. NIF no PDF: [cyan]{', '.join(nifs)}[/cyan]")
            if Confirm.ask("   Usar NIF do PDF?", default=True):
                rule_conditions.append(RuleCondition(
                    source=MatchSource.PDF_NIF,
                    match_type=MatchType.CONTAINS,
                    pattern=nifs[0],
                ))

        # Option 3: Subject pattern
        console.print(f"\n3. Assunto: [cyan]{invoice.subject}[/cyan]")
        if Confirm.ask("   Usar padrão no assunto?", default=False):
            subject_pattern = Prompt.ask("   Padrão a procurar no assunto", default=invoice.subject[:30])
            if subject_pattern:
                rule_conditions.append(RuleCondition(
                    source=MatchSource.SUBJECT,
                    match_type=MatchType.CONTAINS,
                    pattern=subject_pattern,
                ))

        # Option 4: PDF content pattern
        vendor = pdf_info.get("vendor")
        if vendor:
            console.print(f"\n4. Texto no PDF: [cyan]{vendor}[/cyan]")
            if Confirm.ask("   Usar padrão no conteúdo do PDF?", default=False):
                pdf_pattern = Prompt.ask("   Padrão a procurar no PDF", default=vendor)
                if pdf_pattern:
                    rule_conditions.append(RuleCondition(
                        source=MatchSource.PDF_CONTENT,
                        match_type=MatchType.CONTAINS,
                        pattern=pdf_pattern,
                    ))

        # Option 5: Custom body pattern
        if email_body:
            if Confirm.ask("\n5. Usar padrão no body do email?", default=False):
                body_pattern = Prompt.ask("   Padrão a procurar no body")
                if body_pattern:
                    rule_conditions.append(RuleCondition(
                        source=MatchSource.BODY,
                        match_type=MatchType.CONTAINS,
                        pattern=body_pattern,
                    ))

        # Create rule if conditions were selected
        if rule_conditions:
            rule_name = Prompt.ask("Nome da regra", default=f"Regra {name}")

            # Determine if should be AND or OR
            match_all = True
            if len(rule_conditions) > 1:
                console.print("\nComo combinar as condições?")
                console.print("  1. AND - Todas têm de corresponder")
                console.print("  2. OR - Basta uma corresponder")
                combo = Prompt.ask("Escolha", choices=["1", "2"], default="1")
                match_all = combo == "1"

            rule = self.rules_engine.create_rule(
                name=rule_name,
                conditions=rule_conditions,
                action=RuleAction.ASSIGN_ENTITY,
                action_value=entity.id,
                description=f"Auto-criada para {name}",
                match_all=match_all,
            )
            console.print(f"[green]Regra '{rule_name}' criada com {len(rule_conditions)} condição(ões)![/green]")
        else:
            console.print("[dim]Nenhuma regra criada. Emails do remetente serão associados automaticamente.[/dim]")

        return entity

    def _select_existing_entity(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> Optional[Entity]:
        """Select an existing entity and optionally create a rule.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Selected entity or None.
        """
        entities = self.registry.get_all_entities()

        if not entities:
            console.print("[yellow]Não existem entidades registadas.[/yellow]")
            return None

        console.print("\n[bold]Entidades existentes:[/bold]")
        for i, entity in enumerate(entities, 1):
            console.print(f"  {i}. {entity.name} ({entity.folder_name})")

        choice = Prompt.ask("Número da entidade (0 para voltar)", default="0")
        try:
            idx = int(choice)
            if 1 <= idx <= len(entities):
                entity = entities[idx - 1]

                # Ask how to create the mapping
                console.print(f"\n[green]Associar a '{entity.name}'[/green]")
                console.print("Como identificar futuras faturas desta entidade?")
                console.print("  1. Apenas por email do remetente (simples)")
                console.print("  2. Criar regra com múltiplos critérios (avançado)")

                rule_choice = Prompt.ask("Escolha", choices=["1", "2"], default="1")

                if rule_choice == "1":
                    # Simple: just add sender email
                    self.registry.add_sender_email_to_entity(entity.id, invoice.sender)
                    console.print(f"[dim]Emails de {invoice.sender} → {entity.name}[/dim]")
                else:
                    # Advanced: create rule
                    self._create_rule_for_entity(entity, invoice, pdf_info, email_body)

                return entity
        except ValueError:
            pass

        return None

    def _create_rule_for_entity(
        self,
        entity: Entity,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> None:
        """Create a classification rule for an existing entity.

        Args:
            entity: Entity to create rule for.
            invoice: Current invoice for pattern suggestions.
            pdf_info: Extracted PDF info.
            email_body: Optional email body.
        """
        console.print(f"\n[bold]Criar regra para '{entity.name}'[/bold]")

        rule_conditions = []

        # Offer various conditions
        console.print(f"\n1. Email: [cyan]{invoice.sender}[/cyan]")
        if Confirm.ask("   Incluir?", default=True):
            rule_conditions.append(RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.EXACT,
                pattern=invoice.sender,
            ))

        nifs = pdf_info.get("nifs", [])
        if nifs:
            console.print(f"\n2. NIF: [cyan]{nifs[0]}[/cyan]")
            if Confirm.ask("   Incluir?", default=False):
                rule_conditions.append(RuleCondition(
                    source=MatchSource.PDF_NIF,
                    match_type=MatchType.CONTAINS,
                    pattern=nifs[0],
                ))

        console.print(f"\n3. Assunto: [cyan]{invoice.subject[:50]}[/cyan]")
        if Confirm.ask("   Incluir padrão do assunto?", default=False):
            pattern = Prompt.ask("   Padrão", default=invoice.subject[:30])
            if pattern:
                rule_conditions.append(RuleCondition(
                    source=MatchSource.SUBJECT,
                    match_type=MatchType.CONTAINS,
                    pattern=pattern,
                ))

        if rule_conditions:
            rule_name = Prompt.ask("Nome da regra", default=f"Regra {entity.name}")
            self.rules_engine.create_rule(
                name=rule_name,
                conditions=rule_conditions,
                action=RuleAction.ASSIGN_ENTITY,
                action_value=entity.id,
                match_all=len(rule_conditions) == 1,
            )
            console.print(f"[green]Regra criada![/green]")
        else:
            # Fallback to sender email mapping
            self.registry.add_sender_email_to_entity(entity.id, invoice.sender)
            console.print(f"[dim]Usando mapeamento simples por email[/dim]")

    def organize_invoice(
        self,
        invoice: DownloadedInvoice,
        entity: Entity,
        pdf_info: dict,
        move: bool = False,
    ) -> Path:
        """Organize invoice into the correct folder.

        Args:
            invoice: Downloaded invoice.
            entity: Entity to organize under.
            pdf_info: Extracted PDF info.
            move: If True, move file instead of copy.

        Returns:
            Destination path.
        """
        # Determine year
        year = invoice.date.year
        if pdf_info.get("date"):
            try:
                date_str = pdf_info["date"]
                if "/" in date_str:
                    parts = date_str.split("/")
                    if len(parts) == 3:
                        year = int(parts[2]) if len(parts[2]) == 4 else int(parts[0])
                elif "-" in date_str:
                    parts = date_str.split("-")
                    if len(parts) == 3:
                        year = int(parts[0]) if len(parts[0]) == 4 else int(parts[2])
            except (ValueError, IndexError):
                pass

        # Create destination folder: faturas/year/entity_folder/
        dest_folder = settings.data_dir / "faturas" / str(year) / entity.folder_name
        dest_folder.mkdir(parents=True, exist_ok=True)

        # Build filename with date prefix
        date_prefix = invoice.date.strftime("%Y%m%d_")
        dest_filename = f"{date_prefix}{invoice.file_name}"
        dest_path = dest_folder / dest_filename

        # Handle duplicates
        counter = 1
        while dest_path.exists():
            stem = invoice.file_path.stem
            suffix = invoice.file_path.suffix
            dest_path = dest_folder / f"{date_prefix}{stem}_{counter}{suffix}"
            counter += 1

        # Move or copy
        if move:
            shutil.move(str(invoice.file_path), str(dest_path))
        else:
            shutil.copy2(str(invoice.file_path), str(dest_path))

        return dest_path

    def process_invoice(
        self,
        invoice: DownloadedInvoice,
        interactive: bool = True,
        move: bool = False,
    ) -> ProcessedInvoice:
        """Process a single downloaded invoice.

        Args:
            invoice: Downloaded invoice to process.
            interactive: If True, prompt for unknown entities.
            move: If True, move file instead of copy.

        Returns:
            ProcessedInvoice with result.
        """
        try:
            # Extract PDF information
            pdf_info = self.extract_pdf_info(invoice.file_path)

            # Try to find matching entity
            entity, match_reason = self.find_entity_for_invoice(invoice, pdf_info)

            if entity:
                # Known entity - organize automatically
                console.print(f"\n[green]✓[/green] {invoice.file_name}")
                console.print(f"  [dim]{match_reason} → {entity.name}[/dim]")

            elif interactive:
                # Show summary and prompt
                console.print(f"\n[yellow]?[/yellow] {invoice.file_name}")
                self.show_invoice_summary(invoice, pdf_info)
                entity = self.prompt_for_entity(invoice, pdf_info)

            if entity:
                # Organize the file
                dest_path = self.organize_invoice(invoice, entity, pdf_info, move=move)
                console.print(f"  [green]→[/green] {dest_path.parent.name}/{dest_path.name}")

                # Record in registry
                doc_record = DocumentRecord(
                    id="",
                    file_path=str(dest_path),
                    file_name=dest_path.name,
                    document_type=DocumentType.FATURA,
                    status=DocumentStatus.POR_PAGAR,
                    amount=float(pdf_info["amount"].replace(" EUR", "").replace(",", ".")) if pdf_info.get("amount") else None,
                    document_date=pdf_info.get("date"),
                    emitter_entity_id=entity.id,
                )
                self.registry.add_document(doc_record)

                return ProcessedInvoice(
                    original=invoice,
                    success=True,
                    destination_path=dest_path,
                    entity_name=entity.name,
                    document_type=DocumentType.FATURA,
                    amount=pdf_info.get("amount"),
                    nif=pdf_info["nifs"][0] if pdf_info.get("nifs") else None,
                )
            else:
                # Add to pending queue
                self.registry.add_to_pending({
                    "file_path": str(invoice.file_path),
                    "file_name": invoice.file_name,
                    "detected_type": "fatura",
                    "sender": invoice.sender,
                    "subject": invoice.subject,
                    "email_date": invoice.date.isoformat(),
                    "amount": pdf_info.get("amount"),
                    "nifs": pdf_info.get("nifs", []),
                    "pending_reason": "Entidade desconhecida",
                })

                return ProcessedInvoice(
                    original=invoice,
                    success=False,
                    error="Entidade desconhecida - adicionado a pendentes",
                )

        except Exception as e:
            logger.error(f"Error processing invoice {invoice.file_name}: {e}")
            return ProcessedInvoice(
                original=invoice,
                success=False,
                error=str(e),
            )

    def process_invoices(
        self,
        invoices: list[DownloadedInvoice],
        interactive: bool = True,
        move: bool = False,
    ) -> list[ProcessedInvoice]:
        """Process multiple downloaded invoices.

        Args:
            invoices: List of downloaded invoices.
            interactive: If True, prompt for unknown entities.
            move: If True, move files instead of copy.

        Returns:
            List of ProcessedInvoice results.
        """
        if not invoices:
            console.print("[yellow]Nenhuma fatura para processar.[/yellow]")
            return []

        console.print(f"\n[bold]A processar {len(invoices)} faturas...[/bold]")

        results = []
        for invoice in invoices:
            result = self.process_invoice(invoice, interactive=interactive, move=move)
            results.append(result)

        # Summary
        successful = sum(1 for r in results if r.success)
        pending = sum(1 for r in results if not r.success)

        console.print(f"\n[bold]Resumo:[/bold]")
        console.print(f"  [green]Organizadas: {successful}[/green]")
        if pending > 0:
            console.print(f"  [yellow]Pendentes: {pending}[/yellow]")
            console.print(f"  [dim]Use 'bank-extractor pendentes' para ver pendentes[/dim]")

        return results
