# Bank Extractor

Gestor financeiro pessoal para automatização de extratos bancários, faturas, e controlo de despesas.

## Funcionalidades

- **Extração de Extratos Bancários** - CGD Empresas e Banco CTT (via Playwright)
- **Download de Faturas** - Gmail e Hotmail (via IMAP) com sistema de inbox SQLite
- **Organização de Documentos** - Classificação automática por categoria e entidade
- **Gestão de Entidades** - Tracking de fornecedores, clientes, bancos por NIF/IBAN
- **Relatórios Mensais** - Console, HTML, Excel
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

O CLI está organizado em **7 grupos de comandos** (por ordem alfabética):

```
bank-extractor
├── config       # Configuração da aplicação
├── despesas     # Tracking de despesas
├── documentos   # Gestão de documentos
├── entidades    # Gestão de entidades
├── extratos     # Extração de extratos bancários
├── faturas      # Gestão de faturas
└── relatorios   # Relatórios financeiros
```

Use `--help` em qualquer nível para ver opções disponíveis:
```bash
bank-extractor --help              # Lista de grupos
bank-extractor faturas --help      # Subcomandos de faturas
bank-extractor faturas download --help  # Opções do subcomando
```

## Guia de Utilização

### 1. Configurar Credenciais

#### Email (Gmail)
```bash
# Configurar conta Gmail pessoal
bank-extractor faturas download gmail --conta pessoal --config

# Configurar conta Gmail empresarial
bank-extractor faturas download gmail --conta empresa --config
```

**Nota**: O Gmail requer App Passwords:
1. Ativar verificação em 2 passos na conta Google
2. Criar App Password em https://myaccount.google.com/apppasswords
3. Usar a App Password (sem espaços) como password

#### Bancos
```bash
# Configurar credenciais CGD
bank-extractor config credenciais cgd

# Configurar credenciais Banco CTT
bank-extractor config credenciais ctt
```

### 2. Download de Faturas por Email

O comando `faturas` oferece dois fluxos:

#### Fluxo Simples (download + processamento)
```bash
# Download faturas dos últimos 30 dias (Gmail pessoal)
bank-extractor faturas download gmail --conta pessoal

# Download dos últimos 60 dias
bank-extractor faturas download gmail --conta pessoal --dias 60

# Download de todos os providers configurados
bank-extractor faturas download todos

# Processar enquanto descarrega (streaming)
bank-extractor faturas download --paralelo
```

#### Fluxo Inbox (descarregar agora, processar depois)
```bash
# Descarregar emails para o inbox (sem processar)
bank-extractor faturas scrape gmail --dias 60
bank-extractor faturas scrape todos --dias 30

# Ver estado do inbox
bank-extractor faturas inbox --stats

# Listar anexos pendentes
bank-extractor faturas inbox --listar

# Processar anexos pendentes
bank-extractor faturas processar --limite 10
bank-extractor faturas processar --interativo
```

**Sistema de Deduplicação:**
- Emails identificados por Message-ID (não re-descarrega o mesmo email)
- Ficheiros identificados por SHA-256 hash (não duplica anexos)

### 3. Processar e Organizar Documentos

```bash
# Processar documentos de uma pasta (modo interativo)
bank-extractor documentos processar E:\downloads\docs

# Processar em modo automático (sem prompts)
bank-extractor documentos processar E:\downloads\docs --auto

# Mover ficheiros em vez de copiar
bank-extractor documentos processar E:\downloads\docs --mover

# Processar subpastas também
bank-extractor documentos processar E:\downloads\docs --recursivo
```

O sistema:
1. Deteta o tipo de documento (fatura, comprovativo, extrato, etc.)
2. Extrai NIF, IBAN, valores, datas
3. Identifica a entidade (fornecedor/cliente)
4. Se desconhecida, pede para criar ou adicionar a existente
5. Organiza na pasta correta: `faturas/<ano>/<categoria>/<entidade>/`

#### Menu Interativo

Durante o processamento, para cada documento desconhecido:
1. **Criar nova entidade** - Cria entidade e regra de classificação
2. **Associar a entidade existente** - Liga a uma entidade já registada
3. **Ver mais informação** - Mostra body do email, conteúdo do PDF
4. **Ignorar** - Deixa pendente (escolhe razão e pode criar regra)
5. **Eliminar** - Remove permanentemente (escolhe razão e pode criar regra)
6. **Voltar atrás** - Desfaz a última ação (se disponível)

#### Padrões para Regras

Ao criar regras de classificação, pode usar:
- **Wildcards**: `*@vodafone.pt` (qualquer email da vodafone), `*fatura*` (contém "fatura")
- **Múltiplos padrões (OR)**: `termo1|termo2|termo3` (corresponde a qualquer um)
- **Múltiplos padrões (AND)**: `termo1&termo2` (tem de conter ambos)
- **Visualização interativa**: Durante a definição do padrão, use `v` (ver campo), `b` (body), `p` (PDF), `a` (abrir ficheiro)

### 4. Gerir Entidades

```bash
# Listar entidades registadas
bank-extractor entidades gerir listar

# Criar nova entidade
bank-extractor entidades gerir criar --nome "EDP Comercial" --pasta "EDP" --tipo empresa --nif 503504564

# Ver detalhes de uma entidade
bank-extractor entidades gerir ver --nome "EDP Comercial"

# Adicionar IBAN a entidade existente
bank-extractor entidades gerir editar --id abc123 --iban PT50001234567890123456789
```

### 5. Documentos Pendentes

O comando `pendentes` mostra duas categorias:
- **Por Processar**: Ficheiros na pasta `_pendentes/` que ainda não foram processados
- **Ignorados**: Documentos explicitamente ignorados durante o processamento

```bash
# Ver todos os documentos pendentes (ambas categorias)
bank-extractor documentos pendentes --listar

# Ver estatísticas por razão de ignorar
bank-extractor documentos pendentes --stats

# Filtrar ignorados por razão (spam, duplicado, pessoal, irrelevante, incompleto, outro, sem_razao)
bank-extractor documentos pendentes --razao spam

# Remover documento da lista de ignorados (por ID)
bank-extractor documentos pendentes --restaurar 8826ac63

# Remover e reprocessar imediatamente
bank-extractor documentos pendentes --reprocessar 8826ac63

# Processar todos os pendentes interativamente
bank-extractor documentos pendentes --processar

# Limpar fila de ignorados
bank-extractor documentos pendentes --limpar
```

#### Razões para Ignorar/Eliminar

Ao ignorar ou eliminar um documento, pode escolher uma razão:
- `spam` - Spam ou publicidade
- `duplicado` - Documento duplicado
- `pessoal` - Documento pessoal (não empresarial)
- `irrelevante` - Não relevante para contabilidade
- `incompleto` - Documento incompleto ou corrompido
- `outro` - Outra razão

#### Função Undo

Durante o processamento interativo, pode desfazer a última ação (opção 6 no menu).
Ações que podem ser desfeitas:
- Organização de documentos (volta para `_pendentes/`)
- Ignorar documentos (remove da fila de ignorados)

**Nota**: Eliminação de ficheiros não pode ser desfeita.

### 6. Extratos Bancários

```bash
# Extrair extrato CGD do mês atual
bank-extractor extratos cgd

# Extrair com período específico
bank-extractor extratos cgd --inicio 01-01-2026 --fim 31-01-2026

# Extrair do Banco CTT
bank-extractor extratos ctt

# Extrair de todos os bancos
bank-extractor extratos todos
```

### 7. Pesquisar Documentos

```bash
# Pesquisar por texto
bank-extractor documentos pesquisar "EDP"

# Filtrar por tipo
bank-extractor documentos pesquisar "energia" --tipo fatura

# Filtrar por fornecedor
bank-extractor documentos pesquisar "" --fornecedor "EDP"

# Ver detalhes de um documento
bank-extractor documentos ver 42

# Abrir o ficheiro
bank-extractor documentos ver 42 --abrir
```

### 8. Relatórios

```bash
# Relatório do mês atual (consola)
bank-extractor relatorios mensal atual

# Relatório em HTML
bank-extractor relatorios mensal 01-2026 --formato html

# Relatório em Excel
bank-extractor relatorios mensal 01-2026 --formato excel --output relatorio.xlsx

# Relatório anual
bank-extractor relatorios anual 2026

# Enviar por email
bank-extractor relatorios enviar 01-2026 email@exemplo.pt
```

### 9. Despesas e Orçamentos

```bash
# Ver despesas do mês atual
bank-extractor despesas ver

# Importar despesas dos documentos
bank-extractor despesas ver --importar

# Definir orçamento
bank-extractor despesas orcamento comunicacoes --valor 50

# Listar orçamentos
bank-extractor despesas orcamento --listar

# Ver alertas
bank-extractor despesas alertas --verificar

# Ver tendências (últimos 6 meses)
bank-extractor despesas tendencias
```

### 10. Gestão de Ficheiros de Faturas

```bash
# Organizar faturas de uma pasta
bank-extractor faturas gerir organizar --pasta E:\downloads

# Listar faturas por categoria
bank-extractor faturas gerir listar --categoria energia

# Ver estatísticas
bank-extractor faturas gerir stats

# Ver categorias disponíveis
bank-extractor faturas gerir categorias
```

## Estrutura de Pastas

```
data/
├── faturas/                    # Faturas organizadas
│   └── 2026/
│       ├── energia/
│       │   └── EDP/
│       ├── comunicacoes/
│       │   └── Vodafone/
│       └── educacao/
│           └── Misericordia_Amadora/
├── inbox/                      # Base de dados do inbox
│   └── inbox.db
├── pagamentos/                 # Comprovativos de pagamento (saída)
│   └── comprovativos/
│       └── Moveis_Ribeiro/
├── recebimentos/               # Comprovativos de recebimento (entrada)
│   └── comprovativos/
│       └── Cliente_X/
├── extratos/                   # Extratos bancários
│   └── cgd/
└── temp/                       # Ficheiros temporários
```

## Categorias de Documentos

| Categoria | Pasta | Exemplos |
|-----------|-------|----------|
| Comunicações | `comunicacoes` | Vodafone, NOS, MEO |
| Energia | `energia` | EDP, Galp, Endesa |
| Água | `agua` | SIMAS, EPAL |
| Combustível | `combustivel` | Galp, BP, Repsol |
| Seguros | `seguros` | Fidelidade, Allianz |
| Educação | `educacao` | Escolas, ATL |
| Saúde | `saude` | Farmácias, Clínicas |
| Software | `software` | Microsoft, Adobe |
| Bancário | `bancario` | Extratos, comissões |
| Via Verde | `via_verde` | Portagens |
| Outros | `outros` | Não categorizados |

## Tipos de Documentos

- **Fatura** - Documentos de cobrança
- **Comprovativo de Transferência** - Provas de pagamento/recebimento
- **Nota de Crédito** - Devoluções, anulações
- **Extrato Bancário** - Movimentos de conta
- **Recibo** - Comprovativo de pagamento

## Referência Rápida de Comandos

| Grupo | Subcomando | Descrição |
|-------|------------|-----------|
| **config** | credenciais | Gerir credenciais guardadas |
| | ver | Mostrar configuração atual |
| | versao | Mostrar versão |
| **despesas** | alertas | Ver e gerir alertas |
| | orcamento | Gerir orçamentos por categoria |
| | tendencias | Ver tendências de despesas |
| | ver | Ver e analisar despesas |
| **documentos** | organizar | Organizar e catalogar documentos |
| | pendentes | Gerir documentos pendentes |
| | pesquisar | Pesquisar documentos no catálogo |
| | processar | Processar e classificar documentos |
| | ver | Ver detalhes de um documento |
| **entidades** | gerir | Gerir entidades (fornecedores, clientes) |
| | regras | Gerir regras de classificação |
| **extratos** | cgd | Extrair extratos da CGD Empresas |
| | ctt | Extrair extratos do Banco CTT |
| | todos | Extrair extratos de todos os bancos |
| **faturas** | credenciais | Limpar credenciais de email |
| | download | Descarregar e processar faturas do email |
| | gerir | Organizar ficheiros e estatísticas |
| | inbox | Gerir inbox - stats, listar, migrar |
| | processar | Processar anexos pendentes do inbox |
| | scrape | Descarregar emails para inbox (sem processar) |
| **relatorios** | anual | Gerar relatório anual |
| | enviar | Enviar relatório por email |
| | mensal | Gerar relatório mensal |

## Segurança

- Credenciais guardadas no Windows Credential Manager (nunca em ficheiros)
- Passwords nunca aparecem em logs
- Todos os dados ficam locais (sem sincronização cloud)
- Ficheiros de dados ignorados pelo Git

## Troubleshooting

Para um guia completo de resolução de problemas, consulte [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### Quick Fixes

| Problema | Solução Rápida |
|----------|----------------|
| Gmail auth failed | Use App Password, não password normal |
| Banco timeout | Defina `HEADLESS=false` no `.env` |
| Documento desconhecido | Execute com `--interativo` |
| OCR não funciona | `pip install bank-extractor[ocr]` |

### Gmail: "Authentication failed"
1. Verificar se a App Password está correta (sem espaços)
2. Verificar se "Less secure app access" NÃO está ativado
3. Criar nova App Password se necessário

### Banco: Timeout ou erro de login
1. Verificar credenciais: `bank-extractor config credenciais cgd`
2. Tentar em modo não-headless: definir `HEADLESS=false` no `.env`
3. Sites bancários podem ter mudado - verificar manualmente

### Documento não reconhecido
1. Processar em modo interativo: `bank-extractor documentos processar --interativo`
2. Criar entidade manualmente: `bank-extractor entidades gerir criar`
3. Verificar pendentes: `bank-extractor documentos pendentes --listar`

## Licença

Projeto pessoal - uso privado.
