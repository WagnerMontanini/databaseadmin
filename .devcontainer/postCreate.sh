#!/usr/bin/env bash
set -euo pipefail

# Evitar prompts interativos durante setup
export CI=1
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1
# Corepack pode pedir confirmação para baixar gerenciadores; desabilitar prompt
export COREPACK_ENABLE_DOWNLOAD_PROMPT=0
# Desabilitar telemetria do Yarn (sem prompt)
export YARN_ENABLE_TELEMETRY=0

cd /workspaces/databaseadmin

echo "[devcontainer] Configurando pgAdmin DATA_DIR/SQLITE_PATH (config_local.py)..."
# O pgAdmin por padrão tenta usar /var/lib/pgadmin (sem permissão para o usuário vscode).
# Criamos um config_local.py apontando para um diretório gravável no home do container.
PGADMIN_DATA_DIR="${HOME}/.pgadmin_dev"
mkdir -p "${PGADMIN_DATA_DIR}"

if [ ! -f "web/config_local.py" ]; then
  cat > "web/config_local.py" <<EOF
import os

# Devcontainer: manter dados em diretório gravável pelo usuário do container
DATA_DIR = "${PGADMIN_DATA_DIR}"

# Expor o servidor para fora do container (porta encaminhada pelo devcontainer)
DEFAULT_SERVER = "0.0.0.0"
DEFAULT_SERVER_PORT = 5050

# Para dev local, evitar dependência de SMTP e setup interativo do modo server.
SERVER_MODE = False

SQLITE_PATH = os.path.join(DATA_DIR, "pgadmin4-desktop.db")
SESSION_DB_PATH = os.path.join(DATA_DIR, "sessions")
STORAGE_DIR = os.path.join(DATA_DIR, "storage")

# Postgres client utilities dentro do devcontainer (pg_dump/psql/etc)
# Isso evita o erro "Utility file not found. Please correct the Binary Path..."
DEFAULT_BINARY_PATHS = {
    "pg": "/usr/lib/postgresql/16/bin",
    "pg-16": "/usr/lib/postgresql/16/bin",
}
EOF
fi

mkdir -p "${PGADMIN_DATA_DIR}/sessions" "${PGADMIN_DATA_DIR}/storage"

# Se o config_local.py já existia antes (ex.: de um rebuild anterior),
# garanta que o DEFAULT_BINARY_PATHS esteja definido.
if [ -f "web/config_local.py" ] && ! grep -q "DEFAULT_BINARY_PATHS" "web/config_local.py"; then
  cat >> "web/config_local.py" <<'EOF'

# Postgres client utilities dentro do devcontainer (pg_dump/psql/etc)
DEFAULT_BINARY_PATHS = {
    "pg": "/usr/lib/postgresql/16/bin",
    "pg-16": "/usr/lib/postgresql/16/bin",
}
EOF
fi

echo "[devcontainer] Atualizando pip..."
python -m pip install --no-input --upgrade pip

echo "[devcontainer] Instalando dependências Python..."
python -m pip install --no-input -r requirements.txt
python -m pip install --no-input -r web/regression/requirements.txt

echo "[devcontainer] Instalando dependências JS (web/)..."
cd web
corepack enable
yarn install --inline-builds
yarn run bundle

echo "[devcontainer] Pronto."
echo "[devcontainer] Para gerar o bundle: cd web && yarn run bundle"
echo "[devcontainer] Para rodar: python web/setup.py setup-db && python web/pgAdmin4.py"

