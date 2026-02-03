"""Document processing, entity management, and classification rules commands."""

from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from src import __version__
from src.cli.common import console
from src.core import settings
from src.core.classification_rules import RuleAction, get_rules_engine
from src.core.document_registry import AccountingScope, EntityType, get_document_registry
from src.modules.organizer import DocumentProcessor


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


def _get_unprocessed_files() -> list[Path]:
    """Get files in _pendentes folder that haven't been processed yet."""
    pending_dir = settings.faturas_temp_dir
    if not pending_dir.exists():
        return []

    # Get all PDF files in the folder (use set to avoid duplicates from case)
    files_lower = set(pending_dir.glob("*.pdf"))
    files_upper = set(pending_dir.glob("*.PDF"))
    files = list(files_lower | files_upper)
    return sorted(files, key=lambda f: f.name)


def _safe_filename(name: str, max_len: int = 50) -> str:
    """Get a safe filename for display, handling encoding issues."""
    # Replace problematic characters
    safe = name.encode("ascii", errors="replace").decode("ascii")
    if len(safe) > max_len:
        safe = safe[:max_len] + "..."
    return safe


def _show_pending_summary():
    """Show comprehensive summary of pending documents."""
    registry = get_document_registry()

    # Get files from _pendentes folder
    unprocessed_files = _get_unprocessed_files()

    # Get ignored documents from registry
    ignored_docs = registry.get_pending_documents()

    # Get set of file names that are in the registry (to avoid duplicates)
    ignored_file_names = {doc.get("file_name", "") for doc in ignored_docs}

    # Filter unprocessed files (those not in the registry)
    truly_unprocessed = [f for f in unprocessed_files if f.name not in ignored_file_names]

    total_count = len(truly_unprocessed) + len(ignored_docs)

    if total_count == 0:
        console.print("[green]Não há documentos pendentes.[/green]")
        return

    # Section 1: Unprocessed files (in folder but not in registry)
    if truly_unprocessed:
        table = Table(title=f"Por Processar ({len(truly_unprocessed)})")
        table.add_column("#", style="dim", width=4)
        table.add_column("Ficheiro", style="white")
        table.add_column("Tamanho", style="cyan", justify="right")

        for i, f in enumerate(truly_unprocessed[:20], 1):  # Show max 20
            size_kb = f.stat().st_size / 1024
            table.add_row(
                str(i),
                _safe_filename(f.name, 50),
                f"{size_kb:.1f} KB",
            )

        if len(truly_unprocessed) > 20:
            table.add_row("...", f"... e mais {len(truly_unprocessed) - 20} ficheiros", "")

        console.print(table)
        console.print(f"[dim]Use: bank-extractor processar {settings.faturas_temp_dir} --interativo[/dim]\n")

    # Section 2: Ignored documents (in registry)
    if ignored_docs:
        table = Table(title=f"Ignorados ({len(ignored_docs)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Ficheiro", style="white")
        table.add_column("Razao", style="yellow")
        table.add_column("Remetente", style="cyan", max_width=25)

        for doc in ignored_docs[:20]:  # Show max 20
            reason = doc.get("ignore_reason_label") or doc.get("pending_reason", "N/A")
            table.add_row(
                doc.get("id", "")[:8],
                _safe_filename(doc.get("file_name", "N/A"), 40),
                _safe_filename(reason, 20),
                _safe_filename(doc.get("sender", "N/A"), 25),
            )

        if len(ignored_docs) > 20:
            table.add_row("...", f"... e mais {len(ignored_docs) - 20} documentos", "", "")

        console.print(table)

    # Summary
    console.print(f"\n[bold]Total: {total_count} documentos pendentes[/bold]")
    console.print(f"  - Por processar: {len(truly_unprocessed)}")
    console.print(f"  - Ignorados: {len(ignored_docs)}")


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
        help="Limpar a fila de pendentes (apenas ignorados)",
    ),
    razao: Optional[str] = typer.Option(
        None,
        "--razao", "-r",
        help="Filtrar por razao (spam, duplicado, pessoal, irrelevante, incompleto, outro, sem_razao)",
    ),
    stats: bool = typer.Option(
        False,
        "--stats", "-s",
        help="Mostrar estatisticas por razao",
    ),
    restaurar: Optional[str] = typer.Option(
        None,
        "--restaurar",
        help="Remover documento da lista de ignorados por ID (primeiros 8 chars)",
    ),
    reprocessar: Optional[str] = typer.Option(
        None,
        "--reprocessar",
        help="Remover da lista de ignorados e reprocessar imediatamente (ID)",
    ),
):
    """Gerir documentos pendentes de classificacao."""
    console.print(Panel.fit(
        f"[bold yellow]Bank Extractor v{__version__}[/bold yellow]\n"
        "Documentos Pendentes",
        border_style="yellow",
    ))

    registry = get_document_registry()

    # Handle restaurar (remove from ignored list)
    if restaurar:
        pending = registry.get_pending_documents()
        found = None
        for doc in pending:
            if doc.get("id", "").startswith(restaurar):
                found = doc
                break

        if not found:
            console.print(f"[red]Documento nao encontrado com ID: {restaurar}[/red]")
            console.print("[dim]Use 'bank-extractor pendentes --listar' para ver os IDs[/dim]")
            return

        console.print(f"\n[bold]Documento encontrado:[/bold]")
        console.print(f"  Ficheiro: [cyan]{found.get('file_name', 'N/A')}[/cyan]")
        console.print(f"  Remetente: [cyan]{found.get('sender', 'N/A')}[/cyan]")
        console.print(f"  Razao: [yellow]{found.get('ignore_reason_label') or found.get('pending_reason', 'N/A')}[/yellow]")

        if Confirm.ask("\nRemover da lista de ignorados?", default=True):
            registry.remove_from_pending(found["id"])
            console.print("[green]Documento removido da lista de ignorados.[/green]")
            console.print(f"[dim]O ficheiro continua em: {found.get('file_path', 'N/A')}[/dim]")
            console.print("[dim]Use 'bank-extractor processar <pasta> --interativo' para reprocessar[/dim]")
        return

    # Handle reprocessar (remove from ignored and process immediately)
    if reprocessar:
        pending = registry.get_pending_documents()
        found = None
        for doc in pending:
            if doc.get("id", "").startswith(reprocessar):
                found = doc
                break

        if not found:
            console.print(f"[red]Documento nao encontrado com ID: {reprocessar}[/red]")
            console.print("[dim]Use 'bank-extractor pendentes --listar' para ver os IDs[/dim]")
            return

        file_path = Path(found.get("file_path", ""))
        if not file_path.exists():
            console.print(f"[red]Ficheiro nao encontrado: {file_path}[/red]")
            console.print("[dim]O ficheiro pode ter sido movido ou eliminado.[/dim]")
            return

        console.print(f"\n[bold]A reprocessar:[/bold] {found.get('file_name', 'N/A')}")

        # Remove from pending
        registry.remove_from_pending(found["id"])

        # Create a DownloadedInvoice-like object and process it
        from datetime import datetime
        from src.modules.invoices.base import DownloadedInvoice
        from src.modules.invoices.invoice_processor import InvoiceProcessor

        invoice = DownloadedInvoice(
            file_path=file_path,
            file_name=found.get("file_name", file_path.name),
            sender=found.get("sender", ""),
            subject=found.get("subject", ""),
            date=datetime.fromisoformat(found.get("email_date", datetime.now().isoformat())),
            file_size=file_path.stat().st_size if file_path.exists() else 0,
            email_body=found.get("email_body"),
        )

        processor = InvoiceProcessor()
        processor.reset_session_stats()
        result, _, _ = processor.process_invoice(invoice, interactive=True, move=True)

        if result.success:
            console.print(f"[green]Documento processado com sucesso![/green]")
            if result.destination_path:
                console.print(f"[dim]Movido para: {result.destination_path}[/dim]")
        else:
            console.print(f"[yellow]Documento nao processado: {result.error}[/yellow]")
        return

    if limpar:
        pending = registry.get_pending_documents()
        if pending:
            if Confirm.ask(f"Limpar {len(pending)} documentos ignorados da fila?"):
                for doc in pending:
                    registry.remove_from_pending(doc["id"])
                console.print("[green]Fila de ignorados limpa.[/green]")
        else:
            console.print("[green]Não há documentos ignorados na fila.[/green]")
        return

    if stats:
        # Show stats for both unprocessed and ignored
        unprocessed_files = _get_unprocessed_files()
        ignored_docs = registry.get_pending_documents()

        # Get ignored file names to avoid double counting
        ignored_file_names = {doc.get("file_name", "") for doc in ignored_docs}
        truly_unprocessed = [f for f in unprocessed_files if f.name not in ignored_file_names]

        console.print(f"\n[bold]Resumo Geral:[/bold]")
        console.print(f"  - Ficheiros por processar: [cyan]{len(truly_unprocessed)}[/cyan]")
        console.print(f"  - Documentos ignorados: [yellow]{len(ignored_docs)}[/yellow]")
        console.print(f"  - [bold]Total: {len(truly_unprocessed) + len(ignored_docs)}[/bold]")

        # Show stats by reason for ignored documents
        pending_stats = registry.get_pending_stats()
        if pending_stats:
            console.print(f"\n[bold]Ignorados por Razao:[/bold]")
            table = Table()
            table.add_column("Razao", style="cyan")
            table.add_column("Codigo", style="dim")
            table.add_column("Total", style="yellow", justify="right")

            for reason_label, (reason_code, count) in sorted(pending_stats.items(), key=lambda x: -x[1][1]):
                table.add_row(_safe_filename(reason_label, 30), reason_code, str(count))

            console.print(table)

        console.print(f"\n[dim]Use: bank-extractor pendentes --listar[/dim]")
        console.print(f"[dim]Use: bank-extractor pendentes --razao <codigo>[/dim]")
        return

    if razao:
        # Filter ignored documents by reason
        pending = registry.get_pending_by_reason(razao)
        if not pending:
            console.print(f"[yellow]Nenhum documento ignorado com razão '{razao}'.[/yellow]")
            return

        table = Table(title=f"Documentos Ignorados - Razao: {razao} ({len(pending)})")
        table.add_column("ID", style="dim", width=8)
        table.add_column("Ficheiro", style="white")
        table.add_column("Remetente", style="cyan", max_width=30)
        table.add_column("Valor", style="green", justify="right")

        for doc in pending:
            table.add_row(
                doc.get("id", "")[:8],
                doc.get("file_name", "N/A")[:40],
                doc.get("sender", "N/A")[:30],
                doc.get("amount", "N/A"),
            )

        console.print(table)
        return

    if listar or not processar_todos:
        _show_pending_summary()
        return

    if processar_todos:
        processor = DocumentProcessor()
        processor.process_pending_queue(interactive=True)


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
    scope: Optional[str] = typer.Option(
        None,
        "--scope", "-s",
        help="Âmbito contabilístico: pessoal, empresa",
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
        table.add_column("Âmbito", style="magenta")
        table.add_column("Tipo", style="yellow")
        table.add_column("NIFs", style="white")

        for e in entities:
            nifs_display = ", ".join(e.nifs[:2]) if e.nifs else "-"
            if len(e.nifs) > 2:
                nifs_display += f" (+{len(e.nifs) - 2})"

            scope_display = e.scope.value if hasattr(e, 'scope') else "empresa"

            table.add_row(
                e.id[:10],
                e.name[:30],
                e.folder_name[:20],
                scope_display,
                e.entity_type.value,
                nifs_display,
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

        accounting_scope = AccountingScope.EMPRESA
        if scope:
            try:
                accounting_scope = AccountingScope(scope.lower())
            except ValueError:
                console.print(f"[yellow]Âmbito inválido: {scope}. Usando 'empresa'.[/yellow]")

        nifs_list = [nif] if nif else []
        ibans_list = [iban] if iban else []

        entity = registry.create_entity(
            name=nome,
            folder_name=folder_name,
            entity_type=entity_type,
            scope=accounting_scope,
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

        if scope:
            try:
                entity.scope = AccountingScope(scope.lower())
                registry.update_entity(entity)
                console.print(f"[green]Âmbito actualizado: {scope}[/green]")
            except ValueError:
                console.print(f"[yellow]Âmbito inválido: {scope}[/yellow]")

        registry.show_entity_summary(entity_id)

    elif acao_lower == "eliminar":
        if not entity_id:
            console.print("[red]ID é obrigatório para eliminar. Use --id[/red]")
            raise typer.Exit(1)

        entity = registry.get_entity(entity_id)
        if not entity:
            console.print(f"[red]Entidade não encontrada: {entity_id}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[yellow]Vai eliminar a entidade:[/yellow]")
        console.print(f"  Nome: {entity.name}")
        console.print(f"  Pasta: {entity.folder_name}")
        console.print(f"  Âmbito: {entity.scope.value}")

        if Confirm.ask("\nConfirma eliminação?", default=False):
            registry.delete_entity(entity_id)
            console.print("[green]Entidade eliminada.[/green]")
        else:
            console.print("[dim]Cancelado.[/dim]")

    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações disponíveis: listar, criar, ver, editar, eliminar")
        raise typer.Exit(1)


def regras(
    acao: str = typer.Argument(
        "listar",
        help="Ação: listar, ver, editar, eliminar, activar, desactivar",
    ),
    rule_id: Optional[str] = typer.Option(
        None,
        "--id",
        help="ID da regra",
    ),
    nome: Optional[str] = typer.Option(
        None,
        "--nome", "-n",
        help="Novo nome da regra (para editar)",
    ),
    prioridade: Optional[int] = typer.Option(
        None,
        "--prioridade", "-p",
        help="Nova prioridade (menor = mais prioritário)",
    ),
):
    """Gerir regras de classificação automática."""
    console.print(Panel.fit(
        f"[bold magenta]Bank Extractor v{__version__}[/bold magenta]\n"
        "Regras de Classificação",
        border_style="magenta",
    ))

    rules_engine = get_rules_engine()
    acao_lower = acao.lower()

    if acao_lower == "listar":
        rules = rules_engine.get_all_rules()

        if not rules:
            console.print("\n[yellow]Nenhuma regra de classificação definida.[/yellow]")
            console.print("[dim]As regras são criadas automaticamente ao identificar entidades.[/dim]")
            return

        table = Table(title=f"Regras de Classificação ({len(rules)})")
        table.add_column("Pri", style="dim", width=4)
        table.add_column("ID", style="dim", width=10)
        table.add_column("Nome", style="cyan", max_width=25)
        table.add_column("Condições", style="white", max_width=40)
        table.add_column("Acção", style="green")
        table.add_column("Hits", style="yellow", justify="right")
        table.add_column("On", style="dim", width=3)

        for rule in rules:
            # Build conditions summary
            cond_summary = []
            for c in rule.conditions[:2]:  # Show first 2
                source = c.source.value.split("_")[0]
                pattern_short = c.pattern[:15] + "..." if len(c.pattern) > 15 else c.pattern
                cond_summary.append(f"{source}:{pattern_short}")
            if len(rule.conditions) > 2:
                cond_summary.append(f"+{len(rule.conditions) - 2}")

            connector = " AND " if rule.match_all else " OR "

            table.add_row(
                str(rule.priority),
                rule.id[:10],
                rule.name[:25],
                connector.join(cond_summary),
                rule.action.value[:15],
                str(rule.hit_count),
                "✓" if rule.enabled else "✗",
            )

        console.print(table)
        console.print("\n[dim]Use: bank-extractor regras ver --id <ID> para ver detalhes[/dim]")

    elif acao_lower == "ver":
        if not rule_id:
            console.print("[red]ID é obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        rule = rules_engine.get_rule(rule_id)
        if not rule:
            # Try partial match
            rules = rules_engine.get_all_rules()
            for r in rules:
                if r.id.startswith(rule_id):
                    rule = r
                    break

        if not rule:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[bold]Regra: {rule.name}[/bold]")

        info_table = Table(show_header=False)
        info_table.add_column("Campo", style="cyan")
        info_table.add_column("Valor", style="white")

        info_table.add_row("ID", rule.id)
        info_table.add_row("Nome", rule.name)
        info_table.add_row("Descrição", rule.description or "-")
        info_table.add_row("Prioridade", str(rule.priority))
        info_table.add_row("Activada", "Sim" if rule.enabled else "Não")
        info_table.add_row("Lógica", "AND (todas)" if rule.match_all else "OR (qualquer uma)")
        info_table.add_row("Hits", str(rule.hit_count))
        info_table.add_row("Criada em", rule.created_at[:19] if rule.created_at else "-")
        info_table.add_row("Acção", rule.action.value)
        info_table.add_row("Valor Acção", rule.action_value[:30])

        console.print(info_table)

        # Show conditions
        console.print(f"\n[bold]Condições ({len(rule.conditions)}):[/bold]")
        cond_table = Table()
        cond_table.add_column("#", style="dim")
        cond_table.add_column("Fonte", style="cyan")
        cond_table.add_column("Tipo", style="yellow")
        cond_table.add_column("Padrão", style="white")

        for i, cond in enumerate(rule.conditions, 1):
            cond_table.add_row(
                str(i),
                cond.source.value,
                cond.match_type.value,
                cond.pattern[:50] + "..." if len(cond.pattern) > 50 else cond.pattern,
            )

        console.print(cond_table)

        # Show action details
        if rule.action == RuleAction.ASSIGN_ENTITY:
            registry = get_document_registry()
            entity = registry.get_entity(rule.action_value)
            if entity:
                console.print(f"\n[green]→ Associa à entidade: {entity.name}[/green]")

    elif acao_lower == "eliminar":
        if not rule_id:
            console.print("[red]ID é obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        rule = rules_engine.get_rule(rule_id)
        if not rule:
            # Try partial match
            rules = rules_engine.get_all_rules()
            for r in rules:
                if r.id.startswith(rule_id):
                    rule = r
                    break

        if not rule:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")
            raise typer.Exit(1)

        if Confirm.ask(f"Eliminar regra '{rule.name}'?"):
            rules_engine.delete_rule(rule.id)
            console.print("[green]Regra eliminada.[/green]")
        else:
            console.print("[dim]Cancelado.[/dim]")

    elif acao_lower == "activar":
        if not rule_id:
            console.print("[red]ID é obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        if rules_engine.enable_rule(rule_id, True):
            console.print("[green]Regra activada.[/green]")
        else:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")

    elif acao_lower == "desactivar":
        if not rule_id:
            console.print("[red]ID é obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        if rules_engine.enable_rule(rule_id, False):
            console.print("[yellow]Regra desactivada.[/yellow]")
        else:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")

    elif acao_lower == "editar":
        if not rule_id:
            console.print("[red]ID é obrigatório. Use --id[/red]")
            raise typer.Exit(1)

        rule = rules_engine.get_rule(rule_id)
        if not rule:
            # Try partial match
            rules = rules_engine.get_all_rules()
            for r in rules:
                if r.id.startswith(rule_id):
                    rule = r
                    break

        if not rule:
            console.print(f"[red]Regra não encontrada: {rule_id}[/red]")
            raise typer.Exit(1)

        updated = False

        if nome:
            rule.name = nome
            updated = True
            console.print(f"[green]Nome actualizado: {nome}[/green]")

        if prioridade is not None:
            rule.priority = prioridade
            updated = True
            console.print(f"[green]Prioridade actualizada: {prioridade}[/green]")

        if updated:
            rules_engine.update_rule(rule)
        else:
            console.print("[yellow]Nenhuma alteração especificada.[/yellow]")
            console.print("Use --nome ou --prioridade para editar")

    else:
        console.print(f"[red]Ação desconhecida: {acao}[/red]")
        console.print("Ações disponíveis: listar, ver, editar, eliminar, activar, desactivar")
        raise typer.Exit(1)
