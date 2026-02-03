"""Invoice download and management commands."""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from src import __version__
from src.cli.common import console, parse_date
from src.core import CredentialManager, settings
from src.core.categories import InvoiceCategory, InvoiceCategorizer
from src.modules.invoices import EMAIL_PROVIDERS, EmailClient, EmailFilter, InvoiceDownloader, _DOWNLOAD_COMPLETE
from src.modules.organizer import InvoiceDatabase, InvoiceOrganizer


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
    excluir: Optional[list[str]] = typer.Option(
        None,
        "--excluir", "-e",
        help="Excluir provider(s) específico(s). Pode usar múltiplas vezes: -e gmail -e hotmail_empresa",
    ),
    selecionar: bool = typer.Option(
        False,
        "--selecionar", "-s",
        help="Modo interativo: escolher quais contas usar",
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
    paralelo: bool = typer.Option(
        False,
        "--paralelo", "-p",
        help="Modo paralelo: processar faturas enquanto o download continua",
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

    # Interactive selection mode
    if selecionar:
        providers_to_process = _select_providers_interactive(providers_to_process, conta)
        if not providers_to_process:
            console.print("[yellow]Nenhuma conta selecionada.[/yellow]")
            return

    # Apply exclusions
    if excluir:
        providers_to_process = _apply_exclusions(providers_to_process, excluir, conta)
        if not providers_to_process:
            console.print("[yellow]Todos os providers foram excluídos.[/yellow]")
            return

    # Parse dates or use days
    if inicio:
        start_date = parse_date(inicio)
    else:
        start_date = date.today() - timedelta(days=dias)

    end_date = parse_date(fim) if fim else date.today()

    console.print(f"\n[cyan]Período: {start_date.strftime('%d-%m-%Y')} a {end_date.strftime('%d-%m-%Y')}[/cyan]")
    if conta:
        console.print(f"[cyan]Conta: {conta}[/cyan]")
    if paralelo and organizar:
        console.print(f"[cyan]Modo: Paralelo (processar enquanto descarrega)[/cyan]")

    # Create downloader
    downloader = InvoiceDownloader()
    email_filter = EmailFilter(start_date=start_date, end_date=end_date)

    # Parallel mode: process invoices as they arrive
    if paralelo and organizar:
        _process_invoices_streaming(downloader, providers_to_process, email_filter, conta, mover)
        return

    # Standard mode: download all, then process
    all_invoices = []

    for prov_id in providers_to_process:
        display_name = f"{prov_id.upper()} ({conta})" if conta else prov_id.upper()
        console.print(f"\n[bold cyan]A descarregar de {display_name}...[/bold cyan]")

        # Create progress display for this provider
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=20),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            # Create tasks for different stages
            # Start with indeterminate progress (no bar shown for connect phase)
            current_task = progress.add_task("[cyan]A ligar...", total=None)

            def update_progress(stage: str, current: int, total: int, message: str):
                """Callback to update progress display."""
                if stage == "connect":
                    # For connect stage, don't show percentage - just update text
                    # When current=1, connection is done, keep total=None to hide bar
                    if current >= 1:
                        progress.update(current_task, description=f"[green]✓ Ligado[/green]", total=None)
                    else:
                        progress.update(current_task, description=f"[cyan]{message}", total=None)
                elif stage == "search":
                    progress.update(current_task, description=f"[yellow]{message}", total=total, completed=current)
                elif stage == "fetch":
                    progress.update(current_task, description=f"[blue]{message}", total=total, completed=current)
                elif stage == "download":
                    progress.update(current_task, description=f"[green]{message}", total=total, completed=current)

            try:
                invoices = downloader.download_from(
                    prov_id,
                    email_filter,
                    account=conta,
                    progress_callback=update_progress,
                )
                all_invoices.extend(invoices)

                if invoices:
                    console.print(f"  [green]✓ {len(invoices)} faturas encontradas[/green]")
                else:
                    console.print(f"  [dim]Nenhuma fatura encontrada[/dim]")

            except Exception as e:
                console.print(f"[red]Erro: {e}[/red]")

    if not all_invoices:
        console.print("\n[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    # Show download summary
    console.print(f"\n[green]Descarregadas {len(all_invoices)} faturas para pasta temporária[/green]")
    console.print(f"[dim]Localização: {settings.faturas_temp_dir}[/dim]")

    # Process and organize invoices
    if organizar:
        console.print(f"\n[bold cyan]A organizar faturas...[/bold cyan]")
        console.print("[dim]Para cada fatura desconhecida, será mostrada informação para identificação.[/dim]")
        console.print("[dim]Ficheiros organizados serão movidos da pasta temporária para a pasta final.[/dim]\n")

        processor = InvoiceProcessor()
        processor.process_invoices(all_invoices, interactive=True, move=mover)

        # Show remaining pending files
        _show_pending_temp_files()
    else:
        # Just show what was downloaded
        table = Table(title="Faturas Descarregadas (Pasta Temporária)")
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
        console.print(f"\n[yellow]⚠ Ficheiros na pasta temporária: {settings.faturas_temp_dir}[/yellow]")
        console.print("[dim]Execute novamente com --organizar para categorizar e mover para pastas finais[/dim]")
        console.print("[dim]Ou use: bank-extractor gerir-faturas organizar[/dim]")


def _show_pending_temp_files() -> None:
    """Show any remaining files in the temp folder."""
    temp_files = list(settings.faturas_temp_dir.glob("*.pdf"))

    if temp_files:
        console.print(f"\n[yellow]⚠ {len(temp_files)} ficheiro(s) ainda na pasta temporária:[/yellow]")
        for f in temp_files[:5]:  # Show max 5
            console.print(f"  [dim]• {f.name}[/dim]")
        if len(temp_files) > 5:
            console.print(f"  [dim]... e mais {len(temp_files) - 5} ficheiro(s)[/dim]")
        console.print(f"[dim]Pasta: {settings.faturas_temp_dir}[/dim]")
        console.print("[dim]Use 'bank-extractor pendentes' para processar ficheiros pendentes[/dim]")


def _process_invoices_streaming(
    downloader: InvoiceDownloader,
    providers: list[str],
    email_filter: EmailFilter,
    account: Optional[str],
    move: bool,
) -> None:
    """Process invoices in streaming/parallel mode.

    Downloads and processes invoices simultaneously - as each invoice is downloaded,
    it's immediately presented to the user for processing.

    Args:
        downloader: InvoiceDownloader instance
        providers: List of provider IDs to use
        email_filter: Filter criteria
        account: Optional account name
        move: Whether to move (vs copy) files
    """
    from queue import Empty
    from src.modules.invoices import InvoiceProcessor
    from src.core.logger import set_logging_suppressed

    processor = InvoiceProcessor()
    processor.reset_session_stats()

    console.print(f"\n[bold cyan]Modo paralelo: a descarregar e processar simultaneamente...[/bold cyan]")
    console.print("[dim]Faturas serão apresentadas à medida que são descarregadas.[/dim]\n")

    # Suppress logging during interactive processing
    set_logging_suppressed(True)

    # Shared state for progress updates (thread-safe via simple assignment)
    progress_status = {"message": "A iniciar...", "stage": "connect", "current": 0, "total": 0}

    def streaming_progress(stage: str, current: int, total: int, message: str):
        """Update progress status from download thread."""
        progress_status["stage"] = stage
        progress_status["message"] = message
        progress_status["current"] = current
        progress_status["total"] = total

    # Start streaming download in background
    queue, thread = downloader.download_streaming_multi(
        providers=providers,
        email_filter=email_filter,
        account=account,
        progress_callback=streaming_progress,
    )

    # Track invoices for rule application
    processed_count = 0
    pending_invoices = []  # Store invoices waiting to be processed
    auto_actions = {}  # Maps invoice index to (action, rule_name)
    download_complete = False

    # Use a status line that updates in place
    from rich.status import Status

    try:
        with Status("[yellow]A aguardar...[/yellow]", console=console) as status:
            while True:
                try:
                    # Get next invoice with short timeout
                    item = queue.get(timeout=0.3)

                    if item is _DOWNLOAD_COMPLETE:
                        download_complete = True
                        break

                    # Store the invoice
                    pending_invoices.append(item)

                    # Stop status spinner while processing
                    status.stop()

                    # Process this invoice
                    invoice = item
                    invoice_idx = len(pending_invoices) - 1

                    # Check if this invoice has an auto-action from a previously created rule
                    auto_action = auto_actions.get(invoice_idx)

                    if not auto_action:
                        console.print(f"\n[cyan]━━━ Fatura {invoice_idx + 1} ━━━[/cyan]")

                    result, rule_condition, action = processor.process_invoice(
                        invoice,
                        interactive=True,
                        move=move,
                        auto_action=auto_action,
                        suppress_output=bool(auto_action),
                    )
                    processed_count += 1

                    # If user created an ignore/delete rule, create it and apply to pending
                    if rule_condition and action:
                        rule = processor._create_ignore_rule(
                            rule_condition,
                            action,
                            rule_condition.pattern,
                        )
                        console.print(
                            f"\n[dim]Regra criada: '{rule.name}' - "
                            f"será aplicada a documentos futuros desta sessão[/dim]"
                        )

                    # Resume status spinner
                    status.start()

                except Empty:
                    # Update status bar with current progress
                    stage = progress_status["stage"]
                    msg = progress_status["message"]
                    current = progress_status["current"]
                    total = progress_status["total"]

                    if stage == "connect":
                        status.update(f"[cyan]⟳ {msg}[/cyan]")
                    elif stage == "fetch":
                        if total > 0:
                            status.update(f"[yellow]⟳ Email {current}/{total} | Processadas: {processed_count}[/yellow]")
                        else:
                            status.update(f"[yellow]⟳ {msg}[/yellow]")
                    elif stage == "download":
                        status.update(f"[green]⟳ {msg} | Total: {processed_count}[/green]")
                    else:
                        status.update(f"[blue]⟳ {msg}[/blue]")

                    # Check if thread is still alive
                    if not thread.is_alive():
                        # Thread finished, drain remaining items
                        status.stop()
                        while True:
                            try:
                                item = queue.get_nowait()
                                if item is _DOWNLOAD_COMPLETE:
                                    download_complete = True
                                    break

                                # Store and process remaining
                                pending_invoices.append(item)
                                invoice = item
                                invoice_idx = len(pending_invoices) - 1
                                auto_action = auto_actions.get(invoice_idx)

                                if not auto_action:
                                    console.print(f"\n[cyan]━━━ Fatura {invoice_idx + 1} ━━━[/cyan]")

                                result, rule_condition, action = processor.process_invoice(
                                    invoice,
                                    interactive=True,
                                    move=move,
                                    auto_action=auto_action,
                                    suppress_output=bool(auto_action),
                                )
                                processed_count += 1

                                # If user created an ignore/delete rule, create it
                                if rule_condition and action:
                                    rule = processor._create_ignore_rule(
                                        rule_condition,
                                        action,
                                        rule_condition.pattern,
                                    )
                                    console.print(f"\n[dim]Regra criada: '{rule.name}'[/dim]")

                            except Empty:
                                break
                        break
                    continue

        # Wait for thread to fully complete
        thread.join(timeout=2.0)

    finally:
        # Always re-enable logging
        set_logging_suppressed(False)

    # Show comprehensive session summary (after all user interaction is done)
    processor.show_session_summary()

    if processed_count == 0:
        console.print("[yellow]Nenhuma fatura encontrada.[/yellow]")

    # Show remaining files in temp folder
    _show_pending_temp_files()


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


def _get_configured_accounts() -> list[tuple[str, Optional[str]]]:
    """Get all configured email accounts.

    Returns:
        List of tuples (provider_id, account_name or None for default)
    """
    accounts = []

    for provider_id in EMAIL_PROVIDERS.keys():
        # Check default account (no account suffix)
        if CredentialManager.has_credential(provider_id, "email"):
            accounts.append((provider_id, None))

        # Check named accounts (e.g., gmail_pessoal, hotmail_empresa)
        # Common account names to check
        for account_name in ["pessoal", "empresa", "trabalho", "personal", "work"]:
            key = f"{provider_id}_{account_name}"
            if CredentialManager.has_credential(key, "email"):
                accounts.append((provider_id, account_name))

    return accounts


def _select_providers_interactive(
    providers: list[str],
    default_account: Optional[str] = None,
) -> list[str]:
    """Interactive selection of which providers/accounts to use.

    Args:
        providers: List of available providers
        default_account: Default account name if specified

    Returns:
        List of selected providers
    """
    # Get all configured accounts
    configured = _get_configured_accounts()

    if not configured:
        console.print("[yellow]Nenhuma conta de email configurada.[/yellow]")
        console.print("[dim]Use: bank-extractor faturas gmail --config[/dim]")
        return []

    # Filter by requested providers
    available = [(p, a) for p, a in configured if p in providers]

    if not available:
        console.print("[yellow]Nenhuma conta configurada para os providers selecionados.[/yellow]")
        return []

    console.print("\n[bold cyan]Selecionar contas de email:[/bold cyan]")
    console.print("[dim]Escolha quais contas usar para download de faturas[/dim]\n")

    # Show options
    options = []
    for i, (prov, acc) in enumerate(available, 1):
        display = f"{prov.upper()} ({acc})" if acc else prov.upper()
        options.append((prov, acc, display))
        console.print(f"  {i}. {display}")

    console.print(f"  0. [dim]Todas as contas[/dim]")
    console.print()

    # Get selection
    selection = Prompt.ask(
        "Contas a usar (números separados por vírgula, ou 0 para todas)",
        default="0"
    )

    if selection.strip() == "0":
        # Return all providers (accounts will be handled in the main loop)
        return providers

    # Parse selection
    selected_providers = []
    selected_indices = []
    try:
        for s in selection.split(","):
            idx = int(s.strip())
            if 1 <= idx <= len(options):
                selected_indices.append(idx - 1)
    except ValueError:
        console.print("[red]Seleção inválida[/red]")
        return []

    # Build result - for now we return providers
    # The account selection is stored for later use
    for idx in selected_indices:
        prov, acc, _ = options[idx]
        if prov not in selected_providers:
            selected_providers.append(prov)

    return selected_providers


def _apply_exclusions(
    providers: list[str],
    exclusions: list[str],
    account: Optional[str] = None,
) -> list[str]:
    """Apply exclusions to provider list.

    Args:
        providers: List of providers to process
        exclusions: List of providers/accounts to exclude
        account: Current account filter

    Returns:
        Filtered list of providers
    """
    result = []

    for prov in providers:
        # Check if provider is excluded
        if prov in exclusions or prov.lower() in [e.lower() for e in exclusions]:
            console.print(f"[dim]Excluído: {prov}[/dim]")
            continue

        # Check if provider_account is excluded (e.g., gmail_pessoal)
        if account:
            full_key = f"{prov}_{account}"
            if full_key in exclusions or full_key.lower() in [e.lower() for e in exclusions]:
                console.print(f"[dim]Excluído: {full_key}[/dim]")
                continue

        result.append(prov)

    return result


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
