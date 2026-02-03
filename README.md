# Bank Extractor

Gestor financeiro pessoal para automatização de extratos bancários, faturas, e controlo de despesas.

## Funcionalidades

- **Extração de Extratos Bancários** - CGD Empresas e Banco CTT (via Playwright)
- **Download de Faturas** - Gmail e Hotmail (via IMAP) com sistema de inbox SQLite
- **Organização de Documentos** - Classificação automática por tipo, categoria e entidade
- **Gestão de Entidades** - Tracking de fornecedores, clientes, bancos por NIF/IBAN
- **Relatórios Financeiros** - Console, HTML, Excel
- **Controlo de Despesas** - Orçamentos, alertas, tendências

## Instalação

### Requisitos
- Python 3.10+
- Windows (para Windows Credential Manager)

### Instalação
```bash
# Clonar o repositório
git clone https://github.com/Morbey/bankExtractor.git
cd bankExtractor

# Instalar em modo desenvolvimento
pip install -e .

# Instalar browsers para automação bancária
playwright install chromium
```

### Configuração
```bash
# Copiar ficheiro de ambiente
cp .env.example .env

# Editar configurações (opcional)
# LOG_LEVEL=INFO
# DATA_DIR=./data
# HEADLESS=true
```

## Estrutura de Comandos

O CLI está organizado em **6 grupos** principais:

```
bank-extractor
├── config       # Configuração da aplicação
├── documentos   # Processamento de documentos
├── email        # Download de documentos por email
├── entidades    # Gestão de entidades e regras
├── extratos     # Extração de extratos bancários
└── financeiro   # Análise financeira
```

Use `--help` em qualquer nível para ver opções:
```bash
bank-extractor --help              # Lista de grupos
bank-extractor email --help        # Subcomandos de email
bank-extractor email download --help  # Opções do subcomando
```

## Guia de Utilização

### 1. Configurar Credenciais

#### Email (Gmail)
```bash
# Configurar conta Gmail
bank-extractor config credenciais gmail --conta pessoal
```

**Nota**: O Gmail requer App Passwords:
1. Ativar verificação em 2 passos na conta Google
2. Criar App Password em https://myaccount.google.com/apppasswords
3. Usar a App Password (sem espaços) como password

#### Bancos
```bash
# Configurar credenciais CGD
bank-extractor config credenciais cgd
```

### 2. Download de Documentos por Email

#### Fluxo Simples (download + processamento)
```bash
# Download dos últimos 30 dias (Gmail pessoal)
bank-extractor email download gmail --conta pessoal

# Download de todos os providers
bank-extractor email download todos

# Processar enquanto descarrega (streaming)
bank-extractor email download --paralelo
```

#### Fluxo Inbox (descarregar agora, processar depois)
```bash
# Descarregar emails para o inbox (sem processar)
bank-extractor email scrape gmail --dias 60

# Ver estado do inbox
bank-extractor email inbox --stats

# Processar anexos pendentes
bank-extractor documentos processar
```

### 3. Processar Documentos

```bash
# Processar documentos de uma pasta (modo interativo)
bank-extractor documentos processar E:\downloads\docs

# Processar em modo automático
bank-extractor documentos processar E:\downloads\docs --auto

# Mover ficheiros em vez de copiar
bank-extractor documentos processar E:\downloads\docs --mover
```

O sistema:
1. Pergunta o **tipo de documento** (fatura, despesa, comprovativo, etc.)
2. Pergunta a **categoria** (energia, comunicações, etc.) via lista numerada
3. Identifica ou pergunta a **entidade** via lista numerada
4. Organiza na pasta correcta: `documentos/{tipo}/{ano}/{categoria}/{entidade}/`

### 4. Gerir Documentos Pendentes

```bash
# Ver todos os documentos pendentes
bank-extractor documentos pendentes --listar

# Ver estatísticas por razão de ignorar
bank-extractor documentos pendentes --stats

# Filtrar por razão (spam, duplicado, pessoal, irrelevante, etc.)
bank-extractor documentos pendentes --razao spam

# Reprocessar documento
bank-extractor documentos pendentes --reprocessar 8826ac63
```

### 5. Gerir Entidades

```bash
# Listar entidades registadas
bank-extractor entidades listar

# Criar nova entidade
bank-extractor entidades criar --nome "EDP Comercial"
```

### 6. Extratos Bancários

```bash
# Extrair extrato CGD do mês actual
bank-extractor extratos cgd

# Extrair com período específico
bank-extractor extratos cgd --inicio 01-01-2026 --fim 31-01-2026

# Extrair de todos os bancos
bank-extractor extratos todos
```

### 7. Análise Financeira

```bash
# Ver dashboard financeiro
bank-extractor financeiro resumo

# Ver faturas por pagar
bank-extractor financeiro faturas --por-pagar

# Gerar relatório mensal
bank-extractor financeiro relatorio actual

# Ver despesas
bank-extractor financeiro despesas

# Gerir orçamentos
bank-extractor financeiro orcamento
```

### 8. Pesquisar Documentos

```bash
# Pesquisar por texto
bank-extractor documentos pesquisar "EDP"

# Ver detalhes de um documento
bank-extractor documentos ver 42 --abrir
```

## Estrutura de Pastas

```
data/
├── documentos/                 # Documentos organizados
│   ├── faturas/               # Contas a pagar
│   │   └── {ano}/{categoria}/{entidade}/
│   ├── despesas/              # Pagamentos efectuados
│   ├── comprovativos/         # Provas de transferência
│   │   ├── pagamentos/        # Transferências de saída
│   │   └── recebimentos/      # Transferências de entrada
│   ├── extratos/              # Extratos bancários
│   └── outros/                # Outros documentos
├── _pendentes/                # Ficheiros por processar
├── inbox/                     # Base de dados inbox
│   └── inbox.db
├── transactions/              # Base de dados transações
│   └── transactions.db
└── categorias.json            # Categorias de documentos
```

## Tipos de Documentos

| Tipo | Descrição | Pasta |
|------|-----------|-------|
| Fatura | Contas a pagar | `documentos/faturas/` |
| Despesa/Recibo | Pagamentos efectuados | `documentos/despesas/` |
| Comprovativo Pagamento | Provas de transferência (saída) | `documentos/comprovativos/pagamentos/` |
| Comprovativo Recebimento | Provas de transferência (entrada) | `documentos/comprovativos/recebimentos/` |
| Extrato Bancário | Movimentos de conta | `documentos/extratos/` |

## Referência Rápida

| Grupo | Subcomando | Descrição |
|-------|------------|-----------|
| **config** | credenciais | Gerir credenciais (bancos + email) |
| | ver | Mostrar configuração |
| | versao | Mostrar versão |
| **documentos** | pendentes | Gerir documentos pendentes |
| | pesquisar | Pesquisar no catálogo |
| | processar | Processar e classificar |
| | ver | Ver detalhes |
| **email** | download | Descarregar e processar |
| | inbox | Gerir inbox (stats, listar) |
| | scrape | Só descarregar (sem processar) |
| **entidades** | criar | Criar nova entidade |
| | listar | Listar entidades |
| | regras | Regras de classificação |
| **extratos** | cgd | CGD Empresas |
| | ctt | Banco CTT |
| | todos | Todos os bancos |
| **financeiro** | despesas | Ver despesas |
| | faturas | Listar faturas |
| | orcamento | Gerir orçamentos |
| | relatorio | Relatório mensal |
| | resumo | Dashboard |

## Segurança

- Credenciais guardadas no Windows Credential Manager (nunca em ficheiros)
- Passwords nunca aparecem em logs
- Todos os dados ficam locais (sem cloud)
- Ficheiros de dados ignorados pelo Git

## Troubleshooting

Para resolução de problemas, consulte [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Quick Fixes

| Problema | Solução Rápida |
|----------|----------------|
| Gmail auth failed | Use App Password, não password normal |
| Banco timeout | Defina `HEADLESS=false` no `.env` |
| Documento desconhecido | Use modo `--interativo` |

## Documentação Adicional

- [ARCHITECTURE.md](ARCHITECTURE.md) - Arquitectura técnica do projecto
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Resolução de problemas
- [PROJECT_VISION.md](PROJECT_VISION.md) - Visão e história do projecto

## Licença

Projecto pessoal - uso privado.
