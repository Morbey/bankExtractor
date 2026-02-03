"""IBAN mapping manager for organizing bank documents by account."""

import json
import re
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from src.core.config import settings
from src.core.logger import get_logger

console = Console()
logger = get_logger(__name__)


class IBANManager:
    """Manages IBAN to folder name mappings."""

    # Regex pattern for Portuguese IBAN
    IBAN_PATTERN = re.compile(r"PT50\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{4}\s*\d{1}", re.IGNORECASE)

    def __init__(self, config_path: Optional[Path] = None):
        """Initialize IBAN manager.

        Args:
            config_path: Path to IBAN mappings JSON file.
        """
        self.config_path = config_path or settings.data_dir / "iban_mappings.json"
        self._mappings: dict[str, str] = {}
        self._load_mappings()

    def _load_mappings(self) -> None:
        """Load IBAN mappings from config file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._mappings = json.load(f)
                logger.debug(f"Loaded {len(self._mappings)} IBAN mappings")
            except Exception as e:
                logger.error(f"Error loading IBAN mappings: {e}")
                self._mappings = {}
        else:
            self._mappings = {}

    def _save_mappings(self) -> None:
        """Save IBAN mappings to config file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._mappings, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self._mappings)} IBAN mappings")
        except Exception as e:
            logger.error(f"Error saving IBAN mappings: {e}")

    @staticmethod
    def normalize_iban(iban: str) -> str:
        """Normalize IBAN by removing spaces and converting to uppercase.

        Args:
            iban: Raw IBAN string.

        Returns:
            Normalized IBAN (uppercase, no spaces).
        """
        return re.sub(r"\s+", "", iban).upper()

    def extract_iban_from_text(self, text: str) -> Optional[str]:
        """Extract IBAN from text content.

        Args:
            text: Text content (e.g., from PDF).

        Returns:
            Normalized IBAN if found, None otherwise.
        """
        match = self.IBAN_PATTERN.search(text)
        if match:
            return self.normalize_iban(match.group())
        return None

    def get_folder_name(self, iban: str) -> Optional[str]:
        """Get the folder name for an IBAN.

        Args:
            iban: Normalized IBAN.

        Returns:
            Folder name if mapped, None otherwise.
        """
        normalized = self.normalize_iban(iban)
        return self._mappings.get(normalized)

    def set_mapping(self, iban: str, folder_name: str) -> None:
        """Set or update an IBAN mapping.

        Args:
            iban: IBAN to map.
            folder_name: Folder name for this IBAN.
        """
        normalized = self.normalize_iban(iban)
        self._mappings[normalized] = folder_name
        self._save_mappings()
        logger.info(f"IBAN {normalized[:8]}...{normalized[-4:]} mapped to '{folder_name}'")

    def remove_mapping(self, iban: str) -> bool:
        """Remove an IBAN mapping.

        Args:
            iban: IBAN to remove.

        Returns:
            True if removed, False if not found.
        """
        normalized = self.normalize_iban(iban)
        if normalized in self._mappings:
            del self._mappings[normalized]
            self._save_mappings()
            return True
        return False

    def get_all_mappings(self) -> dict[str, str]:
        """Get all IBAN mappings.

        Returns:
            Dictionary of IBAN -> folder name mappings.
        """
        return self._mappings.copy()

    def prompt_for_mapping(self, iban: str) -> str:
        """Prompt user to identify an unknown IBAN.

        Args:
            iban: The unknown IBAN.

        Returns:
            Folder name provided by user.
        """
        masked_iban = f"{iban[:8]}...{iban[-4:]}"
        console.print(f"\n[yellow]IBAN desconhecido encontrado: {masked_iban}[/yellow]")
        console.print(f"[dim]IBAN completo: {iban}[/dim]")

        folder_name = Prompt.ask(
            "De quem é esta conta? (nome para a pasta)",
            default="conta_desconhecida"
        )

        # Sanitize folder name
        folder_name = re.sub(r'[<>:"/\\|?*]', "_", folder_name)
        folder_name = folder_name.strip().lower().replace(" ", "_")

        self.set_mapping(iban, folder_name)
        console.print(f"[green]IBAN mapeado para pasta '{folder_name}'[/green]")

        return folder_name

    def get_or_prompt_folder(self, iban: str) -> str:
        """Get folder name for IBAN, prompting if unknown.

        Args:
            iban: IBAN to look up.

        Returns:
            Folder name (existing or newly created).
        """
        normalized = self.normalize_iban(iban)
        folder = self.get_folder_name(normalized)

        if folder is None:
            folder = self.prompt_for_mapping(normalized)

        return folder


# Global instance
_iban_manager: Optional[IBANManager] = None


def get_iban_manager() -> IBANManager:
    """Get the global IBAN manager instance."""
    global _iban_manager
    if _iban_manager is None:
        _iban_manager = IBANManager()
    return _iban_manager
