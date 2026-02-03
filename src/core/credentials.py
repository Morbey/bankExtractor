"""Secure credential management using system keyring."""

from typing import Optional

import keyring
from rich.console import Console
from rich.prompt import Prompt

console = Console()

# Service name for keyring
SERVICE_NAME = "bank-extractor"


class CredentialManager:
    """Manages credentials securely using Windows Credential Manager."""

    @staticmethod
    def _get_key(bank: str, field: str) -> str:
        """Generate a unique key for storing credentials."""
        return f"{bank}_{field}"

    @classmethod
    def get_credential(cls, bank: str, field: str) -> Optional[str]:
        """Retrieve a credential from the system keyring.

        Args:
            bank: Bank identifier (e.g., 'cgd', 'bancoCtt')
            field: Field name (e.g., 'username', 'password')

        Returns:
            The stored credential or None if not found.
        """
        key = cls._get_key(bank, field)
        return keyring.get_password(SERVICE_NAME, key)

    @classmethod
    def set_credential(cls, bank: str, field: str, value: str) -> None:
        """Store a credential in the system keyring.

        Args:
            bank: Bank identifier
            field: Field name
            value: The credential value to store
        """
        key = cls._get_key(bank, field)
        keyring.set_password(SERVICE_NAME, key, value)

    @classmethod
    def delete_credential(cls, bank: str, field: str) -> None:
        """Delete a credential from the system keyring.

        Args:
            bank: Bank identifier
            field: Field name
        """
        key = cls._get_key(bank, field)
        try:
            keyring.delete_password(SERVICE_NAME, key)
        except keyring.errors.PasswordDeleteError:
            pass  # Credential didn't exist

    @classmethod
    def has_credential(cls, bank: str, field: str) -> bool:
        """Check if a credential exists in the system keyring.

        Args:
            bank: Bank identifier
            field: Field name

        Returns:
            True if the credential exists, False otherwise.
        """
        return cls.get_credential(bank, field) is not None

    @classmethod
    def get_or_prompt(cls, bank: str, field: str, prompt_text: str, password: bool = False) -> str:
        """Get credential from keyring or prompt user.

        Args:
            bank: Bank identifier
            field: Field name
            prompt_text: Text to show when prompting
            password: If True, input will be hidden

        Returns:
            The credential value.
        """
        value = cls.get_credential(bank, field)

        if value is None:
            value = Prompt.ask(prompt_text, password=password)

            # Ask if user wants to save
            save = Prompt.ask(
                "Guardar credencial no Windows Credential Manager?",
                choices=["s", "n"],
                default="s",
            )
            if save.lower() == "s":
                cls.set_credential(bank, field, value)
                console.print("[green]Credencial guardada com sucesso.[/green]")

        return value

    @classmethod
    def prompt_sms_token(cls, bank: str) -> str:
        """Prompt user for SMS token (never saved).

        Args:
            bank: Bank identifier for display

        Returns:
            The SMS token entered by user.
        """
        console.print(f"\n[yellow]Aguardando código SMS do {bank}...[/yellow]")
        return Prompt.ask("Introduza o código SMS")

    @classmethod
    def clear_bank_credentials(cls, bank: str) -> None:
        """Clear all stored credentials for a bank.

        Args:
            bank: Bank identifier
        """
        for field in ["username", "password", "company_id"]:
            cls.delete_credential(bank, field)
        console.print(f"[green]Credenciais do {bank} removidas.[/green]")
