"""CGD Empresas bank integration."""

from datetime import date
from typing import Optional

from .base import BankBase, ExtractedStatement


class CGDEmpresasBank(BankBase):
    """Integration for Caixa Geral de Depósitos - Empresas."""

    BANK_ID = "cgd_empresas"
    BANK_NAME = "CGD Empresas"
    LOGIN_URL = "https://empresas.cgd.pt/"

    def login(self) -> bool:
        """Login to CGD Empresas.

        Returns:
            True if login successful.
        """
        self.logger.info(f"Navegando para {self.LOGIN_URL}")
        self.page.goto(self.LOGIN_URL)

        # Get credentials
        username, password = self.get_credentials()

        # TODO: Implement actual login flow
        # This requires inspecting the CGD Empresas login page
        # to identify the correct selectors
        #
        # Expected flow:
        # 1. Enter company ID
        # 2. Enter username
        # 3. Enter password
        # 4. Click login
        # 5. Wait for SMS
        # 6. Enter SMS token
        # 7. Confirm login success

        self.logger.warning("CGD Empresas login ainda não implementado.")
        self.logger.info("Para implementar, é necessário analisar a página de login.")

        return False

    def extract_statements(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ExtractedStatement]:
        """Extract statements from CGD Empresas.

        Args:
            start_date: Start of period
            end_date: End of period

        Returns:
            List of extracted statements.
        """
        # TODO: Implement statement extraction
        # Expected flow:
        # 1. Navigate to statements section
        # 2. Select account
        # 3. Set date range
        # 4. Download PDF/CSV
        # 5. Save to extratos folder

        self.logger.warning("Extração de extratos ainda não implementada.")
        return []

    def logout(self) -> None:
        """Logout from CGD Empresas."""
        # TODO: Implement logout
        self.logger.info("Logout...")
