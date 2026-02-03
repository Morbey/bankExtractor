"""Bank Extractor CLI - Main entry point.

This module serves as the entry point for the Bank Extractor CLI application.
All commands are organized in submodules under src.cli.commands/.

Command Modules:
- banks: Bank statement extraction (extrair)
- invoices: Invoice download and management (faturas, gerir_faturas, faturas_limpar)
- config: Configuration commands (config, credenciais, versao)
- documents: Document organization and search (organizar, pesquisar, documento)
- processing: Document processing and entities (processar, pendentes, entidades, regras)
- reports: Financial reports (relatorio, enviar, relatorio_anual)
- expenses: Expense tracking (despesas, orcamento, alertas, tendencias)
"""

import typer

from src.cli.commands import (
    # Banks
    extrair,
    # Invoices
    faturas,
    faturas_limpar,
    gerir_faturas,
    # Config
    config,
    credenciais,
    versao,
    # Documents
    documento,
    organizar,
    pesquisar,
    # Processing
    entidades,
    pendentes,
    processar,
    regras,
    # Reports
    enviar,
    relatorio,
    relatorio_anual,
    # Expenses
    alertas,
    despesas,
    orcamento,
    tendencias,
)

app = typer.Typer(
    name="bank-extractor",
    help="Extrator de extratos bancários e gestor financeiro pessoal.",
    no_args_is_help=True,
)

# Register all commands
# Banks
app.command()(extrair)

# Invoices
app.command(name="gerir-faturas")(gerir_faturas)
app.command()(faturas)
app.command(name="faturas-limpar")(faturas_limpar)

# Configuration
app.command()(config)
app.command()(credenciais)
app.command()(versao)

# Documents
app.command()(organizar)
app.command()(pesquisar)
app.command()(documento)

# Processing & Entities
app.command()(processar)
app.command()(pendentes)
app.command()(entidades)
app.command()(regras)

# Reports
app.command()(relatorio)
app.command(name="relatorio-anual")(relatorio_anual)
app.command()(enviar)

# Expenses
app.command()(despesas)
app.command()(orcamento)
app.command()(alertas)
app.command()(tendencias)


def main():
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
