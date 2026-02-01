"""Bank Extractor CLI - Main entry point."""

from datetime import date, datetime
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.core import CredentialManager, settings
from src.modules.banks import BancoCTTBank, CGDEmpresasBank

app = typer.Typer(
    name="bank-extractor",
    help="Extrator de extratos bancários e gestor financeiro pessoal.",
    no_args_is_help=True,
)
console = Console()

# Bank registry
BANKS = {
    "cgd": CGDEmpresasBank,
    "ctt": BancoCTTBank,
}


def parse_date(date_str: str) -> date:
    """Parse date string in DD-MM-YYYY format."""
    return datetime.strptime(date_str, "%d-%m-%Y").date()


@app.command()
def extrair(
    banco: str = typer.Argument(
        ...,
        help="Banco a extrair: cgd, ctt, ou 'todos'",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio", "-i",
        help="Data início (DD-MM-YYYY). Default: início do mês.",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim", "-f",
        help="Data fim (DD-MM-YYYY). Default: hoje.",
    ),
):
    """Extrair extratos bancários."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Extração de extratos bancários",
        border_style="blue",
    ))

    # Parse dates
    start_date = parse_date(inicio) if inicio else None
    end_date = parse_date(fim) if fim else None

    # Determine which banks to process
    if banco.lower() == "todos":
        banks_to_process = list(BANKS.keys())
    elif banco.lower() in BANKS:
        banks_to_process = [banco.lower()]
    else:
        console.print(f"[red]Banco desconhecido: {banco}[/red]")
        console.print(f"Bancos disponíveis: {', '.join(BANKS.keys())}, todos")
        raise typer.Exit(1)

    # Process each bank
    all_statements = []
    for bank_id in banks_to_process:
        console.print(f"\n[bold cyan]Processando {bank_id.upper()}...[/bold cyan]")
        bank_class = BANKS[bank_id]

        with bank_class() as bank:
            statements = bank.run(start_date, end_date)
            all_statements.extend(statements)

    # Summary
    if all_statements:
        table = Table(title="Extratos Extraídos")
        table.add_column("Banco", style="cyan")
        table.add_column("Conta", style="green")
        table.add_column("Período", style="yellow")
        table.add_column("Ficheiro", style="white")

        for stmt in all_statements:
            table.add_row(
                stmt.bank,
                stmt.account,
                f"{stmt.start_date} - {stmt.end_date}",
                str(stmt.file_path.name),
            )

        console.print(table)
    else:
        console.print("\n[yellow]Nenhum extrato extraído.[/yellow]")


@app.command()
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


@app.command()
def credenciais(
    banco: str = typer.Argument(..., help="Banco: cgd, ctt"),
    limpar: bool = typer.Option(
        False,
        "--limpar", "-l",
        help="Limpar credenciais guardadas",
    ),
):
    """Gerir credenciais guardadas."""
    if banco.lower() not in BANKS:
        console.print(f"[red]Banco desconhecido: {banco}[/red]")
        raise typer.Exit(1)

    if limpar:
        CredentialManager.clear_bank_credentials(banco.lower())
    else:
        console.print(f"[cyan]Credenciais para {banco.upper()}:[/cyan]")
        # Just trigger the prompt to set credentials
        bank_class = BANKS[banco.lower()]
        bank = bank_class()
        bank.get_credentials()
        console.print("[green]Credenciais configuradas.[/green]")


@app.command()
def versao():
    """Mostrar versão."""
    console.print(f"Bank Extractor v{__version__}")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
