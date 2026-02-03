"""Transfer document manager - organizes bank transfers by direction and counterparty."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src.core.config import settings
from src.core.logger import get_logger

console = Console()
logger = get_logger(__name__)


@dataclass
class TransferInfo:
    """Information extracted from a bank transfer document."""

    iban_origem: Optional[str] = None
    iban_destino: Optional[str] = None
    cliente: Optional[str] = None
    beneficiario: Optional[str] = None
    montante: Optional[str] = None
    data_hora: Optional[str] = None
    tipo_operacao: Optional[str] = None
    raw_text: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        """Check if transfer has minimum required info."""
        return bool(self.iban_origem and self.iban_destino)


class TransferManager:
    """Manages bank transfer documents organization."""

    # Regex patterns - Portuguese IBAN: PT50 + 21 digits = 25 chars total
    IBAN_PATTERN = re.compile(r"PT50[\s\d]{21,30}", re.IGNORECASE)
    DATE_PATTERN = re.compile(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})")
    AMOUNT_PATTERN = re.compile(r"Montante\s*([\d.,]+)\s*EUR", re.IGNORECASE)

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize transfer manager.

        Args:
            config_path: Path to configuration JSON file.
        """
        self.config_path = config_path or settings.data_dir / "transfer_config.json"
        self._my_ibans: set[str] = set()
        self._iban_mappings: dict[str, str] = {}  # IBAN -> folder name
        self._beneficiary_mappings: dict[str, str] = {}  # Beneficiary name -> folder name
        self._load_config()

    def _load_config(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._my_ibans = set(data.get("my_ibans", []))
                    self._iban_mappings = data.get("iban_mappings", {})
                    self._beneficiary_mappings = data.get("beneficiary_mappings", {})
                logger.debug(f"Loaded transfer config: {len(self._my_ibans)} IBANs, {len(self._iban_mappings)} mappings")
            except Exception as e:
                logger.error(f"Error loading transfer config: {e}")

    def _save_config(self) -> None:
        """Save configuration to file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "my_ibans": list(self._my_ibans),
                "iban_mappings": self._iban_mappings,
                "beneficiary_mappings": self._beneficiary_mappings,
            }
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug("Saved transfer config")
        except Exception as e:
            logger.error(f"Error saving transfer config: {e}")

    @staticmethod
    def normalize_iban(iban: str) -> str:
        """Normalize IBAN by removing spaces."""
        return re.sub(r"\s+", "", iban).upper()

    def add_my_iban(self, iban: str) -> None:
        """Add an IBAN as belonging to me.

        Args:
            iban: IBAN to add.
        """
        normalized = self.normalize_iban(iban)
        self._my_ibans.add(normalized)
        self._save_config()
        logger.info(f"Added my IBAN: {normalized[:8]}...{normalized[-4:]}")

    def remove_my_iban(self, iban: str) -> bool:
        """Remove an IBAN from my IBANs.

        Args:
            iban: IBAN to remove.

        Returns:
            True if removed, False if not found.
        """
        normalized = self.normalize_iban(iban)
        if normalized in self._my_ibans:
            self._my_ibans.discard(normalized)
            self._save_config()
            return True
        return False

    def is_my_iban(self, iban: str) -> bool:
        """Check if IBAN belongs to me.

        Args:
            iban: IBAN to check.

        Returns:
            True if it's my IBAN.
        """
        return self.normalize_iban(iban) in self._my_ibans

    def set_iban_mapping(self, iban: str, folder_name: str) -> None:
        """Map an IBAN to a folder name.

        Args:
            iban: IBAN to map.
            folder_name: Folder name for this IBAN.
        """
        normalized = self.normalize_iban(iban)
        self._iban_mappings[normalized] = folder_name
        self._save_config()
        logger.info(f"IBAN {normalized[:8]}...{normalized[-4:]} -> '{folder_name}'")

    def set_beneficiary_mapping(self, beneficiary: str, folder_name: str) -> None:
        """Map a beneficiary name to a folder name.

        Args:
            beneficiary: Beneficiary name.
            folder_name: Folder name.
        """
        normalized = beneficiary.strip().upper()
        self._beneficiary_mappings[normalized] = folder_name
        self._save_config()
        logger.info(f"Beneficiary '{beneficiary}' -> '{folder_name}'")

    def get_folder_name(self, iban: Optional[str] = None, beneficiary: Optional[str] = None) -> Optional[str]:
        """Get folder name for IBAN or beneficiary.

        Args:
            iban: IBAN to look up.
            beneficiary: Beneficiary name to look up.

        Returns:
            Folder name if found, None otherwise.
        """
        # Try IBAN first
        if iban:
            normalized_iban = self.normalize_iban(iban)
            if normalized_iban in self._iban_mappings:
                return self._iban_mappings[normalized_iban]

        # Try beneficiary
        if beneficiary:
            normalized_ben = beneficiary.strip().upper()
            if normalized_ben in self._beneficiary_mappings:
                return self._beneficiary_mappings[normalized_ben]

        return None

    def extract_transfer_info(self, text: str) -> TransferInfo:
        """Extract transfer information from PDF text.

        Args:
            text: Raw text from PDF.

        Returns:
            TransferInfo with extracted data.
        """
        info = TransferInfo(raw_text=text)

        # Extract IBANs
        ibans = self.IBAN_PATTERN.findall(text)
        ibans = [self.normalize_iban(iban) for iban in ibans]

        if len(ibans) >= 1:
            info.iban_origem = ibans[0]
        if len(ibans) >= 2:
            info.iban_destino = ibans[1]

        # Extract date/time
        date_match = self.DATE_PATTERN.search(text)
        if date_match:
            info.data_hora = date_match.group(1)

        # Extract amount
        amount_match = self.AMOUNT_PATTERN.search(text)
        if amount_match:
            info.montante = amount_match.group(1) + " EUR"

        # Extract client/beneficiary names (heuristic based on common patterns)
        lines = text.split("\n")
        for i, line in enumerate(lines):
            line_lower = line.lower()

            # Look for client name
            if "cliente" in line_lower:
                # Check this line and next few for a name
                for j in range(i, min(i + 3, len(lines))):
                    # Look for typical name patterns (capitalized words)
                    potential_name = lines[j].strip()
                    if re.match(r"^[A-Z][a-z]+ [A-Z]", potential_name):
                        info.cliente = potential_name
                        break

            # Look for beneficiary
            if "benefici" in line_lower:
                for j in range(i, min(i + 3, len(lines))):
                    potential_name = lines[j].strip()
                    # Look for company names (LDA, SA, etc.) or capitalized names
                    if re.search(r"(LDA|SA|UNIPESSOAL|S\.A\.|S\.A)", potential_name, re.IGNORECASE):
                        info.beneficiario = potential_name
                        break
                    elif re.match(r"^[A-Z][A-Z\s]+$", potential_name) and len(potential_name) > 5:
                        info.beneficiario = potential_name
                        break

        # Fallback: extract from known patterns in the text
        if not info.cliente:
            match = re.search(r"Cliente\s+([A-Z][a-zA-Z\s]+?)(?=\s*Conta)", text)
            if match:
                info.cliente = match.group(1).strip()

        if not info.beneficiario:
            match = re.search(r"Benefici.rio\s+([A-Z][A-Z\s]+?)(?=\s*Conta)", text)
            if match:
                info.beneficiario = match.group(1).strip()

        # Clean up extracted names (remove label prefixes)
        if info.cliente:
            info.cliente = re.sub(r"^Cliente\s+", "", info.cliente, flags=re.IGNORECASE).strip()
        if info.beneficiario:
            info.beneficiario = re.sub(r"^Benefici.rio\s+", "", info.beneficiario, flags=re.IGNORECASE).strip()

        return info

    def determine_transfer_direction(self, info: TransferInfo) -> Optional[str]:
        """Determine if transfer is outgoing (pagamento) or incoming (recebimento).

        Args:
            info: Transfer information.

        Returns:
            'pagamento' if outgoing, 'recebimento' if incoming, None if unknown.
        """
        if not info.is_valid:
            return None

        origem_is_mine = self.is_my_iban(info.iban_origem)
        destino_is_mine = self.is_my_iban(info.iban_destino)

        if origem_is_mine and not destino_is_mine:
            return "pagamento"
        elif destino_is_mine and not origem_is_mine:
            return "recebimento"
        elif origem_is_mine and destino_is_mine:
            return "interno"  # Transfer between own accounts
        else:
            return None  # Unknown - neither IBAN is registered

    def get_destination_folder(
        self,
        info: TransferInfo,
        base_dir: Optional[Path] = None,
    ) -> tuple[Optional[Path], Optional[str]]:
        """Get the destination folder for a transfer document.

        Args:
            info: Transfer information.
            base_dir: Base directory (default: settings.data_dir).

        Returns:
            Tuple of (folder path, counterparty folder name) or (None, None) if unknown.
        """
        base = base_dir or settings.data_dir
        direction = self.determine_transfer_direction(info)

        if direction is None:
            return None, None

        if direction == "pagamento":
            # Outgoing - use destination IBAN/beneficiary
            counterparty_folder = self.get_folder_name(
                iban=info.iban_destino,
                beneficiary=info.beneficiario
            )
            if counterparty_folder:
                folder = base / "pagamentos" / "comprovativos" / counterparty_folder
                return folder, counterparty_folder

        elif direction == "recebimento":
            # Incoming - use source IBAN/client
            counterparty_folder = self.get_folder_name(
                iban=info.iban_origem,
                beneficiary=info.cliente
            )
            if counterparty_folder:
                folder = base / "recebimentos" / "comprovativos" / counterparty_folder
                return folder, counterparty_folder

        elif direction == "interno":
            # Internal transfer between own accounts
            folder = base / "transferencias_internas"
            return folder, "interno"

        return None, None

    def prompt_for_mapping(
        self,
        info: TransferInfo,
        direction: str,
    ) -> str:
        """Prompt user to create mapping for unknown counterparty.

        Args:
            info: Transfer information.
            direction: 'pagamento' or 'recebimento'.

        Returns:
            Folder name provided by user.
        """
        console.print("\n[yellow]Contraparte desconhecida encontrada![/yellow]")

        if direction == "pagamento":
            iban = info.iban_destino
            name = info.beneficiario
            console.print(f"[cyan]Tipo:[/cyan] Pagamento (saída)")
            console.print(f"[cyan]IBAN Destino:[/cyan] {iban}")
            console.print(f"[cyan]Beneficiário:[/cyan] {name or 'N/A'}")
        else:
            iban = info.iban_origem
            name = info.cliente
            console.print(f"[cyan]Tipo:[/cyan] Recebimento (entrada)")
            console.print(f"[cyan]IBAN Origem:[/cyan] {iban}")
            console.print(f"[cyan]Cliente:[/cyan] {name or 'N/A'}")

        folder_name = Prompt.ask(
            "\nQual o nome para a pasta desta entidade?",
            default=name.replace(" ", "_")[:30] if name else "desconhecido"
        )

        # Sanitize folder name
        folder_name = re.sub(r'[<>:"/\\|?*]', "_", folder_name)
        folder_name = folder_name.strip()

        # Save mapping
        if iban:
            self.set_iban_mapping(iban, folder_name)
        if name:
            self.set_beneficiary_mapping(name, folder_name)

        console.print(f"[green]Mapeamento guardado: '{folder_name}'[/green]")
        return folder_name

    def prompt_for_my_iban(self, iban: str) -> bool:
        """Ask user if an IBAN belongs to them.

        Args:
            iban: IBAN to check.

        Returns:
            True if user confirms it's theirs.
        """
        masked = f"{iban[:8]}...{iban[-4:]}"
        console.print(f"\n[yellow]IBAN não reconhecido: {masked}[/yellow]")
        console.print(f"[dim]IBAN completo: {iban}[/dim]")

        is_mine = Confirm.ask("Este IBAN pertence-te?", default=False)

        if is_mine:
            self.add_my_iban(iban)
            console.print("[green]IBAN adicionado à tua lista.[/green]")

        return is_mine

    def show_summary(self, info: TransferInfo) -> None:
        """Display a summary of the transfer.

        Args:
            info: Transfer information.
        """
        direction = self.determine_transfer_direction(info)

        table = Table(title="Resumo da Transferência", show_header=False)
        table.add_column("Campo", style="cyan")
        table.add_column("Valor", style="white")

        if direction:
            direction_display = {
                "pagamento": "[red]PAGAMENTO (Saída)[/red]",
                "recebimento": "[green]RECEBIMENTO (Entrada)[/green]",
                "interno": "[yellow]TRANSFERÊNCIA INTERNA[/yellow]",
            }.get(direction, direction)
            table.add_row("Tipo", direction_display)

        table.add_row("Data/Hora", info.data_hora or "N/A")
        table.add_row("Montante", f"[bold]{info.montante or 'N/A'}[/bold]")
        table.add_row("", "")
        table.add_row("Cliente", info.cliente or "N/A")
        table.add_row("IBAN Origem", info.iban_origem or "N/A")
        table.add_row("", "")
        table.add_row("Beneficiário", info.beneficiario or "N/A")
        table.add_row("IBAN Destino", info.iban_destino or "N/A")

        console.print(table)


# Global instance
_transfer_manager: Optional[TransferManager] = None


def get_transfer_manager() -> TransferManager:
    """Get the global transfer manager instance."""
    global _transfer_manager
    if _transfer_manager is None:
        _transfer_manager = TransferManager()
    return _transfer_manager
