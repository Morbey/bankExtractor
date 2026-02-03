"""Common utilities shared across CLI commands."""

from datetime import date, datetime
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt

from src import __version__
from src.core.category_manager import get_category_manager
from src.core.document_registry import Entity, get_document_registry
from src.modules.banks import BancoCTTBank, CGDEmpresasBank

# Shared console instance
console = Console()

# Bank registry
BANKS = {
    "cgd": CGDEmpresasBank,
    "ctt": BancoCTTBank,
}


def parse_date(date_str: str) -> date:
    """Parse date string in DD-MM-YYYY format.

    Args:
        date_str: Date string in DD-MM-YYYY format

    Returns:
        Parsed date object

    Raises:
        ValueError: If date string is invalid
    """
    return datetime.strptime(date_str, "%d-%m-%Y").date()


def version_banner(title: str = "Bank Extractor", color: str = "blue") -> str:
    """Return formatted version banner text.

    Args:
        title: Title text to display
        color: Color for the version text

    Returns:
        Formatted banner string
    """
    return f"[bold {color}]Bank Extractor v{__version__}[/bold {color}]\n{title}"


def prompt_category_selection(
    title: str = "Categoria",
    allow_create: bool = True,
    show_description: bool = True,
) -> Optional[str]:
    """Prompt user to select a category from existing list or create new.

    Displays a numbered list of categories and allows selection.
    Option 0 allows creating a new category if allow_create is True.

    Args:
        title: Title to display above the list.
        allow_create: Whether to show the "Add new category" option.
        show_description: Whether to show category descriptions.

    Returns:
        Selected category ID, or None if cancelled.

    Example output:
        Categoria:
          1. Agua (EPAL, SMAS, SIMAS)
          2. Bancario (CGD, Banco CTT, Millennium)
          ...
          0. + Adicionar nova categoria

        Escolha [1-12, 0]:
    """
    manager = get_category_manager()
    categories = manager.get_all_categories()

    if not categories:
        console.print("[yellow]Nenhuma categoria disponivel.[/yellow]")
        if allow_create:
            return _create_new_category()
        return None

    # Build the selection table
    console.print(f"\n[bold cyan]{title}:[/bold cyan]")

    for i, cat in enumerate(categories, 1):
        if show_description and cat.descricao:
            console.print(f"  [white]{i:2}.[/white] {cat.nome} [dim]({cat.descricao})[/dim]")
        else:
            console.print(f"  [white]{i:2}.[/white] {cat.nome}")

    if allow_create:
        console.print("  [green] 0.[/green] + Adicionar nova categoria")

    # Get user selection
    max_choice = len(categories)
    min_choice = 0 if allow_create else 1

    while True:
        try:
            choice_str = Prompt.ask(
                f"\n[bold]Escolha[/bold] [{min_choice}-{max_choice}]",
                default="",
            )

            if not choice_str:
                return None

            choice = int(choice_str)

            if choice == 0 and allow_create:
                return _create_new_category()
            elif 1 <= choice <= max_choice:
                selected = categories[choice - 1]
                console.print(f"[green]Selecionado:[/green] {selected.nome}")
                return selected.id
            else:
                console.print(f"[red]Escolha invalida. Use {min_choice}-{max_choice}.[/red]")
        except ValueError:
            console.print("[red]Por favor introduza um numero.[/red]")


def _create_new_category() -> Optional[str]:
    """Interactive prompt to create a new category.

    Returns:
        New category ID or None if cancelled.
    """
    console.print("\n[bold cyan]Nova Categoria[/bold cyan]")

    # Get category ID
    category_id = Prompt.ask(
        "[white]ID da categoria[/white] [dim](ex: alimentacao)[/dim]",
        default="",
    )
    if not category_id:
        console.print("[yellow]Cancelado.[/yellow]")
        return None

    # Get display name
    nome = Prompt.ask(
        "[white]Nome[/white] [dim](ex: Alimentacao)[/dim]",
        default=category_id.replace("_", " ").title(),
    )

    # Get description
    descricao = Prompt.ask(
        "[white]Descricao[/white] [dim](opcional)[/dim]",
        default="",
    )

    # Create the category
    manager = get_category_manager()
    try:
        category = manager.add_category(category_id, nome, descricao)
        console.print(f"[green]Categoria '{category.nome}' criada com sucesso![/green]")
        return category.id
    except ValueError as e:
        console.print(f"[red]Erro: {e}[/red]")
        return None


def prompt_entity_selection(
    title: str = "Entidade",
    allow_create: bool = True,
    filter_type: Optional[str] = None,
) -> Optional[Entity]:
    """Prompt user to select an entity from existing list or create new.

    Displays a numbered list of entities and allows selection.
    Option 0 allows creating a new entity if allow_create is True.

    Args:
        title: Title to display above the list.
        allow_create: Whether to show the "Add new entity" option.
        filter_type: Optional entity type to filter by (empresa, pessoa, banco, proprio).

    Returns:
        Selected Entity object, or None if cancelled.

    Example output:
        Entidade:
          1. EDP Comercial (NIF: 503504564)
          2. Vodafone Portugal (NIF: 502618930)
          ...
          0. + Adicionar nova entidade

        Escolha [1-15, 0]:
    """
    registry = get_document_registry()
    entities = registry.get_all_entities()

    # Apply filter if specified
    if filter_type:
        entities = [e for e in entities if e.entity_type.value == filter_type]

    # Sort alphabetically by name
    entities = sorted(entities, key=lambda e: e.name.lower())

    if not entities:
        console.print("[yellow]Nenhuma entidade disponivel.[/yellow]")
        if allow_create:
            return _create_new_entity()
        return None

    # Build the selection list
    console.print(f"\n[bold cyan]{title}:[/bold cyan]")

    for i, entity in enumerate(entities, 1):
        # Show NIF if available, otherwise IBAN, otherwise just name
        extra_info = ""
        if entity.nifs:
            extra_info = f"NIF: {entity.nifs[0]}"
        elif entity.ibans:
            # Show masked IBAN
            iban = entity.ibans[0]
            extra_info = f"IBAN: {iban[:4]}...{iban[-4:]}"

        if extra_info:
            console.print(f"  [white]{i:2}.[/white] {entity.name} [dim]({extra_info})[/dim]")
        else:
            console.print(f"  [white]{i:2}.[/white] {entity.name}")

    if allow_create:
        console.print("  [green] 0.[/green] + Adicionar nova entidade")

    # Get user selection
    max_choice = len(entities)
    min_choice = 0 if allow_create else 1

    while True:
        try:
            choice_str = Prompt.ask(
                f"\n[bold]Escolha[/bold] [{min_choice}-{max_choice}]",
                default="",
            )

            if not choice_str:
                return None

            choice = int(choice_str)

            if choice == 0 and allow_create:
                return _create_new_entity()
            elif 1 <= choice <= max_choice:
                selected = entities[choice - 1]
                console.print(f"[green]Selecionado:[/green] {selected.name}")
                return selected
            else:
                console.print(f"[red]Escolha invalida. Use {min_choice}-{max_choice}.[/red]")
        except ValueError:
            console.print("[red]Por favor introduza um numero.[/red]")


def _create_new_entity() -> Optional[Entity]:
    """Interactive prompt to create a new entity.

    Returns:
        New Entity object or None if cancelled.
    """
    from src.core.document_registry import AccountingScope, EntityType

    console.print("\n[bold cyan]Nova Entidade[/bold cyan]")

    # Get entity name
    name = Prompt.ask(
        "[white]Nome da entidade[/white] [dim](ex: EDP Comercial)[/dim]",
        default="",
    )
    if not name:
        console.print("[yellow]Cancelado.[/yellow]")
        return None

    # Get folder name
    folder_name = Prompt.ask(
        "[white]Nome da pasta[/white] [dim](ex: EDP_Comercial)[/dim]",
        default=name.replace(" ", "_"),
    )

    # Get NIF (optional)
    nif = Prompt.ask(
        "[white]NIF[/white] [dim](opcional, 9 digitos)[/dim]",
        default="",
    )
    nifs = [nif] if nif else []

    # Get IBAN (optional)
    iban = Prompt.ask(
        "[white]IBAN[/white] [dim](opcional)[/dim]",
        default="",
    )
    ibans = [iban] if iban else []

    # Get entity type
    console.print("\n[white]Tipo de entidade:[/white]")
    console.print("  1. Empresa")
    console.print("  2. Pessoa")
    console.print("  3. Banco")
    console.print("  4. Proprio (as minhas contas)")

    type_choice = Prompt.ask("[bold]Tipo[/bold] [1-4]", default="1")
    entity_type_map = {
        "1": EntityType.EMPRESA,
        "2": EntityType.PESSOA,
        "3": EntityType.BANCO,
        "4": EntityType.PROPRIO,
    }
    entity_type = entity_type_map.get(type_choice, EntityType.EMPRESA)

    # Get scope
    console.print("\n[white]Ambito contabilistico:[/white]")
    console.print("  1. Empresa")
    console.print("  2. Pessoal")

    scope_choice = Prompt.ask("[bold]Ambito[/bold] [1-2]", default="1")
    scope = AccountingScope.PESSOAL if scope_choice == "2" else AccountingScope.EMPRESA

    # Create the entity
    registry = get_document_registry()
    try:
        entity = registry.create_entity(
            name=name,
            folder_name=folder_name,
            entity_type=entity_type,
            scope=scope,
            nifs=nifs,
            ibans=ibans,
        )
        console.print(f"[green]Entidade '{entity.name}' criada com sucesso![/green]")
        return entity
    except Exception as e:
        console.print(f"[red]Erro ao criar entidade: {e}[/red]")
        return None
