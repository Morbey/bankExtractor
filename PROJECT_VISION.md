# Bank Extractor - Visão do Projecto

## Sumário Executivo

O **Bank Extractor** é uma ferramenta de gestão financeira pessoal desenvolvida em Python, desenhada para automatizar a extração de extratos bancários, gestão de faturas e tracking de despesas para utilizadores em Portugal. O projecto foca-se na **privacidade total dos dados**, mantendo toda a informação localmente no computador do utilizador.

## Problema que Resolve

### Contexto
Gerir finanças pessoais em Portugal envolve múltiplas tarefas repetitivas:

1. **Acesso manual a múltiplos bancos** - Cada banco tem o seu portal web
2. **Download de extratos** - Processo manual de navegação e download
3. **Faturas dispersas** - Faturas chegam por email e ficam perdidas
4. **Organização documental** - Necessidade de catalogar para contabilidade
5. **Visibilidade financeira** - Dificuldade em ver despesas consolidadas

### Solução
O Bank Extractor automatiza todo este processo:
- Extração automática de extratos via browser automation
- Download automático de faturas de email
- Classificação inteligente de documentos
- Relatórios consolidados
- Tracking de despesas por categoria

## Princípios Fundamentais

### 1. Privacidade Total
- Todos os dados permanecem no computador do utilizador
- Sem cloud, sem servidores externos, sem telemetria
- Credenciais armazenadas de forma segura no keyring do sistema

### 2. Automação Inteligente
- Minimizar intervenção manual
- Regras de classificação auto-aplicadas
- Deduplicação automática de downloads

### 3. Simplicidade de Uso
- Interface CLI intuitiva com output rico
- Configuração mínima necessária
- Documentação clara em português

### 4. Extensibilidade
- Arquitectura modular para adicionar novos bancos
- Suporte para múltiplos providers de email
- Sistema de regras flexível

## Fases de Desenvolvimento

### Fase 1: Infraestrutura ✅
- CLI framework com Typer + Rich
- Sistema de configuração via Pydantic Settings
- Gestão segura de credenciais via keyring
- Classes base para bancos e providers de email

### Fase 2: Download de Faturas ✅
- Implementação Gmail e Hotmail (IMAP)
- Sistema de inbox com SQLite
- Deduplicação por Message-ID e hash
- Streaming/parallel download

### Fase 3: Organizador de Documentos ✅
- Parser de PDFs para extracção de metadados
- Classificação automática por tipo e categoria
- Sistema de regras de classificação
- Base de dados SQLite para indexação

### Fase 4: Relatórios Mensais ✅
- Agregação mensal de documentos
- Geração de relatório (Console, HTML, Excel)
- Envio automático por email

### Fase 5: Tracking de Despesas ✅
- Categorização de despesas
- Orçamentos por categoria
- Alertas de despesas anormais
- Análise de tendências

### Fase 6: Gestão de Entidades ✅
- Registo de entidades (fornecedores, clientes, bancos)
- Regras de classificação automática
- Sistema de undo para processamento
- Matching por NIF, IBAN, email

## Bancos Suportados

| Banco | Estado |
|-------|--------|
| CGD Empresas | ✅ Implementado |
| Banco CTT | ✅ Implementado |

### Planeados para Futuro
- Millennium BCP
- Santander
- Novo Banco
- ActivoBank

## Providers de Email

| Provider | Estado |
|----------|--------|
| Gmail | ✅ Implementado (App Password) |
| Hotmail/Outlook | ✅ Implementado (IMAP) |

## Segurança

### Princípios
1. **Zero Trust em Cloud** - Nenhum dado sai do computador local
2. **Credenciais Seguras** - Via keyring do sistema operativo
3. **Tokens Efémeros** - SMS/2FA pedidos em runtime, nunca guardados
4. **Mínimo Privilégio** - Acesso apenas ao necessário

### Práticas Obrigatórias
- Nunca commit de credenciais ou tokens
- Ficheiros sensíveis em .gitignore
- Validação de inputs externos
- Logs sem informação sensível

## Desenvolvimento

### Setup
```bash
git clone https://github.com/Morbey/bankExtractor.git
cd bankExtractor
pip install -e ".[dev]"
playwright install chromium
```

### Convenções
- **Código**: Inglês
- **UI/Mensagens**: Português
- **Line length**: 100 caracteres
- **Docstrings**: Google-style

## Contacto

Projecto mantido por: Morbey
Repositório: https://github.com/Morbey/bankExtractor
