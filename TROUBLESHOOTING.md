# Guia de Troubleshooting

Este guia ajuda a resolver os problemas mais comuns do Bank Extractor.

## Problemas Comuns

### 1. Autenticação Gmail Falhou

**Erro**: `Authentication failed for gmail` ou `Invalid credentials`

**Soluções**:

1. **Verificar App Password**:
   - O Gmail requer App Passwords, não a password normal
   - Aceda a https://myaccount.google.com/apppasswords
   - Gere uma nova App Password para "Mail"
   - Introduza sem espaços (16 caracteres)

2. **Verificar 2FA está Activo**:
   - App Passwords só funcionam com 2FA activo
   - Active em https://myaccount.google.com/security

3. **IMAP deve estar Activo**:
   - Vá a Definições do Gmail > Encaminhamento e POP/IMAP
   - Active o IMAP

4. **Reconfigurar Credenciais**:
   ```bash
   bank-extractor config credenciais gmail --conta pessoal
   ```

### 2. Login Bancário Timeout/Falhou

**Erro**: `Timeout waiting for element` ou `Login failed`

**Soluções**:

1. **Testar Manualmente Primeiro**:
   - Abra o site do banco num browser
   - Verifique se as credenciais funcionam manualmente

2. **Tentar Modo Não-Headless**:
   ```bash
   # No ficheiro .env:
   HEADLESS=false
   ```
   Execute o comando e observe o browser.

3. **Repor Credenciais**:
   ```bash
   bank-extractor config credenciais cgd
   ```

4. **Site do Banco Pode Ter Mudado**:
   - Os sites bancários actualizam frequentemente
   - Verifique actualizações do projecto ou reporte o problema

### 3. Documento PDF Não Reconhecido

**Erro**: Documento aparece como "outros" ou entidade desconhecida

**Soluções**:

1. **Processar Interactivamente**:
   ```bash
   bank-extractor documentos processar E:\docs --interativo
   ```

2. **Criar Entidade Manualmente**:
   ```bash
   bank-extractor entidades criar --nome "Nome Empresa" --pasta "NomeEmpresa" --nif "123456789"
   ```

3. **Verificar Extracção de Texto do PDF**:
   - Alguns PDFs são imagens digitalizadas
   - Instale suporte OCR: `pip install bank-extractor[ocr]`

4. **Ver Documentos Pendentes**:
   ```bash
   bank-extractor documentos pendentes --listar
   ```

### 4. OCR Não Funciona

**Erro**: `OCR not available` ou `OCR failed`

**Soluções**:

1. **Instalar Dependências OCR**:
   ```bash
   pip install bank-extractor[ocr]
   ```

2. **Primeira Execução é Lenta**:
   - EasyOCR descarrega modelos de linguagem na primeira utilização
   - Aguarde 2-5 minutos para configuração inicial

3. **Problemas de Memória**:
   - OCR requer RAM significativa
   - Feche outras aplicações
   - Processe menos ficheiros de cada vez

### 5. Erros de Base de Dados

**Erro**: Erros `SQLAlchemy` ou database locked

**Soluções**:

1. **Reconstruir Índice**:
   ```bash
   bank-extractor documentos processar --reindexar
   ```

2. **Limpar Fila de Pendentes**:
   ```bash
   bank-extractor documentos pendentes --limpar
   ```

3. **Verificar Ficheiro de Base de Dados**:
   - Localização: `data/catalogo/documents.db`
   - Elimine se corrompido (será recriado)

### 6. Problemas de Armazenamento de Credenciais (Windows)

**Erro**: Erros `keyring`

**Soluções**:

1. **Verificar Windows Credential Manager**:
   - Abra Painel de Controlo > Gestor de Credenciais
   - Procure entradas "bank-extractor"
   - Elimine entradas corrompidas

2. **Repor Todas as Credenciais**:
   ```bash
   bank-extractor config credenciais cgd
   bank-extractor config credenciais ctt
   bank-extractor config credenciais gmail
   ```

### 7. Erros de Import no Arranque

**Erro**: `ModuleNotFoundError` ou `ImportError`

**Soluções**:

1. **Reinstalar Pacote**:
   ```bash
   pip install -e .
   ```

2. **Instalar Browsers Playwright**:
   ```bash
   playwright install chromium
   ```

3. **Verificar Versão Python**:
   ```bash
   python --version  # Deve ser 3.10+
   ```

### 8. Classificação de Transferências Incorrecta

**Erro**: Transferências aparecem como recebimento em vez de pagamento (ou vice-versa)

**Soluções**:

1. **Registar as Suas Contas**:
   - Edite `data/transfer_config.json`
   - Adicione os seus IBANs à lista `my_accounts`

2. **Verificar Mapeamento de IBANs**:
   ```bash
   bank-extractor entidades listar
   ```
   Confirme que os IBANs das entidades estão correctos.

---

## FAQ

### Como faço backup dos meus dados?

Copie toda a pasta `data/`:
- `data/faturas/` - Faturas organizadas
- `data/catalogo/` - Base de dados de documentos
- `data/entities.json` - Definições de entidades
- `data/transfer_config.json` - Mapeamentos de IBAN

### Posso usar múltiplas contas Gmail?

Sim, use a opção `--conta`:
```bash
bank-extractor email download gmail --conta pessoal
bank-extractor email download gmail --conta empresa
```

### Como mudo o directório de dados?

Edite o ficheiro `.env`:
```
DATA_DIR=D:\MinhasFinancas\data
```

### Os meus dados são sincronizados para a cloud?

Não. Todos os dados ficam locais. Nada é enviado para a internet.

### Quão seguros estão os meus dados?

- Credenciais são guardadas no Windows Credential Manager, não em ficheiros
- Tokens SMS nunca são guardados
- Todos os dados financeiros ficam apenas no seu computador

### Como reporto um bug?

Crie um issue em GitHub com:
- Comando que falhou
- Mensagem de erro completa
- Versão Python (`python --version`)
- Versão do SO

---

## Obter Ajuda

1. Consulte este guia de troubleshooting
2. Reveja o README.md
3. Verifique issues existentes no GitHub
4. Crie um novo issue com informação detalhada
