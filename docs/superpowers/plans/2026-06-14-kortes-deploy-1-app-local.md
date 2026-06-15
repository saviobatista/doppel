# Kortes Deploy - Plano 1: App containerizado + paridade local

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Containerizar `api`/`worker`/`web` para produção e introduzir Alembic, sem alterar a experiência local do `docker compose` nem quebrar os 86 testes.

**Architecture:** Imagem do backend ganha um entrypoint que roda `alembic upgrade head` apenas quando o comando é `uvicorn` (o `api`); o `worker` tolera o schema via seu loop resiliente; `init_db`/`create_all` permanece só para os testes. O `web` ganha um `Dockerfile` multi-stage: target `dev` (`next dev` HMR, usado pelo compose) e `runner` (`next start` standalone + ofuscação) para prod. `docker-compose.yml` só recebe um serviço `web` aditivo.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, uv, Next.js 16 (standalone), javascript-obfuscator, Docker, docker compose.

**Referência:** spec `docs/superpowers/specs/2026-06-14-kortes-deploy-design.md` (secoes 8, 9, 10).

---

## File Structure

Criados:
- `backend/alembic.ini` - config do Alembic.
- `backend/alembic/env.py` - runner async (lê `DOPPEL_DATABASE_URL` via Settings).
- `backend/alembic/script.py.mako` - template de migration.
- `backend/alembic/versions/0001_baseline.py` - baseline (autogerada dos models).
- `backend/docker-entrypoint.sh` - roda migration no `api`, depois `exec "$@"`.
- `web/Dockerfile` - multi-stage `deps`/`dev`/`builder`/`runner`.
- `web/.dockerignore`, `backend/.dockerignore` - reduzem o contexto de build.
- `web/scripts/obfuscate.mjs` - ofusca os chunks da app pós-`next build`.

Modificados:
- `backend/pyproject.toml` - adiciona `alembic`.
- `backend/Dockerfile` - copia `alembic*` + entrypoint; define `ENTRYPOINT`.
- `backend/src/doppel_api/main.py:32` - remove `await init_db(engine)` do lifespan.
- `backend/workers/worker.py:1164` - remove `await init_db(engine)` do `main()`.
- `web/next.config.ts` - `output: "standalone"` + `productionBrowserSourceMaps: false`.
- `web/package.json` - devDep `javascript-obfuscator` + script `obfuscate`.
- `docker-compose.yml` - serviço `web` (target `dev`, HMR), aditivo.

Intocado: `backend/src/doppel_api/db.py` (`init_db` continua igual, para testes).

---

## Task 1: Adicionar Alembic ao backend (config, env async, template)

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`

- [ ] **Step 1: Adicionar a dependência `alembic`**

Em `backend/pyproject.toml`, dentro de `dependencies`, após `"pillow>=12.2.0",`:

```toml
    "pillow>=12.2.0",
    "alembic>=1.14",
```

- [ ] **Step 2: Regenerar o lock e sincronizar**

Run: `uv lock --directory /Users/savio/Kortes/backend && uv sync --directory /Users/savio/Kortes/backend`
Expected: `Resolved N packages`, inclui `alembic`.

- [ ] **Step 3: Criar `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = src
# A URL real vem de DOPPEL_DATABASE_URL via env.py; este valor nunca é usado.
sqlalchemy.url = driver://user:pass@localhost/db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Criar `backend/alembic/env.py` (async, lê a URL do Settings)**

```python
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from doppel_api.config import get_settings
from doppel_api.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A fonte da verdade da URL é o Settings (DOPPEL_DATABASE_URL), igual ao runtime.
config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
```

- [ ] **Step 5: Criar `backend/alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Commit**

```bash
git -C /Users/savio/Kortes add backend/pyproject.toml backend/uv.lock backend/alembic.ini backend/alembic/env.py backend/alembic/script.py.mako
git -C /Users/savio/Kortes commit -m "build(api): adicionar Alembic (config + env async)"
```

---

## Task 2: Gerar e verificar a baseline migration

**Files:**
- Create: `backend/alembic/versions/0001_baseline.py` (autogerada)

- [ ] **Step 1: Subir só o Postgres do compose (alvo do autogenerate)**

Run: `docker compose -f /Users/savio/Kortes/docker-compose.yml up -d postgres`
Expected: container `doppel-postgres-1` healthy.

- [ ] **Step 2: Autogerar a baseline a partir dos models (contra o banco vazio)**

Run (a partir de `backend/`, com a URL apontando ao Postgres do compose):
```bash
cd /Users/savio/Kortes/backend
DOPPEL_DATABASE_URL=postgresql+asyncpg://doppel:doppel@localhost:5432/doppel \
  uv run alembic revision --autogenerate -m baseline --rev-id 0001
```
Expected: cria `backend/alembic/versions/0001_baseline.py` com `op.create_table(...)` para `avatars`, `jobs`, `plans`, `videos`, `voices`.

- [ ] **Step 3: Revisar a migration gerada**

Abra `backend/alembic/versions/0001_baseline.py` e confirme: todas as tabelas dos models estão presentes, incluindo a coluna `bundle` (JSON) em `plans`. Remova qualquer `op` espúrio de extensões. Não deve haver `pass` no `upgrade()`.

- [ ] **Step 4: Aplicar num banco limpo e verificar**

```bash
docker compose -f /Users/savio/Kortes/docker-compose.yml exec postgres psql -U doppel -d doppel -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
cd /Users/savio/Kortes/backend
DOPPEL_DATABASE_URL=postgresql+asyncpg://doppel:doppel@localhost:5432/doppel uv run alembic upgrade head
docker compose -f /Users/savio/Kortes/docker-compose.yml exec postgres psql -U doppel -d doppel -c "\dt"
```
Expected: `alembic upgrade head` sem erro; `\dt` lista `alembic_version`, `avatars`, `jobs`, `plans`, `videos`, `voices`.

- [ ] **Step 5: Confirmar idempotência**

Run: `cd /Users/savio/Kortes/backend && DOPPEL_DATABASE_URL=postgresql+asyncpg://doppel:doppel@localhost:5432/doppel uv run alembic upgrade head`
Expected: nenhuma migration aplicada (já no head), exit 0.

- [ ] **Step 6: Commit**

```bash
git -C /Users/savio/Kortes add backend/alembic/versions/0001_baseline.py
git -C /Users/savio/Kortes commit -m "build(api): baseline de schema do Alembic"
```

---

## Task 3: Entrypoint roda a migration no `api`; remover `init_db` do runtime

**Files:**
- Create: `backend/docker-entrypoint.sh`
- Modify: `backend/Dockerfile`, `backend/src/doppel_api/main.py:32`, `backend/workers/worker.py:1164`

- [ ] **Step 1: Criar `backend/docker-entrypoint.sh`**

O entrypoint roda a migration só quando o comando é `uvicorn` (o `api`). O `worker` (comando `python ...`) cai direto no `exec`, e tolera o schema via seu loop resiliente.

```sh
#!/bin/sh
set -e

# Só o processo da API aplica as migrations no boot (idempotente). O worker
# espera o schema pelo seu proprio loop de retry. Em prod, o Helm Job ja
# aplicou antes; aqui vira no-op.
case "$1" in
  uvicorn)
    echo "entrypoint: alembic upgrade head"
    alembic upgrade head
    ;;
esac

exec "$@"
```

- [ ] **Step 2: Tornar executável**

Run: `chmod +x /Users/savio/Kortes/backend/docker-entrypoint.sh`
Expected: sem saída.

- [ ] **Step 3: Atualizar `backend/Dockerfile`**

Substitua o conteúdo a partir da linha `COPY src ./src` para copiar o Alembic e instalar o entrypoint:

```dockerfile
COPY src ./src
COPY workers ./workers
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN uv sync --no-dev
ENV PATH="/app/.venv/bin:$PATH"
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["uvicorn", "doppel_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Remover `init_db` do lifespan do `api`**

Em `backend/src/doppel_api/main.py`, dentro do `lifespan`, remova a linha:

```python
            await init_db(engine)
```

E remova `init_db` do import na linha 9:

```python
from doppel_api.db import make_engine, make_session_factory
```

- [ ] **Step 5: Remover `init_db` do `main()` do worker**

Em `backend/workers/worker.py`, no `main()`, remova a linha:

```python
    await init_db(engine)
```

E ajuste o import (linha 17) removendo `init_db`:

```python
from doppel_api.db import make_engine, make_session_factory
```

- [ ] **Step 6: Rodar os testes (init_db ainda é usado pelo conftest)**

Run: `uv run --directory /Users/savio/Kortes/backend python -m pytest -q`
Expected: `75 passed` no mínimo (a falha pré-existente `test_avatar_prep_second_run_uses_cache` por ffmpeg/cache pode persistir; nenhuma falha NOVA). `init_db` continua importado por `tests/conftest.py`, então sem `ImportError`.

- [ ] **Step 7: Build + subida completa do compose (valida paridade e migration)**

```bash
docker compose -f /Users/savio/Kortes/docker-compose.yml up -d --build api stub-worker postgres redis floci
docker compose -f /Users/savio/Kortes/docker-compose.yml logs --since 2m api | grep -i "alembic upgrade head"
docker compose -f /Users/savio/Kortes/docker-compose.yml exec postgres psql -U doppel -d doppel -c "\dt"
```
Expected: log do entrypoint com "alembic upgrade head"; `\dt` mostra as tabelas + `alembic_version`. O app responde em `http://localhost:8200`.

- [ ] **Step 8: Commit**

```bash
git -C /Users/savio/Kortes add backend/docker-entrypoint.sh backend/Dockerfile backend/src/doppel_api/main.py backend/workers/worker.py
git -C /Users/savio/Kortes commit -m "feat(api): migration automatica via entrypoint; schema por Alembic em runtime"
```

---

## Task 4: `web` - standalone, sem source maps e ofuscação dos chunks

**Files:**
- Modify: `web/next.config.ts`, `web/package.json`
- Create: `web/scripts/obfuscate.mjs`

- [ ] **Step 1: Atualizar `web/next.config.ts`**

```ts
import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Standalone empacota um servidor Node minimo para a imagem de producao.
  output: "standalone",
  // Sem source maps no cliente: nao expor o mapa de volta ao codigo-fonte.
  productionBrowserSourceMaps: false,
  // Pin the workspace root to this app (multiple lockfiles exist higher up).
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
```

- [ ] **Step 2: Adicionar a devDependency e o script de ofuscação**

Run: `cd /Users/savio/Kortes/web && npm install --save-dev javascript-obfuscator`
Expected: adiciona `javascript-obfuscator` em `devDependencies` do `web/package.json`.

Em `web/package.json`, no bloco `scripts`, adicione:

```json
    "obfuscate": "node scripts/obfuscate.mjs"
```

- [ ] **Step 3: Criar `web/scripts/obfuscate.mjs`**

Config moderada (sem control-flow flattening nem dead-code) para nao quebrar o runtime do Next nem degradar a performance.

```js
import { readdir, readFile, writeFile, stat } from "node:fs/promises";
import { join } from "node:path";
import JavaScriptObfuscator from "javascript-obfuscator";

const ROOT = ".next/static/chunks";

const OPTIONS = {
  compact: true,
  controlFlowFlattening: false,
  deadCodeInjection: false,
  selfDefending: false,
  simplify: true,
  stringArray: true,
  stringArrayThreshold: 0.6,
  stringArrayEncoding: ["base64"],
  identifierNamesGenerator: "mangled",
  numbersToExpressions: false,
};

async function* jsFiles(dir) {
  for (const entry of await readdir(dir)) {
    const full = join(dir, entry);
    const info = await stat(full);
    if (info.isDirectory()) {
      yield* jsFiles(full);
    } else if (entry.endsWith(".js")) {
      yield full;
    }
  }
}

let count = 0;
for await (const file of jsFiles(ROOT)) {
  const code = await readFile(file, "utf8");
  const out = JavaScriptObfuscator.obfuscate(code, OPTIONS).getObfuscatedCode();
  await writeFile(file, out);
  count += 1;
}
console.log(`obfuscated ${count} chunk(s)`);
```

- [ ] **Step 4: Commit**

```bash
git -C /Users/savio/Kortes add web/next.config.ts web/package.json web/package-lock.json web/scripts/obfuscate.mjs
git -C /Users/savio/Kortes commit -m "feat(web): standalone, sem source maps e ofuscacao dos chunks"
```

---

## Task 5: `web/Dockerfile` multi-stage (dev HMR + runner standalone + ofuscado)

**Files:**
- Create: `web/Dockerfile`, `web/.dockerignore`, `backend/.dockerignore`

- [ ] **Step 1: Criar `web/.dockerignore`**

```
node_modules
.next
.git
Dockerfile
.dockerignore
npm-debug.log*
```

- [ ] **Step 2: Criar `backend/.dockerignore`**

```
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
tests
.dockerignore
```

- [ ] **Step 3: Criar `web/Dockerfile`**

```dockerfile
# syntax=docker/dockerfile:1

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# Target de desenvolvimento: usado pelo docker compose, com HMR.
FROM node:22-alpine AS dev
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
EXPOSE 3000
CMD ["npm", "run", "dev", "--", "--port", "3000", "--hostname", "0.0.0.0"]

# Build de producao + ofuscacao dos chunks.
FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build
RUN npm run obfuscate

# Runner: imagem minima com o servidor standalone.
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
CMD ["node", "server.js"]
```

- [ ] **Step 4: Buildar o target `runner` e validar que sobe**

```bash
docker build -t kortes-web:test --target runner /Users/savio/Kortes/web
docker run --rm -d --name kortes-web-test -p 3000:3000 kortes-web:test
sleep 3
curl -sSf -o /dev/null -w "%{http_code}\n" http://localhost:3000/
docker logs kortes-web-test | tail -5
docker rm -f kortes-web-test
```
Expected: build OK; `curl` retorna `200`; logs sem erro de runtime (valida que a ofuscação não quebrou o app).

- [ ] **Step 5: Commit**

```bash
git -C /Users/savio/Kortes add web/Dockerfile web/.dockerignore backend/.dockerignore
git -C /Users/savio/Kortes commit -m "feat(web): Dockerfile multi-stage (dev HMR + runner standalone)"
```

---

## Task 6: Serviço `web` no compose (dev/HMR) - aditivo

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Adicionar o serviço `web` ao `docker-compose.yml`**

Após o serviço `stub-worker` (antes do bloco `volumes:`), adicione:

```yaml
  web:
    build:
      context: ./web
      target: dev
    restart: unless-stopped
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8200
      NEXT_TELEMETRY_DISABLED: "1"
      WATCHPACK_POLLING: "true"
    ports: ["3100:3000"]
    volumes:
      - ./web:/app
      - /app/node_modules
      - /app/.next
    depends_on:
      api: {condition: service_started}
```

- [ ] **Step 2: Subir o web pelo compose e validar HMR**

```bash
docker compose -f /Users/savio/Kortes/docker-compose.yml up -d --build web
curl -sSf -o /dev/null -w "%{http_code}\n" http://localhost:3100/
```
Expected: `200`. Editar um arquivo em `web/src/app/page.tsx` recarrega no navegador sem rebuild (HMR via bind mount).

- [ ] **Step 3: Commit**

```bash
git -C /Users/savio/Kortes add docker-compose.yml
git -C /Users/savio/Kortes commit -m "feat(web): servico web no compose com hot reload (dev)"
```

---

## Task 7: Verificação integrada de paridade

**Files:** nenhum (verificação).

- [ ] **Step 1: Subida limpa do stack completo**

```bash
docker compose -f /Users/savio/Kortes/docker-compose.yml down -v
docker compose -f /Users/savio/Kortes/docker-compose.yml up -d --build
docker compose -f /Users/savio/Kortes/docker-compose.yml ps
```
Expected: `postgres`, `redis`, `floci`, `api`, `stub-worker`, `web` todos `Up`.

- [ ] **Step 2: Verificar migration e schema**

```bash
docker compose -f /Users/savio/Kortes/docker-compose.yml exec postgres psql -U doppel -d doppel -c "SELECT version_num FROM alembic_version;"
```
Expected: `0001`.

- [ ] **Step 3: Smoke do fluxo (a mesma experiência de hoje)**

```bash
TOKEN=$(curl -s -X POST http://localhost:8200/v1/sessions | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "token: $TOKEN"
curl -s -o /dev/null -w "web %{http_code}\n" http://localhost:3100/
```
Expected: token não-vazio; `web 200`. O backend responde igual ao fluxo atual.

- [ ] **Step 4: Suite de testes final**

Run: `uv run --directory /Users/savio/Kortes/backend python -m pytest -q`
Expected: mesma contagem de antes do plano (sem falhas novas).

- [ ] **Step 5: Confirmar que o `git diff` no fluxo local é só aditivo**

Run: `git -C /Users/savio/Kortes log --oneline -7`
Expected: os 6 commits deste plano acima do `b57e035`. O `docker-compose.yml` só ganhou o serviço `web`; nenhum serviço existente foi alterado.

---

## Self-Review (cobertura do spec)

- Spec secao 8 (Alembic, migration automatica, create_all -> Alembic): Tasks 1-3. `init_db`/create_all preservado para testes; runtime via entrypoint.
- Spec secao 9 (ofuscacao + sem source maps + minify): Task 4 (next config + obfuscate) e Task 5 (runner roda obfuscate).
- Spec secao 10 (hot reload local, Dockerfile multi-stage dev/runner): Tasks 5-6.
- Princípio P1 (paridade local intocada): `docker-compose.yml` só recebe serviço aditivo; backend/web buildam a mesma imagem que roda em prod; Task 7 valida a subida idêntica.
- Fora deste plano (Planos 2-5): Terraform/IRSA/OIDC/ECR/ACM, Helm chart + Argo + migrate-Job, GitHub Actions, cutover/DNS.

## Riscos

- **Ofuscação quebrar o runtime do Next**: mitigado por config moderada (sem control-flow flattening) e validado no Step 4 da Task 5 (curl 200 + logs). Se quebrar, reduzir o escopo (ofuscar só `static/chunks/app/**`).
- **Autogenerate incompleto**: a Task 2 Step 3 exige revisão manual da baseline (conferir `bundle` em `plans`).
- **Falha pré-existente de teste** (`test_avatar_prep_second_run_uses_cache`, ffmpeg/cache): não é regressão; o critério é "sem falhas novas".
