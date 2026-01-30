## Devcontainer (pgAdmin4)

Este diretório contém a configuração para abrir o projeto no **Dev Containers** (VS Code/Cursor).

### Serviços
- **dev**: ambiente de desenvolvimento (Python + Node) com o código montado em `/workspaces/databaseadmin`.
- **db**: PostgreSQL 16 para desenvolvimento/testes.

### Portas
- **pgAdmin**: `5050` (e `5051` se necessário)
- **Postgres**: dentro da rede do compose: `db:5432`  
  no host: `localhost:5436`

### Pós-criação
O `postCreate.sh`:
- cria `web/config_local.py` (ignorado pelo git) com `DATA_DIR` gravável e `DEFAULT_BINARY_PATHS`
- instala dependências Python (`requirements.txt` e `web/regression/requirements.txt`)
- instala dependências JS e gera o bundle (`web/yarn install` + `yarn run bundle`)

