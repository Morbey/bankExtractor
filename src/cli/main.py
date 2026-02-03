"""Bank Extractor CLI - Main entry point.

Organized command groups (alphabetical):
- config: Configuration
- despesas: Expense tracking
- documentos: Document organization and search
- entidades: Entity and rules management
- extratos: Bank statement extraction
- faturas: Invoice management
- relatorios: Financial reports
"""

import typer

# Create main app
app = typer.Typer(
    name="bank-extractor",
    help="Extrator de extratos bancários e gestor financeiro pessoal.",
    no_args_is_help=True,
)

# ==================== CONFIG ====================
config_app = typer.Typer(help="Configuração da aplicação")

from src.cli.commands.config import config, credenciais, versao

config_app.command(name="credenciais", help="Gerir credenciais guardadas")(credenciais)
config_app.command(name="ver", help="Mostrar configuração atual")(config)
config_app.command(name="versao", help="Mostrar versão")(versao)

app.add_typer(config_app, name="config", help="Configuração")

# ==================== DESPESAS ====================
despesas_app = typer.Typer(help="Tracking de despesas")

from src.cli.commands.expenses import despesas, orcamento, alertas, tendencias

despesas_app.command(name="alertas", help="Ver e gerir alertas")(alertas)
despesas_app.command(name="orcamento", help="Gerir orçamentos por categoria")(orcamento)
despesas_app.command(name="tendencias", help="Ver tendências de despesas")(tendencias)
despesas_app.command(name="ver", help="Ver e analisar despesas")(despesas)

app.add_typer(despesas_app, name="despesas", help="Tracking de despesas")

# ==================== DOCUMENTOS ====================
documentos_app = typer.Typer(help="Organização e pesquisa de documentos")

from src.cli.commands.documents import organizar, pesquisar, documento
from src.cli.commands.processing import processar, pendentes

documentos_app.command(name="organizar", help="Organizar e catalogar documentos")(organizar)
documentos_app.command(name="pendentes", help="Gerir documentos pendentes")(pendentes)
documentos_app.command(name="pesquisar", help="Pesquisar documentos no catálogo")(pesquisar)
documentos_app.command(name="processar", help="Processar e classificar documentos")(processar)
documentos_app.command(name="ver", help="Ver detalhes de um documento")(documento)

app.add_typer(documentos_app, name="documentos", help="Gestão de documentos")

# ==================== ENTIDADES ====================
entidades_app = typer.Typer(help="Gestão de entidades e regras")

from src.cli.commands.processing import entidades, regras

entidades_app.command(name="gerir", help="Gerir entidades (fornecedores, clientes)")(entidades)
entidades_app.command(name="regras", help="Gerir regras de classificação")(regras)

app.add_typer(entidades_app, name="entidades", help="Gestão de entidades")

# ==================== EXTRATOS ====================
extratos_app = typer.Typer(help="Extração de extratos bancários")


@extratos_app.command(name="cgd")
def extratos_cgd(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data início (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos da CGD Empresas."""
    from src.cli.commands.banks import extrair
    extrair("cgd", inicio, fim)


@extratos_app.command(name="ctt")
def extratos_ctt(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data início (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos do Banco CTT."""
    from src.cli.commands.banks import extrair
    extrair("ctt", inicio, fim)


@extratos_app.command(name="todos")
def extratos_todos(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data início (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos de todos os bancos."""
    from src.cli.commands.banks import extrair
    extrair("todos", inicio, fim)


app.add_typer(extratos_app, name="extratos", help="Extração de extratos bancários")

# ==================== FATURAS ====================
from src.cli.commands.faturas_cli import faturas_app
app.add_typer(faturas_app, name="faturas", help="Gestão de faturas")

# ==================== RELATORIOS ====================
relatorios_app = typer.Typer(help="Relatórios financeiros")

from src.cli.commands.reports import relatorio, relatorio_anual, enviar

relatorios_app.command(name="anual", help="Gerar relatório anual")(relatorio_anual)
relatorios_app.command(name="enviar", help="Enviar relatório por email")(enviar)
relatorios_app.command(name="mensal", help="Gerar relatório mensal")(relatorio)

app.add_typer(relatorios_app, name="relatorios", help="Relatórios financeiros")


def main():
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
