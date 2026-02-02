# CLAUDE.md

This file provides guidance for Claude Code when working with this repository.

## Project Overview

Bank Extractor is a personal finance manager written in Python. It automates bank statement extraction, invoice management, and expense tracking for Portuguese banks (CGD Empresas and Banco CTT).

## Architecture

```
bankExtractor/
├── src/
│   ├── core/              # Shared utilities
│   │   ├── config.py      # Pydantic settings (loads from .env)
│   │   ├── credentials.py # Secure credential storage via keyring
│   │   └── logger.py      # Logging configuration
│   ├── modules/
│   │   ├── banks/         # Bank integrations (Playwright-based)
│   │   │   ├── base.py    # Abstract BankBase class
│   │   │   ├── cgd.py     # CGD Empresas implementation
│   │   │   └── banco_ctt.py # Banco CTT implementation
│   │   ├── invoices/      # Email invoice download
│   │   ├── organizer/     # Document cataloging
│   │   ├── reporter/      # Monthly reports
│   │   └── expenses/      # Expense tracking
│   └── cli/               # Typer CLI application
│       └── main.py        # Entry point with commands
├── data/
│   ├── extratos/          # Downloaded bank statements
│   └── faturas/           # Downloaded invoices
└── pyproject.toml         # Project configuration
```

## Key Technologies

- **Python 3.10+** - Minimum required version
- **Playwright** - Browser automation for bank websites
- **Typer + Rich** - CLI framework with rich terminal output
- **Pydantic** - Settings and data validation
- **Keyring** - Secure credential storage (Windows Credential Manager)
- **SQLAlchemy** - Database ORM
- **Pandas** - Data processing
- **pdfplumber** - PDF parsing

## Development Commands

```bash
# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Install Playwright browsers
playwright install chromium

# Run the CLI
bank-extractor --help
bank-extractor extrair cgd
bank-extractor extrair todos
bank-extractor config
bank-extractor credenciais cgd

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

## Bank Integration Pattern

New bank integrations should:
1. Inherit from `BankBase` in `src/modules/banks/base.py`
2. Implement `login()`, `extract_statements()`, and `logout()` methods
3. Use the context manager pattern for browser lifecycle
4. Use `CredentialManager` for secure credential handling

## Security Considerations

- **NEVER** commit credentials or sensitive data
- Credentials are stored in system keyring, not files
- SMS tokens are always requested at runtime (never saved)
- Data files in `data/` are gitignored
- The `.env` file is gitignored

## Environment Variables

Copy `.env.example` to `.env` and configure:
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR
- `DATA_DIR` - Path to data directory
- `HEADLESS` - Run browser in headless mode (true/false)
- `BROWSER_TIMEOUT` - Timeout for browser operations (ms)

## Testing

- Tests use pytest
- Run with `pytest` from project root
- Test files should be in a `tests/` directory

## Important Notes

- This is a personal finance tool - all data stays local
- Browser automation may break if bank websites change
- Always test bank integrations manually before relying on them
