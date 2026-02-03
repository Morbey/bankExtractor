"""Email CLI - Command group for email document management.

Usage:
    bank-extractor email                    # Show help
    bank-extractor email download           # Download and process
    bank-extractor email scrape gmail       # Just download to inbox
    bank-extractor email inbox --stats      # Inbox management

Credentials are managed via: config credenciais
"""

import typer

from src.cli.commands.invoices import (
    faturas as _email_download,
    faturas_inbox as _email_inbox,
    faturas_scrape as _email_scrape,
)

# Create the email app group
email_app = typer.Typer(
    name="email",
    help="Documentos por email - download, scrape e inbox.",
    no_args_is_help=False,
)


# Default command (when just running "email")
@email_app.callback(invoke_without_command=True)
def email_default(ctx: typer.Context):
    """Documentos por email - download, scrape e gestao de inbox.

    Sem subcomando: mostra ajuda.
    Use 'email download' para descarregar e processar documentos.
    """
    if ctx.invoked_subcommand is None:
        print(ctx.get_help())


# Register subcommands (alphabetical order)
email_app.command(name="download", help="Descarregar e processar documentos do email")(
    _email_download
)
email_app.command(name="inbox", help="Gerir inbox - stats, listar, migrar")(_email_inbox)
email_app.command(name="scrape", help="Descarregar emails para inbox (sem processar)")(
    _email_scrape
)
