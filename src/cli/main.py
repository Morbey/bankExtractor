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
from src.modules.organizer import InvoiceDatabase, InvoiceOrganizer, DocumentProcessor
from src.modules.invoices import EMAIL_PROVIDERS, EmailFilter, InvoiceDownloader
from src.modules.organizer import DocumentIndexer, DocumentType
from src.core.document_registry import get_document_registry, EntityType
from src.modules.reporter import (
    ConsoleFormatter,
    ReportConfig,
    ReportFormat,
    ReportGenerator,
    ReportMailer,
)
from src.modules.expenses import (
    CATEGORY_NAMES,
    ExpenseCategory,
    ExpenseTracker,
)

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
def gerir_faturas(
    acao: str = typer.Argument(
        ...,
        help="Ação: organizar, listar, stats, categorias",
    ),
    pasta: Optional[str] = typer.Option(
        None,
        "--pasta", "-p",
        help="Pasta de origem para organizar ficheiros.",
    ),
    destino: Optional[str] = typer.Option(
        None,
        "--destino", "-d",
        help="Pasta de destino para ficheiros organizados.",
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
    ano: Optional[int] = typer.Option(
        None,
        "--ano", "-a",
        help="Filtrar por ano.",
    ),
    sem_ano: bool = typer.Option(
        False,
        "--sem-ano",
        help="Não criar subpastas por ano.",
    ),
):
    """Gerir faturas - organização e estatísticas."""
    console.print(Panel.fit(
        f"[bold green]Bank Extractor v{__version__}[/bold green]\n"
        "Gestão de Faturas",
        border_style="green",
    ))

    acao_lower = acao.lower()

    if acao_lower == "organizar":
        _faturas_organizar(pasta, destino, mover, not sem_ano)
    elif acao_lower == "listar":
        _faturas_listar(categoria, ano, destino)
    elif acao_lower == "stats":
        _faturas_stats(destino)
    elif acao_lower == "categorias":
        _faturas_categorias()
    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações disponíveis: organizar, listar, stats, categorias")
        console.print("[dim]Para download de faturas por email use: bank-extractor faturas[/dim]")
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


def _faturas_organizar(
    pasta: Optional[str],
    destino: Optional[str],
    mover: bool,
    organize_by_year: bool = True,
):
    """Organize invoice files from a directory."""
    source_dir = Path(pasta) if pasta else settings.faturas_dir
    dest_dir = Path(destino) if destino else None

    if not source_dir.exists():
        console.print(f"[red]Pasta não encontrada: {source_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[cyan]Organizando faturas de: {source_dir}[/cyan]")
    if dest_dir:
        console.print(f"[cyan]Destino: {dest_dir}[/cyan]")
    console.print(f"[dim]Organização por ano: {'Sim' if organize_by_year else 'Não'}[/dim]\n")

    organizer = InvoiceOrganizer(base_dir=dest_dir, organize_by_year=organize_by_year)
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


def _faturas_listar(
    categoria: Optional[str],
    ano: Optional[int] = None,
    destino: Optional[str] = None,
):
    """List organized invoices."""
    dest_dir = Path(destino) if destino else None
    organizer = InvoiceOrganizer(base_dir=dest_dir)

    if categoria:
        try:
            cat = InvoiceCategory(categoria.lower())
            files = organizer.list_category_files(cat, year=ano)

            title = f"Faturas em '{cat.value}'"
            if ano:
                title += f" ({ano})"
            console.print(f"\n[cyan]{title}:[/cyan]\n")

            for f in files:
                # Show relative path from category folder
                console.print(f"  {f.relative_to(organizer.base_dir)}")

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


def _faturas_stats(destino: Optional[str] = None):
    """Show invoice statistics from database."""
    db = InvoiceDatabase()
    stats = db.get_statistics()
    dest_dir = Path(destino) if destino else None
    organizer = InvoiceOrganizer(base_dir=dest_dir)

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
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta (ex: pessoal, empresa). Permite múltiplas contas por provider.",
    ),
    config_creds: bool = typer.Option(
        False,
        "--config", "-c",
        help="Configurar credenciais de email",
    ),
    organizar: bool = typer.Option(
        True,
        "--organizar/--sem-organizar",
        help="Organizar faturas após download (default: sim)",
    ),
    mover: bool = typer.Option(
        False,
        "--mover", "-m",
        help="Mover ficheiros em vez de copiar ao organizar",
    ),
):
    """Descarregar faturas do email."""
    from src.modules.invoices import InvoiceProcessor

    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Download de faturas por email",
        border_style="blue",
    ))

    # Handle credential configuration
    if config_creds:
        _configure_email_credentials(provider, conta)
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
    if conta:
        console.print(f"[cyan]Conta: {conta}[/cyan]")

    # Create downloader and process
    downloader = InvoiceDownloader()
    all_invoices = []

    for prov_id in providers_to_process:
        display_name = f"{prov_id.upper()} ({conta})" if conta else prov_id.upper()
        console.print(f"\n[bold cyan]A descarregar de {display_name}...[/bold cyan]")
        try:
            email_filter = EmailFilter(
                start_date=start_date,
                end_date=end_date,
            )
            invoices = downloader.download_from(prov_id, email_filter, account=conta)
            all_invoices.extend(invoices)
        except Exception as e:
            console.print(f"[red]Erro: {e}[/red]")

    if not all_invoices:
        console.print("\n[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    # Show download summary
    console.print(f"\n[green]Descarregadas {len(all_invoices)} faturas[/green]")

    # Process and organize invoices
    if organizar:
        console.print(f"\n[bold cyan]A organizar faturas...[/bold cyan]")
        console.print("[dim]Para cada fatura desconhecida, será mostrada informação para identificação.[/dim]\n")

        processor = InvoiceProcessor()
        processor.process_invoices(all_invoices, interactive=True, move=mover)
    else:
        # Just show what was downloaded
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
        console.print(f"\n[dim]Guardadas em: {settings.faturas_dir}[/dim]")
        console.print("[dim]Use --organizar para organizar as faturas por entidade[/dim]")


def _configure_email_credentials(provider: str, account: Optional[str] = None) -> None:
    """Configure email credentials for a provider.

    Args:
        provider: Provider name (gmail, hotmail, todos)
        account: Optional account name (e.g., pessoal, empresa)
    """
    if provider.lower() == "todos":
        providers = list(EMAIL_PROVIDERS.keys())
    elif provider.lower() in EMAIL_PROVIDERS:
        providers = [provider.lower()]
    else:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        raise typer.Exit(1)

    for prov_id in providers:
        # Build credential key with account name if provided
        credential_key = f"{prov_id}_{account}" if account else prov_id
        display_name = f"{prov_id.upper()} ({account})" if account else prov_id.upper()

        console.print(f"\n[bold cyan]Configurar credenciais {display_name}[/bold cyan]")

        if prov_id == "gmail":
            console.print(
                "[yellow]Nota: O Gmail requer uma App Password.[/yellow]\n"
                "1. Ative a verificação em 2 passos\n"
                "2. Vá a https://myaccount.google.com/apppasswords\n"
                "3. Gere uma App Password para 'Mail'\n"
            )

        # Prompt for credentials
        email_addr = CredentialManager.get_or_prompt(
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


@app.command()
def faturas_limpar(
    provider: str = typer.Argument(..., help="Provider de email: gmail, hotmail"),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta a limpar (ex: pessoal, empresa)",
    ),
):
    """Limpar credenciais de email guardadas."""
    if provider.lower() not in EMAIL_PROVIDERS:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        raise typer.Exit(1)

    # Build credential key with account name if provided
    credential_key = f"{provider.lower()}_{conta}" if conta else provider.lower()
    display_name = f"{provider} ({conta})" if conta else provider

    CredentialManager.delete_credential(credential_key, "email")
    CredentialManager.delete_credential(credential_key, "password")
    console.print(f"[green]Credenciais de {display_name} removidas.[/green]")


@app.command()
def organizar(
    diretorio: Optional[str] = typer.Argument(
        None,
        help="Diretório a indexar. Default: data/",
    ),
    reindexar: bool = typer.Option(
        False,
        "--reindexar", "-r",
        help="Limpar índice e reindexar tudo",
    ),
    estatisticas: bool = typer.Option(
        False,
        "--stats", "-s",
        help="Mostrar estatísticas do catálogo",
    ),
):
    """Organizar e catalogar documentos."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Organizador de documentos",
        border_style="blue",
    ))

    indexer = DocumentIndexer()

    # Show statistics only
    if estatisticas:
        _show_catalog_stats(indexer)
        return

    # Reindex all
    if reindexar:
        console.print("\n[yellow]A limpar índice e reindexar...[/yellow]")
        result = indexer.reindex_all()
    else:
        # Index directory
        from pathlib import Path
        dir_path = Path(diretorio) if diretorio else None
        console.print(f"\n[cyan]A indexar documentos em {dir_path or settings.data_dir}...[/cyan]")
        result = indexer.index_directory(dir_path)

    # Show results
    console.print(f"\n[green]Indexação completa![/green]")

    table = Table(title="Resultado da Indexação")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="white", justify="right")

    table.add_row("Ficheiros encontrados", str(result.total_files))
    table.add_row("Indexados", f"[green]{result.indexed}[/green]")
    table.add_row("Ignorados (já existentes)", str(result.skipped))
    table.add_row("Erros", f"[red]{result.errors}[/red]" if result.errors else "0")

    console.print(table)

    # Show recent documents
    if result.documents:
        console.print("\n[bold]Documentos indexados:[/bold]")
        doc_table = Table()
        doc_table.add_column("Tipo", style="cyan")
        doc_table.add_column("Ficheiro", style="white")
        doc_table.add_column("Data", style="yellow")
        doc_table.add_column("Valor", style="green", justify="right")

        for doc in result.documents[:10]:  # Show first 10
            doc_date = doc.document_date.strftime("%d-%m-%Y") if doc.document_date else "-"
            amount = f"{doc.amount:.2f}€" if doc.amount else "-"
            doc_table.add_row(
                doc.document_type,
                doc.file_name[:40] + "..." if len(doc.file_name) > 40 else doc.file_name,
                doc_date,
                amount,
            )

        console.print(doc_table)

        if len(result.documents) > 10:
            console.print(f"[dim]... e mais {len(result.documents) - 10} documentos[/dim]")


def _show_catalog_stats(indexer: DocumentIndexer) -> None:
    """Show catalog statistics."""
    stats = indexer.get_statistics()

    console.print("\n[bold]Estatísticas do Catálogo[/bold]")

    # General stats
    table = Table(title="Resumo Geral")
    table.add_column("Métrica", style="cyan")
    table.add_column("Valor", style="white", justify="right")

    table.add_row("Total de documentos", str(stats["total_documents"]))
    table.add_row("Fornecedores", str(stats["total_providers"]))
    table.add_row("Tags", str(stats["total_tags"]))
    table.add_row("Valor total", f"{stats['total_amount']:.2f}€")

    console.print(table)

    # By type
    if stats["by_type"]:
        type_table = Table(title="Por Tipo")
        type_table.add_column("Tipo", style="cyan")
        type_table.add_column("Quantidade", style="white", justify="right")

        for doc_type, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            type_table.add_row(doc_type, str(count))

        console.print(type_table)

    # By provider
    if stats["by_provider"]:
        prov_table = Table(title="Por Fornecedor")
        prov_table.add_column("Fornecedor", style="cyan")
        prov_table.add_column("Documentos", style="white", justify="right")

        for provider, count in sorted(stats["by_provider"].items(), key=lambda x: -x[1])[:10]:
            prov_table.add_row(provider, str(count))

        console.print(prov_table)


@app.command()
def pesquisar(
    query: str = typer.Argument(..., help="Texto a pesquisar"),
    tipo: Optional[str] = typer.Option(
        None,
        "--tipo", "-t",
        help="Filtrar por tipo: fatura, extrato, recibo, contrato, imposto",
    ),
    fornecedor: Optional[str] = typer.Option(
        None,
        "--fornecedor", "-f",
        help="Filtrar por fornecedor",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio", "-i",
        help="Data início (DD-MM-YYYY)",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim",
        help="Data fim (DD-MM-YYYY)",
    ),
    limite: int = typer.Option(
        20,
        "--limite", "-l",
        help="Número máximo de resultados",
    ),
):
    """Pesquisar documentos no catálogo."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        f"Pesquisa: [cyan]{query}[/cyan]",
        border_style="blue",
    ))

    indexer = DocumentIndexer()

    # Parse document type
    doc_type = None
    if tipo:
        try:
            doc_type = DocumentType(tipo.lower())
        except ValueError:
            console.print(f"[red]Tipo inválido: {tipo}[/red]")
            console.print("Tipos válidos: fatura, extrato, recibo, contrato, imposto, outro")
            raise typer.Exit(1)

    # Parse dates
    start_date = parse_date(inicio) if inicio else None
    end_date = parse_date(fim) if fim else None

    # Search
    result = indexer.search(
        query=query,
        document_type=doc_type,
        provider_name=fornecedor,
        start_date=start_date,
        end_date=end_date,
        limit=limite,
    )

    if not result.documents:
        console.print("\n[yellow]Nenhum documento encontrado.[/yellow]")
        return

    console.print(f"\n[green]Encontrados {result.total_count} documentos:[/green]")

    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Tipo", style="cyan")
    table.add_column("Ficheiro", style="white")
    table.add_column("Fornecedor", style="green")
    table.add_column("Data", style="yellow")
    table.add_column("Valor", style="magenta", justify="right")

    for doc in result.documents:
        doc_date = doc.document_date.strftime("%d-%m-%Y") if doc.document_date else "-"
        amount = f"{doc.amount:.2f}€" if doc.amount else "-"
        provider = doc.provider.name if doc.provider else "-"
        table.add_row(
            str(doc.id),
            doc.document_type,
            doc.file_name[:35] + "..." if len(doc.file_name) > 35 else doc.file_name,
            provider[:15] + "..." if len(provider) > 15 else provider,
            doc_date,
            amount,
        )

    console.print(table)
    console.print(f"\n[dim]Use 'bank-extractor documento <ID>' para ver detalhes[/dim]")


@app.command()
def processar(
    diretorio: Optional[str] = typer.Argument(
        None,
        help="Diretório com documentos a processar. Default: data/temp",
    ),
    interativo: bool = typer.Option(
        True,
        "--interativo/--auto",
        help="Modo interativo para entidades desconhecidas",
    ),
    mover: bool = typer.Option(
        False,
        "--mover", "-m",
        help="Mover ficheiros em vez de copiar",
    ),
    recursivo: bool = typer.Option(
        False,
        "--recursivo", "-r",
        help="Processar subdiretórios",
    ),
):
    """Processar documentos - classificar, identificar entidades e organizar."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Processamento de Documentos",
        border_style="blue",
    ))

    source_dir = Path(diretorio) if diretorio else settings.data_dir / "temp"

    if not source_dir.exists():
        console.print(f"[red]Diretório não encontrado: {source_dir}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[cyan]A processar documentos de: {source_dir}[/cyan]")
    console.print(f"[dim]Modo: {'Interativo' if interativo else 'Automático'}[/dim]")
    console.print(f"[dim]Ação: {'Mover' if mover else 'Copiar'}[/dim]\n")

    processor = DocumentProcessor()
    results = processor.process_directory(
        source_dir,
        interactive=interativo,
        move=mover,
        recursive=recursivo,
    )

    # Check pending count
    registry = get_document_registry()
    pending_count = registry.get_pending_count()
    if pending_count > 0:
        console.print(f"\n[yellow]Existem {pending_count} documentos pendentes.[/yellow]")
        console.print("[dim]Use: bank-extractor pendentes[/dim]")


@app.command()
def pendentes(
    processar_todos: bool = typer.Option(
        False,
        "--processar", "-p",
        help="Processar todos os documentos pendentes",
    ),
    listar: bool = typer.Option(
        False,
        "--listar", "-l",
        help="Listar documentos pendentes",
    ),
    limpar: bool = typer.Option(
        False,
        "--limpar",
        help="Limpar a fila de pendentes",
    ),
):
    """Gerir documentos pendentes de classificação."""
    console.print(Panel.fit(
        f"[bold yellow]Bank Extractor v{__version__}[/bold yellow]\n"
        "Documentos Pendentes",
        border_style="yellow",
    ))

    registry = get_document_registry()

    if limpar:
        pending = registry.get_pending_documents()
        if pending:
            if Confirm.ask(f"Limpar {len(pending)} documentos pendentes?"):
                for doc in pending:
                    registry.remove_from_pending(doc["id"])
                console.print("[green]Fila de pendentes limpa.[/green]")
        else:
            console.print("[green]Não há documentos pendentes.[/green]")
        return

    if listar or (not processar_todos):
        registry.show_pending_summary()
        pending_count = registry.get_pending_count()
        if pending_count > 0:
            console.print(f"\n[dim]Use: bank-extractor pendentes --processar[/dim]")
        return

    if processar_todos:
        processor = DocumentProcessor()
        processor.process_pending_queue(interactive=True)


@app.command()
def entidades(
    acao: str = typer.Argument(
        "listar",
        help="Ação: listar, criar, ver, editar",
    ),
    nome: Optional[str] = typer.Option(
        None,
        "--nome", "-n",
        help="Nome da entidade",
    ),
    pasta: Optional[str] = typer.Option(
        None,
        "--pasta", "-p",
        help="Nome da pasta",
    ),
    tipo: Optional[str] = typer.Option(
        None,
        "--tipo", "-t",
        help="Tipo: empresa, pessoa, banco, proprio",
    ),
    nif: Optional[str] = typer.Option(
        None,
        "--nif",
        help="NIF a adicionar",
    ),
    iban: Optional[str] = typer.Option(
        None,
        "--iban",
        help="IBAN a adicionar",
    ),
    entity_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="ID da entidade (para ver/editar)",
    ),
):
    """Gerir entidades (fornecedores, clientes, etc.)."""
    console.print(Panel.fit(
        f"[bold green]Bank Extractor v{__version__}[/bold green]\n"
        "Gestão de Entidades",
        border_style="green",
    ))

    registry = get_document_registry()
    acao_lower = acao.lower()

    if acao_lower == "listar":
        entities = registry.get_all_entities()

        if not entities:
            console.print("\n[yellow]Nenhuma entidade registada.[/yellow]")
            console.print("[dim]Use: bank-extractor entidades criar --nome \"Nome\" --pasta \"pasta\"[/dim]")
            return

        table = Table(title=f"Entidades Registadas ({len(entities)})")
        table.add_column("ID", style="dim", width=10)
        table.add_column("Nome", style="cyan")
        table.add_column("Pasta", style="green")
        table.add_column("Tipo", style="yellow")
        table.add_column("NIFs", style="white")
        table.add_column("IBANs", style="white")

        for e in entities:
            nifs_display = ", ".join(e.nifs[:2]) if e.nifs else "-"
            if len(e.nifs) > 2:
                nifs_display += f" (+{len(e.nifs) - 2})"

            ibans_display = []
            for i in e.ibans[:2]:
                ibans_display.append(f"{i[:8]}...{i[-4:]}")
            ibans_str = ", ".join(ibans_display) if ibans_display else "-"
            if len(e.ibans) > 2:
                ibans_str += f" (+{len(e.ibans) - 2})"

            table.add_row(
                e.id[:10],
                e.name[:30],
                e.folder_name[:20],
                e.entity_type.value,
                nifs_display,
                ibans_str,
            )

        console.print(table)

    elif acao_lower == "criar":
        if not nome:
            console.print("[red]Nome é obrigatório. Use --nome[/red]")
            raise typer.Exit(1)

        folder_name = pasta or nome.replace(" ", "_")[:30]

        entity_type = EntityType.DESCONHECIDO
        if tipo:
            try:
                entity_type = EntityType(tipo.lower())
            except ValueError:
                console.print(f"[yellow]Tipo inválido: {tipo}. Usando 'desconhecido'.[/yellow]")

        nifs_list = [nif] if nif else []
        ibans_list = [iban] if iban else []

        entity = registry.create_entity(
            name=nome,
            folder_name=folder_name,
            entity_type=entity_type,
            nifs=nifs_list,
            ibans=ibans_list,
        )

        console.print(f"\n[green]Entidade criada com sucesso![/green]")
        registry.show_entity_summary(entity.id)

    elif acao_lower == "ver":
        if entity_id:
            registry.show_entity_summary(entity_id)
        elif nome:
            entity = registry.find_entity(name=nome)
            if entity:
                registry.show_entity_summary(entity.id)
            else:
                console.print(f"[red]Entidade não encontrada: {nome}[/red]")
        else:
            console.print("[red]Especifique --id ou --nome[/red]")

    elif acao_lower == "editar":
        if not entity_id:
            console.print("[red]ID é obrigatório para editar. Use --id[/red]")
            raise typer.Exit(1)

        entity = registry.get_entity(entity_id)
        if not entity:
            console.print(f"[red]Entidade não encontrada: {entity_id}[/red]")
            raise typer.Exit(1)

        if nif:
            registry.add_nif_to_entity(entity_id, nif)
            console.print(f"[green]NIF adicionado: {nif}[/green]")

        if iban:
            registry.add_iban_to_entity(entity_id, iban)
            console.print(f"[green]IBAN adicionado[/green]")

        if nome:
            entity.name = nome
            registry.update_entity(entity)
            console.print(f"[green]Nome actualizado: {nome}[/green]")

        if pasta:
            entity.folder_name = pasta
            registry.update_entity(entity)
            console.print(f"[green]Pasta actualizada: {pasta}[/green]")

        registry.show_entity_summary(entity_id)

    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações disponíveis: listar, criar, ver, editar")
        raise typer.Exit(1)


@app.command()
def documento(
    doc_id: int = typer.Argument(..., help="ID do documento"),
    abrir: bool = typer.Option(
        False,
        "--abrir", "-a",
        help="Abrir o ficheiro",
    ),
):
    """Ver detalhes de um documento."""
    indexer = DocumentIndexer()
    doc = indexer.get_document_by_id(doc_id)

    if not doc:
        console.print(f"[red]Documento não encontrado: {doc_id}[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold]Documento #{doc.id}[/bold]",
        border_style="blue",
    ))

    table = Table(show_header=False)
    table.add_column("Campo", style="cyan")
    table.add_column("Valor", style="white")

    table.add_row("Ficheiro", doc.file_name)
    table.add_row("Caminho", str(doc.file_path))
    table.add_row("Tipo", doc.document_type)
    table.add_row("Estado", doc.status)
    table.add_row("Fornecedor", doc.provider.name if doc.provider else "-")
    table.add_row("Data documento", doc.document_date.strftime("%d-%m-%Y") if doc.document_date else "-")
    table.add_row("Data vencimento", doc.due_date.strftime("%d-%m-%Y") if doc.due_date else "-")
    table.add_row("Valor", f"{doc.amount:.2f}€" if doc.amount else "-")
    table.add_row("Referência", doc.reference or "-")
    table.add_row("Tamanho", f"{doc.file_size / 1024:.1f} KB")
    table.add_row("Hash", doc.file_hash[:16] + "...")
    table.add_row("Indexado em", doc.created_at.strftime("%d-%m-%Y %H:%M"))

    if doc.tags:
        tags_str = ", ".join(t.name for t in doc.tags)
        table.add_row("Tags", tags_str)

    console.print(table)

    # Open file if requested
    if abrir:
        import subprocess
        import sys

        file_path = doc.path
        if not file_path.exists():
            console.print(f"[red]Ficheiro não encontrado: {file_path}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[cyan]A abrir {file_path.name}...[/cyan]")

        if sys.platform == "win32":
            subprocess.run(["start", "", str(file_path)], shell=True)
        elif sys.platform == "darwin":
            subprocess.run(["open", str(file_path)])
        else:
            subprocess.run(["xdg-open", str(file_path)])


@app.command()
def relatorio(
    mes: str = typer.Argument(
        ...,
        help="Mês do relatório (MM-YYYY ou 'atual')",
    ),
    formato: str = typer.Option(
        "console",
        "--formato", "-f",
        help="Formato: console, html, excel",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Ficheiro de output (para html/excel)",
    ),
    sem_comparacao: bool = typer.Option(
        False,
        "--sem-comparacao",
        help="Não incluir comparação com mês anterior",
    ),
):
    """Gerar relatório financeiro mensal."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Relatórios Financeiros",
        border_style="blue",
    ))

    # Parse month
    if mes.lower() == "atual":
        today = date.today()
        year, month = today.year, today.month
    else:
        try:
            parts = mes.split("-")
            if len(parts) == 2:
                month, year = int(parts[0]), int(parts[1])
            else:
                raise ValueError()
        except ValueError:
            console.print("[red]Formato de mês inválido. Use MM-YYYY ou 'atual'[/red]")
            raise typer.Exit(1)

    # Parse format
    format_map = {
        "console": ReportFormat.CONSOLE,
        "html": ReportFormat.HTML,
        "excel": ReportFormat.EXCEL,
        "pdf": ReportFormat.PDF,
    }
    report_format = format_map.get(formato.lower())
    if not report_format:
        console.print(f"[red]Formato inválido: {formato}[/red]")
        console.print("Formatos disponíveis: console, html, excel")
        raise typer.Exit(1)

    # Generate report
    config = ReportConfig(
        year=year,
        month=month,
        format=report_format,
        include_comparison=not sem_comparacao,
    )

    console.print(f"\n[cyan]A gerar relatório para {month:02d}/{year}...[/cyan]")

    generator = ReportGenerator()
    report = generator.generate(config)

    # Output based on format
    if report_format == ReportFormat.CONSOLE:
        formatter = ConsoleFormatter()
        formatter.render(report)
    else:
        # Save to file
        from pathlib import Path
        from src.modules.reporter import get_formatter

        if output:
            output_path = Path(output)
        else:
            ext = {"html": ".html", "excel": ".xlsx", "pdf": ".html"}.get(formato.lower(), ".txt")
            output_path = settings.data_dir / f"relatorio_{year}_{month:02d}{ext}"

        formatter = get_formatter(report_format)
        if formatter.save(report, output_path):
            console.print(f"\n[green]Relatório guardado em: {output_path}[/green]")
        else:
            console.print("[red]Erro ao guardar relatório.[/red]")
            raise typer.Exit(1)


@app.command()
def enviar(
    mes: str = typer.Argument(
        ...,
        help="Mês do relatório (MM-YYYY ou 'atual')",
    ),
    email: str = typer.Argument(
        ...,
        help="Email do destinatário",
    ),
    provider: str = typer.Option(
        "gmail",
        "--provider", "-p",
        help="Provider de email para envio: gmail, hotmail",
    ),
    anexar_docs: bool = typer.Option(
        False,
        "--anexar", "-a",
        help="Anexar documentos do período",
    ),
):
    """Enviar relatório por email."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Envio de Relatório",
        border_style="blue",
    ))

    # Parse month
    if mes.lower() == "atual":
        today = date.today()
        year, month = today.year, today.month
    else:
        try:
            parts = mes.split("-")
            if len(parts) == 2:
                month, year = int(parts[0]), int(parts[1])
            else:
                raise ValueError()
        except ValueError:
            console.print("[red]Formato de mês inválido. Use MM-YYYY ou 'atual'[/red]")
            raise typer.Exit(1)

    # Generate report
    config = ReportConfig(year=year, month=month)
    generator = ReportGenerator()
    report = generator.generate(config)

    if not report.has_data:
        console.print("[yellow]Relatório sem dados. Nada a enviar.[/yellow]")
        raise typer.Exit(0)

    # Get attachments if requested
    attachments = []
    if anexar_docs and report.documents:
        from pathlib import Path
        for doc in report.documents:
            doc_path = Path(doc.file_name) if doc.file_name else None
            # We'd need the actual path from the indexer
            # For now, just note that attachments would be added here

    # Send email
    console.print(f"\n[cyan]A enviar relatório para {email}...[/cyan]")

    try:
        mailer = ReportMailer(provider=provider)
        if mailer.send_report(report, email, attachments if attachments else None):
            console.print(f"\n[green]Relatório enviado com sucesso para {email}![/green]")
        else:
            console.print("[red]Falha ao enviar relatório.[/red]")
            raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def relatorio_anual(
    ano: int = typer.Argument(..., help="Ano do relatório"),
    formato: str = typer.Option(
        "console",
        "--formato", "-f",
        help="Formato: console, html, excel",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output", "-o",
        help="Ficheiro de output",
    ),
):
    """Gerar relatório anual."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        f"Relatório Anual {ano}",
        border_style="blue",
    ))

    console.print(f"\n[cyan]A gerar relatório anual para {ano}...[/cyan]")

    generator = ReportGenerator()
    report = generator.generate_yearly(ano)

    # Parse format
    format_map = {
        "console": ReportFormat.CONSOLE,
        "html": ReportFormat.HTML,
        "excel": ReportFormat.EXCEL,
    }
    report_format = format_map.get(formato.lower(), ReportFormat.CONSOLE)

    if report_format == ReportFormat.CONSOLE:
        formatter = ConsoleFormatter()
        formatter.render(report)
    else:
        from pathlib import Path
        from src.modules.reporter import get_formatter

        if output:
            output_path = Path(output)
        else:
            ext = {"html": ".html", "excel": ".xlsx"}.get(formato.lower(), ".txt")
            output_path = settings.data_dir / f"relatorio_anual_{ano}{ext}"

        formatter = get_formatter(report_format)
        if formatter.save(report, output_path):
            console.print(f"\n[green]Relatório guardado em: {output_path}[/green]")
        else:
            console.print("[red]Erro ao guardar relatório.[/red]")


@app.command()
def despesas(
    mes: str = typer.Argument(
        "atual",
        help="Mês a analisar (MM-YYYY ou 'atual')",
    ),
    importar: bool = typer.Option(
        False,
        "--importar", "-i",
        help="Importar despesas dos documentos indexados",
    ),
    categoria: Optional[str] = typer.Option(
        None,
        "--categoria", "-c",
        help="Filtrar por categoria",
    ),
):
    """Ver e analisar despesas."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Tracking de Despesas",
        border_style="blue",
    ))

    tracker = ExpenseTracker()

    # Import from documents if requested
    if importar:
        console.print("\n[cyan]A importar despesas dos documentos...[/cyan]")
        count = tracker.import_from_documents()
        console.print(f"[green]Importadas {count} despesas.[/green]\n")

    # Parse month
    if mes.lower() == "atual":
        today = date.today()
        year, month = today.year, today.month
    else:
        try:
            parts = mes.split("-")
            month, year = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            console.print("[red]Formato inválido. Use MM-YYYY ou 'atual'[/red]")
            raise typer.Exit(1)

    # Get analysis
    analysis = tracker.analyzer.analyze_month(year, month)

    # Summary
    console.print(f"\n[bold]Despesas de {month:02d}/{year}[/bold]")

    summary_table = Table(show_header=False)
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Total despesas", f"[bold green]{analysis.total_expenses:.2f}€[/bold green]")
    summary_table.add_row("Número de despesas", str(analysis.expense_count))

    if analysis.comparison_previous is not None:
        trend = "▲" if analysis.comparison_percentage > 0 else "▼"
        color = "red" if analysis.comparison_percentage > 0 else "green"
        summary_table.add_row(
            "vs. mês anterior",
            f"[{color}]{trend} {analysis.comparison_previous:+.2f}€ ({analysis.comparison_percentage:+.1f}%)[/{color}]"
        )

    console.print(summary_table)

    # By category
    if analysis.by_category:
        console.print("\n[bold]Por Categoria[/bold]")
        cat_table = Table()
        cat_table.add_column("Categoria", style="cyan")
        cat_table.add_column("Total", justify="right", style="green")
        cat_table.add_column("Qtd", justify="right")
        cat_table.add_column("Média", justify="right")
        cat_table.add_column("Tendência", justify="center")

        for cat in analysis.by_category:
            if categoria and categoria.lower() not in cat.category.lower():
                continue

            trend_icon = {"up": "▲", "down": "▼", "stable": "─", "new": "★"}.get(cat.trend, "─")
            trend_color = {"up": "red", "down": "green", "stable": "yellow", "new": "cyan"}.get(cat.trend, "white")

            cat_table.add_row(
                cat.category_name,
                f"{cat.total_amount:.2f}€",
                str(cat.expense_count),
                f"{cat.average_amount:.2f}€",
                f"[{trend_color}]{trend_icon}[/{trend_color}]",
            )

        console.print(cat_table)

    # Top providers
    if analysis.top_providers:
        console.print("\n[bold]Top Fornecedores[/bold]")
        prov_table = Table()
        prov_table.add_column("Fornecedor", style="cyan")
        prov_table.add_column("Total", justify="right", style="green")

        for provider, amount in analysis.top_providers[:5]:
            prov_table.add_row(provider, f"{amount:.2f}€")

        console.print(prov_table)

    # Alerts
    if analysis.alerts:
        console.print(f"\n[bold yellow]Alertas ({len(analysis.alerts)})[/bold yellow]")
        for alert in analysis.alerts[:5]:
            severity_color = {"info": "blue", "aviso": "yellow", "critico": "red"}.get(alert.severity, "white")
            console.print(f"  [{severity_color}]•[/{severity_color}] {alert.message}")


@app.command()
def orcamento(
    categoria: Optional[str] = typer.Argument(
        None,
        help="Categoria para definir/ver orçamento",
    ),
    valor: Optional[float] = typer.Option(
        None,
        "--valor", "-v",
        help="Valor limite mensal",
    ),
    listar: bool = typer.Option(
        False,
        "--listar", "-l",
        help="Listar todos os orçamentos",
    ),
    remover: bool = typer.Option(
        False,
        "--remover", "-r",
        help="Remover orçamento da categoria",
    ),
):
    """Gerir orçamentos por categoria."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Gestão de Orçamentos",
        border_style="blue",
    ))

    tracker = ExpenseTracker()

    # List all budgets
    if listar or (not categoria and not valor):
        today = date.today()
        status = tracker.get_budget_status(today.year, today.month)

        if not status:
            console.print("\n[yellow]Nenhum orçamento definido.[/yellow]")
            console.print("[dim]Use: bank-extractor orcamento <categoria> --valor <limite>[/dim]")

            # Show available categories
            console.print("\n[bold]Categorias disponíveis:[/bold]")
            for cat in ExpenseCategory:
                name = CATEGORY_NAMES.get(cat, cat.value)
                console.print(f"  • {cat.value} - {name}")
            return

        console.print(f"\n[bold]Orçamentos - {today.strftime('%B %Y')}[/bold]")
        table = Table()
        table.add_column("Categoria", style="cyan")
        table.add_column("Limite", justify="right")
        table.add_column("Gasto", justify="right")
        table.add_column("Restante", justify="right")
        table.add_column("Progresso", justify="left")

        for s in status:
            # Progress bar
            pct = min(s["percentage"], 100)
            filled = int(pct / 5)
            bar = "█" * filled + "░" * (20 - filled)

            if s["is_exceeded"]:
                color = "red"
            elif s["is_warning"]:
                color = "yellow"
            else:
                color = "green"

            table.add_row(
                s["category_name"],
                f"{s['limit']:.2f}€",
                f"{s['spent']:.2f}€",
                f"[{color}]{s['remaining']:.2f}€[/{color}]",
                f"[{color}]{bar}[/{color}] {s['percentage']:.0f}%",
            )

        console.print(table)
        return

    # Validate category
    try:
        cat_enum = ExpenseCategory(categoria.lower())
    except ValueError:
        console.print(f"[red]Categoria inválida: {categoria}[/red]")
        console.print("Categorias válidas:")
        for cat in ExpenseCategory:
            console.print(f"  • {cat.value}")
        raise typer.Exit(1)

    # Remove budget
    if remover:
        if tracker.delete_budget(cat_enum):
            console.print(f"[green]Orçamento de {categoria} removido.[/green]")
        else:
            console.print(f"[yellow]Nenhum orçamento encontrado para {categoria}.[/yellow]")
        return

    # Set budget
    if valor is not None:
        tracker.set_budget(cat_enum, valor)
        cat_name = CATEGORY_NAMES.get(cat_enum, categoria)
        console.print(f"[green]Orçamento definido: {cat_name} = {valor:.2f}€/mês[/green]")
    else:
        console.print("[yellow]Use --valor para definir o limite mensal.[/yellow]")


@app.command()
def alertas(
    limpar: bool = typer.Option(
        False,
        "--limpar", "-l",
        help="Limpar todos os alertas",
    ),
    verificar: bool = typer.Option(
        False,
        "--verificar", "-v",
        help="Verificar orçamentos e gerar alertas",
    ),
):
    """Ver e gerir alertas de despesas."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Alertas de Despesas",
        border_style="blue",
    ))

    tracker = ExpenseTracker()

    # Check budgets and generate alerts
    if verificar:
        console.print("\n[cyan]A verificar orçamentos...[/cyan]")
        alerts = tracker.check_all_budgets()
        if alerts:
            console.print(f"[yellow]Gerados {len(alerts)} alertas.[/yellow]")
        else:
            console.print("[green]Todos os orçamentos dentro dos limites.[/green]")

    # Get pending alerts
    alerts = tracker.get_alerts()

    if not alerts:
        console.print("\n[green]Sem alertas pendentes.[/green]")
        return

    console.print(f"\n[bold]Alertas Pendentes ({len(alerts)})[/bold]")

    table = Table()
    table.add_column("ID", style="dim")
    table.add_column("Severidade", justify="center")
    table.add_column("Tipo", style="cyan")
    table.add_column("Mensagem", style="white")
    table.add_column("Data", style="yellow")

    for alert in alerts:
        severity_icon = {
            "info": "[blue]ℹ[/blue]",
            "aviso": "[yellow]⚠[/yellow]",
            "critico": "[red]🔴[/red]",
        }.get(alert.severity, "•")

        table.add_row(
            str(alert.id),
            severity_icon,
            alert.alert_type,
            alert.message[:50] + "..." if len(alert.message) > 50 else alert.message,
            alert.created_at.strftime("%d-%m-%Y"),
        )

    console.print(table)

    if limpar:
        console.print("\n[cyan]A limpar alertas...[/cyan]")
        for alert in alerts:
            tracker.analyzer.dismiss_alert(alert.id)
        console.print("[green]Alertas limpos.[/green]")


@app.command()
def tendencias(
    meses: int = typer.Option(
        6,
        "--meses", "-m",
        help="Número de meses a analisar",
    ),
):
    """Ver tendências de despesas."""
    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        f"Tendências ({meses} meses)",
        border_style="blue",
    ))

    tracker = ExpenseTracker()
    trends = tracker.get_trends(meses)

    # Monthly totals
    console.print("\n[bold]Totais Mensais[/bold]")
    table = Table()
    table.add_column("Mês", style="cyan")
    table.add_column("Total", justify="right", style="green")
    table.add_column("Gráfico", style="blue")

    max_total = max((m["total"] for m in trends["monthly_totals"]), default=1)

    for m in trends["monthly_totals"]:
        bar_width = int((m["total"] / max_total) * 30) if max_total > 0 else 0
        bar = "█" * bar_width

        table.add_row(
            f"{m['month']:02d}/{m['year']}",
            f"{m['total']:.2f}€",
            bar,
        )

    console.print(table)

    # Summary
    console.print(f"\n[bold]Resumo[/bold]")
    summary = Table(show_header=False)
    summary.add_column("Metric", style="cyan")
    summary.add_column("Value", style="white")

    summary.add_row("Média mensal", f"{trends['average_monthly']:.2f}€")

    trend_icon = {"up": "▲", "down": "▼", "stable": "─"}.get(trends["trend_direction"], "─")
    trend_color = {"up": "red", "down": "green", "stable": "yellow"}.get(trends["trend_direction"], "white")
    summary.add_row("Tendência", f"[{trend_color}]{trend_icon} {trends['trend_direction'].title()}[/{trend_color}]")

    console.print(summary)


# ============================================================================
# EMAIL BROWSING (View body and selective attachment download)
# ============================================================================


@app.command()
def emails(
    provider: str = typer.Argument(
        "todos",
        help="Provider de email: gmail, hotmail, ou 'todos'",
    ),
    dias: int = typer.Option(
        settings.invoice_days_default,
        "--dias", "-d",
        help="Número de dias a pesquisar",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio", "-i",
        help="Data início (DD-MM-YYYY)",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim", "-f",
        help="Data fim (DD-MM-YYYY)",
    ),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta",
    ),
    ver_corpo: bool = typer.Option(
        False,
        "--ver-corpo", "-b",
        help="Mostrar corpo dos emails",
    ),
    interativo: bool = typer.Option(
        False,
        "--interativo", "-I",
        help="Modo interativo para seleccionar anexos",
    ),
):
    """Navegar emails com anexos - ver corpo e descarregar anexos individualmente."""
    from src.modules.invoices import EMAIL_PROVIDERS

    console.print(Panel.fit(
        f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
        "Navegação de Emails",
        border_style="blue",
    ))

    # Determine providers
    if provider.lower() == "todos":
        providers_to_process = list(EMAIL_PROVIDERS.keys())
    elif provider.lower() in EMAIL_PROVIDERS:
        providers_to_process = [provider.lower()]
    else:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        raise typer.Exit(1)

    # Parse dates
    if inicio:
        start_date = parse_date(inicio)
    else:
        from datetime import timedelta
        start_date = date.today() - timedelta(days=dias)

    end_date = parse_date(fim) if fim else date.today()

    console.print(f"\n[cyan]Período: {start_date.strftime('%d-%m-%Y')} a {end_date.strftime('%d-%m-%Y')}[/cyan]")

    all_email_messages = []

    for prov_id in providers_to_process:
        display_name = f"{prov_id.upper()} ({conta})" if conta else prov_id.upper()
        console.print(f"\n[bold cyan]A pesquisar em {display_name}...[/bold cyan]")

        try:
            provider_class = EMAIL_PROVIDERS[prov_id]
            with provider_class(account=conta) as prov:
                email_filter = EmailFilter(
                    start_date=start_date,
                    end_date=end_date,
                )
                messages = prov.get_email_messages(email_filter)
                all_email_messages.extend(messages)
                console.print(f"  Encontrados {len(messages)} emails com anexos")
        except Exception as e:
            console.print(f"[red]Erro: {e}[/red]")

    if not all_email_messages:
        console.print("\n[yellow]Nenhum email encontrado.[/yellow]")
        return

    # Display emails
    console.print(f"\n[green]Total: {len(all_email_messages)} emails[/green]\n")

    for idx, email_msg in enumerate(all_email_messages, 1):
        # Header
        console.print(f"\n[bold]═══ Email {idx}/{len(all_email_messages)} ═══[/bold]")

        info_table = Table(show_header=False, box=None)
        info_table.add_column("Campo", style="cyan", width=12)
        info_table.add_column("Valor", style="white")

        info_table.add_row("De:", email_msg.sender[:60])
        info_table.add_row("Assunto:", email_msg.subject[:70])
        info_table.add_row("Data:", email_msg.date.strftime("%d-%m-%Y %H:%M"))
        info_table.add_row("Provider:", email_msg.provider.upper())

        console.print(Panel(info_table, border_style="blue"))

        # Show attachments
        if email_msg.attachments:
            console.print("[bold]Anexos:[/bold]")
            for i, att in enumerate(email_msg.attachments):
                size_kb = att.size / 1024
                console.print(f"  [{i}] {att.filename} ({size_kb:.1f} KB)")

        # Show body if requested
        if ver_corpo:
            body = email_msg.body_text or "[sem corpo de texto]"
            # Truncate long bodies
            if len(body) > 2000:
                body = body[:2000] + "\n\n[... truncado ...]"
            console.print(Panel(body, title="Corpo do Email", border_style="green"))

        # Interactive mode - select attachments to download
        if interativo and email_msg.attachments:
            console.print("\n[yellow]Opções: [número] descarregar anexo, [t] todos, [c] corpo, [n] próximo, [s] sair[/yellow]")

            while True:
                choice = Prompt.ask("Escolha", default="n")

                if choice.lower() == "s":
                    console.print("[yellow]Saindo...[/yellow]")
                    return
                elif choice.lower() == "n":
                    break
                elif choice.lower() == "c":
                    body = email_msg.body_text or "[sem corpo de texto]"
                    console.print(Panel(body, title="Corpo do Email", border_style="green"))
                elif choice.lower() == "t":
                    # Download all attachments
                    for prov_id in providers_to_process:
                        provider_class = EMAIL_PROVIDERS[prov_id]
                        with provider_class(account=conta) as prov:
                            for att_idx in range(len(email_msg.attachments)):
                                result = prov.download_attachment(email_msg, att_idx)
                                if result:
                                    console.print(f"[green]✓ Guardado: {result.file_path.name}[/green]")
                            break
                elif choice.isdigit():
                    att_idx = int(choice)
                    if 0 <= att_idx < len(email_msg.attachments):
                        for prov_id in providers_to_process:
                            provider_class = EMAIL_PROVIDERS[prov_id]
                            with provider_class(account=conta) as prov:
                                result = prov.download_attachment(email_msg, att_idx)
                                if result:
                                    console.print(f"[green]✓ Guardado: {result.file_path.name}[/green]")
                                break
                    else:
                        console.print("[red]Índice inválido[/red]")

    console.print(f"\n[dim]Emails processados: {len(all_email_messages)}[/dim]")


# ============================================================================
# CLASSIFICATION RULES MANAGEMENT
# ============================================================================


@app.command()
def regras(
    acao: str = typer.Argument(
        "listar",
        help="Ação: listar, adicionar, remover, limpar, exportar, importar",
    ),
    tipo: Optional[str] = typer.Option(
        None,
        "--tipo", "-t",
        help="Tipo de regra: sender, body_pattern, pdf_pattern, nif",
    ),
    padrao: Optional[str] = typer.Option(
        None,
        "--padrao", "-p",
        help="Padrão a adicionar (email, regex, ou NIF)",
    ),
    categoria: Optional[str] = typer.Option(
        None,
        "--categoria", "-c",
        help="Categoria para a regra",
    ),
    rule_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="ID da regra (para remover)",
    ),
    ficheiro: Optional[str] = typer.Option(
        None,
        "--ficheiro", "-f",
        help="Ficheiro para exportar/importar",
    ),
):
    """Gerir regras de classificação automática."""
    from src.core import get_rules_manager
    from src.core.categories import InvoiceCategory

    console.print(Panel.fit(
        f"[bold green]Bank Extractor v{__version__}[/bold green]\n"
        "Gestão de Regras de Classificação",
        border_style="green",
    ))

    rules_manager = get_rules_manager()
    acao_lower = acao.lower()

    if acao_lower == "listar":
        rules = rules_manager.get_all_rules()

        if not rules:
            console.print("\n[yellow]Nenhuma regra de classificação definida.[/yellow]")
            console.print("[dim]As regras são aprendidas automaticamente ao classificar faturas,[/dim]")
            console.print("[dim]ou podem ser adicionadas manualmente com: bank-extractor regras adicionar[/dim]")
            return

        console.print(f"\n[bold]Regras de Classificação ({len(rules)})[/bold]\n")

        # Group by type
        by_type: dict[str, list] = {}
        for rule in rules:
            by_type.setdefault(rule.rule_type, []).append(rule)

        for rule_type, type_rules in by_type.items():
            type_name = {
                "sender": "Por Remetente",
                "body_pattern": "Por Padrão no Corpo",
                "pdf_pattern": "Por Padrão no PDF",
                "nif": "Por NIF",
            }.get(rule_type, rule_type)

            console.print(f"\n[bold cyan]{type_name}[/bold cyan]")

            table = Table(show_header=True)
            table.add_column("ID", style="dim", width=12)
            table.add_column("Padrão", style="white")
            table.add_column("Categoria", style="green")
            table.add_column("Usos", justify="right")
            table.add_column("Confiança", justify="right")

            for rule in sorted(type_rules, key=lambda r: r.match_count, reverse=True):
                confidence_pct = f"{rule.confidence * 100:.0f}%"
                table.add_row(
                    rule.id[:12],
                    rule.pattern[:40] + "..." if len(rule.pattern) > 40 else rule.pattern,
                    rule.category,
                    str(rule.match_count),
                    confidence_pct,
                )

            console.print(table)

    elif acao_lower == "adicionar":
        if not tipo:
            console.print("[red]Tipo de regra obrigatório. Use --tipo[/red]")
            console.print("Tipos: sender, body_pattern, pdf_pattern, nif")
            raise typer.Exit(1)

        if not padrao:
            console.print("[red]Padrão obrigatório. Use --padrao[/red]")
            raise typer.Exit(1)

        if not categoria:
            console.print("[red]Categoria obrigatória. Use --categoria[/red]")
            console.print(f"Categorias: {', '.join(c.value for c in InvoiceCategory)}")
            raise typer.Exit(1)

        try:
            cat = InvoiceCategory(categoria.lower())
        except ValueError:
            console.print(f"[red]Categoria inválida: {categoria}[/red]")
            raise typer.Exit(1)

        tipo_lower = tipo.lower()
        if tipo_lower == "sender":
            rule = rules_manager.add_sender_rule(padrao, cat, source="manual")
        elif tipo_lower == "body_pattern":
            rule = rules_manager.add_body_pattern_rule(padrao, cat, source="manual")
        elif tipo_lower == "pdf_pattern":
            rule = rules_manager.add_pdf_pattern_rule(padrao, cat, source="manual")
        elif tipo_lower == "nif":
            rule = rules_manager.add_nif_rule(padrao, cat, source="manual")
        else:
            console.print(f"[red]Tipo inválido: {tipo}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[green]Regra adicionada:[/green]")
        console.print(f"  ID: {rule.id}")
        console.print(f"  Tipo: {rule.rule_type}")
        console.print(f"  Padrão: {rule.pattern}")
        console.print(f"  Categoria: {rule.category}")

    elif acao_lower == "remover":
        if not rule_id:
            console.print("[red]ID da regra obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        if rules_manager.delete_rule(rule_id):
            console.print(f"[green]Regra {rule_id} removida.[/green]")
        else:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")

    elif acao_lower == "limpar":
        rules = rules_manager.get_all_rules()
        if not rules:
            console.print("[yellow]Não há regras para limpar.[/yellow]")
            return

        if Confirm.ask(f"Limpar todas as {len(rules)} regras?"):
            count = rules_manager.clear_all_rules()
            console.print(f"[green]{count} regras removidas.[/green]")

    elif acao_lower == "exportar":
        if not ficheiro:
            ficheiro = str(settings.data_dir / "classification_rules_export.json")

        from pathlib import Path
        output_path = Path(ficheiro)

        if rules_manager.export_rules(output_path):
            console.print(f"[green]Regras exportadas para: {output_path}[/green]")
        else:
            console.print("[red]Erro ao exportar regras.[/red]")

    elif acao_lower == "importar":
        if not ficheiro:
            console.print("[red]Ficheiro obrigatório. Use --ficheiro[/red]")
            raise typer.Exit(1)

        from pathlib import Path
        input_path = Path(ficheiro)

        if not input_path.exists():
            console.print(f"[red]Ficheiro não encontrado: {input_path}[/red]")
            raise typer.Exit(1)

        count = rules_manager.import_rules(input_path, merge=True)
        console.print(f"[green]Importadas {count} regras.[/green]")

    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações: listar, adicionar, remover, limpar, exportar, importar")
        raise typer.Exit(1)


@app.command()
def classificar(
    ficheiro: str = typer.Argument(..., help="Caminho do ficheiro PDF a classificar"),
    remetente: Optional[str] = typer.Option(
        None,
        "--remetente", "-r",
        help="Email do remetente (para melhorar classificação)",
    ),
    corpo: Optional[str] = typer.Option(
        None,
        "--corpo", "-b",
        help="Texto do corpo do email (para melhorar classificação)",
    ),
    aprender: bool = typer.Option(
        True,
        "--aprender/--sem-aprender",
        help="Guardar regra se classificação manual",
    ),
):
    """Classificar um ficheiro PDF usando regras automáticas."""
    from pathlib import Path
    from src.core import get_rules_manager
    from src.core.categories import InvoiceCategory
    from src.modules.invoices import PDFInvoiceParser

    file_path = Path(ficheiro)
    if not file_path.exists():
        console.print(f"[red]Ficheiro não encontrado: {file_path}[/red]")
        raise typer.Exit(1)

    console.print(Panel.fit(
        f"[bold blue]Classificação de Documento[/bold blue]\n"
        f"{file_path.name}",
        border_style="blue",
    ))

    # Extract PDF content
    parser = PDFInvoiceParser()
    metadata = parser.parse(file_path)

    pdf_content = metadata.raw_text or ""
    nifs = []

    # Extract NIFs from content
    import re
    nif_pattern = re.compile(r"\b(\d{9})\b")
    if pdf_content:
        matches = nif_pattern.findall(pdf_content)
        for m in matches:
            if m[0] in "12359":
                nifs.append(m)
        nifs = list(set(nifs))

    # Show extracted info
    console.print("\n[bold]Informação extraída:[/bold]")
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Campo", style="cyan")
    info_table.add_column("Valor", style="white")

    info_table.add_row("Fornecedor:", metadata.vendor or "[não detectado]")
    info_table.add_row("Valor:", f"{metadata.total_amount:.2f} EUR" if metadata.total_amount else "[não detectado]")
    info_table.add_row("Data:", metadata.invoice_date.strftime("%d-%m-%Y") if metadata.invoice_date else "[não detectada]")
    info_table.add_row("NIFs:", ", ".join(nifs) if nifs else "[nenhum]")
    if remetente:
        info_table.add_row("Remetente:", remetente)

    console.print(info_table)

    # Classify using rules manager
    rules_manager = get_rules_manager()
    result = rules_manager.classify(
        sender=remetente,
        email_body=corpo,
        pdf_content=pdf_content,
        nifs=nifs,
    )

    # Show result
    console.print(f"\n[bold]Resultado da classificação:[/bold]")
    console.print(f"  Categoria: [green]{result.category.value}[/green]")
    console.print(f"  Confiança: {result.confidence * 100:.0f}%")
    console.print(f"  Método: {result.matched_by}")

    if result.matched_rule:
        console.print(f"  Regra: {result.matched_rule.id} ({result.matched_rule.pattern[:30]}...)")

    # If low confidence, offer manual classification
    if result.confidence < 0.7 or result.category == InvoiceCategory.OUTROS:
        console.print("\n[yellow]Classificação incerta. Deseja classificar manualmente?[/yellow]")
        console.print(f"Categorias: {', '.join(c.value for c in InvoiceCategory)}")

        manual_cat = Prompt.ask("Categoria (Enter para aceitar sugestão)", default=result.category.value)

        try:
            selected_cat = InvoiceCategory(manual_cat.lower())

            if selected_cat != result.category and aprender:
                # Learn from this classification
                console.print("\n[cyan]A aprender com esta classificação...[/cyan]")
                learned_rules = rules_manager.learn_from_classification(
                    sender=remetente,
                    email_body=corpo,
                    pdf_content=pdf_content,
                    nifs=nifs,
                    category=selected_cat,
                )
                if learned_rules:
                    console.print(f"[green]Criadas {len(learned_rules)} regras para classificações futuras.[/green]")

            console.print(f"\n[green]Categoria final: {selected_cat.value}[/green]")

        except ValueError:
            console.print(f"[yellow]Categoria inválida, mantendo: {result.category.value}[/yellow]")


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
