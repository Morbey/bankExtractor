"""Bank extraction commands."""

from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import BANKS, console, parse_date


def extrair(
    banco: str = typer.Argument(
        ...,
        help="Banco a extrair: cgd, ctt, ou 'todos'",
    ),
    inicio: Optional[str] = typer.Option(
        None,
        "--inicio",
        "-i",
        help="Data início (DD-MM-YYYY). Default: início do mês.",
    ),
    fim: Optional[str] = typer.Option(
        None,
        "--fim",
        "-f",
        help="Data fim (DD-MM-YYYY). Default: hoje.",
    ),
):
    """Extrair extratos bancários."""
    console.print(
        Panel.fit(
            f"[bold blue]Bank Extractor v{__version__}[/bold blue]\n"
            "Extração de extratos bancários",
            border_style="blue",
        )
    )

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
