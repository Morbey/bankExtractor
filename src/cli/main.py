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
from src.modules.organizer import DocumentIndexer, DocumentType
from src.modules.reporter import (
    ConsoleFormatter,
    ReportConfig,
    ReportFormat,
    ReportGenerator,
    ReportMailer,
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


def main():
    """Entry point."""
    app()


if __name__ == "__main__":
    main()
