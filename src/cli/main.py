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
from src.modules.invoices import EMAIL_PROVIDERS, EmailFilter, InvoiceDownloader

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


@app.command()
def faturas(
    provider: str = typer.Argument(
        "todos",
        help="Provider de email: gmail, hotmail, ou 'todos'",
    ),
    dias: int = typer.Option(
        settings.invoice_days_default,
        "--dias", "-d",
        help="Número de dias a pesquisar (padrão: 30)",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio", "-i",
        help="Data início (DD-MM-YYYY). Sobrepõe --dias.",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim", "-f",
        help="Data fim (DD-MM-YYYY). Default: hoje.",
    ),
    config_creds: bool = typer.Option(
        False,
        "--config", "-c",
        help="Configurar credenciais de email",
    ),
):
    """Descarregar faturas do email."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Download de faturas por email",
        border_style="blue",
    ))

    # Handle credential configuration
    if config_creds:
        _configure_email_credentials(provider)
        return

    # Determine which providers to use
    if provider.lower() == "todos":
        providers_to_process = list(EMAIL_PROVIDERS.keys())
    elif provider.lower() in EMAIL_PROVIDERS:
        providers_to_process = [provider.lower()]
    else:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        console.print(f"Providers disponíveis: {', '.join(EMAIL_PROVIDERS.keys())}, todos")
        raise typer.Exit(1)

    # Parse dates or use days
    if inicio:
        start_date = parse_date(inicio)
    else:
        from datetime import timedelta
        start_date = date.today() - timedelta(days=dias)

    end_date = parse_date(fim) if fim else date.today()

    console.print(f"\n[cyan]Período: {start_date.strftime('%d-%m-%Y')} a {end_date.strftime('%d-%m-%Y')}[/cyan]")

    # Create downloader and process
    downloader = InvoiceDownloader()
    all_invoices = []

    for prov_id in providers_to_process:
        console.print(f"\n[bold cyan]Processando {prov_id.upper()}...[/bold cyan]")
        try:
            email_filter = EmailFilter(
                start_date=start_date,
                end_date=end_date,
            )
            invoices = downloader.download_from(prov_id, email_filter)
            all_invoices.extend(invoices)
        except Exception as e:
            console.print(f"[red]Erro: {e}[/red]")

    # Summary
    if all_invoices:
        table = Table(title="Faturas Descarregadas")
        table.add_column("Provider", style="cyan")
        table.add_column("Remetente", style="green", max_width=30)
        table.add_column("Data", style="yellow")
        table.add_column("Ficheiro", style="white")
        table.add_column("Tamanho", style="magenta", justify="right")

        for inv in all_invoices:
            size_kb = inv.file_size / 1024
            table.add_row(
                inv.provider,
                inv.sender[:30] + "..." if len(inv.sender) > 30 else inv.sender,
                inv.date.strftime("%d-%m-%Y"),
                inv.file_path.name,
                f"{size_kb:.1f} KB",
            )

        console.print(table)
        console.print(f"\n[green]Total: {len(all_invoices)} faturas descarregadas[/green]")
        console.print(f"[dim]Guardadas em: {settings.faturas_dir}[/dim]")
    else:
        console.print("\n[yellow]Nenhuma fatura encontrada.[/yellow]")


def _configure_email_credentials(provider: str) -> None:
    """Configure email credentials for a provider."""
    if provider.lower() == "todos":
        providers = list(EMAIL_PROVIDERS.keys())
    elif provider.lower() in EMAIL_PROVIDERS:
        providers = [provider.lower()]
    else:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        raise typer.Exit(1)

    for prov_id in providers:
        console.print(f"\n[bold cyan]Configurar credenciais {prov_id.upper()}[/bold cyan]")

        if prov_id == "gmail":
            console.print(
                "[yellow]Nota: O Gmail requer uma App Password.[/yellow]\n"
                "1. Ative a verificação em 2 passos\n"
                "2. Vá a https://myaccount.google.com/apppasswords\n"
                "3. Gere uma App Password para 'Mail'\n"
            )

        # Prompt for credentials
        email_addr = CredentialManager.get_or_prompt(
            prov_id,
            "email",
            f"Email {prov_id}",
            password=False,
        )
        CredentialManager.get_or_prompt(
            prov_id,
            "password",
            f"Password/App Password {prov_id}",
            password=True,
        )
        console.print(f"[green]Credenciais configuradas para {email_addr}[/green]")


@app.command()
def faturas_limpar(
    provider: str = typer.Argument(..., help="Provider de email: gmail, hotmail"),
):
    """Limpar credenciais de email guardadas."""
    if provider.lower() not in EMAIL_PROVIDERS:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        raise typer.Exit(1)

    CredentialManager.delete_credential(provider.lower(), "email")
    CredentialManager.delete_credential(provider.lower(), "password")
    console.print(f"[green]Credenciais do {provider} removidas.[/green]")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
