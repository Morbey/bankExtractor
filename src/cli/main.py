"""Bank Extractor CLI - Main entry point.

Organized command groups (alphabetical):
- config: Configuracao
- documentos: Processamento e pesquisa de documentos
- email: Fonte de documentos por email
- entidades: Gestao de entidades e regras
- extratos: Extracao de extratos bancarios
- financeiro: Analise financeira
"""

import typer

# Create main app
app = typer.Typer(
    name="bank-extractor",
    help="Extrator de extratos bancarios e gestor financeiro pessoal.",
    no_args_is_help=True,
)

# ==================== CONFIG ====================
config_app = typer.Typer(help="Configuracao da aplicacao")

from src.cli.commands.config import config, credenciais, versao

config_app.command(name="credenciais", help="Gerir credenciais guardadas")(credenciais)
config_app.command(name="ver", help="Mostrar configuracao atual")(config)
config_app.command(name="versao", help="Mostrar versao")(versao)

app.add_typer(config_app, name="config", help="Configuracao")

# ==================== DOCUMENTOS ====================
documentos_app = typer.Typer(help="Processamento e pesquisa de documentos")

from src.cli.commands.documents import pesquisar, documento
from src.cli.commands.processing import processar, pendentes

documentos_app.command(name="pendentes", help="Gerir documentos pendentes")(pendentes)
documentos_app.command(name="pesquisar", help="Pesquisar documentos no catalogo")(pesquisar)
documentos_app.command(name="processar", help="Processar e classificar documentos")(processar)
documentos_app.command(name="ver", help="Ver detalhes de um documento")(documento)

app.add_typer(documentos_app, name="documentos", help="Gestao de documentos")

# ==================== EMAIL ====================
from src.cli.commands.email_cli import email_app

app.add_typer(email_app, name="email", help="Documentos por email")

# ==================== ENTIDADES ====================
entidades_app = typer.Typer(help="Gestao de entidades e regras")

from src.cli.commands.processing import entidades, regras


@entidades_app.command(name="criar")
def entidades_criar(
    nome: str = typer.Option(..., "--nome", "-n", help="Nome da entidade"),
    pasta: str = typer.Option(None, "--pasta", "-p", help="Nome da pasta"),
    tipo: str = typer.Option(None, "--tipo", "-t", help="Tipo: empresa, pessoa, banco, proprio"),
    scope: str = typer.Option(None, "--scope", "-s", help="Ambito: pessoal, empresa"),
    nif: str = typer.Option(None, "--nif", help="NIF a adicionar"),
    iban: str = typer.Option(None, "--iban", help="IBAN a adicionar"),
):
    """Criar nova entidade."""
    entidades("criar", nome=nome, pasta=pasta, tipo=tipo, scope=scope, nif=nif, iban=iban)


@entidades_app.command(name="listar")
def entidades_listar():
    """Listar todas as entidades."""
    entidades("listar")


entidades_app.command(name="regras", help="Gerir regras de classificacao")(regras)

app.add_typer(entidades_app, name="entidades", help="Gestao de entidades")

# ==================== EXTRATOS ====================
extratos_app = typer.Typer(help="Extracao de extratos bancarios")


@extratos_app.command(name="cgd")
def extratos_cgd(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data inicio (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos da CGD Empresas."""
    from src.cli.commands.banks import extrair

    extrair("cgd", inicio, fim)


@extratos_app.command(name="ctt")
def extratos_ctt(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data inicio (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos do Banco CTT."""
    from src.cli.commands.banks import extrair

    extrair("ctt", inicio, fim)


@extratos_app.command(name="todos")
def extratos_todos(
    inicio: str = typer.Option(None, "--inicio", "-i", help="Data inicio (DD-MM-YYYY)"),
    fim: str = typer.Option(None, "--fim", "-f", help="Data fim (DD-MM-YYYY)"),
):
    """Extrair extratos de todos os bancos."""
    from src.cli.commands.banks import extrair

    extrair("todos", inicio, fim)


app.add_typer(extratos_app, name="extratos", help="Extracao de extratos bancarios")

# ==================== FINANCEIRO ====================
from src.cli.commands.financeiro_cli import financeiro_app

app.add_typer(financeiro_app, name="financeiro", help="Analise financeira")


def main():
    """Entry point for the CLI application."""
    app()


if __name__ == "__main__":
    main()
