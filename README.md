# Bank Extractor

Gestor financeiro pessoal para automatização de extratos bancários, faturas, e controlo de despesas.

## Funcionalidades

- **Extração de Extratos Bancários** - CGD Empresas e Banco CTT (via Playwright)
- **Download de Faturas** - Gmail e Hotmail (via IMAP)
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

## Guia de Utilização

### 1. Configurar Credenciais

#### Email (Gmail)
```bash
# Configurar conta Gmail pessoal
bank-extractor faturas gmail --conta pessoal --config

# Configurar conta Gmail empresarial
bank-extractor faturas gmail --conta empresa --config
```

**Nota**: O Gmail requer App Passwords:
1. Ativar verificação em 2 passos na conta Google
2. Criar App Password em https://myaccount.google.com/apppasswords
3. Usar a App Password (sem espaços) como password

#### Bancos
```bash
# Configurar credenciais CGD
bank-extractor credenciais cgd

# Configurar credenciais Banco CTT
bank-extractor credenciais ctt
```

### 2. Download de Faturas por Email

```bash
# Download faturas dos últimos 30 dias (Gmail pessoal)
bank-extractor faturas gmail --conta pessoal

# Download dos últimos 60 dias
bank-extractor faturas gmail --conta pessoal --dias 60

# Download com datas específicas
bank-extractor faturas gmail --inicio 01-01-2026 --fim 31-01-2026

# Download de todos os providers configurados
bank-extractor faturas todos
```

### 3. Processar e Organizar Documentos

```bash
# Processar documentos de uma pasta (modo interativo)
bank-extractor processar E:\downloads\docs

# Processar em modo automático (sem prompts)
bank-extractor processar E:\downloads\docs --auto

# Mover ficheiros em vez de copiar
bank-extractor processar E:\downloads\docs --mover

# Processar subpastas também
bank-extractor processar E:\downloads\docs --recursivo
```

O sistema:
1. Deteta o tipo de documento (fatura, comprovativo, extrato, etc.)
2. Extrai NIF, IBAN, valores, datas
3. Identifica a entidade (fornecedor/cliente)
4. Se desconhecida, pede para criar ou adicionar a existente
5. Organiza na pasta correta: `faturas/<ano>/<categoria>/<entidade>/`

### 4. Gerir Entidades

```bash
# Listar entidades registadas
bank-extractor entidades listar

# Criar nova entidade
bank-extractor entidades criar --nome "EDP Comercial" --pasta "EDP" --tipo empresa --nif 503504564

# Ver detalhes de uma entidade
bank-extractor entidades ver --nome "EDP Comercial"

# Adicionar IBAN a entidade existente
bank-extractor entidades editar --id abc123 --iban PT50001234567890123456789
```

### 5. Documentos Pendentes

```bash
# Ver documentos na fila de pendentes
bank-extractor pendentes --listar

# Processar pendentes interativamente
bank-extractor pendentes --processar

# Limpar fila de pendentes
bank-extractor pendentes --limpar
```

### 6. Extratos Bancários

```bash
# Extrair extrato CGD do mês atual
bank-extractor extrair cgd

# Extrair com período específico
bank-extractor extrair cgd --inicio 01-01-2026 --fim 31-01-2026

# Extrair de todos os bancos
bank-extractor extrair todos
```

### 7. Pesquisar Documentos

```bash
# Pesquisar por texto
bank-extractor pesquisar "EDP"

# Filtrar por tipo
bank-extractor pesquisar "energia" --tipo fatura

# Filtrar por fornecedor
bank-extractor pesquisar "" --fornecedor "EDP"

# Ver detalhes de um documento
bank-extractor documento 42

# Abrir o ficheiro
bank-extractor documento 42 --abrir
```

### 8. Relatórios

```bash
# Relatório do mês atual (consola)
bank-extractor relatorio atual

# Relatório em HTML
bank-extractor relatorio 01-2026 --formato html

# Relatório em Excel
bank-extractor relatorio 01-2026 --formato excel --output relatorio.xlsx

# Relatório anual
bank-extractor relatorio-anual 2026

# Enviar por email
bank-extractor enviar 01-2026 email@exemplo.pt
```

### 9. Despesas e Orçamentos

```bash
# Ver despesas do mês atual
bank-extractor despesas

# Importar despesas dos documentos
bank-extractor despesas --importar

# Definir orçamento
bank-extractor orcamento comunicacoes --valor 50

# Listar orçamentos
bank-extractor orcamento --listar

# Ver alertas
bank-extractor alertas --verificar

# Ver tendências (últimos 6 meses)
bank-extractor tendencias
```

### 10. Gestão de Faturas

```bash
# Organizar faturas de uma pasta
bank-extractor gerir-faturas organizar --pasta E:\downloads

# Listar faturas por categoria
bank-extractor gerir-faturas listar --categoria energia

# Ver estatísticas
bank-extractor gerir-faturas stats

# Ver categorias disponíveis
bank-extractor gerir-faturas categorias
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

## Referência de Comandos

| Comando | Descrição |
|---------|-----------|
| `extrair` | Extrair extratos bancários |
| `faturas` | Download faturas do email |
| `faturas-limpar` | Limpar credenciais de email |
| `processar` | Processar e organizar documentos |
| `pendentes` | Gerir documentos pendentes |
| `entidades` | Gerir entidades (fornecedores, clientes) |
| `gerir-faturas` | Organizar faturas por categoria |
| `organizar` | Indexar documentos na base de dados |
| `pesquisar` | Pesquisar documentos |
| `documento` | Ver detalhes de um documento |
| `relatorio` | Gerar relatório mensal |
| `relatorio-anual` | Gerar relatório anual |
| `enviar` | Enviar relatório por email |
| `despesas` | Ver e analisar despesas |
| `orcamento` | Gerir orçamentos |
| `alertas` | Ver alertas de orçamento |
| `tendencias` | Ver tendências de despesas |
| `config` | Ver configuração atual |
| `credenciais` | Gerir credenciais |
| `versao` | Ver versão |

## Segurança

- Credenciais guardadas no Windows Credential Manager (nunca em ficheiros)
- Passwords nunca aparecem em logs
- Todos os dados ficam locais (sem sincronização cloud)
- Ficheiros de dados ignorados pelo Git

## Troubleshooting

### Gmail: "Authentication failed"
1. Verificar se a App Password está correta (sem espaços)
2. Verificar se "Less secure app access" NÃO está ativado
3. Criar nova App Password se necessário

### Banco: Timeout ou erro de login
1. Verificar credenciais: `bank-extractor credenciais cgd`
2. Tentar em modo não-headless: definir `HEADLESS=false` no `.env`
3. Sites bancários podem ter mudado - verificar manualmente

### Documento não reconhecido
1. Processar em modo interativo: `bank-extractor processar --interativo`
2. Criar entidade manualmente: `bank-extractor entidades criar`
3. Verificar pendentes: `bank-extractor pendentes --listar`

## Licença

Projeto pessoal - uso privado.
