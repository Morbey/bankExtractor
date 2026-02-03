"""Faturas CLI - Unified command group for invoice management.

Usage:
    bank-extractor faturas                    # Show help
    bank-extractor faturas download           # Download and process
    bank-extractor faturas scrape gmail       # Just download to inbox
    bank-extractor faturas inbox --stats      # Inbox management
    bank-extractor faturas processar          # Process pending from inbox
    bank-extractor faturas gerir organizar    # File organization

Credentials are managed via: config credenciais
"""

import typer

# Create the faturas app group
faturas_app = typer.Typer(
    name="faturas",
    help="Gestão de faturas - download, processamento e organização.",
    no_args_is_help=False,  # Allow default command
)


# Import the actual command implementations
from src.cli.commands.invoices import (
    faturas as _faturas_download,
    faturas_scrape as _faturas_scrape,
    faturas_inbox as _faturas_inbox,
    faturas_processar_inbox as _faturas_processar,
    gerir_faturas as _gerir_faturas,
)


# Default command (when just running "faturas")
@faturas_app.callback(invoke_without_command=True)
def faturas_default(ctx: typer.Context):
    """Gestão de faturas - download, processamento e organização.

    Sem subcomando: mostra ajuda.
    Use 'faturas download' para descarregar e processar faturas.
    """
    if ctx.invoked_subcommand is None:
        # Show help when no subcommand
        print(ctx.get_help())


# Register subcommands (alphabetical order)
faturas_app.command(name="download", help="Descarregar e processar faturas do email")(_faturas_download)
faturas_app.command(name="gerir", help="Organizar ficheiros e estatísticas")(_gerir_faturas)
faturas_app.command(name="inbox", help="Gerir inbox - stats, listar, migrar")(_faturas_inbox)
faturas_app.command(name="processar", help="Processar anexos pendentes do inbox")(_faturas_processar)
faturas_app.command(name="scrape", help="Descarregar emails para inbox (sem processar)")(_faturas_scrape)
