"""CLI command modules.

This package contains all CLI commands organized by domain:
- banks: Bank statement extraction
- invoices: Invoice download and management
- config: Configuration and credentials
- documents: Document organization and search
- processing: Document processing, entities, and rules
- reports: Financial reports
- expenses: Expense tracking and budgets
"""

from src.cli.commands.banks import extrair
from src.cli.commands.config import config, credenciais, versao
from src.cli.commands.documents import documento, organizar, pesquisar
from src.cli.commands.expenses import alertas, despesas, orcamento, tendencias
from src.cli.commands.invoices import (
    faturas,
    faturas_inbox,
    faturas_limpar,
    faturas_processar_inbox,
    faturas_scrape,
    gerir_faturas,
)
from src.cli.commands.processing import entidades, pendentes, processar, regras
from src.cli.commands.reports import enviar, relatorio, relatorio_anual

__all__ = [
    # Banks
    "extrair",
    # Invoices
    "gerir_faturas",
    "faturas",
    "faturas_limpar",
    "faturas_scrape",
    "faturas_inbox",
    "faturas_processar_inbox",
    # Config
    "config",
    "credenciais",
    "versao",
    # Documents
    "organizar",
    "pesquisar",
    "documento",
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
