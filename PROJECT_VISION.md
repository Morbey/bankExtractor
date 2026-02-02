# Bank Extractor - Visão e Descrição do Projeto

## Sumário Executivo

O **Bank Extractor** é uma ferramenta de gestão financeira pessoal desenvolvida em Python, desenhada para automatizar a extração de extratos bancários, gestão de faturas e tracking de despesas para utilizadores em Portugal. O projeto foca-se na privacidade total dos dados, mantendo toda a informação localmente no computador do utilizador.

---

## Problema que Resolve

### Contexto
Gerir finanças pessoais em Portugal envolve múltiplas tarefas repetitivas e demoradas:

1. **Acesso manual a múltiplos bancos** - Cada banco tem o seu portal web com interface diferente
2. **Download de extratos** - Processo manual de navegação, seleção de datas e download
3. **Faturas dispersas** - Faturas de serviços (EDP, NOS, MEO, etc.) chegam por email e ficam perdidas
4. **Organização documental** - Necessidade de catalogar documentos para contabilidade
5. **Visibilidade financeira** - Dificuldade em ter uma visão consolidada das despesas

### Solução
O Bank Extractor automatiza todo este processo através de:
- Extração automática de extratos via browser automation
- Download automático de faturas de email
- Catalogação inteligente de documentos
- Relatórios consolidados
- Tracking de despesas por categoria

---

## Visão do Produto

> **"Uma ferramenta simples que torna a gestão financeira pessoal sem esforço, mantendo total controlo e privacidade dos dados."**

### Princípios Fundamentais

1. **Privacidade Total**
   - Todos os dados permanecem no computador do utilizador
   - Sem cloud, sem servidores externos, sem telemetria
   - Credenciais armazenadas de forma segura no keyring do sistema operativo

2. **Automação Inteligente**
   - Minimizar intervenção manual
   - Execução agendável via cron/task scheduler
   - Notificações apenas quando necessário

3. **Simplicidade de Uso**
   - Interface CLI intuitiva com output rico
   - Configuração mínima necessária
   - Documentação clara em português

4. **Extensibilidade**
   - Arquitetura modular para adicionar novos bancos
   - Suporte para múltiplos providers de email
   - API interna bem definida

---

## Roadmap de Desenvolvimento

### Fase 1: Infraestrutura do Projeto ✅
**Objetivo**: Estabelecer a base técnica sólida

**Deliverables**:
- [x] Estrutura de diretórios do projeto
- [x] CLI framework com Typer + Rich
- [x] Sistema de configuração via Pydantic Settings
- [x] Gestão segura de credenciais via keyring
- [x] Sistema de logging configurável
- [x] Classe base abstrata para bancos (`BankBase`)
- [x] Stubs para CGD Empresas e Banco CTT
- [x] Documentação inicial (README, CLAUDE.md)

### Fase 2: Download de Faturas ✅
**Objetivo**: Automatizar recolha de faturas de email

**Deliverables**:
- [x] Classe base para providers de email (`EmailProviderBase`)
- [x] Implementação Gmail (IMAP com App Password)
- [x] Implementação Hotmail/Outlook (IMAP)
- [x] Sistema de filtros (data, remetente, extensão)
- [x] Lista pré-configurada de remetentes portugueses
- [x] Comandos CLI: `faturas`, `faturas-limpar`
- [x] Armazenamento organizado por data

### Fase 3: Organizador de Documentos 📋
**Objetivo**: Catalogar e organizar automaticamente documentos financeiros

**Deliverables Planeados**:
- [ ] Parser de PDFs para extração de metadados
- [ ] Classificação automática por tipo (fatura, extrato, recibo)
- [ ] Extração de valores e datas dos documentos
- [ ] Sistema de tags e categorias
- [ ] Base de dados SQLite para indexação
- [ ] Pesquisa full-text nos documentos
- [ ] Comandos CLI: `organizar`, `pesquisar`

**Estrutura de Dados**:
```
data/
├── extratos/
│   └── YYYY/
│       └── MM/
│           └── banco_YYYYMMDD.pdf
├── faturas/
│   └── YYYY/
│       └── MM/
│           └── fornecedor_YYYYMMDD.pdf
└── catalogos/
    └── index.db
```

### Fase 4: Relatórios Mensais 📊
**Objetivo**: Gerar relatórios consolidados e enviar ao contabilista

**Deliverables Planeados**:
- [ ] Agregação mensal de documentos
- [ ] Geração de relatório PDF/Excel
- [ ] Resumo de despesas por categoria
- [ ] Comparação com meses anteriores
- [ ] Envio automático por email ao contabilista
- [ ] Templates personalizáveis
- [ ] Comandos CLI: `relatorio`, `enviar`

**Exemplo de Relatório**:
```
═══════════════════════════════════════
    RELATÓRIO FINANCEIRO - Janeiro 2024
═══════════════════════════════════════

RESUMO DE DESPESAS
├── Utilities........... 245.30€
│   ├── EDP............. 89.50€
│   ├── Água............ 35.80€
│   └── Gás............. 120.00€
├── Telecomunicações.... 75.00€
│   └── NOS............. 75.00€
└── Seguros............. 150.00€

TOTAL: 470.30€ (▲ 12% vs mês anterior)

DOCUMENTOS ANEXADOS: 8
```

### Fase 5: Tracking de Despesas 💰
**Objetivo**: Análise detalhada e categorização de despesas

**Deliverables Planeados**:
- [ ] Parsing de movimentos bancários dos extratos
- [ ] Categorização automática via regras/ML
- [ ] Dashboard CLI com gráficos ASCII
- [ ] Alertas de despesas anormais
- [ ] Orçamentos por categoria
- [ ] Exportação para Excel/CSV
- [ ] Comandos CLI: `despesas`, `orcamento`, `alertas`

**Categorias Padrão**:
- Alimentação
- Transportes
- Utilities (água, luz, gás)
- Telecomunicações
- Saúde
- Educação
- Lazer
- Seguros
- Impostos
- Outros

---

## Arquitetura Técnica

### Stack Tecnológica

| Componente | Tecnologia | Justificação |
|------------|------------|--------------|
| Linguagem | Python 3.10+ | Ecossistema rico, fácil manutenção |
| Browser Automation | Playwright | Moderno, fiável, suporte headless |
| CLI Framework | Typer + Rich | UX excelente, output formatado |
| Configuração | Pydantic Settings | Validação, type safety |
| Base de Dados | SQLAlchemy + SQLite | Leve, sem servidor, portável |
| Credenciais | Keyring | Integração nativa com OS |
| PDF Parsing | pdfplumber | Extração precisa de texto |
| Data Processing | Pandas | Manipulação eficiente de dados |

### Estrutura de Módulos

```
src/
├── core/                    # Utilitários partilhados
│   ├── config.py           # Configurações globais
│   ├── credentials.py      # Gestão de credenciais
│   └── logger.py           # Sistema de logging
│
├── modules/
│   ├── banks/              # Integrações bancárias
│   │   ├── base.py         # Classe abstrata BankBase
│   │   ├── cgd.py          # CGD Empresas
│   │   └── banco_ctt.py    # Banco CTT
│   │
│   ├── invoices/           # Download de faturas
│   │   ├── base.py         # Classe abstrata EmailProviderBase
│   │   ├── gmail.py        # Provider Gmail
│   │   ├── hotmail.py      # Provider Hotmail
│   │   └── downloader.py   # Orquestrador
│   │
│   ├── organizer/          # Catalogação (Fase 3)
│   │   ├── parser.py       # Extração de PDFs
│   │   ├── classifier.py   # Classificação
│   │   └── indexer.py      # Indexação SQLite
│   │
│   ├── reporter/           # Relatórios (Fase 4)
│   │   ├── generator.py    # Geração de relatórios
│   │   ├── templates/      # Templates de relatório
│   │   └── mailer.py       # Envio por email
│   │
│   └── expenses/           # Tracking (Fase 5)
│       ├── parser.py       # Parser de extratos
│       ├── categorizer.py  # Categorização
│       └── analyzer.py     # Análise e alertas
│
└── cli/
    └── main.py             # Entry point CLI
```

### Padrões de Design

1. **Abstract Factory** - Para criação de providers (bancos, emails)
2. **Context Manager** - Para gestão de recursos (browser, conexões)
3. **Repository Pattern** - Para acesso a dados (documentos, despesas)
4. **Strategy Pattern** - Para algoritmos de categorização

---

## Bancos Suportados

### Atualmente Implementados (Stubs)
| Banco | Estado | Notas |
|-------|--------|-------|
| CGD Empresas | 🔄 Stub | Aguarda implementação Playwright |
| Banco CTT | 🔄 Stub | Aguarda implementação Playwright |

### Planeados para Futuro
| Banco | Prioridade | Complexidade |
|-------|------------|--------------|
| Millennium BCP | Alta | Média |
| Santander | Alta | Média |
| Novo Banco | Média | Alta (2FA complexo) |
| ActivoBank | Média | Baixa |
| Revolut | Baixa | API disponível |

---

## Providers de Email Suportados

| Provider | Estado | Autenticação |
|----------|--------|--------------|
| Gmail | ✅ Implementado | App Password (IMAP) |
| Hotmail/Outlook | ✅ Implementado | Password/App Password (IMAP) |
| Yahoo | 📋 Planeado | App Password (IMAP) |
| ProtonMail | 📋 Planeado | ProtonMail Bridge |

---

## Remetentes de Faturas Pré-configurados

O sistema reconhece automaticamente faturas dos seguintes fornecedores:

### Utilities
- EDP (`noreply@edp.pt`, `facturacao@edp.pt`)
- Galp (`galp@comunicacoes.galp.com`)
- Endesa (`endurocomunicacao@endesa.pt`)
- E-Redes (`noreply@e-redes.pt`)

### Telecomunicações
- NOS (`comunicacao@nos.pt`, `factura@nos.pt`)
- MEO (`fatura@meo.pt`)
- Vodafone (`vodafone@vodafone.pt`)
- NOWO (`noreply@nowo.pt`)

### Serviços
- Via Verde (`noreply@via-verde.pt`)

### Seguros
- Fidelidade (`noreply@fidelidade.pt`)
- Allianz (`comunicacoes@allianz.pt`)

### Governo
- Portal das Finanças (`noreply@portaldasfinancas.gov.pt`)

---

## Comandos CLI

### Implementados
```bash
# Extratos bancários
bank-extractor extrair cgd              # Extrair CGD
bank-extractor extrair ctt              # Extrair Banco CTT
bank-extractor extrair todos            # Extrair todos os bancos

# Faturas
bank-extractor faturas                  # Download de todos os providers
bank-extractor faturas gmail            # Apenas Gmail
bank-extractor faturas --dias 60        # Últimos 60 dias
bank-extractor faturas --config         # Configurar credenciais
bank-extractor faturas-limpar gmail     # Remover credenciais

# Configuração
bank-extractor config                   # Mostrar configuração
bank-extractor credenciais cgd          # Gerir credenciais banco
bank-extractor versao                   # Versão da aplicação
```

### Planeados
```bash
# Organizador (Fase 3)
bank-extractor organizar                # Organizar documentos
bank-extractor pesquisar "EDP"          # Pesquisar documentos

# Relatórios (Fase 4)
bank-extractor relatorio janeiro 2024   # Gerar relatório
bank-extractor enviar janeiro 2024      # Enviar ao contabilista

# Despesas (Fase 5)
bank-extractor despesas                 # Ver despesas do mês
bank-extractor despesas --mes 01-2024   # Mês específico
bank-extractor orcamento                # Ver orçamentos
bank-extractor alertas                  # Ver alertas ativos
```

---

## Considerações de Segurança

### Princípios
1. **Zero Trust em Cloud** - Nenhum dado sai do computador local
2. **Credenciais Seguras** - Sempre via keyring do sistema operativo
3. **Tokens Efémeros** - SMS/2FA pedidos em runtime, nunca guardados
4. **Mínimo Privilégio** - Acesso apenas ao necessário

### Práticas Obrigatórias
- [ ] Nunca commit de credenciais ou tokens
- [ ] Ficheiros sensíveis sempre em .gitignore
- [ ] Validação de todos os inputs externos
- [ ] Sem execução de código dinâmico de fontes externas
- [ ] Logs sem informação sensível

---

## Contribuição e Desenvolvimento

### Setup de Desenvolvimento
```bash
# Clonar repositório
git clone https://github.com/Morbey/bankExtractor.git
cd bankExtractor

# Criar ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate   # Windows

# Instalar dependências
pip install -e ".[dev]"

# Instalar Playwright browsers
playwright install chromium

# Executar testes
pytest

# Formatar código
black .
ruff check --fix .
```

### Convenções
- **Código**: Inglês
- **UI/Mensagens**: Português
- **Commits**: Mensagens descritivas em inglês
- **Line length**: 100 caracteres
- **Docstrings**: Google-style

---

## Licença

Este é um projeto pessoal para uso próprio. Todos os direitos reservados.

---

## Contacto

Projeto mantido por: Morbey
Repositório: https://github.com/Morbey/bankExtractor
