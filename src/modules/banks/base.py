"""Base class for bank integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from playwright.sync_api import Browser, Page, sync_playwright

from src.core import CredentialManager, get_logger, settings


@dataclass
class ExtractedStatement:
    """Represents an extracted bank statement."""

    bank: str
    account: str
    start_date: date
    end_date: date
    file_path: Path
    file_type: str  # 'pdf' or 'csv'


class BankBase(ABC):
    """Abstract base class for bank integrations.

    All bank implementations should inherit from this class
    and implement the abstract methods.
    """

    # Override these in subclasses
    BANK_ID: str = "base"
    BANK_NAME: str = "Base Bank"
    LOGIN_URL: str = ""

    def __init__(self):
        self.logger = get_logger(f"banks.{self.BANK_ID}")
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def __enter__(self):
        """Context manager entry - starts browser."""
        self._start_browser()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - closes browser."""
        self._close_browser()

    def _start_browser(self) -> None:
        """Initialize Playwright browser."""
        self.logger.info("Iniciando browser...")
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(
            headless=settings.headless,
            slow_mo=100,  # Slow down for visibility
        )
        self.page = self.browser.new_page()
        self.page.set_default_timeout(settings.browser_timeout)

    def _close_browser(self) -> None:
        """Close browser and cleanup."""
        if self.browser:
            self.browser.close()
        if hasattr(self, "_playwright"):
            self._playwright.stop()
        self.logger.info("Browser fechado.")

    def get_credentials(self) -> tuple[str, str]:
        """Get username and password for this bank.

        Returns:
            Tuple of (username, password)
        """
        username = CredentialManager.get_or_prompt(
            self.BANK_ID,
            "username",
            f"Username {self.BANK_NAME}",
            password=False,
        )
        password = CredentialManager.get_or_prompt(
            self.BANK_ID,
            "password",
            f"Password {self.BANK_NAME}",
            password=True,
        )
        return username, password

    def get_sms_token(self) -> str:
        """Prompt user for SMS token.

        Returns:
            The SMS token entered by user.
        """
        return CredentialManager.prompt_sms_token(self.BANK_NAME)

    @abstractmethod
    def login(self) -> bool:
        """Perform login to the bank website.

        Should handle:
        1. Navigate to login page
        2. Enter credentials
        3. Handle SMS/2FA token
        4. Verify login success

        Returns:
            True if login successful, False otherwise.
        """
        pass

    @abstractmethod
    def extract_statements(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ExtractedStatement]:
        """Extract bank statements for the given period.

        Args:
            start_date: Start of period (default: beginning of current month)
            end_date: End of period (default: today)

        Returns:
            List of extracted statement information.
        """
        pass

    @abstractmethod
    def logout(self) -> None:
        """Logout from the bank website."""
        pass

    def run(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ExtractedStatement]:
        """Execute full extraction workflow.

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            List of extracted statements.
        """
        self.logger.info(f"Iniciando extração {self.BANK_NAME}...")

        if not self.login():
            self.logger.error("Falha no login.")
            return []

        try:
            statements = self.extract_statements(start_date, end_date)
            self.logger.info(f"Extraídos {len(statements)} extratos.")
            return statements
        finally:
            self.logout()
