# Arquitectura do Projecto

## Visão Geral

O Bank Extractor segue uma arquitectura modular com separação clara de responsabilidades.

```
src/
├── core/                    # Utilitários e configurações partilhadas
├── modules/                 # Módulos funcionais (bancos, emails, documentos)
└── cli/                     # Interface de linha de comandos
```

## Componentes Principais

### 1. Core (`src/core/`)

Componentes partilhados por todo o sistema:

| Ficheiro | Responsabilidade |
|----------|------------------|
| `config.py` | Configurações via Pydantic Settings |
| `credentials.py` | Gestão segura de credenciais (Windows Credential Manager) |
| `logger.py` | Sistema de logging configurável |
| `categories.py` | Definições de categorias e razões ignore/delete |
| `category_manager.py` | Gestão de categorias customizadas (JSON) |
| `classification_rules.py` | Motor de regras para classificação automática |
| `document_registry.py` | Registo de entidades e documentos |
| `iban_manager.py` | Extracção e mapeamento de IBANs |
| `transfer_manager.py` | Detecção de direcção de transferências |

### 2. Módulo Banks (`src/modules/banks/`)

Integrações com portais bancários via Playwright.

```python
# Padrão: Classes que herdam de BankBase
class CGDEmpresasBank(BankBase):
    def login(self): ...
    def extract_statements(self, start, end): ...
    def logout(self): ...
```

**Bancos Suportados:**
- CGD Empresas (`cgd.py`)
- Banco CTT (`banco_ctt.py`)

### 3. Módulo Invoices (`src/modules/invoices/`)

Download e processamento de faturas de email.

| Ficheiro | Responsabilidade |
|----------|------------------|
| `base.py` | Classes base e tipos de dados |
| `gmail.py` | Provider Gmail (IMAP) |
| `hotmail.py` | Provider Hotmail/Outlook (IMAP) |
| `downloader.py` | Orquestrador de downloads |
| `inbox_models.py` | Modelos SQLAlchemy para inbox |
| `inbox_db.py` | Base de dados inbox (SQLite) |
| `invoice_processor.py` | Processamento interactivo de faturas |
| `pdf_parser.py` | Extracção de dados de PDFs |

**Fluxo de Download:**
```
Email IMAP → inbox.db → _pendentes/ → Processamento → documentos/
```

### 4. Módulo Organizer (`src/modules/organizer/`)

Catalogação e indexação de documentos.

| Ficheiro | Responsabilidade |
|----------|------------------|
| `models.py` | Modelos SQLAlchemy para catálogo |
| `parser.py` | Parsing de PDFs (pdfplumber) |
| `classifier.py` | Classificação automática |
| `indexer.py` | Indexação em SQLite |
| `document_processor.py` | Processamento unificado |
| `invoice_database.py` | Base de dados de facturas |

### 5. Módulo Transactions (`src/modules/transactions/`)

Gestão de transacções bancárias (preparado para matching automático).

| Ficheiro | Responsabilidade |
|----------|------------------|
| `models.py` | Modelo BankTransaction |
| `transaction_db.py` | Base de dados e queries de matching |

### 6. Módulo Reporter (`src/modules/reporter/`)

Geração de relatórios financeiros.

| Ficheiro | Responsabilidade |
|----------|------------------|
| `generator.py` | Geração de dados do relatório |
| `formatters.py` | Output: Console, HTML, Excel |
| `mailer.py` | Envio de relatórios por email |

### 7. Módulo Expenses (`src/modules/expenses/`)

Tracking de despesas e orçamentos.

| Ficheiro | Responsabilidade |
|----------|------------------|
| `models.py` | Modelos SQLAlchemy |
| `categorizer.py` | Categorização de despesas |
| `analyzer.py` | Análise e alertas |
| `tracker.py` | Interface principal |

## CLI (`src/cli/`)

### Estrutura de Comandos

```
bank-extractor
├── config           # Configuração
│   ├── credenciais  # Gerir credenciais
│   ├── ver          # Ver configuração
│   └── versao       # Versão
├── documentos       # Gestão de documentos
│   ├── pendentes    # Documentos pendentes
│   ├── pesquisar    # Pesquisa
│   ├── processar    # Processamento
│   └── ver          # Ver documento
├── email            # Documentos por email
│   ├── download     # Download + processar
│   ├── inbox        # Gerir inbox
│   └── scrape       # Só download
├── entidades        # Gestão de entidades
│   ├── criar        # Criar entidade
│   ├── listar       # Listar
│   └── regras       # Regras de classificação
├── extratos         # Extratos bancários
│   ├── cgd          # CGD Empresas
│   ├── ctt          # Banco CTT
│   └── todos        # Todos os bancos
└── financeiro       # Análise financeira
    ├── despesas     # Despesas
    ├── faturas      # Listagem de faturas
    ├── orcamento    # Orçamentos
    ├── relatorio    # Relatório mensal
    ├── relatorio-anual
    └── resumo       # Dashboard
```

### Ficheiros CLI

| Ficheiro | Comandos |
|----------|----------|
| `main.py` | Entry point e definição de grupos |
| `common.py` | Utilitários partilhados (console, prompts) |
| `commands/banks.py` | Extracção bancária |
| `commands/config.py` | Configuração |
| `commands/documents.py` | Documentos |
| `commands/email_cli.py` | Grupo email |
| `commands/expenses.py` | Despesas |
| `commands/financeiro_cli.py` | Grupo financeiro |
| `commands/invoices.py` | Funções core de faturas |
| `commands/processing.py` | Processamento |
| `commands/reports.py` | Relatórios |

## Bases de Dados

### SQLite Databases

| Base de Dados | Localização | Conteúdo |
|---------------|-------------|----------|
| Inbox | `data/inbox/inbox.db` | Emails e anexos pendentes |
| Transacções | `data/transactions/transactions.db` | Movimentos bancários |

### Ficheiros JSON

| Ficheiro | Conteúdo |
|----------|----------|
| `categorias.json` | Categorias de documentos |

## Estrutura de Pastas de Dados

```
data/
├── documentos/              # Documentos organizados
│   ├── faturas/             # Contas a pagar
│   │   └── {ano}/{categoria}/{entidade}/
│   ├── despesas/            # Pagamentos efectuados
│   │   └── {ano}/{categoria}/{entidade}/
│   ├── comprovativos/       # Provas de transferência
│   │   ├── pagamentos/      # Transferências de saída
│   │   └── recebimentos/    # Transferências de entrada
│   ├── extratos/            # Extratos bancários
│   └── outros/              # Outros documentos
├── _pendentes/              # Ficheiros por processar
├── inbox/                   # Base de dados inbox (inbox.db)
├── transactions/            # Base de dados transacções (transactions.db)
└── categorias.json          # Categorias de documentos
```

## Tecnologias

| Componente | Tecnologia |
|------------|------------|
| Linguagem | Python 3.10+ |
| CLI | Typer + Rich |
| Browser Automation | Playwright |
| Base de Dados | SQLAlchemy + SQLite |
| Configuração | Pydantic Settings |
| Credenciais | Keyring |
| PDF Parsing | pdfplumber |
| Data Processing | Pandas |

## Padrões de Design

1. **Abstract Factory** - Providers de email e bancos
2. **Context Manager** - Gestão de browser e conexões
3. **Repository Pattern** - Acesso a dados
4. **Strategy Pattern** - Algoritmos de categorização
5. **Rules Engine** - Classificação automática

## Fluxo de Processamento de Documentos

```
1. Download
   Email IMAP → inbox.db → _pendentes/

2. Processamento Interactivo
   Ficheiro → Extracção PDF → Identificação Entidade

3. Decisão do Utilizador
   ├── Organizar → documentos/{tipo}/{ano}/{categoria}/{entidade}/
   ├── Ignorar → pending_documents.json (com razão)
   └── Eliminar → Remove ficheiro

4. Regras Automáticas
   Ao criar entidade/ignorar → Opção de criar regra
   Futuras correspondências → Auto-aplicadas
```

## Extensibilidade

### Adicionar Novo Banco

1. Criar classe em `src/modules/banks/`
2. Herdar de `BankBase`
3. Implementar `login()`, `extract_statements()`, `logout()`
4. Registar em `BANKS` em `src/cli/common.py`

### Adicionar Novo Provider de Email

1. Criar classe em `src/modules/invoices/`
2. Herdar de `EmailProviderBase`
3. Implementar métodos IMAP
4. Registar em `EMAIL_PROVIDERS` em `downloader.py`
