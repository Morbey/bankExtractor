"""Configuration and credential management commands."""

from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import BANKS, console
from src.core import CredentialManager, settings

# Email providers supported
EMAIL_PROVIDERS = ["gmail", "hotmail"]

# Common account names to check
ACCOUNT_NAMES = ["pessoal", "empresa", "trabalho", "personal", "work"]


def config():
    """Mostrar configuração atual."""
    console.print(
        Panel.fit(
            "[bold]Configuração Atual[/bold]",
            border_style="green",
        )
    )

    table = Table()
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Data directory", str(settings.data_dir.absolute()))
    table.add_row("Extratos directory", str(settings.extratos_dir.absolute()))
    table.add_row("Faturas directory", str(settings.faturas_dir.absolute()))
    table.add_row("Database", str(settings.database_path.absolute()))
    table.add_row("Headless mode", str(settings.headless))
    table.add_row("Log level", settings.log_level)

    console.print(table)


def _get_all_credentials() -> tuple[list[tuple[str, str]], list[tuple[str, str, str]]]:
    """Get all configured credentials.

    Returns:
        Tuple of (bank_credentials, email_credentials)
        - bank_credentials: list of (bank_id, username)
        - email_credentials: list of (provider, account_name, email)
    """
    banks = []
    emails = []

    # Check banks
    for bank_id in BANKS.keys():
        username = CredentialManager.get_credential(bank_id, "username")
        if username:
            banks.append((bank_id, username))

    # Check email providers
    for provider in EMAIL_PROVIDERS:
        # Check default account
        email = CredentialManager.get_credential(provider, "email")
        if email:
            emails.append((provider, None, email))

        # Check named accounts
        for account in ACCOUNT_NAMES:
            key = f"{provider}_{account}"
            email = CredentialManager.get_credential(key, "email")
            if email:
                emails.append((provider, account, email))

    return banks, emails


def credenciais(
    servico: Optional[str] = typer.Argument(
        None,
        help="Serviço: cgd, ctt, gmail, hotmail (sem argumento lista todas)",
    ),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta de email (ex: pessoal, empresa)",
    ),
    apagar: bool = typer.Option(
        False,
        "--apagar",
        help="Apagar credenciais (requer confirmação)",
    ),
    confirmar: bool = typer.Option(
        False,
        "--sim",
        "-y",
        help="Confirmar eliminação sem perguntar",
    ),
):
    """Gerir credenciais guardadas (bancos e email).

    Sem argumentos: lista todas as credenciais configuradas.
    Com serviço: configura ou apaga credenciais.

    Exemplos:
        config credenciais                          # Lista todas
        config credenciais cgd                      # Configura banco CGD
        config credenciais gmail --conta pessoal    # Configura Gmail
        config credenciais gmail --apagar           # Apaga Gmail
    """
    # No service = list all credentials
    if servico is None:
        banks, emails = _get_all_credentials()

        if not banks and not emails:
            console.print("[yellow]Nenhuma credencial configurada.[/yellow]")
            console.print("\n[dim]Para configurar:[/dim]")
            console.print("  config credenciais cgd                      # Banco CGD")
            console.print("  config credenciais gmail --conta pessoal    # Email Gmail")
            return

        console.print("\n[bold cyan]Credenciais Configuradas[/bold cyan]\n")

        if banks:
            console.print("[bold]Bancos:[/bold]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("Banco", style="cyan")
            table.add_column("Utilizador", style="white")
            for bank_id, username in banks:
                table.add_row(bank_id.upper(), username)
            console.print(table)
            console.print()

        if emails:
            console.print("[bold]Email:[/bold]")
            table = Table(show_header=True, header_style="bold")
            table.add_column("Provider", style="cyan")
            table.add_column("Conta", style="green")
            table.add_column("Email", style="white")
            for provider, account, email in emails:
                table.add_row(provider.upper(), account or "(default)", email)
            console.print(table)

        console.print(f"\n[dim]Total: {len(banks)} banco(s), {len(emails)} conta(s) email[/dim]")
        console.print("[dim]Para apagar: config credenciais <serviço> --apagar[/dim]")
        return

    servico_lower = servico.lower()

    # Determine if it's a bank or email provider
    is_bank = servico_lower in BANKS
    is_email = servico_lower in EMAIL_PROVIDERS

    if not is_bank and not is_email:
        console.print(f"[red]Serviço desconhecido: {servico}[/red]")
        console.print(f"Bancos: {', '.join(BANKS.keys())}")
        console.print(f"Email: {', '.join(EMAIL_PROVIDERS)}")
        raise typer.Exit(1)

    # Handle bank credentials
    if is_bank:
        if conta:
            console.print("[yellow]Opção --conta não aplicável a bancos.[/yellow]")

        if apagar:
            username = CredentialManager.get_credential(servico_lower, "username")
            if not username:
                console.print(f"[yellow]Não existem credenciais para {servico.upper()}.[/yellow]")
                return

            console.print("\n[bold red]APAGAR credenciais de:[/bold red]")
            console.print(f"  Banco: {servico.upper()}")
            console.print(f"  Utilizador: {username}")

            if not confirmar:
                from rich.prompt import Confirm

                if not Confirm.ask("\n[red]Tem a certeza?[/red]", default=False):
                    console.print("[dim]Operação cancelada.[/dim]")
                    return

            CredentialManager.clear_bank_credentials(servico_lower)
        else:
            console.print(f"[cyan]Configurar credenciais {servico.upper()}:[/cyan]")
            bank_class = BANKS[servico_lower]
            bank = bank_class()
            bank.get_credentials()
            console.print("[green]Credenciais configuradas.[/green]")
        return

    # Handle email credentials
    credential_key = f"{servico_lower}_{conta}" if conta else servico_lower
    display_name = f"{servico.upper()} ({conta})" if conta else servico.upper()

    if apagar:
        email = CredentialManager.get_credential(credential_key, "email")
        if not email:
            console.print(f"[yellow]Não existem credenciais para {display_name}.[/yellow]")
            return

        console.print("\n[bold red]APAGAR credenciais de:[/bold red]")
        console.print(f"  Provider: {servico.upper()}")
        console.print(f"  Conta: {conta or '(default)'}")
        console.print(f"  Email: {email}")

        if not confirmar:
            from rich.prompt import Confirm

            if not Confirm.ask("\n[red]Tem a certeza?[/red]", default=False):
                console.print("[dim]Operação cancelada.[/dim]")
                return

        CredentialManager.delete_credential(credential_key, "email")
        CredentialManager.delete_credential(credential_key, "password")
        console.print(f"\n[green]Credenciais de {display_name} apagadas.[/green]")
    else:
        console.print(f"\n[bold cyan]Configurar credenciais {display_name}[/bold cyan]")

        if servico_lower == "gmail":
            console.print(
                "[yellow]Nota: O Gmail requer uma App Password.[/yellow]\n"
                "1. Ative a verificação em 2 passos\n"
                "2. Crie App Password em: https://myaccount.google.com/apppasswords\n"
            )

        CredentialManager.get_or_prompt(
            credential_key,
            "email",
            f"Email {display_name}",
            password=False,
        )
        CredentialManager.get_or_prompt(
            credential_key,
            "password",
            f"Password/App Password {display_name}",
            password=True,
        )
        console.print(f"[green]Credenciais configuradas para {display_name}[/green]")


def versao():
    """Mostrar versão."""
    console.print(f"Bank Extractor v{__version__}")
