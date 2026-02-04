"""Invoice download and management commands."""

from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt
from rich.table import Table

from src import __version__
from src.cli.common import console, parse_date
from src.core import CredentialManager, settings
from src.modules.invoices import EMAIL_PROVIDERS, EmailFilter, InvoiceDownloader, _DOWNLOAD_COMPLETE


def faturas(
    provider: str = typer.Argument(
        "todos",
        help="Provider de email: gmail, hotmail, ou 'todos'",
    ),
    dias: int = typer.Option(
        settings.invoice_days_default,
        "--dias",
        "-d",
        help="Número de dias a pesquisar (padrão: 30)",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio",
        "-i",
        help="Data início (DD-MM-YYYY). Sobrepõe --dias.",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim",
        "-f",
        help="Data fim (DD-MM-YYYY). Default: hoje.",
    ),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta (ex: pessoal, empresa). Permite múltiplas contas por provider.",
    ),
    excluir: Optional[list[str]] = typer.Option(
        None,
        "--excluir",
        "-e",
        help="Excluir provider(s) específico(s). Pode usar múltiplas vezes: -e gmail -e hotmail_empresa",
    ),
    selecionar: bool = typer.Option(
        False,
        "--selecionar",
        "-s",
        help="Modo interativo: escolher quais contas usar",
    ),
    config_creds: bool = typer.Option(
        False,
        "--config",
        "-c",
        help="Configurar credenciais de email",
    ),
    organizar: bool = typer.Option(
        True,
        "--organizar/--sem-organizar",
        help="Organizar faturas após download (default: sim)",
    ),
    mover: bool = typer.Option(
        False,
        "--mover",
        "-m",
        help="Mover ficheiros em vez de copiar ao organizar",
    ),
    paralelo: bool = typer.Option(
        False,
        "--paralelo",
        "-p",
        help="Modo paralelo: processar faturas enquanto o download continua",
    ),
):
    """Descarregar faturas do email."""
    from src.modules.invoices import InvoiceProcessor

    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
            "Download de faturas por email",
            border_style="blue",
        )
    )

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

    console.print(
        f"\n[cyan]Período: {start_date.strftime('%d-%m-%Y')} a {end_date.strftime('%d-%m-%Y')}[/cyan]"
    )
    if conta:
        console.print(f"[cyan]Conta: {conta}[/cyan]")
    if paralelo and organizar:
        console.print("[cyan]Modo: Paralelo (processar enquanto descarrega)[/cyan]")

    # Create downloader and inbox database
    from src.modules.invoices.inbox_db import InboxDatabase
    from src.modules.invoices.base import DownloadedInvoice

    downloader = InvoiceDownloader()
    inbox_db = InboxDatabase()
    email_filter = EmailFilter(start_date=start_date, end_date=end_date)

    # Parallel mode: process invoices as they arrive
    if paralelo and organizar:
        _process_invoices_streaming(downloader, providers_to_process, email_filter, conta, mover)
        return

    # Standard mode: use inbox database for deduplication
    total_emails_added = 0
    total_emails_skipped = 0
    total_attachments_added = 0
    total_attachments_skipped = 0

    for prov_id in providers_to_process:
        display_name = f"{prov_id.upper()} ({conta})" if conta else prov_id.upper()
        console.print(f"\n[bold cyan]━━━ {display_name} ━━━[/bold cyan]")

        # Create progress display for this provider
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TextColumn("•"),
            TextColumn("{task.completed}/{task.total}", style="cyan"),
            console=console,
            transient=False,
            refresh_per_second=10,
        ) as progress:
            # Track different stages
            search_task = None
            download_task = None

            def update_progress(stage: str, current: int, total: int, message: str):
                """Callback to update progress display."""
                nonlocal search_task, download_task

                if stage == "connect":
                    if current >= 1:
                        console.print("  [green]✓[/green] Ligado ao servidor")
                    # Connection stage - no progress bar needed
                elif stage == "search":
                    if search_task is None:
                        search_task = progress.add_task(
                            "[yellow]A pesquisar remetentes...", total=total or 1
                        )
                    progress.update(
                        search_task,
                        description=f"[yellow]A pesquisar: {message.split(':')[-1].strip()[:25]}",
                        completed=current,
                        total=total or 1,
                    )
                elif stage == "fetch":
                    # Hide search task when fetch starts
                    if search_task is not None:
                        progress.update(search_task, visible=False)
                    if download_task is None and total > 0:
                        download_task = progress.add_task("[blue]A obter emails...", total=total)
                    if download_task is not None:
                        progress.update(
                            download_task,
                            description=f"[blue]Email {current}/{total}",
                            completed=current,
                            total=total,
                        )
                elif stage == "download":
                    if download_task is not None:
                        progress.update(
                            download_task,
                            description=f"[green]A processar {current}/{total}",
                            completed=current,
                            total=total or current,
                        )

            try:
                # Use scrape_to_inbox for automatic deduplication
                ea, es, aa, as_ = downloader.scrape_to_inbox(
                    prov_id,
                    email_filter,
                    account=conta,
                    progress_callback=update_progress,
                )

                total_emails_added += ea
                total_emails_skipped += es
                total_attachments_added += aa
                total_attachments_skipped += as_

            except Exception as e:
                console.print(f"  [red]✗ Erro: {e}[/red]")
                ea, es, aa, as_ = 0, 0, 0, 0

        # Summary after progress bar
        if aa > 0:
            console.print(f"  [green]✓ {aa} faturas novas[/green]", end="")
            if as_ > 0:
                console.print(f" [dim]({as_} duplicadas)[/dim]")
            else:
                console.print()
        elif es > 0:
            console.print(f"  [dim]✓ {ea + es} emails verificados, todos já existiam[/dim]")
        else:
            console.print("  [dim]Nenhuma fatura encontrada[/dim]")

    if total_attachments_added == 0:
        if total_attachments_skipped > 0 or total_emails_skipped > 0:
            console.print(
                f"\n[yellow]Nenhuma fatura nova. {total_attachments_skipped + total_emails_skipped} já existiam na BD.[/yellow]"
            )
        else:
            console.print("\n[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    # Show download summary
    console.print(
        f"\n[green]Adicionadas {total_attachments_added} faturas novas à BD inbox[/green]"
    )
    if total_attachments_skipped > 0:
        console.print(f"[dim]{total_attachments_skipped} duplicadas ignoradas[/dim]")

    # Process and organize invoices from inbox database
    if organizar:
        console.print("\n[bold cyan]A organizar faturas...[/bold cyan]")
        console.print(
            "[dim]Para cada fatura desconhecida, será mostrada informação para identificação.[/dim]"
        )
        console.print(
            "[dim]Ficheiros organizados serão movidos da pasta temporária para a pasta final.[/dim]\n"
        )

        # Get pending attachments from inbox and convert to DownloadedInvoice
        pending_attachments = inbox_db.get_pending_attachments(limit=total_attachments_added + 10)

        all_invoices = []
        attachment_map = {}  # Map invoice index to attachment for status updates

        for att in pending_attachments:
            if not Path(att.file_path).exists():
                inbox_db.mark_deleted(
                    att.id, reason="file_not_found", reason_label="Ficheiro não encontrado"
                )
                continue

            invoice = DownloadedInvoice(
                provider=att.email.provider,
                sender=att.email.sender,
                subject=att.email.subject,
                date=att.email.email_date,
                file_path=Path(att.file_path),
                file_name=att.file_name,
                file_size=att.file_size,
                email_body=att.email.body,
                message_id=att.email.message_id,
            )
            attachment_map[len(all_invoices)] = att
            all_invoices.append(invoice)

        if not all_invoices:
            console.print("[yellow]Nenhum ficheiro válido para processar.[/yellow]")
            return

        processor = InvoiceProcessor()

        # Process with callback to update inbox database
        results = []
        processor.reset_session_stats()

        for i, invoice in enumerate(all_invoices):
            att = attachment_map[i]

            result, rule_condition, action = processor.process_invoice(
                invoice,
                interactive=True,
                move=mover,
            )
            results.append(result)

            # Update inbox database based on result
            if result.success and result.destination_path:
                inbox_db.mark_processed(
                    att.id,
                    destination_path=str(result.destination_path),
                    entity_name=result.entity_name,
                )
            elif action == "delete":
                inbox_db.mark_deleted(
                    att.id, reason="manual", reason_label="Eliminado pelo utilizador"
                )
            elif action == "ignore" or (not result.success and "Ignorado" in (result.error or "")):
                inbox_db.mark_ignored(
                    att.id, reason="manual", reason_label="Ignorado pelo utilizador"
                )

        processor.show_session_summary()

        # Show remaining pending in inbox
        _show_pending_inbox_files(inbox_db)
    else:
        # Just show what was downloaded (from inbox database)
        pending_attachments = inbox_db.get_pending_attachments(limit=100)

        if pending_attachments:
            table = Table(title="Faturas Pendentes (BD Inbox)")
            table.add_column("ID", style="dim", width=5)
            table.add_column("Provider", style="cyan")
            table.add_column("Remetente", style="green", max_width=30)
            table.add_column("Data", style="yellow")
            table.add_column("Ficheiro", style="white")
            table.add_column("Tamanho", style="magenta", justify="right")

            for att in pending_attachments:
                size_kb = att.file_size / 1024
                table.add_row(
                    str(att.id),
                    att.email.provider,
                    (
                        att.email.sender[:28] + ".."
                        if len(att.email.sender) > 30
                        else att.email.sender
                    ),
                    att.email.email_date.strftime("%d-%m-%Y"),
                    att.file_name[:30] + ".." if len(att.file_name) > 32 else att.file_name,
                    f"{size_kb:.1f} KB",
                )

            console.print(table)

        console.print(
            "\n[cyan]Use 'bank-extractor faturas-processar-inbox' para processar as faturas[/cyan]"
        )
        console.print("[dim]Ou execute novamente com --organizar para processar agora[/dim]")


def _show_pending_temp_files() -> None:
    """Show any remaining files in the temp folder (legacy)."""
    temp_files = list(settings.faturas_temp_dir.glob("*.pdf"))

    if temp_files:
        console.print(
            f"\n[yellow]⚠ {len(temp_files)} ficheiro(s) ainda na pasta temporária:[/yellow]"
        )
        for f in temp_files[:5]:  # Show max 5
            console.print(f"  [dim]• {f.name}[/dim]")
        if len(temp_files) > 5:
            console.print(f"  [dim]... e mais {len(temp_files) - 5} ficheiro(s)[/dim]")
        console.print(f"[dim]Pasta: {settings.faturas_temp_dir}[/dim]")
        console.print("[dim]Use 'bank-extractor faturas-processar-inbox' para processar[/dim]")


def _show_pending_inbox_files(inbox_db) -> None:
    """Show pending files from inbox database."""
    stats = inbox_db.get_status_counts()
    pending_count = stats.get("pending", 0)

    if pending_count > 0:
        console.print(f"\n[cyan]Inbox: {pending_count} ficheiro(s) pendente(s)[/cyan]")
        console.print("[dim]Use 'bank-extractor faturas-processar-inbox' para processar[/dim]")
        console.print("[dim]Use 'bank-extractor faturas-inbox --stats' para ver estatísticas[/dim]")


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

    console.print(
        "\n[bold cyan]Modo paralelo: a descarregar e processar simultaneamente...[/bold cyan]"
    )
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

    # Use a status line that updates in place
    from rich.status import Status

    try:
        with Status("[yellow]A aguardar...[/yellow]", console=console) as status:
            while True:
                try:
                    # Get next invoice with short timeout
                    item = queue.get(timeout=0.3)

                    if item is _DOWNLOAD_COMPLETE:
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
                            status.update(
                                f"[yellow]⟳ Email {current}/{total} | Processadas: {processed_count}[/yellow]"
                            )
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
                                    break

                                # Store and process remaining
                                pending_invoices.append(item)
                                invoice = item
                                invoice_idx = len(pending_invoices) - 1
                                auto_action = auto_actions.get(invoice_idx)

                                if not auto_action:
                                    console.print(
                                        f"\n[cyan]━━━ Fatura {invoice_idx + 1} ━━━[/cyan]"
                                    )

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

    console.print("  0. [dim]Todas as contas[/dim]")
    console.print()

    # Get selection
    selection = Prompt.ask(
        "Contas a usar (números separados por vírgula, ou 0 para todas)", default="0"
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


def faturas_credenciais(
    provider: Optional[str] = typer.Argument(
        None,
        help="Provider de email: gmail, hotmail (sem argumento lista contas)",
    ),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta (ex: pessoal, empresa)",
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
    """Gerir credenciais de email.

    Sem argumentos: lista contas configuradas.
    Com provider: configura credenciais.
    Com --apagar: remove credenciais (pede confirmação).

    Exemplos:
        faturas credenciais                     # Lista contas
        faturas credenciais gmail --conta pessoal   # Configura
        faturas credenciais gmail --apagar      # Apaga
    """
    from rich.table import Table

    # No provider = list accounts
    if provider is None:
        accounts = _get_configured_accounts()

        if not accounts:
            console.print("[yellow]Nenhuma conta de email configurada.[/yellow]")
            console.print("\n[dim]Para configurar:[/dim]")
            console.print("  bank-extractor faturas credenciais gmail --conta pessoal")
            return

        console.print("\n[bold cyan]Contas de email configuradas:[/bold cyan]\n")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Provider", style="cyan")
        table.add_column("Conta", style="green")
        table.add_column("Email", style="white")

        for provider_id, account_name in accounts:
            credential_key = f"{provider_id}_{account_name}" if account_name else provider_id
            email = CredentialManager.get_credential(credential_key, "email") or "[não definido]"
            account_display = account_name or "(default)"
            table.add_row(provider_id.upper(), account_display, email)

        console.print(table)
        console.print(f"\n[dim]Total: {len(accounts)} conta(s) configurada(s)[/dim]")
        console.print("\n[dim]Para apagar: faturas credenciais <provider> --apagar[/dim]")
        return

    # Validate provider
    if provider.lower() not in EMAIL_PROVIDERS:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        console.print(f"Providers disponíveis: {', '.join(EMAIL_PROVIDERS.keys())}")
        raise typer.Exit(1)

    credential_key = f"{provider.lower()}_{conta}" if conta else provider.lower()
    display_name = f"{provider.upper()} ({conta})" if conta else provider.upper()

    # Delete mode
    if apagar:
        email = CredentialManager.get_credential(credential_key, "email")
        if not email:
            console.print(f"[yellow]Não existem credenciais para {display_name}.[/yellow]")
            return

        console.print("\n[bold red]APAGAR credenciais de:[/bold red]")
        console.print(f"  Provider: {provider.upper()}")
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
        return

    # Configure mode
    console.print(f"\n[bold cyan]Configurar credenciais {display_name}[/bold cyan]")

    if provider.lower() == "gmail":
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


# ==================== Inbox System Commands ====================


def faturas_scrape(
    provider: str = typer.Argument(
        "todos",
        help="Provider de email: gmail, hotmail, ou 'todos'",
    ),
    dias: int = typer.Option(
        settings.invoice_days_default,
        "--dias",
        "-d",
        help="Número de dias a pesquisar (padrão: 30)",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio",
        "-i",
        help="Data início (DD-MM-YYYY). Sobrepõe --dias.",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim",
        "-f",
        help="Data fim (DD-MM-YYYY). Default: hoje.",
    ),
    conta: Optional[str] = typer.Option(
        None,
        "--conta",
        help="Nome da conta (ex: pessoal, empresa).",
    ),
):
    """Descarregar emails para inbox (sem processar).

    Este comando descarrega emails e anexos para a base de dados inbox
    para serem processados mais tarde. Faz deduplicação automática.

    Exemplos:
        bank-extractor faturas scrape gmail --dias 30
        bank-extractor faturas scrape todos --dias 60 --conta pessoal
    """
    from src import __version__

    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
            "Scrape de faturas para inbox",
            border_style="blue",
        )
    )

    # Validate provider
    if provider.lower() == "todos":
        providers_to_process = list(EMAIL_PROVIDERS.keys())
    elif provider.lower() in EMAIL_PROVIDERS:
        providers_to_process = [provider.lower()]
    else:
        console.print(f"[red]Provider desconhecido: {provider}[/red]")
        console.print(f"Providers disponíveis: {', '.join(EMAIL_PROVIDERS.keys())}, todos")
        raise typer.Exit(1)

    # Parse dates
    if inicio:
        start_date = parse_date(inicio)
    else:
        start_date = date.today() - timedelta(days=dias)

    end_date = parse_date(fim) if fim else date.today()

    console.print(
        f"\n[cyan]Período: {start_date.strftime('%d-%m-%Y')} a {end_date.strftime('%d-%m-%Y')}[/cyan]"
    )
    if conta:
        console.print(f"[cyan]Conta: {conta}[/cyan]")

    # Create downloader
    downloader = InvoiceDownloader()
    email_filter = EmailFilter(start_date=start_date, end_date=end_date)

    total_emails_added = 0
    total_emails_skipped = 0
    total_attachments_added = 0
    total_attachments_skipped = 0

    for prov_id in providers_to_process:
        display_name = f"{prov_id.upper()} ({conta})" if conta else prov_id.upper()
        console.print(f"\n[bold cyan]A fazer scrape de {display_name}...[/bold cyan]")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=20),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            current_task = progress.add_task("[cyan]A ligar...", total=None)

            def update_progress(stage: str, current: int, total: int, message: str):
                if stage == "connect":
                    if current >= 1:
                        progress.update(
                            current_task, description="[green]✓ Ligado[/green]", total=None
                        )
                    else:
                        progress.update(current_task, description=f"[cyan]{message}", total=None)
                elif stage == "search":
                    progress.update(
                        current_task,
                        description=f"[yellow]{message}",
                        total=total,
                        completed=current,
                    )
                elif stage == "fetch":
                    progress.update(
                        current_task, description=f"[blue]{message}", total=total, completed=current
                    )
                elif stage == "download":
                    progress.update(
                        current_task,
                        description=f"[green]{message}",
                        total=total,
                        completed=current,
                    )

            try:
                ea, es, aa, as_ = downloader.scrape_to_inbox(
                    prov_id,
                    email_filter,
                    account=conta,
                    progress_callback=update_progress,
                )

                total_emails_added += ea
                total_emails_skipped += es
                total_attachments_added += aa
                total_attachments_skipped += as_

                console.print(f"  [green]✓ {ea} emails novos, {aa} anexos novos[/green]")
                if es > 0 or as_ > 0:
                    console.print(f"  [dim]{es} emails já existiam, {as_} anexos duplicados[/dim]")

            except Exception as e:
                console.print(f"[red]Erro: {e}[/red]")

    # Summary
    console.print("\n[bold]━━━ Resumo do Scrape ━━━[/bold]")
    console.print(f"  Emails novos: [green]{total_emails_added}[/green]")
    console.print(f"  Emails existentes: [dim]{total_emails_skipped}[/dim]")
    console.print(f"  Anexos novos: [green]{total_attachments_added}[/green]")
    console.print(f"  Anexos duplicados: [dim]{total_attachments_skipped}[/dim]")

    if total_attachments_added > 0:
        console.print(
            "\n[cyan]Use 'bank-extractor faturas processar-inbox' para processar os anexos[/cyan]"
        )


def faturas_inbox(
    stats: bool = typer.Option(
        False,
        "--stats",
        "-s",
        help="Mostrar estatísticas do inbox",
    ),
    listar: bool = typer.Option(
        False,
        "--listar",
        "-l",
        help="Listar anexos pendentes",
    ),
    status: Optional[str] = typer.Option(
        None,
        "--status",
        help="Filtrar por status: pending, processed, ignored, deleted",
    ),
    remetente: Optional[str] = typer.Option(
        None,
        "--remetente",
        "-r",
        help="Filtrar por remetente (parcial)",
    ),
    limite: int = typer.Option(
        50,
        "--limite",
        help="Limite de resultados a mostrar",
    ),
    migrar: bool = typer.Option(
        False,
        "--migrar",
        help="Migrar dados existentes para a base de dados inbox",
    ),
):
    """Gerir o inbox de faturas.

    Mostra estatísticas, lista anexos, ou migra dados existentes.

    Exemplos:
        bank-extractor faturas inbox --stats
        bank-extractor faturas inbox --listar
        bank-extractor faturas inbox --status ignored
        bank-extractor faturas inbox --migrar
    """
    from src import __version__
    from src.modules.invoices.inbox_db import InboxDatabase
    from src.modules.invoices.inbox_models import AttachmentStatus

    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n" "Gestão do Inbox",
            border_style="blue",
        )
    )

    inbox_db = InboxDatabase()

    # Handle migration
    if migrar:
        _migrate_to_inbox(inbox_db)
        return

    # Default to stats if no option specified
    if not stats and not listar and not status and not remetente:
        stats = True

    # Show statistics
    if stats:
        inbox_stats = inbox_db.get_statistics()

        console.print("\n[bold cyan]Estatísticas do Inbox[/bold cyan]\n")

        # General stats table
        general_table = Table(title="Resumo Geral")
        general_table.add_column("Métrica", style="cyan")
        general_table.add_column("Valor", style="green", justify="right")

        general_table.add_row("Total de emails", str(inbox_stats["total_emails"]))
        general_table.add_row("Total de anexos", str(inbox_stats["total_attachments"]))
        general_table.add_row("Tamanho total", f"{inbox_stats['total_size_mb']:.2f} MB")

        console.print(general_table)

        # Status breakdown
        console.print()
        status_table = Table(title="Por Status")
        status_table.add_column("Status", style="cyan")
        status_table.add_column("Quantidade", style="green", justify="right")

        for status_name, count in inbox_stats["by_status"].items():
            status_style = {
                "pending": "yellow",
                "processed": "green",
                "ignored": "dim",
                "deleted": "red",
            }.get(status_name, "white")
            status_table.add_row(f"[{status_style}]{status_name}[/{status_style}]", str(count))

        console.print(status_table)

        # Provider breakdown
        if inbox_stats["by_provider"]:
            console.print()
            prov_table = Table(title="Por Provider")
            prov_table.add_column("Provider", style="cyan")
            prov_table.add_column("Emails", style="green", justify="right")

            for prov, count in inbox_stats["by_provider"].items():
                prov_table.add_row(prov.upper(), str(count))

            console.print(prov_table)

        return

    # List attachments by status or search
    attachments = []

    if status:
        try:
            status_enum = AttachmentStatus(status.lower())
            attachments = inbox_db.get_attachments_by_status(status_enum, limit=limite)
        except ValueError:
            console.print(f"[red]Status inválido: {status}[/red]")
            console.print("Status válidos: pending, processed, ignored, deleted")
            raise typer.Exit(1)
    elif remetente:
        attachments = inbox_db.search_by_sender(remetente, limit=limite)
    elif listar:
        attachments = inbox_db.get_pending_attachments(limit=limite)

    if not attachments:
        console.print("[yellow]Nenhum anexo encontrado.[/yellow]")
        return

    # Display attachments
    table = Table(title=f"Anexos ({len(attachments)} resultados)")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Remetente", style="cyan", max_width=30)
    table.add_column("Ficheiro", style="white", max_width=35)
    table.add_column("Data", style="yellow", width=10)
    table.add_column("Status", style="green", width=10)
    table.add_column("Tamanho", style="magenta", justify="right", width=8)

    for att in attachments:
        status_style = {
            "pending": "yellow",
            "processed": "green",
            "ignored": "dim",
            "deleted": "red",
        }.get(att.status, "white")

        sender_display = (
            att.email.sender[:28] + ".." if len(att.email.sender) > 30 else att.email.sender
        )
        file_display = att.file_name[:33] + ".." if len(att.file_name) > 35 else att.file_name
        size_kb = att.file_size / 1024

        table.add_row(
            str(att.id),
            sender_display,
            file_display,
            att.email.email_date.strftime("%d-%m-%Y"),
            f"[{status_style}]{att.status}[/{status_style}]",
            f"{size_kb:.1f} KB",
        )

    console.print(table)


def _migrate_to_inbox(inbox_db) -> None:
    """Migrate existing data to inbox database."""
    import json
    from datetime import datetime
    from pathlib import Path

    console.print("\n[bold cyan]Migração de dados para inbox[/bold cyan]\n")

    migrated_files = 0
    migrated_pending = 0

    # 1. Migrate files in _pendentes folder
    console.print("[dim]1. A verificar ficheiros em _pendentes/...[/dim]")

    pending_dir = settings.faturas_temp_dir
    if pending_dir.exists():
        pdf_files = list(pending_dir.glob("*.pdf"))

        for pdf_file in pdf_files:
            try:
                # Compute hash
                file_hash = inbox_db.compute_file_hash(pdf_file)

                # Check if already exists
                if inbox_db.attachment_exists_by_hash(file_hash):
                    console.print(f"  [dim]Já existe: {pdf_file.name}[/dim]")
                    continue

                # Create "manual import" email record
                email_id = inbox_db.add_email(
                    provider="manual_import",
                    message_id=f"manual_{file_hash[:32]}",
                    sender="manual_import@local",
                    subject=f"Importação manual: {pdf_file.name}",
                    email_date=datetime.fromtimestamp(pdf_file.stat().st_mtime),
                    body=None,
                )

                # Add attachment
                inbox_db.add_attachment(
                    email_id=email_id,
                    file_name=pdf_file.name,
                    file_path=str(pdf_file),
                    file_size=pdf_file.stat().st_size,
                    content_hash=file_hash,
                )

                migrated_files += 1
                console.print(f"  [green]✓ Migrado: {pdf_file.name}[/green]")

            except Exception as e:
                console.print(f"  [red]Erro em {pdf_file.name}: {e}[/red]")

    console.print(f"  [dim]Total: {migrated_files} ficheiros migrados[/dim]")

    # 2. Migrate pending_documents.json
    console.print("\n[dim]2. A verificar pending_documents.json...[/dim]")

    pending_json = settings.data_dir / "pending_documents.json"
    if pending_json.exists():
        try:
            with open(pending_json, "r", encoding="utf-8") as f:
                pending_docs = json.load(f)

            for doc in pending_docs:
                try:
                    file_path = Path(doc.get("file_path", ""))

                    if not file_path.exists():
                        console.print(f"  [dim]Ficheiro não existe: {file_path.name}[/dim]")
                        continue

                    # Compute hash
                    file_hash = inbox_db.compute_file_hash(file_path)

                    # Check if already exists
                    if inbox_db.attachment_exists_by_hash(file_hash):
                        console.print(f"  [dim]Já existe: {file_path.name}[/dim]")
                        continue

                    # Parse email date
                    email_date_str = doc.get("email_date")
                    if email_date_str:
                        try:
                            email_date = datetime.fromisoformat(email_date_str)
                        except ValueError:
                            email_date = datetime.now()
                    else:
                        email_date = datetime.now()

                    # Create email record
                    email_id = inbox_db.add_email(
                        provider="pending_migration",
                        message_id=f"pending_{file_hash[:32]}",
                        sender=doc.get("sender", "unknown@local"),
                        subject=doc.get("subject", file_path.name),
                        email_date=email_date,
                        body=None,
                    )

                    # Add attachment
                    att_id = inbox_db.add_attachment(
                        email_id=email_id,
                        file_name=file_path.name,
                        file_path=str(file_path),
                        file_size=file_path.stat().st_size,
                        content_hash=file_hash,
                    )

                    # If it was ignored, mark as such
                    ignore_reason = doc.get("ignore_reason")
                    if ignore_reason:
                        inbox_db.mark_ignored(
                            att_id,
                            reason=ignore_reason,
                            reason_label=doc.get("ignore_reason_label"),
                        )

                    migrated_pending += 1
                    console.print(f"  [green]✓ Migrado: {file_path.name}[/green]")

                except Exception as e:
                    console.print(f"  [red]Erro: {e}[/red]")

        except json.JSONDecodeError as e:
            console.print(f"  [red]Erro ao ler pending_documents.json: {e}[/red]")

    console.print(f"  [dim]Total: {migrated_pending} documentos pendentes migrados[/dim]")

    # Summary
    console.print("\n[bold]━━━ Resumo da Migração ━━━[/bold]")
    console.print(f"  Ficheiros de _pendentes/: [green]{migrated_files}[/green]")
    console.print(f"  Documentos de pending_documents.json: [green]{migrated_pending}[/green]")

    if migrated_files > 0 or migrated_pending > 0:
        console.print(
            "\n[cyan]Use 'bank-extractor faturas inbox --stats' para ver o estado actual[/cyan]"
        )


def faturas_processar_inbox(
    limite: int = typer.Option(
        None,
        "--limite",
        "-n",
        help="Número máximo de anexos a processar",
    ),
    remetente: Optional[str] = typer.Option(
        None,
        "--remetente",
        "-r",
        help="Filtrar por remetente (parcial)",
    ),
    interativo: bool = typer.Option(
        True,
        "--interativo/--auto",
        help="Modo interativo (default) ou automático",
    ),
    mover: bool = typer.Option(
        False,
        "--mover",
        "-m",
        help="Mover ficheiros em vez de copiar ao organizar",
    ),
):
    """Processar anexos pendentes do inbox.

    Processa os anexos pendentes na base de dados inbox,
    permitindo organizar, ignorar ou eliminar cada um.

    Exemplos:
        bank-extractor faturas processar-inbox
        bank-extractor faturas processar-inbox --limite 10
        bank-extractor faturas processar-inbox --remetente vodafone
    """
    from src import __version__
    from src.modules.invoices import InvoiceProcessor
    from src.modules.invoices.inbox_db import InboxDatabase
    from src.modules.invoices.base import DownloadedInvoice

    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n" "Processar anexos do inbox",
            border_style="blue",
        )
    )

    inbox_db = InboxDatabase()

    # Get pending attachments
    attachments = inbox_db.get_pending_attachments(
        limit=limite,
        sender_pattern=remetente,
    )

    if not attachments:
        console.print("[yellow]Nenhum anexo pendente encontrado.[/yellow]")
        return

    console.print(f"\n[cyan]Encontrados {len(attachments)} anexos pendentes[/cyan]")
    if remetente:
        console.print(f"[dim]Filtro: remetente contém '{remetente}'[/dim]")

    # Convert attachments to DownloadedInvoice objects for compatibility
    invoices = []
    attachment_map = {}  # Map invoice index to attachment

    for att in attachments:
        # Check if file still exists
        if not Path(att.file_path).exists():
            console.print(f"[yellow]Ficheiro não encontrado: {att.file_path}[/yellow]")
            # Mark as deleted in database
            inbox_db.mark_deleted(
                att.id, reason="file_not_found", reason_label="Ficheiro não encontrado"
            )
            continue

        invoice = DownloadedInvoice(
            provider=att.email.provider,
            sender=att.email.sender,
            subject=att.email.subject,
            date=att.email.email_date,
            file_path=Path(att.file_path),
            file_name=att.file_name,
            file_size=att.file_size,
            email_body=att.email.body,
            message_id=att.email.message_id,
        )
        invoices.append(invoice)
        attachment_map[len(invoices) - 1] = att

    if not invoices:
        console.print("[yellow]Nenhum ficheiro válido para processar.[/yellow]")
        return

    # Create processor and process invoices
    processor = InvoiceProcessor()

    console.print(f"\n[bold]A processar {len(invoices)} faturas...[/bold]\n")

    # Process each invoice and update inbox database
    for i, invoice in enumerate(invoices):
        att = attachment_map[i]

        result, rule_condition, action = processor.process_invoice(
            invoice,
            interactive=interativo,
            move=mover,
        )

        # Update inbox database based on result
        if result.success and result.destination_path:
            inbox_db.mark_processed(
                att.id,
                destination_path=str(result.destination_path),
                entity_id=None,  # Could be extracted from result
                entity_name=result.entity_name,
            )
        elif action == "delete":
            inbox_db.mark_deleted(
                att.id,
                reason=rule_condition.pattern if rule_condition else "manual",
                reason_label="Eliminado pelo utilizador",
            )
        elif action == "ignore":
            inbox_db.mark_ignored(
                att.id,
                reason=rule_condition.pattern if rule_condition else "manual",
                reason_label="Ignorado pelo utilizador",
            )

    # Show summary
    processor.show_session_summary()

    # Show updated stats
    stats = inbox_db.get_status_counts()
    console.print(
        f"\n[dim]Inbox: {stats['pending']} pendentes, {stats['processed']} processados[/dim]"
    )
