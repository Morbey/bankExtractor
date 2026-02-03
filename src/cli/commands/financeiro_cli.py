"""Financeiro CLI - Command group for financial analysis.

Usage:
    bank-extractor financeiro                       # Show help
    bank-extractor financeiro resumo               # Dashboard summary
    bank-extractor financeiro faturas --por-pagar  # List invoices
    bank-extractor financeiro despesas 01-2026     # View expenses
    bank-extractor financeiro orcamento            # Manage budgets
    bank-extractor financeiro relatorio atual      # Generate report
"""

from datetime import date
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.commands.expenses import despesas as _despesas_ver
from src.cli.commands.expenses import orcamento as _orcamento
from src.cli.commands.reports import relatorio as _relatorio
from src.cli.commands.reports import relatorio_anual as _relatorio_anual
from src.cli.common import console

# Create the financeiro app group
financeiro_app = typer.Typer(
    name="financeiro",
    help="Analise financeira - resumo, faturas, despesas, orcamentos e relatorios.",
    no_args_is_help=False,
)


@financeiro_app.callback(invoke_without_command=True)
def financeiro_default(ctx: typer.Context):
    """Analise financeira - resumo, faturas, despesas, orcamentos e relatorios.

    Sem subcomando: mostra ajuda.
    Use 'financeiro resumo' para ver o dashboard.
    """
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


# ==================== DESPESAS ====================
financeiro_app.command(name="despesas", help="Ver despesas por categoria/periodo")(_despesas_ver)
financeiro_app.command(name="orcamento", help="Gerir orcamentos por categoria")(_orcamento)


# ==================== FATURAS (invoice listing) ====================


@financeiro_app.command(name="faturas")
def faturas_listar(
    por_pagar: bool = typer.Option(
        False,
        "--por-pagar",
        "-p",
        help="Mostrar apenas faturas por pagar",
    ),
    pagas: bool = typer.Option(
        False,
        "--pagas",
        help="Mostrar apenas faturas pagas",
    ),
    categoria: Optional[str] = typer.Option(
        None,
        "--categoria",
        "-c",
        help="Filtrar por categoria",
    ),
    limite: int = typer.Option(
        50,
        "--limite",
        "-l",
        help="Numero maximo de resultados",
    ),
):
    """Listar faturas (por pagar, pagas, todas).

    Por defeito mostra todas as faturas.

    Exemplos:
        financeiro faturas --por-pagar           # Faturas por pagar
        financeiro faturas --categoria energia   # Filtrar por categoria
        financeiro faturas --pagas               # Faturas pagas
    """
    from src.modules.organizer.invoice_database import InvoiceRecord
    from src.modules.organizer.models import get_session

    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n" "Listagem de Faturas",
            border_style="blue",
        )
    )

    # Get invoices using existing methods based on filters
    try:
        with get_session() as session:
            query = session.query(InvoiceRecord)

            # Apply filters
            if por_pagar:
                query = query.filter(InvoiceRecord.is_paid.is_(False))
            elif pagas:
                query = query.filter(InvoiceRecord.is_paid.is_(True))

            if categoria:
                query = query.filter(InvoiceRecord.category == categoria)

            # Order by date descending
            query = query.order_by(InvoiceRecord.invoice_date.desc())

            # Limit results
            invoices = query.limit(limite).all()
    except Exception as e:
        console.print(f"[red]Erro ao obter faturas: {e}[/red]")
        raise typer.Exit(1)

    if not invoices:
        console.print("[yellow]Nenhuma fatura encontrada.[/yellow]")
        return

    # Build title
    title_parts = ["Faturas"]
    if por_pagar:
        title_parts.append("Por Pagar")
    elif pagas:
        title_parts.append("Pagas")
    if categoria:
        title_parts.append(f"- {categoria}")

    table = Table(title=" ".join(title_parts) + f" ({len(invoices)})")
    table.add_column("ID", style="dim", width=5)
    table.add_column("Data", style="cyan", width=10)
    table.add_column("Entidade", style="green", max_width=25)
    table.add_column("Categoria", style="yellow", width=15)
    table.add_column("Valor", style="magenta", justify="right", width=10)
    table.add_column("Estado", style="white", width=8)

    total_amount = 0.0
    for inv in invoices:
        inv_date = inv.invoice_date.strftime("%d-%m-%Y") if inv.invoice_date else "-"
        amount = inv.total_amount or 0.0
        total_amount += amount
        amount_str = f"{amount:.2f}" if amount else "-"
        status = "[green]Paga[/green]" if inv.is_paid else "[yellow]Pendente[/yellow]"
        entity = inv.nif_emitente or inv.email_sender or "-"

        table.add_row(
            str(inv.id),
            inv_date,
            entity[:25] if entity else "-",
            inv.category or "-",
            amount_str,
            status,
        )

    console.print(table)

    # Summary
    console.print(f"\n[bold]Total: {len(invoices)} faturas = {total_amount:.2f} EUR[/bold]")

    if por_pagar:
        console.print(f"[yellow]Valor por pagar: {total_amount:.2f} EUR[/yellow]")


# ==================== RELATORIO ====================
financeiro_app.command(name="relatorio", help="Gerar relatorio financeiro mensal")(_relatorio)
financeiro_app.command(name="relatorio-anual", help="Gerar relatorio anual")(_relatorio_anual)


# ==================== RESUMO (Dashboard) ====================


@financeiro_app.command(name="resumo")
def resumo(
    mes: str = typer.Argument(
        "atual",
        help="Mes a analisar (MM-YYYY ou 'atual')",
    ),
):
    """Dashboard financeiro: faturas por pagar, despesas do mes.

    Mostra um resumo rapido do estado financeiro atual.

    Exemplos:
        financeiro resumo           # Mes atual
        financeiro resumo 01-2026   # Janeiro 2026
    """
    from src.modules.expenses import ExpenseTracker
    from src.modules.organizer import InvoiceDatabase

    console.print(
        Panel.fit(
            f"[bold green]Bank Extractor v{__version__}[/bold green]\n" "Dashboard Financeiro",
            border_style="green",
        )
    )

    # Parse month
    if mes.lower() == "atual":
        today = date.today()
        year, month = today.year, today.month
    else:
        try:
            parts = mes.split("-")
            month, year = int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            console.print("[red]Formato invalido. Use MM-YYYY ou 'atual'[/red]")
            raise typer.Exit(1)

    console.print(f"\n[bold cyan]Resumo de {month:02d}/{year}[/bold cyan]\n")

    # Section 1: Invoices to pay
    db = InvoiceDatabase()
    stats = db.get_statistics()

    invoice_table = Table(title="Faturas")
    invoice_table.add_column("Metrica", style="cyan")
    invoice_table.add_column("Valor", style="white", justify="right")

    invoice_table.add_row("Total faturas", str(stats["total_invoices"]))
    invoice_table.add_row("Valor total", f"{stats['total_amount']:.2f} EUR")
    invoice_table.add_row("[yellow]Por pagar[/yellow]", f"[yellow]{stats['unpaid_count']}[/yellow]")
    invoice_table.add_row("[green]Pagas[/green]", f"[green]{stats['paid_count']}[/green]")

    console.print(invoice_table)

    # Section 2: Expenses this month
    tracker = ExpenseTracker()
    analysis = tracker.analyzer.analyze_month(year, month)

    console.print()
    expense_table = Table(title="Despesas do Mes")
    expense_table.add_column("Metrica", style="cyan")
    expense_table.add_column("Valor", style="white", justify="right")

    expense_table.add_row("Total despesas", f"[bold]{analysis.total_expenses:.2f} EUR[/bold]")
    expense_table.add_row("Numero de despesas", str(analysis.expense_count))

    if analysis.comparison_previous is not None:
        trend = "+" if analysis.comparison_percentage > 0 else ""
        color = "red" if analysis.comparison_percentage > 0 else "green"
        diff_str = f"{trend}{analysis.comparison_previous:.2f} EUR"
        pct_str = f"({trend}{analysis.comparison_percentage:.1f}%)"
        expense_table.add_row(
            "vs. mes anterior",
            f"[{color}]{diff_str} {pct_str}[/{color}]",
        )

    console.print(expense_table)

    # Section 3: Top categories this month
    if analysis.by_category:
        console.print()
        cat_table = Table(title="Top Categorias")
        cat_table.add_column("Categoria", style="cyan")
        cat_table.add_column("Total", style="green", justify="right")
        cat_table.add_column("Tendencia", style="yellow", justify="center")

        for cat in analysis.by_category[:5]:  # Top 5
            trend_icon = {
                "up": "[red]^[/red]",
                "down": "[green]v[/green]",
                "stable": "-",
                "new": "[cyan]*[/cyan]",
            }.get(cat.trend, "-")
            cat_table.add_row(
                cat.category_name,
                f"{cat.total_amount:.2f} EUR",
                trend_icon,
            )

        console.print(cat_table)

    # Section 4: Budget alerts
    if analysis.alerts:
        console.print()
        console.print(f"[bold yellow]Alertas ({len(analysis.alerts)})[/bold yellow]")
        for alert in analysis.alerts[:3]:
            severity_color = {"info": "blue", "aviso": "yellow", "critico": "red"}.get(
                alert.severity, "white"
            )
            console.print(f"  [{severity_color}]*[/{severity_color}] {alert.message}")
        if len(analysis.alerts) > 3:
            console.print(f"  [dim]... e mais {len(analysis.alerts) - 3} alertas[/dim]")

    # Quick actions hint
    console.print("\n[dim]Comandos rapidos:[/dim]")
    console.print("  [dim]financeiro faturas --por-pagar     Ver faturas por pagar[/dim]")
    console.print("  [dim]financeiro despesas                Ver despesas detalhadas[/dim]")
    console.print("  [dim]financeiro orcamento               Ver orcamentos[/dim]")
