"""Banco CTT integration."""

from datetime import date
from typing import Optional

from .base import BankBase, ExtractedStatement


class BancoCTTBank(BankBase):
    """Integration for Banco CTT."""

    BANK_ID = "banco_ctt"
    BANK_NAME = "Banco CTT"
    LOGIN_URL = "https://homebanking.bancoctt.pt/"

    def login(self) -> bool:
        """Login to Banco CTT.

        Returns:
            True if login successful.
        """
        self.logger.info(f"Navegando para {self.LOGIN_URL}")
        self.page.goto(self.LOGIN_URL)

        # Get credentials
        username, password = self.get_credentials()

        # TODO: Implement actual login flow
        # This requires inspecting the Banco CTT login page
        # to identify the correct selectors
        #
        # Expected flow:
        # 1. Enter username/NIF
        # 2. Enter password
        # 3. Click login
        # 4. Wait for SMS
        # 5. Enter SMS token
        # 6. Confirm login success

        self.logger.warning("Banco CTT login ainda não implementado.")
        self.logger.info("Para implementar, é necessário analisar a página de login.")

        return False

    def extract_statements(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ExtractedStatement]:
        """Extract statements from Banco CTT.

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            List of extracted statements.
        """
        # TODO: Implement statement extraction
        # Expected flow:
        # 1. Navigate to statements/movements section
        # 2. Select account
        # 3. Set date range
        # 4. Download PDF/CSV
        # 5. Save to extratos folder

        self.logger.warning("Extração de extratos ainda não implementada.")
        return []

    def logout(self) -> None:
        """Logout from Banco CTT."""
        # TODO: Implement logout
        self.logger.info("Logout...")
