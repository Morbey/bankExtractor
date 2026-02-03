"""Configuration and credential management commands."""

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import BANKS, console
from src.core import CredentialManager, settings


def config():
    """Mostrar configuração atual."""
    console.print(Panel.fit(
        "[bold]Configuração Atual[/bold]",
        border_style="green",
    ))

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


def credenciais(
    servico: str = typer.Argument(..., help="Serviço: cgd, ctt, email"),
    limpar: bool = typer.Option(
        False,
        "--limpar", "-l",
        help="Limpar credenciais guardadas",
    ),
):
    """Gerir credenciais guardadas."""
    servico_lower = servico.lower()

    if limpar:
        if servico_lower == "email":
            CredentialManager.delete_credential("email", "server")
            CredentialManager.delete_credential("email", "username")
            CredentialManager.delete_credential("email", "password")
            console.print("[green]Credenciais de email removidas.[/green]")
        elif servico_lower in BANKS:
            CredentialManager.clear_bank_credentials(servico_lower)
        else:
            console.print(f"[red]Serviço desconhecido: {servico}[/red]")
            raise typer.Exit(1)
    else:
        if servico_lower == "email":
            console.print("[cyan]Credenciais de email:[/cyan]")
            CredentialManager.get_or_prompt("email", "server", "Servidor IMAP")
            CredentialManager.get_or_prompt("email", "username", "Email")
            CredentialManager.get_or_prompt("email", "password", "Password", password=True)
            console.print("[green]Credenciais de email configuradas.[/green]")
        elif servico_lower in BANKS:
            console.print(f"[cyan]Credenciais para {servico_lower.upper()}:[/cyan]")
            bank_class = BANKS[servico_lower]
            bank = bank_class()
            bank.get_credentials()
            console.print("[green]Credenciais configuradas.[/green]")
        else:
            console.print(f"[red]Serviço desconhecido: {servico}[/red]")
            console.print(f"Serviços disponíveis: {', '.join(BANKS.keys())}, email")
            raise typer.Exit(1)


def versao():
    """Mostrar versão."""
    console.print(f"Bank Extractor v{__version__}")
