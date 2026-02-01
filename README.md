# Bank Extractor

Personal finance manager for extracting bank statements, managing invoices, and tracking expenses.

## Features

- **Bank Statement Extraction** - Automated extraction from CGD Empresas and Banco CTT
- **Invoice Management** - Download invoices from email (Gmail, Hotmail)
- **Document Organization** - Automatic file cataloging
- **Monthly Reports** - Send documentation to accountant
- **Expense Tracking** - Analyze and control expenses

## Security

- Credentials stored in Windows Credential Manager (never in files)
- SMS tokens always requested manually
- All data stays local - no external servers
- Sensitive files excluded from git

## Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd bankExtractor

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows

# Install dependencies
pip install -e .

# Install Playwright browsers
playwright install chromium
```

## Usage

```bash
# Extract statements from a specific bank
bank-extractor extrair cgd
bank-extractor extrair ctt

# Extract from all banks
bank-extractor extrair todos

# With date range
bank-extractor extrair cgd --inicio 01-01-2025 --fim 31-01-2025

# Manage credentials
bank-extractor credenciais cgd           # Set credentials
bank-extractor credenciais cgd --limpar  # Clear credentials

# Show configuration
bank-extractor config

# Show version
bank-extractor versao
```

## Project Structure

```
bankExtractor/
├── src/
│   ├── core/              # Shared utilities
│   │   ├── config.py      # Configuration management
│   │   ├── credentials.py # Secure credential handling
│   │   └── logger.py      # Logging setup
│   ├── modules/
│   │   ├── banks/         # Bank integrations
│   │   ├── invoices/      # Email invoice download
│   │   ├── organizer/     # Document cataloging
│   │   ├── reporter/      # Monthly reports
│   │   └── expenses/      # Expense tracking
│   └── cli/               # Command-line interface
├── data/
│   ├── extratos/          # Downloaded statements
│   └── faturas/           # Downloaded invoices
└── pyproject.toml         # Project configuration
```

## Development Status

- [x] Project structure
- [x] CLI framework
- [x] Credential management
- [ ] CGD Empresas integration
- [ ] Banco CTT integration
- [ ] Invoice download from email
- [ ] Document organization
- [ ] Monthly reporter
- [ ] Expense tracker

## License

Private - Personal use only.
