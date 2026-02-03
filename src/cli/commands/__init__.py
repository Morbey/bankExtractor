"""CLI command modules.

This package contains all CLI commands organized by domain:
- banks: Bank statement extraction
- config: Configuration and credentials
- documents: Document organization and search
- email_cli: Email document download and inbox management
- expenses: Expense tracking and budgets
- financeiro_cli: Financial analysis (dashboard, invoices, reports)
- invoices: Invoice download core functions
- processing: Document processing, entities, and rules
- reports: Financial reports
"""

from src.cli.commands.banks import extrair
from src.cli.commands.config import config, credenciais, versao
from src.cli.commands.documents import documento, organizar, pesquisar
from src.cli.commands.expenses import alertas, despesas, orcamento, tendencias
from src.cli.commands.invoices import (
    faturas,
    faturas_inbox,
    faturas_processar_inbox,
    faturas_scrape,
)
from src.cli.commands.processing import entidades, pendentes, processar, regras
from src.cli.commands.reports import enviar, relatorio, relatorio_anual

__all__ = [
    # Banks
    "extrair",
    # Config
    "config",
    "credenciais",
    "versao",
    # Documents
    "organizar",
    "pesquisar",
    "documento",
    # Email/Invoices (core functions)
    "faturas",
    "faturas_scrape",
    "faturas_inbox",
    "faturas_processar_inbox",
    # Processing
    "processar",
    "pendentes",
    "entidades",
    "regras",
    # Reports
    "relatorio",
    "relatorio_anual",
    "enviar",
    # Expenses
    "despesas",
    "orcamento",
    "alertas",
    "tendencias",
]
