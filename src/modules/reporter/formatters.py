"""Report formatters for different output types."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core import get_logger

from .models import ReportData, ReportFormat

logger = get_logger("reporter.formatters")


class ReportFormatter(ABC):
    """Abstract base class for report formatters."""

    @abstractmethod
    def format(self, report: ReportData) -> str:
        """Format the report data.

        Args:
            report: ReportData to format

        Returns:
            Formatted string representation
        """
        pass

    @abstractmethod
    def save(self, report: ReportData, output_path: Path) -> bool:
        """Save the formatted report to a file.

        Args:
            report: ReportData to save
            output_path: Path to save the report

        Returns:
            True if saved successfully
        """
        pass


class ConsoleFormatter(ReportFormatter):
    """Formatter for rich console output."""

    def __init__(self):
        self.console = Console(record=True)

    def format(self, report: ReportData) -> str:
        """Format report for console display."""
        self._render_to_console(report)
        return self.console.export_text()

    def render(self, report: ReportData) -> None:
        """Render report directly to console."""
        console = Console()
        self._render_to_console(report, console)

    def _render_to_console(self, report: ReportData, console: Optional[Console] = None) -> None:
        """Internal method to render report to a console."""
        if console is None:
            console = self.console

        # Header
        console.print(Panel.fit(
            f"[bold blue]RELATÓRIO FINANCEIRO[/bold blue]\n"
            f"[cyan]{report.period_name}[/cyan]",
            border_style="blue",
        ))

        if not report.has_data:
            console.print("\n[yellow]Sem dados para este período.[/yellow]")
            return

        # Summary section
        console.print("\n[bold]RESUMO[/bold]")
        summary_table = Table(show_header=False, box=None)
        summary_table.add_column("Metric", style="cyan", width=25)
        summary_table.add_column("Value", style="white")

        summary_table.add_row("Período", f"{report.period_start} a {report.period_end}")
        summary_table.add_row("Total documentos", str(report.total_documents))
        summary_table.add_row("Faturas", str(report.total_invoices))
        summary_table.add_row("Extratos", str(report.total_statements))
        summary_table.add_row("Recibos", str(report.total_receipts))
        summary_table.add_row("", "")
        summary_table.add_row(
            "[bold]TOTAL[/bold]",
            f"[bold green]{report.total_amount:.2f}€[/bold green]"
        )

        console.print(summary_table)

        # Comparison with previous month
        if report.comparison:
            console.print("\n[bold]COMPARAÇÃO COM MÊS ANTERIOR[/bold]")
            comp = report.comparison

            if comp.trend == "up":
                trend_icon = "▲"
                trend_color = "red"
            elif comp.trend == "down":
                trend_icon = "▼"
                trend_color = "green"
            else:
                trend_icon = "─"
                trend_color = "yellow"

            comp_table = Table(show_header=False, box=None)
            comp_table.add_column("Metric", style="cyan", width=25)
            comp_table.add_column("Value", style="white")

            comp_table.add_row("Mês anterior", f"{comp.previous_total:.2f}€")
            comp_table.add_row("Mês atual", f"{comp.current_total:.2f}€")
            comp_table.add_row(
                "Diferença",
                f"[{trend_color}]{trend_icon} {comp.difference:+.2f}€ ({comp.percentage_change:+.1f}%)[/{trend_color}]"
            )

            console.print(comp_table)

        # Expenses by category
        if report.by_category:
            console.print("\n[bold]DESPESAS POR CATEGORIA[/bold]")
            cat_table = Table()
            cat_table.add_column("Categoria", style="cyan")
            cat_table.add_column("Documentos", justify="right")
            cat_table.add_column("Total", justify="right", style="green")
            cat_table.add_column("%", justify="right")

            for cat in report.by_category:
                cat_table.add_row(
                    cat.name,
                    str(cat.count),
                    f"{cat.amount:.2f}€",
                    f"{cat.percentage:.1f}%",
                )

            console.print(cat_table)

        # Top providers
        if report.by_provider:
            console.print("\n[bold]TOP FORNECEDORES[/bold]")
            prov_table = Table()
            prov_table.add_column("Fornecedor", style="cyan")
            prov_table.add_column("Categoria", style="dim")
            prov_table.add_column("Docs", justify="right")
            prov_table.add_column("Total", justify="right", style="green")
            prov_table.add_column("Média", justify="right")

            for prov in report.by_provider[:10]:  # Top 10
                prov_table.add_row(
                    prov.name[:20] + "..." if len(prov.name) > 20 else prov.name,
                    prov.category or "-",
                    str(prov.document_count),
                    f"{prov.total_amount:.2f}€",
                    f"{prov.average_amount:.2f}€",
                )

            console.print(prov_table)

        # Document list
        if report.documents:
            console.print("\n[bold]DOCUMENTOS[/bold]")
            doc_table = Table()
            doc_table.add_column("Data", style="yellow")
            doc_table.add_column("Tipo", style="cyan")
            doc_table.add_column("Fornecedor", style="white")
            doc_table.add_column("Ficheiro", style="dim")
            doc_table.add_column("Valor", justify="right", style="green")

            for doc in report.documents[:20]:  # Show first 20
                doc_date = doc.document_date.strftime("%d-%m") if doc.document_date else "-"
                doc_table.add_row(
                    doc_date,
                    doc.document_type,
                    (doc.provider or "-")[:15],
                    doc.file_name[:25] + "..." if len(doc.file_name) > 25 else doc.file_name,
                    f"{doc.amount:.2f}€" if doc.amount else "-",
                )

            console.print(doc_table)

            if len(report.documents) > 20:
                console.print(f"[dim]... e mais {len(report.documents) - 20} documentos[/dim]")

        # Notes
        if report.notes:
            console.print("\n[bold]NOTAS[/bold]")
            for note in report.notes:
                console.print(f"  • {note}")

        # Footer
        console.print(f"\n[dim]Relatório gerado em {report.generated_at}[/dim]")

    def save(self, report: ReportData, output_path: Path) -> bool:
        """Save console output as text file."""
        try:
            content = self.format(report)
            output_path.write_text(content, encoding="utf-8")
            logger.info(f"Relatório guardado em {output_path}")
            return True
        except Exception as e:
            logger.error(f"Erro ao guardar relatório: {e}")
            return False


class HTMLFormatter(ReportFormatter):
    """Formatter for HTML output (can be converted to PDF)."""

    def format(self, report: ReportData) -> str:
        """Format report as HTML."""
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='pt'>",
            "<head>",
            "  <meta charset='UTF-8'>",
            f"  <title>Relatório Financeiro - {report.period_name}</title>",
            "  <style>",
            self._get_css(),
            "  </style>",
            "</head>",
            "<body>",
            f"  <h1>Relatório Financeiro</h1>",
            f"  <h2>{report.period_name}</h2>",
        ]

        if not report.has_data:
            html_parts.append("  <p class='warning'>Sem dados para este período.</p>")
        else:
            # Summary
            html_parts.extend([
                "  <section class='summary'>",
                "    <h3>Resumo</h3>",
                "    <table>",
                f"      <tr><td>Total documentos</td><td>{report.total_documents}</td></tr>",
                f"      <tr><td>Faturas</td><td>{report.total_invoices}</td></tr>",
                f"      <tr><td>Extratos</td><td>{report.total_statements}</td></tr>",
                f"      <tr><td>Recibos</td><td>{report.total_receipts}</td></tr>",
                f"      <tr class='total'><td><strong>TOTAL</strong></td><td><strong>{report.total_amount:.2f}€</strong></td></tr>",
                "    </table>",
                "  </section>",
            ])

            # Comparison
            if report.comparison:
                comp = report.comparison
                trend_class = "trend-" + comp.trend
                html_parts.extend([
                    "  <section class='comparison'>",
                    "    <h3>Comparação com Mês Anterior</h3>",
                    "    <table>",
                    f"      <tr><td>Mês anterior</td><td>{comp.previous_total:.2f}€</td></tr>",
                    f"      <tr><td>Mês atual</td><td>{comp.current_total:.2f}€</td></tr>",
                    f"      <tr class='{trend_class}'><td>Diferença</td><td>{comp.difference:+.2f}€ ({comp.percentage_change:+.1f}%)</td></tr>",
                    "    </table>",
                    "  </section>",
                ])

            # Categories
            if report.by_category:
                html_parts.extend([
                    "  <section class='categories'>",
                    "    <h3>Despesas por Categoria</h3>",
                    "    <table>",
                    "      <tr><th>Categoria</th><th>Docs</th><th>Total</th><th>%</th></tr>",
                ])
                for cat in report.by_category:
                    html_parts.append(
                        f"      <tr><td>{cat.name}</td><td>{cat.count}</td>"
                        f"<td>{cat.amount:.2f}€</td><td>{cat.percentage:.1f}%</td></tr>"
                    )
                html_parts.extend(["    </table>", "  </section>"])

            # Providers
            if report.by_provider:
                html_parts.extend([
                    "  <section class='providers'>",
                    "    <h3>Top Fornecedores</h3>",
                    "    <table>",
                    "      <tr><th>Fornecedor</th><th>Docs</th><th>Total</th><th>Média</th></tr>",
                ])
                for prov in report.by_provider[:10]:
                    html_parts.append(
                        f"      <tr><td>{prov.name}</td><td>{prov.document_count}</td>"
                        f"<td>{prov.total_amount:.2f}€</td><td>{prov.average_amount:.2f}€</td></tr>"
                    )
                html_parts.extend(["    </table>", "  </section>"])

        html_parts.extend([
            f"  <footer>Relatório gerado em {report.generated_at}</footer>",
            "</body>",
            "</html>",
        ])

        return "\n".join(html_parts)

    def _get_css(self) -> str:
        """Get CSS styles for HTML report."""
        return """
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
        h1 { color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        h2 { color: #7f8c8d; }
        h3 { color: #2c3e50; margin-top: 30px; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background-color: #3498db; color: white; }
        tr:hover { background-color: #f5f5f5; }
        .total { font-weight: bold; background-color: #e8f4f8; }
        .trend-up { color: #e74c3c; }
        .trend-down { color: #27ae60; }
        .trend-stable { color: #f39c12; }
        .warning { color: #e67e22; font-style: italic; }
        footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #7f8c8d; font-size: 0.9em; }
        """

    def save(self, report: ReportData, output_path: Path) -> bool:
        """Save report as HTML file."""
        try:
            content = self.format(report)
            output_path.write_text(content, encoding="utf-8")
            logger.info(f"Relatório HTML guardado em {output_path}")
            return True
        except Exception as e:
            logger.error(f"Erro ao guardar relatório HTML: {e}")
            return False


class ExcelFormatter(ReportFormatter):
    """Formatter for Excel output."""

    def format(self, report: ReportData) -> str:
        """Excel format doesn't return string, use save() instead."""
        return f"Excel report for {report.period_name}"

    def save(self, report: ReportData, output_path: Path) -> bool:
        """Save report as Excel file using pandas."""
        try:
            import pandas as pd

            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                # Summary sheet
                summary_data = {
                    "Métrica": [
                        "Período", "Total Documentos", "Faturas",
                        "Extratos", "Recibos", "Total (€)"
                    ],
                    "Valor": [
                        report.period_name, report.total_documents, report.total_invoices,
                        report.total_statements, report.total_receipts, report.total_amount
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name="Resumo", index=False)

                # Categories sheet
                if report.by_category:
                    cat_data = {
                        "Categoria": [c.name for c in report.by_category],
                        "Documentos": [c.count for c in report.by_category],
                        "Total (€)": [c.amount for c in report.by_category],
                        "Percentagem": [c.percentage for c in report.by_category],
                    }
                    pd.DataFrame(cat_data).to_excel(writer, sheet_name="Categorias", index=False)

                # Providers sheet
                if report.by_provider:
                    prov_data = {
                        "Fornecedor": [p.name for p in report.by_provider],
                        "Categoria": [p.category or "" for p in report.by_provider],
                        "Documentos": [p.document_count for p in report.by_provider],
                        "Total (€)": [p.total_amount for p in report.by_provider],
                        "Média (€)": [p.average_amount for p in report.by_provider],
                    }
                    pd.DataFrame(prov_data).to_excel(writer, sheet_name="Fornecedores", index=False)

                # Documents sheet
                if report.documents:
                    doc_data = {
                        "Data": [d.document_date for d in report.documents],
                        "Tipo": [d.document_type for d in report.documents],
                        "Fornecedor": [d.provider or "" for d in report.documents],
                        "Ficheiro": [d.file_name for d in report.documents],
                        "Valor (€)": [d.amount for d in report.documents],
                        "Referência": [d.reference or "" for d in report.documents],
                    }
                    pd.DataFrame(doc_data).to_excel(writer, sheet_name="Documentos", index=False)

            logger.info(f"Relatório Excel guardado em {output_path}")
            return True

        except ImportError:
            logger.error("Pandas ou openpyxl não instalado. Use: pip install pandas openpyxl")
            return False
        except Exception as e:
            logger.error(f"Erro ao guardar relatório Excel: {e}")
            return False


def get_formatter(format_type: ReportFormat) -> ReportFormatter:
    """Get the appropriate formatter for the given format type.

    Args:
        format_type: The desired output format

    Returns:
        ReportFormatter instance
    """
    formatters = {
        ReportFormat.CONSOLE: ConsoleFormatter,
        ReportFormat.HTML: HTMLFormatter,
        ReportFormat.PDF: HTMLFormatter,  # PDF uses HTML then converts
        ReportFormat.EXCEL: ExcelFormatter,
    }

    formatter_class = formatters.get(format_type, ConsoleFormatter)
    return formatter_class()
