"""Bank Extractor CLI - Main entry point."""

from datetime import date, datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src import __version__
from src.core import CredentialManager, settings
from src.core.categories import InvoiceCategory, InvoiceCategorizer
from src.modules.banks import BancoCTTBank, CGDEmpresasBank
from src.modules.invoices import EmailClient, PDFInvoiceParser
from src.modules.organizer import InvoiceDatabase, InvoiceOrganizer
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


# ============================================================================
# EXTRATOS (Bank Statements)
# ============================================================================


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


# ============================================================================
# FATURAS (Invoices)
# ============================================================================


@app.command()
def faturas(
    acao: str = typer.Argument(
        ...,
        help="Ação: email, organizar, listar, stats",
    ),
    pasta: Optional[str] = typer.Option(
        None,
        "--pasta", "-p",
        help="Pasta de origem para organizar ficheiros.",
    ),
    mover: bool = typer.Option(
        False,
        "--mover", "-m",
        help="Mover ficheiros em vez de copiar.",
    ),
    categoria: Optional[str] = typer.Option(
        None,
        "--categoria", "-c",
        help="Filtrar por categoria.",
    ),
):
    """Gerir faturas - download de email e organização."""
    console.print(Panel.fit(
        f"[bold green]Bank Extractor v{__version__}[/bold green]\n"
        "Gestão de Faturas",
        border_style="green",
    ))

    acao_lower = acao.lower()

    if acao_lower == "email":
        _faturas_email()
    elif acao_lower == "organizar":
        _faturas_organizar(pasta, mover)
    elif acao_lower == "listar":
        _faturas_listar(categoria)
    elif acao_lower == "stats":
        _faturas_stats()
    elif acao_lower == "categorias":
        _faturas_categorias()
    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações disponíveis: email, organizar, listar, stats, categorias")
        raise typer.Exit(1)


def _faturas_email():
    """Download invoices from email."""
    console.print("\n[bold cyan]Download de faturas por email[/bold cyan]\n")

    # Get email credentials
    server = CredentialManager.get_or_prompt("email", "server", "Servidor IMAP (ex: imap.gmail.com)")
    username = CredentialManager.get_or_prompt("email", "username", "Email")
    password = CredentialManager.get_or_prompt("email", "password", "Password", password=True)

    # Date range
    console.print("\n[dim]Deixe em branco para pesquisar os últimos 30 dias[/dim]")
    inicio_str = Prompt.ask("Data início (DD-MM-YYYY)", default="")
    fim_str = Prompt.ask("Data fim (DD-MM-YYYY)", default="")

    start_date = parse_date(inicio_str) if inicio_str else None
    end_date = parse_date(fim_str) if fim_str else None

    # If no dates, default to last 30 days
    if not start_date:
        from datetime import timedelta
        start_date = date.today() - timedelta(days=30)

    console.print(f"\n[dim]Pesquisando desde {start_date}...[/dim]\n")

    try:
        with EmailClient(server, username, password) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Pesquisando emails...", total=None)

                invoices = client.search_invoices(
                    since_date=start_date,
                    before_date=end_date,
                )

                progress.update(task, description=f"Encontradas {len(invoices)} faturas")

            if not invoices:
                console.print("[yellow]Nenhuma fatura encontrada.[/yellow]")
                return

            # Display found invoices
            table = Table(title="Faturas Encontradas")
            table.add_column("#", style="dim")
            table.add_column("Data", style="cyan")
            table.add_column("Remetente", style="green")
            table.add_column("Assunto", style="white", max_width=40)
            table.add_column("PDFs", style="yellow")

            for i, inv in enumerate(invoices, 1):
                table.add_row(
                    str(i),
                    inv.date.strftime("%Y-%m-%d"),
                    inv.sender[:30] + "..." if len(inv.sender) > 30 else inv.sender,
                    inv.subject[:40] + "..." if len(inv.subject) > 40 else inv.subject,
                    str(len(inv.pdf_attachments)),
                )

            console.print(table)

            # Confirm download
            if not Confirm.ask("\nDescarregar e organizar estas faturas?"):
                return

            # Download and organize
            organizer = InvoiceOrganizer()
            db = InvoiceDatabase()
            downloaded = 0

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processando...", total=len(invoices))

                for inv in invoices:
                    # Save attachments to temp location
                    temp_dir = settings.data_dir / "temp"
                    saved_files = client.save_attachments(inv, temp_dir)

                    # Organize each file
                    for file_path in saved_files:
                        result = organizer.organize_file(
                            file_path,
                            sender=inv.sender,
                            subject=inv.subject,
                            move=True,
                        )

                        if result.success and result.metadata:
                            # Add to database
                            db.add_invoice(
                                file_path=result.destination_path,
                                category=result.category,
                                nif_emitente=result.metadata.nif_emitente,
                                invoice_date=result.metadata.invoice_date,
                                total_amount=result.metadata.total_amount,
                                email_sender=inv.sender,
                                email_subject=inv.subject,
                                email_date=inv.date,
                                email_message_id=inv.message_id,
                            )
                            downloaded += 1

                    progress.advance(task)

            console.print(f"\n[green]✓ {downloaded} faturas descarregadas e organizadas.[/green]")

    except Exception as e:
        console.print(f"[red]Erro: {e}[/red]")
        raise typer.Exit(1)


def _faturas_organizar(pasta: Optional[str], mover: bool):
    """Organize invoice files from a directory."""
    source_dir = Path(pasta) if pasta else settings.faturas_dir

    if not source_dir.exists():
        console.print(f"[red]Pasta não encontrada: {source_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[cyan]Organizando faturas em: {source_dir}[/cyan]\n")

    organizer = InvoiceOrganizer()
    db = InvoiceDatabase()

    # Find PDF files
    pdf_files = list(source_dir.glob("*.pdf"))

    if not pdf_files:
        console.print("[yellow]Nenhum ficheiro PDF encontrado na raiz da pasta.[/yellow]")
        console.print("[dim]Os ficheiros já organizados em subpastas são ignorados.[/dim]")
        return

    console.print(f"Encontrados {len(pdf_files)} ficheiros PDF\n")

    if not Confirm.ask(f"{'Mover' if mover else 'Copiar'} e organizar estes ficheiros?"):
        return

    # Process files
    results = organizer.organize_directory(source_dir, move=mover)

    # Summary by category
    summary: dict[InvoiceCategory, int] = {}
    errors = []

    for result in results:
        if result.success:
            summary[result.category] = summary.get(result.category, 0) + 1

            # Add to database
            if result.metadata:
                if not db.invoice_exists(result.destination_path):
                    db.add_invoice(
                        file_path=result.destination_path,
                        category=result.category,
                        nif_emitente=result.metadata.nif_emitente,
                        invoice_date=result.metadata.invoice_date,
                        total_amount=result.metadata.total_amount,
                    )
        else:
            errors.append(result)

    # Display summary
    if summary:
        table = Table(title="Resumo da Organização")
        table.add_column("Categoria", style="cyan")
        table.add_column("Ficheiros", style="green", justify="right")

        for cat, count in sorted(summary.items(), key=lambda x: x[1], reverse=True):
            table.add_row(cat.value, str(count))

        table.add_row("─" * 15, "─" * 5)
        table.add_row("[bold]Total[/bold]", f"[bold]{sum(summary.values())}[/bold]")

        console.print(table)

    if errors:
        console.print(f"\n[red]{len(errors)} ficheiros com erros.[/red]")


def _faturas_listar(categoria: Optional[str]):
    """List organized invoices."""
    organizer = InvoiceOrganizer()

    if categoria:
        try:
            cat = InvoiceCategory(categoria.lower())
            files = organizer.list_category_files(cat)
            console.print(f"\n[cyan]Faturas em '{cat.value}':[/cyan]\n")

            for f in files:
                console.print(f"  {f.name}")

            console.print(f"\n[dim]Total: {len(files)} ficheiros[/dim]")

        except ValueError:
            console.print(f"[red]Categoria desconhecida: {categoria}[/red]")
            console.print(f"Categorias: {', '.join(c.value for c in InvoiceCategory)}")
    else:
        # Show all categories with counts
        stats = organizer.get_category_stats()

        if not stats:
            console.print("[yellow]Nenhuma fatura organizada ainda.[/yellow]")
            return

        table = Table(title="Faturas por Categoria")
        table.add_column("Categoria", style="cyan")
        table.add_column("Ficheiros", style="green", justify="right")
        table.add_column("Pasta", style="dim")

        total = 0
        for cat, count in sorted(stats.items(), key=lambda x: x[1], reverse=True):
            folder = settings.faturas_dir / cat.value
            table.add_row(cat.value, str(count), str(folder))
            total += count

        table.add_row("─" * 15, "─" * 5, "")
        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]", "")

        console.print(table)


def _faturas_stats():
    """Show invoice statistics from database."""
    db = InvoiceDatabase()
    stats = db.get_statistics()

    console.print("\n[bold cyan]Estatísticas de Faturas[/bold cyan]\n")

    # General stats
    table = Table(title="Resumo Geral")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="green", justify="right")

    table.add_row("Total de faturas", str(stats["total_invoices"]))
    table.add_row("Valor total", f"€ {stats['total_amount']:.2f}")
    table.add_row("Pagas", str(stats["paid_count"]))
    table.add_row("Por pagar", str(stats["unpaid_count"]))

    console.print(table)

    # By category
    if stats["by_category"]:
        console.print()
        cat_table = Table(title="Por Categoria")
        cat_table.add_column("Categoria", style="cyan")
        cat_table.add_column("Quantidade", style="green", justify="right")

        for cat_name, count in sorted(
            stats["by_category"].items(), key=lambda x: x[1], reverse=True
        ):
            cat_table.add_row(cat_name, str(count))

        console.print(cat_table)


def _faturas_categorias():
    """Show available categories."""
    console.print("\n[bold cyan]Categorias Disponíveis[/bold cyan]\n")

    categorizer = InvoiceCategorizer()

    table = Table()
    table.add_column("Categoria", style="cyan")
    table.add_column("Pasta", style="green")
    table.add_column("Exemplos de Fornecedores", style="dim")

    # Map categories to example providers
    examples = {
        InvoiceCategory.COMUNICACOES: "Vodafone, NOS, MEO",
        InvoiceCategory.VIA_VERDE: "Via Verde, Brisa",
        InvoiceCategory.ENERGIA: "EDP, Galp, Endesa",
        InvoiceCategory.AGUA: "EPAL, Águas de Portugal",
        InvoiceCategory.COMBUSTIVEL: "Galp, BP, Repsol",
        InvoiceCategory.SEGUROS: "Fidelidade, Allianz",
        InvoiceCategory.SAUDE: "Farmácias, Clínicas",
        InvoiceCategory.SOFTWARE: "Microsoft, Google, Adobe",
        InvoiceCategory.MATERIAL_ESCRITORIO: "Staples, Note!",
        InvoiceCategory.ALIMENTACAO: "Continente, Pingo Doce",
        InvoiceCategory.TRANSPORTES: "Uber, CP, Metro",
        InvoiceCategory.ALOJAMENTO: "Booking, Airbnb",
        InvoiceCategory.SERVICOS: "Serviços diversos",
        InvoiceCategory.OUTROS: "Não categorizados",
    }

    for cat in InvoiceCategory:
        table.add_row(
            cat.value,
            str(settings.faturas_dir / cat.value),
            examples.get(cat, ""),
        )

    console.print(table)


# ============================================================================
# CONFIGURATION
# ============================================================================


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
