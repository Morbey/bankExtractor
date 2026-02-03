"""Application configuration management."""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load .env file if it exists
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # General
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    data_dir: Path = Field(default=Path("./data"))

    # Browser automation
    headless: bool = False
    browser_timeout: int = 30000  # milliseconds

    # Email settings (for invoice download)
    invoice_days_default: int = 30  # Default number of days to look back

    # Paths derived from data_dir

    # === Legacy paths (mantidos para compatibilidade) ===
    @property
    def extratos_dir(self) -> Path:
        """Legacy: extratos bancários. Use documentos_extratos_dir para novos."""
        path = self.data_dir / "extratos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def faturas_dir(self) -> Path:
        """Legacy: faturas. Use documentos_faturas_dir para novos."""
        path = self.data_dir / "faturas"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def faturas_temp_dir(self) -> Path:
        """Temporary folder for downloaded files pending organization."""
        path = self.data_dir / "_pendentes"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # Alias para consistência
    @property
    def pendentes_dir(self) -> Path:
        """Alias for faturas_temp_dir - pending files folder."""
        return self.faturas_temp_dir

    # === Nova estrutura de documentos ===
    @property
    def documentos_dir(self) -> Path:
        """Base folder for all organized documents."""
        path = self.data_dir / "documentos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def documentos_faturas_dir(self) -> Path:
        """Folder for invoices (contas a pagar)."""
        path = self.documentos_dir / "faturas"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def documentos_despesas_dir(self) -> Path:
        """Folder for expenses/receipts (pagamentos efectuados)."""
        path = self.documentos_dir / "despesas"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def documentos_comprovativos_dir(self) -> Path:
        """Folder for transfer proofs."""
        path = self.documentos_dir / "comprovativos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def documentos_extratos_dir(self) -> Path:
        """Folder for bank statements."""
        path = self.documentos_dir / "extratos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def documentos_outros_dir(self) -> Path:
        """Folder for other documents."""
        path = self.documentos_dir / "outros"
        path.mkdir(parents=True, exist_ok=True)
        return path

    # === Databases ===
    @property
    def database_path(self) -> Path:
        return self.data_dir / "database.sqlite"

    @property
    def inbox_db_path(self) -> Path:
        """Path to inbox database."""
        inbox_dir = self.data_dir / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        return inbox_dir / "inbox.db"

    @property
    def transactions_db_path(self) -> Path:
        """Path to transactions database."""
        tx_dir = self.data_dir / "transactions"
        tx_dir.mkdir(parents=True, exist_ok=True)
        return tx_dir / "transactions.db"

    @property
    def categorias_path(self) -> Path:
        """Path to categories JSON file."""
        return self.data_dir / "categorias.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
