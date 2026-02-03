"""Document organization and search commands."""

import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from src import __version__
from src.cli.common import console, parse_date
from src.core import settings
from src.modules.organizer import DocumentIndexer, DocumentType


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
