"""Expense tracking, budgets, alerts, and trends commands."""

from datetime import date
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import console
from src.modules.expenses import CATEGORY_NAMES, ExpenseCategory, ExpenseTracker


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
