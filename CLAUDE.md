# CLAUDE.md

This file provides guidance for Claude Code when working with this repository.

## Project Overview

Bank Extractor is a personal finance manager written in Python. It automates bank statement extraction, invoice management, document organization, entity tracking, reporting, and expense tracking for Portuguese banks (CGD Empresas and Banco CTT).

## Project Status

All 6 implementation phases are **COMPLETE**:

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Infrastructure (CLI, config, credentials) | ✅ Complete |
| 2 | Invoice Download (Gmail, Hotmail via IMAP) | ✅ Complete |
| 3 | Document Organizer (PDF parsing, SQLite indexing) | ✅ Complete |
| 4 | Monthly Reports (Console, HTML, Excel, Email) | ✅ Complete |
| 5 | Expense Tracking (Budgets, Alerts, Trends) | ✅ Complete |
| 6 | Document Registry & Entity Management | ✅ Complete |

## Architecture

```
bankExtractor/
├── src/
│   ├── core/                    # Shared utilities
│   │   ├── config.py            # Pydantic settings (loads from .env)
│   │   ├── credentials.py       # Secure credential storage via keyring
│   │   ├── categories.py        # Centralized category definitions
│   │   ├── iban_manager.py      # IBAN extraction and mapping
│   │   ├── transfer_manager.py  # Bank transfer direction detection
│   │   ├── document_registry.py # Entity and document tracking
│   │   └── logger.py            # Logging configuration
│   ├── modules/
│   │   ├── banks/               # Bank integrations (Playwright-based)
│   │   │   ├── base.py          # Abstract BankBase class
│   │   │   ├── cgd.py           # CGD Empresas implementation
│   │   │   └── banco_ctt.py     # Banco CTT implementation
│   │   ├── invoices/            # Email invoice download (Phase 2)
│   │   │   ├── base.py          # EmailProviderBase class
│   │   │   ├── gmail.py         # Gmail IMAP provider
│   │   │   ├── hotmail.py       # Hotmail/Outlook IMAP provider
│   │   │   ├── downloader.py    # Download orchestrator
│   │   │   ├── inbox_models.py  # SQLAlchemy models for inbox (Email, Attachment)
│   │   │   └── inbox_db.py      # Inbox database operations
│   │   ├── organizer/           # Document cataloging (Phase 3 & 6)
│   │   │   ├── models.py        # SQLAlchemy models
│   │   │   ├── parser.py        # PDF text extraction
│   │   │   ├── classifier.py    # Auto-classification
│   │   │   ├── indexer.py       # SQLite indexing
│   │   │   ├── file_organizer.py # File organization by category/year
│   │   │   └── document_processor.py # Unified document processing
│   │   ├── reporter/            # Monthly reports (Phase 4)
│   │   │   ├── models.py        # Report data structures
│   │   │   ├── generator.py     # Report generation
│   │   │   ├── formatters.py    # Console/HTML/Excel output
│   │   │   └── mailer.py        # Email delivery
│   │   └── expenses/            # Expense tracking (Phase 5)
│   │       ├── models.py        # Expense/Budget/Alert models
│   │       ├── categorizer.py   # Auto-categorization
│   │       ├── analyzer.py      # Trends and alerts
│   │       └── tracker.py       # Main tracker interface
│   └── cli/
│       ├── main.py              # Entry point (~100 lines)
│       ├── common.py            # Shared utilities (console, parse_date)
│       └── commands/            # Command modules by domain
│           ├── banks.py         # extrair
│           ├── config.py        # config, credenciais, versao
│           ├── documents.py     # organizar, pesquisar, documento
│           ├── email_cli.py     # email group (download, scrape, inbox)
│           ├── expenses.py      # despesas, orcamento, alertas, tendencias
│           ├── financeiro_cli.py # financeiro group (resumo, faturas, despesas, orcamento, relatorio)
│           ├── invoices.py      # Core invoice functions (used by email_cli)
│           ├── processing.py    # processar, pendentes, entidades, regras
│           └── reports.py       # relatorio, relatorio_anual, enviar
├── data/
│   ├── extratos/                # Downloaded bank statements
│   ├── faturas/                 # Organized invoices
│   │   ├── _pendentes/          # Temp folder for downloaded invoices (pre-organization)
│   │   └── <year>/<scope>/<entity>/  # Final organized location
│   ├── pagamentos/              # Outgoing payments (comprovativos)
│   ├── recebimentos/            # Incoming payments (comprovativos)
│   ├── catalogo/                # Document index (SQLite)
│   ├── inbox/                   # Email inbox database (SQLite)
│   ├── expenses/                # Expense database (SQLite)
│   ├── entities.json            # Registered entities
│   ├── documents.json           # Document registry
│   ├── pending_documents.json   # Pending classification queue
│   └── transfer_config.json     # IBAN mappings and my accounts
└── pyproject.toml               # Project configuration
```

## Key Technologies

- **Python 3.10+** - Minimum required version
- **Playwright** - Browser automation for bank websites
- **Typer + Rich** - CLI framework with rich terminal output
- **Pydantic** - Settings and data validation
- **Keyring** - Secure credential storage (Windows Credential Manager)
- **SQLAlchemy** - Database ORM for documents and expenses
- **Pandas** - Data processing and Excel export
- **pdfplumber** - PDF text extraction

## CLI Commands

O CLI esta organizado em **6 grupos de comandos** (por ordem alfabetica):

```
bank-extractor
├── config       # Configuracao da aplicacao
├── documentos   # Processamento e pesquisa de documentos
├── email        # Fonte de documentos por email
├── entidades    # Gestao de entidades e regras
├── extratos     # Extracao de extratos bancarios
└── financeiro   # Analise financeira
```

### config - Configuracao
```bash
bank-extractor config credenciais <servico>     # Gerir credenciais (cgd, ctt, gmail, hotmail)
bank-extractor config ver                       # Mostrar configuracao
bank-extractor config versao                    # Mostrar versao
```

### documentos - Processamento e Pesquisa
```bash
bank-extractor documentos pendentes [--listar] [--processar] [--stats] [--razao X] [--restaurar ID]
bank-extractor documentos pesquisar <query> [--tipo fatura|extrato] [--fornecedor X]
bank-extractor documentos processar [directory] [--interativo/--auto] [--mover] [--recursivo]
bank-extractor documentos ver <id> [--abrir]
```

Options for `pendentes`:
- `--listar/-l`: Show pending files (unprocessed + ignored)
- `--stats/-s`: Show statistics by ignore reason
- `--razao/-r X`: Filter by reason code (spam, duplicado, pessoal, irrelevante, incompleto, outro, sem_razao)
- `--restaurar ID`: Remove document from ignored list (by ID prefix)
- `--reprocessar ID`: Remove from ignored and reprocess immediately
- `--limpar`: Clear ignored documents queue

### email - Fonte de Documentos por Email
```bash
# Download e processamento (fluxo principal)
bank-extractor email download [gmail|hotmail|todos] [--dias N] [--conta NAME]
bank-extractor email download --paralelo         # Processar enquanto descarrega

# Scrape (so descarrega para BD inbox, sem processar)
bank-extractor email scrape gmail --dias 60

# Gestao do inbox
bank-extractor email inbox --stats               # Ver estado do inbox
bank-extractor email inbox --listar              # Listar pendentes
bank-extractor email inbox --migrar              # Migrar dados existentes
```

**Opcoes comuns de download:**
- `--dias/-d N`: Numero de dias a pesquisar (default: 30)
- `--conta NAME`: Nome da conta (pessoal, empresa)
- `--paralelo/-p`: Processar enquanto descarrega (streaming mode)
- `--config/-c`: Configurar credenciais

**Base de dados inbox:** `data/inbox/inbox.db`
- Deduplicacao por Message-ID (email) e SHA-256 (ficheiro)
- Tracking de estado: pending, processed, ignored, deleted

### entidades - Gestao de Entidades
```bash
bank-extractor entidades criar --nome "Nome" [--pasta X] [--nif X] [--iban X]
bank-extractor entidades listar
bank-extractor entidades regras listar|ver|editar|eliminar|activar|desactivar
```

### extratos - Extracao de Extratos Bancarios
```bash
bank-extractor extratos cgd [--inicio DD-MM-YYYY] [--fim DD-MM-YYYY]
bank-extractor extratos ctt [--inicio DD-MM-YYYY] [--fim DD-MM-YYYY]
bank-extractor extratos todos [--inicio DD-MM-YYYY] [--fim DD-MM-YYYY]
```

### financeiro - Analise Financeira
```bash
# Dashboard (resumo rapido)
bank-extractor financeiro resumo [MM-YYYY|atual]

# Faturas
bank-extractor financeiro faturas [--por-pagar] [--pagas] [--categoria X]

# Despesas
bank-extractor financeiro despesas [MM-YYYY|atual] [--importar] [--categoria X]

# Orcamentos
bank-extractor financeiro orcamento [categoria] [--valor N] [--listar] [--remover]

# Relatorios
bank-extractor financeiro relatorio <MM-YYYY|atual> [--formato console|html|excel]
bank-extractor financeiro relatorio-anual <ano> [--formato html|excel]
```

**Subcomandos (alfabetico):**
- `despesas`: Ver despesas por categoria/periodo
- `faturas`: Listar faturas (por pagar, pagas)
- `orcamento`: Gerir orcamentos por categoria
- `relatorio`: Gerar relatorio financeiro mensal
- `relatorio-anual`: Gerar relatorio anual
- `resumo`: Dashboard com faturas por pagar e despesas do mes

## Document Organization Structure

### Invoices (Faturas)
```
data/faturas/<year>/<category>/<entity>/
```
Example: `data/faturas/2026/educacao/Misericordia_Amadora/`

### Bank Transfers (Comprovativos)
```
data/pagamentos/comprovativos/<entity>/   # Outgoing transfers
data/recebimentos/comprovativos/<entity>/ # Incoming transfers
```

Transfer direction is determined by matching IBANs against registered "my accounts".

## Development Commands

```bash
# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Run tests
pytest

# Format code
black .
ruff check --fix .
```

## Code Conventions

- **Language**: Code is in English, user-facing text (CLI output) is in Portuguese
- **Line length**: 100 characters (configured in pyproject.toml)
- **Linting**: Uses Black for formatting and Ruff for linting
- **Type hints**: Use Python type hints throughout
- **Docstrings**: Google-style docstrings

## Integration Patterns

### Bank Integrations
New bank integrations should:
1. Inherit from `BankBase` in `src/modules/banks/base.py`
2. Implement `login()`, `extract_statements()`, and `logout()` methods
3. Use the context manager pattern for browser lifecycle
4. Use `CredentialManager` for secure credential handling

### Email Providers
New email providers should:
1. Inherit from `EmailProviderBase` in `src/modules/invoices/base.py`
2. Implement `connect()`, `search_emails()`, `download_attachments()`, `disconnect()`
3. Use IMAP protocol with SSL
4. Support multi-account via `account` parameter

### Entity Management
Entities (suppliers, clients, banks) are tracked with:
- **NIF** (Portuguese tax number)
- **IBAN** (bank account)
- **Email** addresses
- **Name** and aliases

The system automatically identifies entities when processing documents.

## Security Considerations

- **NEVER** commit credentials or sensitive data
- Credentials are stored in system keyring, not files
- SMS tokens are always requested at runtime (never saved)
- Data files in `data/` are gitignored
- The `.env` file is gitignored
- All financial data stays local (no cloud sync)
- Passwords are never logged (use masked display)

## Environment Variables

Copy `.env.example` to `.env` and configure:
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR
- `DATA_DIR` - Path to data directory
- `HEADLESS` - Run browser in headless mode (true/false)
- `BROWSER_TIMEOUT` - Timeout for browser operations (ms)
- `INVOICE_DAYS_DEFAULT` - Default days to search for invoices (30)

## Data Files

### SQLite Databases
- `data/catalogo/documents.db` - Document index (Phase 3)
- `data/expenses/expenses.db` - Expenses and budgets (Phase 5)

### JSON Configuration
- `data/entities.json` - Registered entities with NIFs, IBANs
- `data/documents.json` - Processed document records
- `data/pending_documents.json` - Queue for manual classification
- `data/transfer_config.json` - My IBANs and counterparty mappings

## Additional Documentation

- `PROJECT_VISION.md` - Project vision and roadmap
- `README.md` - User guide and command reference
- `ARCHITECTURE.md` - Technical architecture documentation
- `TROUBLESHOOTING.md` - Common issues and solutions

## Important Notes

- This is a personal finance tool - all data stays local
- Browser automation may break if bank websites change
- Always test bank integrations manually before relying on them
- Gmail requires App Passwords (not regular passwords) for IMAP access
- Multi-account email support: use `--conta pessoal` or `--conta empresa`
