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
    ClassificationRule,
    ClassificationRulesEngine,
    MatchSource,
    MatchType,
    RuleAction,
    RuleCondition,
    get_rules_engine,
)
from src.core.document_registry import (
    AccountingScope,
    DocumentRecord,
    DocumentStatus,
    DocumentType,
    Entity,
    EntityType,
    get_document_registry,
)
from src.core.logger import get_logger, set_logging_suppressed
from src.modules.invoices.base import DownloadedInvoice

console = Console()
logger = get_logger(__name__)


class _DeleteMarker:
    """Marker to indicate file should be deleted/ignored permanently."""
    pass


class _IgnoreMarker:
    """Marker to indicate file should be ignored (left pending but skipped)."""
    pass


DELETE_FILE = _DeleteMarker()
IGNORE_FILE = _IgnoreMarker()


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

    # Ignore reason options
    IGNORE_REASONS = {
        "1": ("sender", "Este remetente (todos os emails deste endereço)"),
        "2": ("subject_pattern", "Padrão no assunto"),
        "3": ("filename_pattern", "Padrão no nome do ficheiro"),
        "4": ("this_only", "Apenas este documento (sem regra)"),
    }

    def __init__(self):
        """Initialize the invoice processor."""
        self.registry = get_document_registry()
        self.rules_engine = get_rules_engine()
        self._pdf_parser = None
        # Session statistics (for summary at the end)
        self._session_stats = {
            "organized": [],      # List of (filename, entity_name, dest_path)
            "deleted": [],        # List of (filename, reason)
            "ignored": [],        # List of (filename, reason)
            "auto_ignored": [],   # List of (filename, rule_name)
            "auto_deleted": [],   # List of (filename, rule_name)
            "errors": [],         # List of (filename, error)
        }

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
            info["vendor"] = metadata.vendor_name

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

    def reset_session_stats(self) -> None:
        """Reset session statistics for a new processing batch."""
        self._session_stats = {
            "organized": [],
            "deleted": [],
            "ignored": [],
            "auto_ignored": [],
            "auto_deleted": [],
            "errors": [],
        }

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

    def check_ignore_rules(
        self,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str] = None,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Check if any ignore rules match this invoice.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.

        Returns:
            Tuple of (should_ignore, action_value, rule_name).
            action_value is 'delete' for permanent deletion, 'ignore' for pending.
        """
        rule_data = self.build_rule_data(invoice, pdf_info, email_body)
        rule_match = self.rules_engine.get_best_match(rule_data)

        if rule_match and rule_match.action == RuleAction.MARK_IGNORE:
            return True, rule_match.action_value, rule_match.rule.name

        return False, None, None

    def _prompt_ignore_reason(
        self,
        invoice: DownloadedInvoice,
        action: str,  # "ignore" or "delete"
    ) -> tuple[Optional[RuleCondition], str]:
        """Prompt user to select reason for ignoring/deleting.

        Args:
            invoice: Invoice being ignored/deleted.
            action: "ignore" or "delete".

        Returns:
            Tuple of (rule_condition, reason_description).
        """
        action_name = "ignorar" if action == "ignore" else "eliminar"
        console.print(f"\n[bold]Porque quer {action_name} este documento?[/bold]")
        console.print("[dim]Esta escolha será aplicada automaticamente a documentos similares.[/dim]\n")

        for key, (_, desc) in self.IGNORE_REASONS.items():
            console.print(f"  {key}. {desc}")

        choice = Prompt.ask("Razão", choices=list(self.IGNORE_REASONS.keys()), default="1")
        reason_type, reason_desc = self.IGNORE_REASONS[choice]

        condition = None
        description = ""

        if reason_type == "sender":
            condition = RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.EXACT,
                pattern=invoice.sender,
            )
            description = f"Email: {invoice.sender}"

        elif reason_type == "subject_pattern":
            console.print(f"\nAssunto atual: [cyan]{invoice.subject}[/cyan]")
            pattern = Prompt.ask("Padrão a procurar no assunto", default=invoice.subject[:30])
            if pattern:
                condition = RuleCondition(
                    source=MatchSource.SUBJECT,
                    match_type=MatchType.CONTAINS,
                    pattern=pattern,
                )
                description = f"Assunto contém: {pattern}"

        elif reason_type == "filename_pattern":
            console.print(f"\nFicheiro: [cyan]{invoice.file_name}[/cyan]")
            pattern = Prompt.ask("Padrão a procurar no nome", default=invoice.file_name.split(".")[0][:20])
            if pattern:
                condition = RuleCondition(
                    source=MatchSource.FILENAME,
                    match_type=MatchType.CONTAINS,
                    pattern=pattern,
                )
                description = f"Nome contém: {pattern}"

        elif reason_type == "this_only":
            description = "Documento individual"

        return condition, description

    def _create_ignore_rule(
        self,
        condition: RuleCondition,
        action: str,  # "ignore" or "delete"
        description: str,
    ) -> ClassificationRule:
        """Create an ignore/delete rule.

        Args:
            condition: Rule condition to match.
            action: "ignore" or "delete".
            description: Human-readable description.

        Returns:
            Created rule.
        """
        rule_name = f"Auto-{action}: {description}"
        return self.rules_engine.create_rule(
            name=rule_name,
            conditions=[condition],
            action=RuleAction.MARK_IGNORE,
            action_value=action,  # "ignore" or "delete"
            description=f"Criada automaticamente: {description}",
            priority=50,  # High priority for ignore rules
            match_all=True,
        )

    def apply_ignore_rules_to_queue(
        self,
        invoices: list[DownloadedInvoice],
        current_index: int,
    ) -> dict[int, tuple[str, str]]:
        """Apply ignore rules to remaining invoices in queue.

        Args:
            invoices: Full list of invoices.
            current_index: Current processing index.

        Returns:
            Dictionary mapping invoice index to (action, rule_name) for matches.
        """
        auto_actions = {}

        for i in range(current_index + 1, len(invoices)):
            invoice = invoices[i]
            try:
                pdf_info = self.extract_pdf_info(invoice.file_path)
                should_ignore, action_value, rule_name = self.check_ignore_rules(
                    invoice, pdf_info, invoice.email_body
                )
                if should_ignore:
                    auto_actions[i] = (action_value, rule_name)
            except Exception:
                pass  # Skip errors during pre-check

        return auto_actions

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
        create_rules: bool = True,
    ) -> tuple[Optional[Entity], Optional[RuleCondition], Optional[str]]:
        """Prompt user to create or select an entity.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.
            create_rules: If True, ask for rule creation on ignore/delete.

        Returns:
            Tuple of (entity_or_marker, rule_condition, action).
            - entity_or_marker: Entity, DELETE_FILE, IGNORE_FILE, or None
            - rule_condition: Condition for auto-applying to similar docs (or None)
            - action: "delete", "ignore", or None
        """
        while True:
            console.print("\n[yellow]Entidade desconhecida![/yellow]")
            console.print("Opções:")
            console.print("  1. Criar nova entidade (com regra)")
            console.print("  2. Associar a entidade existente")
            console.print("  3. Ver mais informação (body/PDF)")
            console.print("  4. Ignorar (deixar pendente)")
            console.print("  5. [red]Eliminar ficheiro[/red]")

            choice = Prompt.ask("Escolha", choices=["1", "2", "3", "4", "5"], default="1")

            if choice == "1":
                return self._create_entity_with_rule(invoice, pdf_info, email_body), None, None
            elif choice == "2":
                entity = self._select_existing_entity(invoice, pdf_info, email_body)
                if entity:
                    return entity, None, None
                # If cancelled, show menu again
            elif choice == "3":
                self._show_extended_info(invoice, pdf_info, email_body)
                # Show menu again after displaying info
            elif choice == "4":
                # Ask for reason and create ignore rule
                if create_rules:
                    condition, description = self._prompt_ignore_reason(invoice, "ignore")
                    return IGNORE_FILE, condition, "ignore"
                return IGNORE_FILE, None, "ignore"
            elif choice == "5":
                # Confirm deletion and ask for reason
                if Confirm.ask(
                    f"[red]Tem a certeza que quer eliminar '{invoice.file_name}'?[/red]",
                    default=False,
                ):
                    if create_rules:
                        condition, description = self._prompt_ignore_reason(invoice, "delete")
                        return DELETE_FILE, condition, "delete"
                    return DELETE_FILE, None, "delete"
                # If not confirmed, show menu again

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

        # Accounting scope (personal vs business)
        console.print("Âmbito contabilístico: [cyan]pessoal[/cyan] ou [cyan]empresa[/cyan]")
        scope_str = Prompt.ask("Âmbito", choices=["pessoal", "empresa"], default="empresa")
        scope = AccountingScope(scope_str)

        # Create entity
        entity = self.registry.create_entity(
            name=name,
            folder_name=folder_name,
            entity_type=entity_type,
            scope=scope,
            nifs=pdf_info.get("nifs", []),
            sender_emails=[invoice.sender],
        )

        console.print(f"[green]Entidade '{name}' criada![/green]")

        # Ask about creating classification rule
        console.print("\n[bold]Criar regra de classificação[/bold]")
        console.print("Que critérios usar para identificar automaticamente futuras faturas?")

        rule_conditions = []
        option_num = 1

        # Option 1: Sender email (always suggested)
        console.print(f"\n{option_num}. Email remetente: [cyan]{invoice.sender}[/cyan]")
        if Confirm.ask("   Usar email do remetente?", default=True):
            rule_conditions.append(RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.EXACT,
                pattern=invoice.sender,
            ))
        option_num += 1

        # Option 2: Subject pattern
        console.print(f"\n{option_num}. Assunto: [cyan]{invoice.subject}[/cyan]")
        if Confirm.ask("   Usar padrão no assunto?", default=False):
            subject_pattern = Prompt.ask("   Padrão a procurar no assunto", default=invoice.subject[:30])
            if subject_pattern:
                rule_conditions.append(RuleCondition(
                    source=MatchSource.SUBJECT,
                    match_type=MatchType.CONTAINS,
                    pattern=subject_pattern,
                ))
        option_num += 1

        # Option 3: Body pattern (always show, with preview if available)
        body_preview = ""
        if email_body:
            body_preview = email_body[:100].replace("\n", " ")
            if len(email_body) > 100:
                body_preview += "..."
            console.print(f"\n{option_num}. Body do email: [cyan]{body_preview}[/cyan]")
        else:
            console.print(f"\n{option_num}. Body do email: [dim](não disponível)[/dim]")

        if Confirm.ask("   Usar padrão no body do email?", default=False):
            if email_body:
                # Show more of the body to help user identify a pattern
                console.print(f"   [dim]Primeiros 500 chars:[/dim]")
                console.print(f"   {email_body[:500]}")
            body_pattern = Prompt.ask("   Padrão a procurar no body")
            if body_pattern:
                rule_conditions.append(RuleCondition(
                    source=MatchSource.BODY,
                    match_type=MatchType.CONTAINS,
                    pattern=body_pattern,
                ))
        option_num += 1

        # Option 4: PDF content pattern (always show, with preview)
        raw_text = pdf_info.get("raw_text", "")
        vendor = pdf_info.get("vendor")
        if raw_text:
            pdf_preview = raw_text[:100].replace("\n", " ")
            if len(raw_text) > 100:
                pdf_preview += "..."
            console.print(f"\n{option_num}. Conteúdo do PDF: [cyan]{pdf_preview}[/cyan]")
        else:
            console.print(f"\n{option_num}. Conteúdo do PDF: [dim](não disponível)[/dim]")

        if Confirm.ask("   Usar padrão no conteúdo do PDF?", default=False):
            if raw_text:
                # Show more of the PDF to help user identify a pattern
                console.print(f"   [dim]Primeiros 500 chars:[/dim]")
                console.print(f"   {raw_text[:500]}")
            default_pdf_pattern = vendor if vendor else ""
            pdf_pattern = Prompt.ask("   Padrão a procurar no PDF", default=default_pdf_pattern)
            if pdf_pattern:
                rule_conditions.append(RuleCondition(
                    source=MatchSource.PDF_CONTENT,
                    match_type=MatchType.CONTAINS,
                    pattern=pdf_pattern,
                ))
        option_num += 1

        # Option 5: NIF from PDF (if found)
        nifs = pdf_info.get("nifs", [])
        if nifs:
            console.print(f"\n{option_num}. NIF no PDF: [cyan]{', '.join(nifs)}[/cyan]")
            if Confirm.ask("   Usar NIF do PDF?", default=False):
                rule_conditions.append(RuleCondition(
                    source=MatchSource.PDF_NIF,
                    match_type=MatchType.CONTAINS,
                    pattern=nifs[0],
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
                  Note: Files in temp folder are always moved regardless of this flag.

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

        # Create destination folder: faturas/year/scope/entity_folder/
        dest_folder = settings.data_dir / "faturas" / str(year) / entity.scope.value / entity.folder_name
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

        # Always move files from temp folder to clean it up
        # Otherwise respect the move parameter
        is_in_temp = settings.faturas_temp_dir in invoice.file_path.parents or \
                     invoice.file_path.parent == settings.faturas_temp_dir
        should_move = move or is_in_temp

        if should_move:
            shutil.move(str(invoice.file_path), str(dest_path))
        else:
            shutil.copy2(str(invoice.file_path), str(dest_path))

        return dest_path

    def process_invoice(
        self,
        invoice: DownloadedInvoice,
        interactive: bool = True,
        move: bool = False,
        auto_action: Optional[tuple[str, str]] = None,
        suppress_output: bool = False,
    ) -> tuple[ProcessedInvoice, Optional[RuleCondition], Optional[str]]:
        """Process a single downloaded invoice.

        Args:
            invoice: Downloaded invoice to process.
            interactive: If True, prompt for unknown entities.
            move: If True, move file instead of copy.
            auto_action: If provided, (action, rule_name) to apply automatically.
            suppress_output: If True, don't print progress (for batch summary mode).

        Returns:
            Tuple of (ProcessedInvoice, rule_condition, action).
            rule_condition and action are set when user creates ignore/delete rule.
        """
        try:
            # Extract PDF information
            pdf_info = self.extract_pdf_info(invoice.file_path)

            # Get email body from invoice
            email_body = invoice.email_body

            # Check for auto-action (from previously created rule in this session)
            if auto_action:
                action_value, rule_name = auto_action
                if action_value == "delete":
                    try:
                        invoice.file_path.unlink()
                        self._session_stats["auto_deleted"].append((invoice.file_name, rule_name))
                        return ProcessedInvoice(
                            original=invoice,
                            success=True,
                            error=f"Auto-eliminado: {rule_name}",
                        ), None, None
                    except Exception as e:
                        self._session_stats["errors"].append((invoice.file_name, str(e)))
                        return ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error=f"Erro ao auto-eliminar: {e}",
                        ), None, None
                else:  # ignore
                    self._session_stats["auto_ignored"].append((invoice.file_name, rule_name))
                    return ProcessedInvoice(
                        original=invoice,
                        success=False,
                        error=f"Auto-ignorado: {rule_name}",
                    ), None, None

            # Check for existing ignore rules
            should_ignore, action_value, rule_name = self.check_ignore_rules(
                invoice, pdf_info, email_body
            )
            if should_ignore:
                if action_value == "delete":
                    try:
                        invoice.file_path.unlink()
                        self._session_stats["auto_deleted"].append((invoice.file_name, rule_name))
                        return ProcessedInvoice(
                            original=invoice,
                            success=True,
                            error=f"Auto-eliminado por regra: {rule_name}",
                        ), None, None
                    except Exception as e:
                        self._session_stats["errors"].append((invoice.file_name, str(e)))
                        return ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error=f"Erro ao auto-eliminar: {e}",
                        ), None, None
                else:  # ignore
                    self._session_stats["auto_ignored"].append((invoice.file_name, rule_name))
                    return ProcessedInvoice(
                        original=invoice,
                        success=False,
                        error=f"Auto-ignorado por regra: {rule_name}",
                    ), None, None

            # Try to find matching entity
            entity, match_reason = self.find_entity_for_invoice(invoice, pdf_info, email_body)
            rule_condition = None
            action = None

            if entity:
                # Known entity - organize automatically
                if not suppress_output:
                    console.print(f"\n[green]✓[/green] {invoice.file_name}")
                    console.print(f"  [dim]{match_reason} → {entity.name}[/dim]")

            elif interactive:
                # Show summary and prompt
                if not suppress_output:
                    console.print(f"\n[yellow]?[/yellow] {invoice.file_name}")
                self.show_invoice_summary(invoice, pdf_info)
                entity, rule_condition, action = self.prompt_for_entity(invoice, pdf_info, email_body)

            # Check if user chose to delete the file
            if isinstance(entity, _DeleteMarker):
                # Delete the file permanently
                try:
                    invoice.file_path.unlink()
                    self._session_stats["deleted"].append(
                        (invoice.file_name, f"Manual: {rule_condition.pattern if rule_condition else 'individual'}")
                    )
                    return ProcessedInvoice(
                        original=invoice,
                        success=True,
                        error="Ficheiro eliminado pelo utilizador",
                    ), rule_condition, action
                except Exception as e:
                    self._session_stats["errors"].append((invoice.file_name, str(e)))
                    return ProcessedInvoice(
                        original=invoice,
                        success=False,
                        error=f"Erro ao eliminar: {e}",
                    ), None, None

            # Check if user chose to ignore the file
            if isinstance(entity, _IgnoreMarker):
                self._session_stats["ignored"].append(
                    (invoice.file_name, f"Manual: {rule_condition.pattern if rule_condition else 'individual'}")
                )
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
                    "pending_reason": "Ignorado pelo utilizador",
                })
                return ProcessedInvoice(
                    original=invoice,
                    success=False,
                    error="Ignorado pelo utilizador - adicionado a pendentes",
                ), rule_condition, action

            if entity:
                # Organize the file
                dest_path = self.organize_invoice(invoice, entity, pdf_info, move=move)
                if not suppress_output:
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

                self._session_stats["organized"].append(
                    (invoice.file_name, entity.name, str(dest_path))
                )

                return ProcessedInvoice(
                    original=invoice,
                    success=True,
                    destination_path=dest_path,
                    entity_name=entity.name,
                    document_type=DocumentType.FATURA,
                    amount=pdf_info.get("amount"),
                    nif=pdf_info["nifs"][0] if pdf_info.get("nifs") else None,
                ), None, None
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

                self._session_stats["ignored"].append(
                    (invoice.file_name, "Entidade desconhecida")
                )

                return ProcessedInvoice(
                    original=invoice,
                    success=False,
                    error="Entidade desconhecida - adicionado a pendentes",
                ), None, None

        except Exception as e:
            logger.error(f"Error processing invoice {invoice.file_name}: {e}")
            self._session_stats["errors"].append((invoice.file_name, str(e)))
            return ProcessedInvoice(
                original=invoice,
                success=False,
                error=str(e),
            ), None, None

    def show_session_summary(self) -> None:
        """Display comprehensive summary of the processing session."""
        stats = self._session_stats

        console.print(f"\n[bold]━━━ Resumo da Sessão ━━━[/bold]")

        # Organized documents
        if stats["organized"]:
            console.print(f"\n[green]✓ Organizadas ({len(stats['organized'])}):[/green]")
            for filename, entity, dest in stats["organized"]:
                console.print(f"  • {filename[:40]} → {entity}")

        # Auto-ignored by rules
        if stats["auto_ignored"]:
            console.print(f"\n[cyan]⊘ Auto-ignoradas por regra ({len(stats['auto_ignored'])}):[/cyan]")
            # Group by rule name
            by_rule = {}
            for filename, rule in stats["auto_ignored"]:
                by_rule.setdefault(rule, []).append(filename)
            for rule, files in by_rule.items():
                console.print(f"  [dim]{rule}:[/dim]")
                for f in files[:3]:  # Show max 3 files per rule
                    console.print(f"    • {f[:50]}")
                if len(files) > 3:
                    console.print(f"    [dim]... e mais {len(files) - 3} ficheiros[/dim]")

        # Auto-deleted by rules
        if stats["auto_deleted"]:
            console.print(f"\n[red]✗ Auto-eliminadas por regra ({len(stats['auto_deleted'])}):[/red]")
            by_rule = {}
            for filename, rule in stats["auto_deleted"]:
                by_rule.setdefault(rule, []).append(filename)
            for rule, files in by_rule.items():
                console.print(f"  [dim]{rule}:[/dim]")
                for f in files[:3]:
                    console.print(f"    • {f[:50]}")
                if len(files) > 3:
                    console.print(f"    [dim]... e mais {len(files) - 3} ficheiros[/dim]")

        # Manually ignored
        if stats["ignored"]:
            console.print(f"\n[yellow]○ Ignoradas/Pendentes ({len(stats['ignored'])}):[/yellow]")
            for filename, reason in stats["ignored"][:5]:
                console.print(f"  • {filename[:40]} [{reason[:30]}]")
            if len(stats["ignored"]) > 5:
                console.print(f"  [dim]... e mais {len(stats['ignored']) - 5} ficheiros[/dim]")

        # Manually deleted
        if stats["deleted"]:
            console.print(f"\n[red]✗ Eliminadas ({len(stats['deleted'])}):[/red]")
            for filename, reason in stats["deleted"]:
                console.print(f"  • {filename[:40]}")

        # Errors
        if stats["errors"]:
            console.print(f"\n[red bold]⚠ Erros ({len(stats['errors'])}):[/red bold]")
            for filename, error in stats["errors"][:5]:
                console.print(f"  • {filename[:30]}: {error[:40]}")
            if len(stats["errors"]) > 5:
                console.print(f"  [dim]... e mais {len(stats['errors']) - 5} erros[/dim]")

        # Final counts
        total = (
            len(stats["organized"]) +
            len(stats["auto_ignored"]) +
            len(stats["auto_deleted"]) +
            len(stats["ignored"]) +
            len(stats["deleted"]) +
            len(stats["errors"])
        )
        console.print(f"\n[bold]Total processado: {total}[/bold]")

        pending_count = len(stats["ignored"]) + len(stats["auto_ignored"])
        if pending_count > 0:
            console.print(f"[dim]Use 'bank-extractor pendentes' para ver documentos pendentes[/dim]")

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

        # Reset session stats
        self.reset_session_stats()

        # Suppress logging during interactive processing
        if interactive:
            set_logging_suppressed(True)

        console.print(f"\n[bold]A processar {len(invoices)} faturas...[/bold]\n")

        results = []
        auto_actions = {}  # Maps invoice index to (action, rule_name)

        try:
            i = 0
            while i < len(invoices):
                invoice = invoices[i]

                # Check if this invoice has an auto-action from a previously created rule
                auto_action = auto_actions.get(i)

                result, rule_condition, action = self.process_invoice(
                    invoice,
                    interactive=interactive,
                    move=move,
                    auto_action=auto_action,
                    suppress_output=bool(auto_action),  # Don't show output for auto-processed
                )
                results.append(result)

                # If user created an ignore/delete rule, create it and apply to remaining
                if rule_condition and action:
                    # Create the rule
                    rule = self._create_ignore_rule(
                        rule_condition,
                        action,
                        rule_condition.pattern,
                    )
                    console.print(
                        f"\n[dim]Regra criada: '{rule.name}' - "
                        f"a verificar {len(invoices) - i - 1} documentos restantes...[/dim]"
                    )

                    # Apply to remaining invoices
                    new_auto_actions = self.apply_ignore_rules_to_queue(invoices, i)
                    auto_actions.update(new_auto_actions)

                    if new_auto_actions:
                        console.print(
                            f"[cyan]→ {len(new_auto_actions)} documentos serão "
                            f"{'eliminados' if action == 'delete' else 'ignorados'} "
                            f"automaticamente[/cyan]\n"
                        )

                i += 1

        finally:
            # Always re-enable logging
            if interactive:
                set_logging_suppressed(False)

        # Show comprehensive summary at the end
        self.show_session_summary()

        return results
