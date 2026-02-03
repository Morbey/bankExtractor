"""Financial report generation and email commands."""

from datetime import date
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import console
from src.core import settings
from src.modules.reporter import (
    ConsoleFormatter,
    ReportConfig,
    ReportFormat,
    ReportGenerator,
    ReportMailer,
    get_formatter,
)


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
