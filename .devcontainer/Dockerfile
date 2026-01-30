FROM mcr.microsoft.com/devcontainers/python:3.11-bookworm

# Dependências de sistema para builds de wheels (psycopg/cryptography/pillow/etc.)
# A imagem base pode vir com repo APT do Yarn sem a chave GPG.
# Como usamos Corepack/feature do Node, removemos esse repo para evitar falha no apt-get update.
RUN rm -f /etc/apt/sources.list.d/yarn.list /etc/apt/sources.list.d/yarn*.list || true && \
  apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libpq-dev \
    libssl-dev \
    libffi-dev \
    libkrb5-dev \
    libsasl2-dev \
    libldap2-dev \
    zlib1g-dev \
    libjpeg-dev \
    libpng-dev \
    ca-certificates \
    curl \
    git \
    gnupg \
  && rm -rf /var/lib/apt/lists/*

# PostgreSQL client utilities (pg_dump/psql/etc) via PGDG
# Necessário para ferramentas como Import/Export Data, Backup/Restore.
RUN mkdir -p /usr/share/keyrings && \
  curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg && \
  echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list && \
  apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client-16 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /workspaces/databaseadmin

