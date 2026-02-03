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
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.categories import DELETE_REASONS, IGNORE_REASONS
from src.core.config import settings
from src.core.classification_rules import (
    ClassificationRule,
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
from src.cli.common import prompt_category_selection, prompt_entity_selection
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


# Pattern syntax help text (used in multiple places)
PATTERN_HELP = """[dim]Sintaxe de padroes:[/dim]
  [cyan]*[/cyan]  wildcard     [dim]ex: *@vodafone.pt, *fatura*[/dim]
  [cyan]|[/cyan]  OU (or)      [dim]ex: fatura|invoice|factura[/dim]
  [cyan]+[/cyan]  E (and)      [dim]ex: fatura+vodafone (ambos presentes)[/dim]
  [dim]Combinar: *energia*+*edp* (contem energia E edp)[/dim]"""


def _convert_pattern_to_regex(pattern: str) -> tuple[str, bool]:
    """Convert user pattern to regex, handling *, |, and + operators.

    Args:
        pattern: User-provided pattern with *, |, + operators.

    Returns:
        Tuple of (regex_pattern, uses_special_chars).
        For AND patterns (+), returns a lookahead-based regex.
    """
    has_special = "*" in pattern or "|" in pattern or "+" in pattern

    if not has_special:
        # Simple contains - escape for regex
        return re.escape(pattern), False

    # Handle AND patterns first (highest precedence)
    if "+" in pattern:
        # Split by + and create lookahead assertions for each part
        parts = [p.strip() for p in pattern.split("+") if p.strip()]
        lookaheads = []
        for p in parts:
            # Convert each part (may have wildcards)
            escaped = p.replace(".", r"\.").replace("*", ".*")
            lookaheads.append(f"(?=.*{escaped})")
        # Combine lookaheads - all must match
        return "".join(lookaheads) + ".*", True

    # Handle OR patterns
    if "|" in pattern:
        parts = [p.strip() for p in pattern.split("|") if p.strip()]
        regex_parts = []
        for p in parts:
            escaped = p.replace(".", r"\.").replace("*", ".*")
            regex_parts.append(f"({escaped})")
        return "|".join(regex_parts), True

    # Just wildcards
    return pattern.replace(".", r"\.").replace("*", ".*"), True


@dataclass
class UndoAction:
    """Represents an action that can be undone."""

    file_path: Path  # Original file path
    action_type: str  # "organize", "ignore", "delete"
    destination: Optional[Path] = None  # Where file was moved (for organize)
    rule_id: Optional[str] = None  # Rule created (if any)
    pending_id: Optional[str] = None  # Pending document ID (for ignore)
    entity_id: Optional[str] = None  # Entity associated
    document_id: Optional[str] = None  # Document record ID (for organize)


class UndoStack:
    """Stack of undoable actions for the current session."""

    def __init__(self):
        self._actions: list[UndoAction] = []

    def push(self, action: UndoAction) -> None:
        """Add an action to the stack."""
        self._actions.append(action)

    def pop(self) -> Optional[UndoAction]:
        """Remove and return the last action."""
        if self._actions:
            return self._actions.pop()
        return None

    def peek(self) -> Optional[UndoAction]:
        """Return the last action without removing it."""
        if self._actions:
            return self._actions[-1]
        return None

    def can_undo(self) -> bool:
        """Check if there are actions to undo."""
        return len(self._actions) > 0

    def clear(self) -> None:
        """Clear all actions."""
        self._actions.clear()


@dataclass
class ProcessedInvoice:
    """Result of processing an invoice."""

    original: DownloadedInvoice
    success: bool
    destination_path: Optional[Path] = None
    entity_name: Optional[str] = None
    document_type: Optional[DocumentType] = None
    category: Optional[str] = None  # Category ID
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

    # Rule creation options (for ignore/delete)
    RULE_OPTIONS = {
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
        self._undo_stack = UndoStack()
        # Session statistics (for summary at the end)
        self._session_stats = {
            "organized": [],  # List of (filename, entity_name, dest_path)
            "deleted": [],  # List of (filename, reason)
            "ignored": [],  # List of (filename, reason)
            "auto_ignored": [],  # List of (filename, rule_name)
            "auto_deleted": [],  # List of (filename, rule_name)
            "errors": [],  # List of (filename, error)
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

    def prompt_document_type(self) -> Optional[DocumentType]:
        """Prompt user to select the document type.

        Returns:
            Selected DocumentType, None if cancelled, or "ignore" marker.
        """
        console.print("\n[bold cyan]Que tipo de documento e?[/bold cyan]")

        options = DocumentType.get_display_options()
        for i, (doc_type, label) in enumerate(options, 1):
            console.print(f"  [white]{i}.[/white] {label}")

        console.print("  [red] 8.[/red] Ignorar / Eliminar")
        console.print("  [dim] 0.[/dim] Cancelar")

        while True:
            try:
                choice_str = Prompt.ask("\n[bold]Escolha[/bold] [1-8, 0]", default="1")

                if not choice_str or choice_str == "0":
                    return None

                choice = int(choice_str)

                if choice == 8:
                    # Return special marker for ignore/delete
                    return "ignore"  # type: ignore

                if 1 <= choice <= len(options):
                    selected_type = options[choice - 1][0]
                    console.print(f"[green]Tipo:[/green] {options[choice - 1][1]}")
                    return selected_type
                else:
                    console.print("[red]Escolha invalida. Use 0-8.[/red]")
            except ValueError:
                console.print("[red]Por favor introduza um numero.[/red]")

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
        pdf_info: dict,
        email_body: Optional[str],
        action: str,  # "ignore" or "delete"
    ) -> tuple[Optional[RuleCondition], str, str]:
        """Prompt user to select reason for ignoring/deleting.

        Args:
            invoice: Invoice being ignored/deleted.
            pdf_info: Extracted PDF information.
            email_body: Optional email body content.
            action: "ignore" or "delete".

        Returns:
            Tuple of (rule_condition, reason_code, reason_label).
        """
        action_name = "ignorar" if action == "ignore" else "eliminar"
        reasons = IGNORE_REASONS if action == "ignore" else DELETE_REASONS

        # Step 1: Ask for reason
        console.print(f"\n[bold]Razão para {action_name}:[/bold]")
        reason_keys = list(reasons.keys())
        for i, (key, label) in enumerate(reasons.items(), 1):
            console.print(f"  {i}. {label}")
        console.print("  0. ← Cancelar (voltar ao menu)")

        choices = ["0"] + [str(i) for i in range(1, len(reason_keys) + 1)]
        choice = Prompt.ask("Escolha", choices=choices, default="1")

        if choice == "0":
            return None, "", ""

        reason_idx = int(choice) - 1
        reason_code = reason_keys[reason_idx]
        reason_label = reasons[reason_code]

        # Step 2: Ask if user wants to create a rule for auto-apply
        console.print(
            f"\n[bold]Criar regra para {action_name} automaticamente documentos similares?[/bold]"
        )
        console.print("  1. Sim, por remetente (todos deste email)")
        console.print("  2. Sim, por padrão no assunto")
        console.print("  3. Sim, por padrão no nome do ficheiro")
        console.print("  4. Não, apenas este documento")

        rule_choice = Prompt.ask("Escolha", choices=["1", "2", "3", "4"], default="4")

        condition = None
        description = reason_label

        if rule_choice == "1":
            # By sender - with wildcard support
            condition, description = self._prompt_sender_pattern(invoice)

        elif rule_choice == "2":
            # By subject pattern - with interactive viewing
            condition, description = self._prompt_text_pattern(
                "assunto",
                invoice.subject,
                MatchSource.SUBJECT,
                pdf_info,
                email_body,
            )

        elif rule_choice == "3":
            # By filename pattern
            condition, description = self._prompt_text_pattern(
                "nome do ficheiro",
                invoice.file_name,
                MatchSource.FILENAME,
                pdf_info,
                email_body,
            )

        return condition, reason_code, reason_label

    def _prompt_sender_pattern(
        self,
        invoice: DownloadedInvoice,
    ) -> tuple[Optional[RuleCondition], str]:
        """Prompt for sender email pattern with wildcard support.

        Args:
            invoice: Downloaded invoice.

        Returns:
            Tuple of (rule_condition, description).
        """
        console.print("\n[bold]Padrao do remetente[/bold]")
        console.print(f"Email atual: [cyan]{invoice.sender}[/cyan]")
        console.print(PATTERN_HELP)

        # Suggest domain-based pattern
        if "@" in invoice.sender:
            domain = invoice.sender.split("@")[1]
            default_pattern = f"*@{domain}"
        else:
            default_pattern = invoice.sender

        pattern = Prompt.ask("Padrão", default=default_pattern)

        if not pattern:
            return None, ""

        # Convert pattern using helper function
        regex_pattern, uses_special = _convert_pattern_to_regex(pattern)

        if uses_special:
            condition = RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.REGEX,
                pattern=regex_pattern,
            )
        else:
            condition = RuleCondition(
                source=MatchSource.SENDER_EMAIL,
                match_type=MatchType.EXACT,
                pattern=pattern,
            )

        return condition, f"Remetente: {pattern}"

    def _prompt_text_pattern(
        self,
        field_name: str,
        field_value: str,
        match_source: MatchSource,
        pdf_info: dict,
        email_body: Optional[str],
    ) -> tuple[Optional[RuleCondition], str]:
        """Prompt for text pattern with viewing and composite support.

        Args:
            field_name: Name of the field (for display).
            field_value: Current value of the field.
            match_source: Source to match against.
            pdf_info: Extracted PDF information.
            email_body: Optional email body.

        Returns:
            Tuple of (rule_condition, description).
        """
        console.print(f"\n[bold]Padrao no {field_name}[/bold]")
        console.print(
            f"Valor atual: [cyan]{field_value[:100]}{'...' if len(field_value) > 100 else ''}[/cyan]"
        )

        console.print("\n[dim]Visualizacao: v=campo, b=body, p=PDF, a=abrir[/dim]")
        console.print(PATTERN_HELP)

        while True:
            user_input = Prompt.ask(
                "Padrão (ou v/b/p/a)", default=field_value[:30] if len(field_value) > 0 else ""
            )

            if user_input.lower() == "v":
                console.print(f"\n[bold]{field_name.capitalize()} completo:[/bold]")
                console.print(Panel(field_value, border_style="cyan"))
                continue

            if user_input.lower() == "b":
                if email_body:
                    console.print("\n[bold]Body do email:[/bold]")
                    console.print(Panel(email_body[:2000], border_style="blue"))
                else:
                    console.print("[dim]Body do email não disponível[/dim]")
                continue

            if user_input.lower() == "p":
                raw_text = pdf_info.get("raw_text", "")
                if raw_text:
                    console.print("\n[bold]Conteúdo do PDF:[/bold]")
                    console.print(Panel(raw_text[:2000], border_style="green"))
                else:
                    console.print("[dim]Conteúdo do PDF não disponível[/dim]")
                continue

            if user_input.lower() == "a":
                (
                    self._open_file(Path(pdf_info.get("file_path", "")))
                    if pdf_info.get("file_path")
                    else None
                )
                continue

            # It's a pattern
            if not user_input:
                return None, ""

            pattern = user_input
            break

        # Convert pattern using helper function
        regex_pattern, uses_special = _convert_pattern_to_regex(pattern)

        if uses_special:
            condition = RuleCondition(
                source=match_source,
                match_type=MatchType.REGEX,
                pattern=regex_pattern,
            )
        else:
            condition = RuleCondition(
                source=match_source,
                match_type=MatchType.CONTAINS,
                pattern=pattern,
            )

        description = f"{field_name.capitalize()} contem: {pattern}"
        return condition, description

    def _prompt_pattern_with_viewing(
        self,
        field_name: str,
        field_value: str,
        match_source: MatchSource,
        invoice: DownloadedInvoice,
        pdf_info: dict,
        email_body: Optional[str],
        default_pattern: str = "",
    ) -> Optional[RuleCondition]:
        """Prompt for a pattern with interactive viewing and wildcard/composite support.

        Args:
            field_name: Name of the field being configured.
            field_value: Current value of the field.
            match_source: Source for the rule condition.
            invoice: Current invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body.
            default_pattern: Default pattern suggestion.

        Returns:
            RuleCondition or None if cancelled.
        """
        console.print(f"\n[bold]Definir padrao para {field_name}[/bold]")

        # Show current value preview
        preview = field_value[:100].replace("\n", " ")
        if len(field_value) > 100:
            preview += "..."
        console.print(f"Valor actual: [cyan]{preview}[/cyan]")

        console.print(
            "\n[dim]Visualizacao: v=campo, e=email, b=body, p=PDF, a=abrir, c=cancelar[/dim]"
        )
        console.print(PATTERN_HELP)

        while True:
            user_input = Prompt.ask(
                "Padrão (ou v/e/b/p/a/c)", default=default_pattern if default_pattern else ""
            )

            cmd = user_input.lower().strip()

            if cmd == "v":
                console.print(f"\n[bold]{field_name} completo:[/bold]")
                console.print(Panel(field_value[:3000], border_style="cyan"))
                if len(field_value) > 3000:
                    console.print(f"[dim]... ({len(field_value) - 3000} caracteres omitidos)[/dim]")
                continue

            if cmd == "e":
                console.print("\n[bold]Informação do Email:[/bold]")
                console.print(f"  Remetente: [cyan]{invoice.sender}[/cyan]")
                console.print(f"  Assunto: [cyan]{invoice.subject}[/cyan]")
                console.print(f"  Data: [cyan]{invoice.date.strftime('%d/%m/%Y %H:%M')}[/cyan]")
                continue

            if cmd == "b":
                if email_body:
                    console.print("\n[bold]Body do email:[/bold]")
                    console.print(Panel(email_body[:3000], border_style="blue"))
                    if len(email_body) > 3000:
                        console.print(
                            f"[dim]... ({len(email_body) - 3000} caracteres omitidos)[/dim]"
                        )
                else:
                    console.print("[dim]Body do email não disponível[/dim]")
                continue

            if cmd == "p":
                raw_text = pdf_info.get("raw_text", "")
                if raw_text:
                    console.print("\n[bold]Conteúdo do PDF:[/bold]")
                    console.print(Panel(raw_text[:3000], border_style="green"))
                    if len(raw_text) > 3000:
                        console.print(
                            f"[dim]... ({len(raw_text) - 3000} caracteres omitidos)[/dim]"
                        )
                else:
                    console.print("[dim]Conteúdo do PDF não disponível[/dim]")
                continue

            if cmd == "a":
                if invoice.file_path.exists():
                    self._open_file(invoice.file_path)
                else:
                    console.print("[dim]Ficheiro não disponível[/dim]")
                continue

            if cmd == "c":
                return None

            # It's a pattern - process it
            if not user_input:
                return None

            pattern = user_input
            break

        # Convert pattern using helper function
        regex_pattern, uses_special = _convert_pattern_to_regex(pattern)

        if uses_special:
            return RuleCondition(
                source=match_source,
                match_type=MatchType.REGEX,
                pattern=regex_pattern,
            )
        else:
            return RuleCondition(
                source=match_source,
                match_type=MatchType.CONTAINS,
                pattern=pattern,
            )

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
    ) -> tuple[
        Optional[Entity], Optional[RuleCondition], Optional[str], Optional[str], Optional[str]
    ]:
        """Prompt user to create or select an entity.

        Args:
            invoice: Downloaded invoice.
            pdf_info: Extracted PDF info.
            email_body: Optional email body content.
            create_rules: If True, ask for rule creation on ignore/delete.

        Returns:
            Tuple of (entity_or_marker, rule_condition, action, reason_code, reason_label).
            - entity_or_marker: Entity, DELETE_FILE, IGNORE_FILE, None, or "undo"
            - rule_condition: Condition for auto-applying to similar docs (or None)
            - action: "delete", "ignore", or None
            - reason_code: Code for ignore/delete reason (or None)
            - reason_label: Human-readable reason label (or None)
        """
        while True:
            console.print("\n[yellow]Entidade desconhecida![/yellow]")
            console.print("Opções:")
            console.print("  1. Criar nova entidade (com regra)")
            console.print("  2. Associar a entidade existente")
            console.print("  3. Ver mais informação (body/PDF)")
            console.print("  4. Ignorar (deixar pendente)")
            console.print("  5. [red]Eliminar ficheiro[/red]")

            choices = ["1", "2", "3", "4", "5"]

            # Show undo option if there are actions to undo
            if self._undo_stack.can_undo():
                last_action = self._undo_stack.peek()
                action_desc = {
                    "organize": "organização",
                    "ignore": "ignorar",
                    "delete": "eliminação",
                }.get(last_action.action_type, last_action.action_type)
                console.print(f"  6. [cyan]← Voltar atrás (desfazer {action_desc})[/cyan]")
                choices.append("6")

            choice = Prompt.ask("Escolha", choices=choices, default="1")

            if choice == "1":
                return (
                    self._create_entity_with_rule(invoice, pdf_info, email_body),
                    None,
                    None,
                    None,
                    None,
                )
            elif choice == "2":
                entity = self._select_existing_entity(invoice, pdf_info, email_body)
                if entity:
                    return entity, None, None, None, None
                # If cancelled, show menu again
            elif choice == "3":
                self._show_extended_info(invoice, pdf_info, email_body)
                # Show menu again after displaying info
            elif choice == "4":
                # Ask for reason and create ignore rule
                if create_rules:
                    condition, reason_code, reason_label = self._prompt_ignore_reason(
                        invoice, pdf_info, email_body, "ignore"
                    )
                    if reason_code == "":
                        # User cancelled
                        continue
                    return IGNORE_FILE, condition, "ignore", reason_code, reason_label
                return IGNORE_FILE, None, "ignore", None, None
            elif choice == "5":
                # Show warning and ask for reason
                console.print("\n[red bold]⚠ ATENÇÃO: Esta ação é permanente![/red bold]")
                if create_rules:
                    condition, reason_code, reason_label = self._prompt_ignore_reason(
                        invoice, pdf_info, email_body, "delete"
                    )
                    if reason_code == "":
                        # User cancelled
                        continue
                    # Final confirmation
                    if Confirm.ask(
                        f"[red]Tem a certeza que quer eliminar '{invoice.file_name}'?[/red]",
                        default=False,
                    ):
                        return DELETE_FILE, condition, "delete", reason_code, reason_label
                    continue
                else:
                    if Confirm.ask(
                        f"[red]Tem a certeza que quer eliminar '{invoice.file_name}'?[/red]",
                        default=False,
                    ):
                        return DELETE_FILE, None, "delete", None, None
                # If not confirmed, show menu again
            elif choice == "6":
                # Handle undo
                if self._handle_undo():
                    return "undo", None, None, None, None
                # If undo failed or cancelled, show menu again

    def _handle_undo(self) -> bool:
        """Handle undo of the last action.

        Returns:
            True if undo was successful, False otherwise.
        """
        if not self._undo_stack.can_undo():
            console.print("[yellow]Não há ações para desfazer[/yellow]")
            return False

        action = self._undo_stack.peek()

        if action.action_type == "delete":
            console.print("[red]Não é possível recuperar ficheiros eliminados[/red]")
            return False

        # Show what will be undone
        console.print("\n[bold]Desfazer última ação:[/bold]")
        if action.action_type == "organize":
            console.print("  Tipo: Organização")
            console.print(f"  Ficheiro: [cyan]{action.file_path.name}[/cyan]")
            console.print(f"  Destino: [cyan]{action.destination}[/cyan]")
            console.print("  [dim]O ficheiro será movido de volta para _pendentes/[/dim]")
        elif action.action_type == "ignore":
            console.print("  Tipo: Ignorar")
            console.print(f"  Ficheiro: [cyan]{action.file_path.name}[/cyan]")
            console.print("  [dim]O ficheiro será removido dos pendentes[/dim]")

        if action.rule_id:
            console.print("  [dim]Regra criada será eliminada[/dim]")

        if not Confirm.ask("Confirma desfazer?", default=True):
            return False

        # Execute undo
        success = self._execute_undo(action)

        if success:
            self._undo_stack.pop()
            console.print("[green]Ação desfeita com sucesso![/green]")
            return True
        else:
            console.print("[red]Erro ao desfazer ação[/red]")
            return False

    def _execute_undo(self, action: UndoAction) -> bool:
        """Execute the undo of an action.

        Args:
            action: The action to undo.

        Returns:
            True if successful, False otherwise.
        """
        try:
            if action.action_type == "organize":
                # Move file back from destination to pending folder
                if action.destination and action.destination.exists():
                    pending_dir = settings.faturas_temp_dir
                    pending_dir.mkdir(parents=True, exist_ok=True)
                    dest_path = pending_dir / action.file_path.name
                    shutil.move(str(action.destination), str(dest_path))

                # Remove document record
                if action.document_id:
                    # Note: DocumentRegistry doesn't have delete_document, so we skip this
                    pass

                # Delete rule if created
                if action.rule_id:
                    self.rules_engine.delete_rule(action.rule_id)

                # Update session stats
                self._session_stats["organized"] = [
                    s for s in self._session_stats["organized"] if s[0] != action.file_path.name
                ]

                return True

            elif action.action_type == "ignore":
                # Remove from pending queue
                if action.pending_id:
                    self.registry.remove_from_pending(action.pending_id)

                # Delete rule if created
                if action.rule_id:
                    self.rules_engine.delete_rule(action.rule_id)

                # Update session stats
                self._session_stats["ignored"] = [
                    s for s in self._session_stats["ignored"] if s[0] != action.file_path.name
                ]

                return True

            return False

        except Exception as e:
            logger.error(f"Error executing undo: {e}")
            return False

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
        console.print(PATTERN_HELP)
        console.print()

        rule_conditions = []
        option_num = 1

        # Option 1: Sender email (with wildcard support)
        console.print(f"{option_num}. Email remetente: [cyan]{invoice.sender}[/cyan]")
        if Confirm.ask("   Usar email do remetente?", default=True):
            # Offer wildcard option for sender
            console.print("   [dim]Pode usar padrões: *@empresa.pt, *noreply*, etc.[/dim]")
            if "@" in invoice.sender:
                domain = invoice.sender.split("@")[1]
                default_sender = f"*@{domain}"
            else:
                default_sender = invoice.sender

            sender_pattern = Prompt.ask("   Padrão do remetente", default=default_sender)
            if sender_pattern:
                if "*" in sender_pattern:
                    # Convert to regex
                    regex_pattern = sender_pattern.replace(".", r"\.").replace("*", ".*")
                    rule_conditions.append(
                        RuleCondition(
                            source=MatchSource.SENDER_EMAIL,
                            match_type=MatchType.REGEX,
                            pattern=regex_pattern,
                        )
                    )
                else:
                    rule_conditions.append(
                        RuleCondition(
                            source=MatchSource.SENDER_EMAIL,
                            match_type=MatchType.EXACT,
                            pattern=sender_pattern,
                        )
                    )
        option_num += 1

        # Option 2: Subject pattern (with enhanced input)
        console.print(
            f"\n{option_num}. Assunto: [cyan]{invoice.subject[:60]}{'...' if len(invoice.subject) > 60 else ''}[/cyan]"
        )
        if Confirm.ask("   Usar padrão no assunto?", default=False):
            condition = self._prompt_pattern_with_viewing(
                "assunto",
                invoice.subject,
                MatchSource.SUBJECT,
                invoice,
                pdf_info,
                email_body,
                default_pattern=invoice.subject[:30],
            )
            if condition:
                rule_conditions.append(condition)
        option_num += 1

        # Option 3: Body pattern (with enhanced input)
        body_preview = ""
        if email_body:
            body_preview = email_body[:80].replace("\n", " ")
            if len(email_body) > 80:
                body_preview += "..."
            console.print(f"\n{option_num}. Body do email: [cyan]{body_preview}[/cyan]")
        else:
            console.print(f"\n{option_num}. Body do email: [dim](não disponível)[/dim]")

        if email_body and Confirm.ask("   Usar padrão no body do email?", default=False):
            condition = self._prompt_pattern_with_viewing(
                "body do email",
                email_body,
                MatchSource.BODY,
                invoice,
                pdf_info,
                email_body,
            )
            if condition:
                rule_conditions.append(condition)
        option_num += 1

        # Option 4: PDF content pattern (with enhanced input)
        raw_text = pdf_info.get("raw_text", "")
        vendor = pdf_info.get("vendor")
        if raw_text:
            pdf_preview = raw_text[:80].replace("\n", " ")
            if len(raw_text) > 80:
                pdf_preview += "..."
            console.print(f"\n{option_num}. Conteúdo do PDF: [cyan]{pdf_preview}[/cyan]")
        else:
            console.print(f"\n{option_num}. Conteúdo do PDF: [dim](não disponível)[/dim]")

        if raw_text and Confirm.ask("   Usar padrão no conteúdo do PDF?", default=False):
            condition = self._prompt_pattern_with_viewing(
                "conteúdo do PDF",
                raw_text,
                MatchSource.PDF_CONTENT,
                invoice,
                pdf_info,
                email_body,
                default_pattern=vendor if vendor else "",
            )
            if condition:
                rule_conditions.append(condition)
        option_num += 1

        # Option 5: NIF from PDF (if found)
        nifs = pdf_info.get("nifs", [])
        if nifs:
            console.print(f"\n{option_num}. NIF no PDF: [cyan]{', '.join(nifs)}[/cyan]")
            if Confirm.ask("   Usar NIF do PDF?", default=False):
                rule_conditions.append(
                    RuleCondition(
                        source=MatchSource.PDF_NIF,
                        match_type=MatchType.CONTAINS,
                        pattern=nifs[0],
                    )
                )

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

            self.rules_engine.create_rule(
                name=rule_name,
                conditions=rule_conditions,
                action=RuleAction.ASSIGN_ENTITY,
                action_value=entity.id,
                description=f"Auto-criada para {name}",
                match_all=match_all,
            )
            console.print(
                f"[green]Regra '{rule_name}' criada com {len(rule_conditions)} condição(ões)![/green]"
            )
        else:
            console.print(
                "[dim]Nenhuma regra criada. Emails do remetente serão associados automaticamente.[/dim]"
            )

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
        console.print(PATTERN_HELP)
        console.print()

        rule_conditions = []

        # Option 1: Email with wildcard support
        console.print(f"1. Email: [cyan]{invoice.sender}[/cyan]")
        if Confirm.ask("   Incluir?", default=True):
            console.print("   [dim]Pode usar padrões: *@empresa.pt, *noreply*, etc.[/dim]")
            if "@" in invoice.sender:
                domain = invoice.sender.split("@")[1]
                default_sender = f"*@{domain}"
            else:
                default_sender = invoice.sender

            sender_pattern = Prompt.ask("   Padrão do remetente", default=default_sender)
            if sender_pattern:
                if "*" in sender_pattern:
                    regex_pattern = sender_pattern.replace(".", r"\.").replace("*", ".*")
                    rule_conditions.append(
                        RuleCondition(
                            source=MatchSource.SENDER_EMAIL,
                            match_type=MatchType.REGEX,
                            pattern=regex_pattern,
                        )
                    )
                else:
                    rule_conditions.append(
                        RuleCondition(
                            source=MatchSource.SENDER_EMAIL,
                            match_type=MatchType.EXACT,
                            pattern=sender_pattern,
                        )
                    )

        nifs = pdf_info.get("nifs", [])
        if nifs:
            console.print(f"\n2. NIF: [cyan]{nifs[0]}[/cyan]")
            if Confirm.ask("   Incluir?", default=False):
                rule_conditions.append(
                    RuleCondition(
                        source=MatchSource.PDF_NIF,
                        match_type=MatchType.CONTAINS,
                        pattern=nifs[0],
                    )
                )

        console.print(f"\n3. Assunto: [cyan]{invoice.subject[:50]}[/cyan]")
        if Confirm.ask("   Incluir padrão do assunto?", default=False):
            condition = self._prompt_pattern_with_viewing(
                "assunto",
                invoice.subject,
                MatchSource.SUBJECT,
                invoice,
                pdf_info,
                email_body,
                default_pattern=invoice.subject[:30],
            )
            if condition:
                rule_conditions.append(condition)

        # Option 4: Body pattern
        if email_body:
            console.print(f"\n4. Body do email: [cyan]{email_body[:50]}...[/cyan]")
            if Confirm.ask("   Incluir padrão no body?", default=False):
                condition = self._prompt_pattern_with_viewing(
                    "body do email",
                    email_body,
                    MatchSource.BODY,
                    invoice,
                    pdf_info,
                    email_body,
                )
                if condition:
                    rule_conditions.append(condition)

        # Option 5: PDF content
        raw_text = pdf_info.get("raw_text", "")
        if raw_text:
            console.print(f"\n5. Conteúdo do PDF: [cyan]{raw_text[:50]}...[/cyan]")
            if Confirm.ask("   Incluir padrão no PDF?", default=False):
                condition = self._prompt_pattern_with_viewing(
                    "conteúdo do PDF",
                    raw_text,
                    MatchSource.PDF_CONTENT,
                    invoice,
                    pdf_info,
                    email_body,
                )
                if condition:
                    rule_conditions.append(condition)

        if rule_conditions:
            rule_name = Prompt.ask("Nome da regra", default=f"Regra {entity.name}")

            # Determine AND/OR for multiple conditions
            match_all = True
            if len(rule_conditions) > 1:
                console.print("\nComo combinar as condições?")
                console.print("  1. AND - Todas têm de corresponder")
                console.print("  2. OR - Basta uma corresponder")
                combo = Prompt.ask("Escolha", choices=["1", "2"], default="1")
                match_all = combo == "1"

            self.rules_engine.create_rule(
                name=rule_name,
                conditions=rule_conditions,
                action=RuleAction.ASSIGN_ENTITY,
                action_value=entity.id,
                match_all=match_all,
            )
            console.print("[green]Regra criada![/green]")
        else:
            # Fallback to sender email mapping
            self.registry.add_sender_email_to_entity(entity.id, invoice.sender)
            console.print("[dim]Usando mapeamento simples por email[/dim]")

    def organize_invoice(
        self,
        invoice: DownloadedInvoice,
        entity: Entity,
        pdf_info: dict,
        move: bool = False,
        document_type: DocumentType = DocumentType.FATURA,
        category: Optional[str] = None,
    ) -> Path:
        """Organize invoice into the correct folder.

        Args:
            invoice: Downloaded invoice.
            entity: Entity to organize under.
            pdf_info: Extracted PDF info.
            move: If True, move file instead of copy.
                  Note: Files in temp folder are always moved regardless of this flag.
            document_type: Type of document for folder organization.
            category: Category ID for folder organization.

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

        # Get folder name based on document type
        folder_name = DocumentType.get_folder_name(document_type)

        # Build destination path: documentos/folder_name/year/category/entity_folder/
        # Example: documentos/faturas/2026/energia/EDP/
        if category:
            dest_folder = (
                settings.documentos_dir / folder_name / str(year) / category / entity.folder_name
            )
        else:
            # Fallback without category
            dest_folder = settings.documentos_dir / folder_name / str(year) / entity.folder_name

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
        is_in_temp = (
            settings.faturas_temp_dir in invoice.file_path.parents
            or invoice.file_path.parent == settings.faturas_temp_dir
        )
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
                        return (
                            ProcessedInvoice(
                                original=invoice,
                                success=True,
                                error=f"Auto-eliminado: {rule_name}",
                            ),
                            None,
                            None,
                        )
                    except Exception as e:
                        self._session_stats["errors"].append((invoice.file_name, str(e)))
                        return (
                            ProcessedInvoice(
                                original=invoice,
                                success=False,
                                error=f"Erro ao auto-eliminar: {e}",
                            ),
                            None,
                            None,
                        )
                else:  # ignore
                    self._session_stats["auto_ignored"].append((invoice.file_name, rule_name))
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error=f"Auto-ignorado: {rule_name}",
                        ),
                        None,
                        None,
                    )

            # Check for existing ignore rules
            should_ignore, action_value, rule_name = self.check_ignore_rules(
                invoice, pdf_info, email_body
            )
            if should_ignore:
                if action_value == "delete":
                    try:
                        invoice.file_path.unlink()
                        self._session_stats["auto_deleted"].append((invoice.file_name, rule_name))
                        return (
                            ProcessedInvoice(
                                original=invoice,
                                success=True,
                                error=f"Auto-eliminado por regra: {rule_name}",
                            ),
                            None,
                            None,
                        )
                    except Exception as e:
                        self._session_stats["errors"].append((invoice.file_name, str(e)))
                        return (
                            ProcessedInvoice(
                                original=invoice,
                                success=False,
                                error=f"Erro ao auto-eliminar: {e}",
                            ),
                            None,
                            None,
                        )
                else:  # ignore
                    self._session_stats["auto_ignored"].append((invoice.file_name, rule_name))
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error=f"Auto-ignorado por regra: {rule_name}",
                        ),
                        None,
                        None,
                    )

            # Initialize processing state
            reason_code = None
            reason_label = None
            document_type = DocumentType.FATURA  # Default
            category = None
            entity = None
            match_reason = None

            if interactive:
                # === Interactive Flow ===
                # Step 1: Show document summary
                if not suppress_output:
                    console.print(f"\n[yellow]?[/yellow] {invoice.file_name}")
                self.show_invoice_summary(invoice, pdf_info)

                # Step 2: Prompt for document type
                doc_type_result = self.prompt_document_type()

                # Handle ignore/delete from document type selection
                if doc_type_result == "ignore":
                    # Ask for reason and create ignore rule
                    condition, reason_code, reason_label = self._prompt_ignore_reason(
                        invoice, pdf_info, email_body, "ignore"
                    )
                    if reason_code == "":
                        # User cancelled - add to pending without reason
                        self.registry.add_to_pending(
                            {
                                "file_path": str(invoice.file_path),
                                "file_name": invoice.file_name,
                                "detected_type": "desconhecido",
                                "sender": invoice.sender,
                                "subject": invoice.subject,
                                "email_date": invoice.date.isoformat(),
                                "amount": pdf_info.get("amount"),
                                "nifs": pdf_info.get("nifs", []),
                                "pending_reason": "Cancelado pelo utilizador",
                            }
                        )
                        return (
                            ProcessedInvoice(
                                original=invoice,
                                success=False,
                                error="Cancelado - adicionado a pendentes",
                            ),
                            None,
                            None,
                        )

                    # Check if delete or ignore
                    if reason_code in DELETE_REASONS:
                        # Delete the file
                        try:
                            invoice.file_path.unlink()
                            self._session_stats["deleted"].append((invoice.file_name, reason_label))
                            return (
                                ProcessedInvoice(
                                    original=invoice,
                                    success=True,
                                    error="Ficheiro eliminado pelo utilizador",
                                ),
                                condition,
                                "delete",
                            )
                        except Exception as e:
                            self._session_stats["errors"].append((invoice.file_name, str(e)))
                            return (
                                ProcessedInvoice(
                                    original=invoice,
                                    success=False,
                                    error=f"Erro ao eliminar: {e}",
                                ),
                                None,
                                None,
                            )

                    # Ignore - add to pending
                    pending_data = {
                        "file_path": str(invoice.file_path),
                        "file_name": invoice.file_name,
                        "detected_type": "ignorado",
                        "sender": invoice.sender,
                        "subject": invoice.subject,
                        "email_date": invoice.date.isoformat(),
                        "amount": pdf_info.get("amount"),
                        "nifs": pdf_info.get("nifs", []),
                        "pending_reason": "Ignorado pelo utilizador",
                        "ignore_reason": reason_code,
                        "ignore_reason_label": reason_label,
                    }
                    self.registry.add_to_pending(pending_data)
                    self._session_stats["ignored"].append((invoice.file_name, reason_label))

                    # Track for undo
                    pending_docs = self.registry.get_pending_documents()
                    pending_id = pending_docs[-1].get("id") if pending_docs else None
                    undo_action = UndoAction(
                        file_path=invoice.file_path,
                        action_type="ignore",
                        pending_id=pending_id,
                    )
                    self._undo_stack.push(undo_action)

                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error="Ignorado pelo utilizador - adicionado a pendentes",
                        ),
                        condition,
                        "ignore",
                    )

                elif doc_type_result is None:
                    # Cancelled
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error="Cancelado pelo utilizador",
                        ),
                        None,
                        None,
                    )
                else:
                    document_type = doc_type_result

                # Step 3: Prompt for category
                category = prompt_category_selection(
                    title="Categoria do documento",
                    allow_create=True,
                    show_description=True,
                )
                if category is None:
                    # User cancelled - add to pending
                    self.registry.add_to_pending(
                        {
                            "file_path": str(invoice.file_path),
                            "file_name": invoice.file_name,
                            "detected_type": document_type.value,
                            "sender": invoice.sender,
                            "subject": invoice.subject,
                            "email_date": invoice.date.isoformat(),
                            "amount": pdf_info.get("amount"),
                            "nifs": pdf_info.get("nifs", []),
                            "pending_reason": "Categoria nao selecionada",
                        }
                    )
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error="Cancelado - adicionado a pendentes",
                        ),
                        None,
                        None,
                    )

                # Step 4: Try to find entity automatically
                entity, match_reason = self.find_entity_for_invoice(invoice, pdf_info, email_body)

                if entity:
                    console.print(f"\n[green]Entidade detectada:[/green] {entity.name}")
                    console.print(f"  [dim]{match_reason}[/dim]")
                    if not Confirm.ask("Usar esta entidade?", default=True):
                        entity = None

                # Step 5: If no entity found, prompt for selection
                if not entity:
                    entity = prompt_entity_selection(
                        title="Entidade do documento",
                        allow_create=True,
                    )

                if entity is None:
                    # User cancelled - add to pending
                    self.registry.add_to_pending(
                        {
                            "file_path": str(invoice.file_path),
                            "file_name": invoice.file_name,
                            "detected_type": document_type.value,
                            "category": category,
                            "sender": invoice.sender,
                            "subject": invoice.subject,
                            "email_date": invoice.date.isoformat(),
                            "amount": pdf_info.get("amount"),
                            "nifs": pdf_info.get("nifs", []),
                            "pending_reason": "Entidade nao selecionada",
                        }
                    )
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error="Cancelado - adicionado a pendentes",
                        ),
                        None,
                        None,
                    )

            else:
                # === Non-interactive mode ===
                # Try to find matching entity automatically
                entity, match_reason = self.find_entity_for_invoice(invoice, pdf_info, email_body)

                if entity:
                    if not suppress_output:
                        console.print(f"\n[green]OK[/green] {invoice.file_name}")
                        console.print(f"  [dim]{match_reason} -> {entity.name}[/dim]")
                else:
                    # Add to pending queue
                    self.registry.add_to_pending(
                        {
                            "file_path": str(invoice.file_path),
                            "file_name": invoice.file_name,
                            "detected_type": "fatura",
                            "sender": invoice.sender,
                            "subject": invoice.subject,
                            "email_date": invoice.date.isoformat(),
                            "amount": pdf_info.get("amount"),
                            "nifs": pdf_info.get("nifs", []),
                            "pending_reason": "Entidade desconhecida",
                        }
                    )
                    self._session_stats["ignored"].append(
                        (invoice.file_name, "Entidade desconhecida")
                    )
                    return (
                        ProcessedInvoice(
                            original=invoice,
                            success=False,
                            error="Entidade desconhecida - adicionado a pendentes",
                        ),
                        None,
                        None,
                    )

            # === Organize the file ===
            if entity:
                dest_path = self.organize_invoice(
                    invoice,
                    entity,
                    pdf_info,
                    move=move,
                    document_type=document_type,
                    category=category,
                )
                if not suppress_output:
                    console.print(f"  [green]->[/green] {dest_path.parent.name}/{dest_path.name}")

                # Determine status based on document type
                if document_type in (DocumentType.FATURA, DocumentType.NOTA_CREDITO):
                    status = DocumentStatus.POR_PAGAR
                elif document_type in (DocumentType.DESPESA, DocumentType.RECIBO):
                    status = DocumentStatus.PAGO
                else:
                    status = DocumentStatus.ARQUIVADO

                # Record in registry
                doc_record = DocumentRecord(
                    id="",
                    file_path=str(dest_path),
                    file_name=dest_path.name,
                    document_type=document_type,
                    status=status,
                    amount=(
                        float(pdf_info["amount"].replace(" EUR", "").replace(",", "."))
                        if pdf_info.get("amount")
                        else None
                    ),
                    document_date=pdf_info.get("date"),
                    emitter_entity_id=entity.id,
                )
                doc_record = self.registry.add_document(doc_record)

                self._session_stats["organized"].append(
                    (invoice.file_name, entity.name, str(dest_path))
                )

                # Track for undo
                undo_action = UndoAction(
                    file_path=invoice.file_path,
                    action_type="organize",
                    destination=dest_path,
                    entity_id=entity.id,
                    document_id=doc_record.id,
                )
                self._undo_stack.push(undo_action)

                return (
                    ProcessedInvoice(
                        original=invoice,
                        success=True,
                        destination_path=dest_path,
                        entity_name=entity.name,
                        document_type=document_type,
                        category=category,
                        amount=pdf_info.get("amount"),
                        nif=pdf_info["nifs"][0] if pdf_info.get("nifs") else None,
                    ),
                    None,
                    None,
                )
            else:
                # Should not reach here, but handle gracefully
                return (
                    ProcessedInvoice(
                        original=invoice,
                        success=False,
                        error="Erro interno - entidade nao definida",
                    ),
                    None,
                    None,
                )

        except Exception as e:
            logger.error(f"Error processing invoice {invoice.file_name}: {e}")
            self._session_stats["errors"].append((invoice.file_name, str(e)))
            return (
                ProcessedInvoice(
                    original=invoice,
                    success=False,
                    error=str(e),
                ),
                None,
                None,
            )

    def show_session_summary(self) -> None:
        """Display comprehensive summary of the processing session."""
        stats = self._session_stats

        console.print("\n[bold]━━━ Resumo da Sessão ━━━[/bold]")

        # Organized documents
        if stats["organized"]:
            console.print(f"\n[green]✓ Organizadas ({len(stats['organized'])}):[/green]")
            for filename, entity, dest in stats["organized"]:
                console.print(f"  • {filename[:40]} → {entity}")

        # Auto-ignored by rules
        if stats["auto_ignored"]:
            console.print(
                f"\n[cyan]⊘ Auto-ignoradas por regra ({len(stats['auto_ignored'])}):[/cyan]"
            )
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
            console.print(
                f"\n[red]✗ Auto-eliminadas por regra ({len(stats['auto_deleted'])}):[/red]"
            )
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
            len(stats["organized"])
            + len(stats["auto_ignored"])
            + len(stats["auto_deleted"])
            + len(stats["ignored"])
            + len(stats["deleted"])
            + len(stats["errors"])
        )
        console.print(f"\n[bold]Total processado: {total}[/bold]")

        pending_count = len(stats["ignored"]) + len(stats["auto_ignored"])
        if pending_count > 0:
            console.print("[dim]Use 'bank-extractor pendentes' para ver documentos pendentes[/dim]")

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

        # Reset session stats and undo stack
        self.reset_session_stats()
        self._undo_stack.clear()

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

                # Handle undo action - reprocess current invoice
                if action == "undo":
                    # Don't add to results, continue with same index
                    continue

                results.append(result)

                # If user created an ignore/delete rule, create it and apply to remaining
                if rule_condition and action and action != "undo":
                    # Create the rule
                    rule = self._create_ignore_rule(
                        rule_condition,
                        action,
                        rule_condition.pattern,
                    )

                    # Update the undo action with the rule ID
                    if self._undo_stack.can_undo():
                        last_action = self._undo_stack.peek()
                        if last_action and last_action.file_path == invoice.file_path:
                            last_action.rule_id = rule.id

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
