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

    # Paths derived from data_dir
    @property
    def extratos_dir(self) -> Path:
        path = self.data_dir / "extratos"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def faturas_dir(self) -> Path:
        path = self.data_dir / "faturas"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def database_path(self) -> Path:
        return self.data_dir / "database.sqlite"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
