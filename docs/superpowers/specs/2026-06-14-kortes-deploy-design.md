# Design: Deploy do Kortes no cluster `mda-development`

Data: 2026-06-14
Branch alvo: `feature/v2beta`
Status: aprovado (brainstorming), pendente de plano de implementação.

## 1. Contexto e objetivo

Kortes gera vídeos de avatar com IA (API FastAPI + worker assíncrono + frontend
Next.js). A `feature/v2beta` (o "Video Agent") está validada localmente via
`docker compose`. Este documento define o deploy do MVP em produção no cluster
EKS `mda-development` (conta `mydatagent-dev`), servindo o apex `kortes.ai`,
via GitOps com ArgoCD.

Objetivo: app no ar em `kortes.ai` (web) e `api.kortes.ai` (api), com a **mesma
experiência** do compose local, sem regredir o fluxo de desenvolvimento.

## 2. Escopo

Dentro:
- Workloads do app no namespace `kortes-dev`: `web`, `api`, `worker`, `postgres`, `redis`.
- Imagens (ECR), CI (GitHub Actions/OIDC), CD (ArgoCD/Helm).
- Networking: Ingress/ALB, TLS (ACM), DNS (Route53).
- Config/secrets/IRSA, storage (PVC), migrations (Alembic).
- Proteção/ofuscação do frontend.
- Provisionamento AWS via Terraform + Terragrunt.

Fora:
- **FLUX.2 self-hosted** (cluster Starya / `eks-inference-stack`): permanece
  externo, consumido por URL apenas quando `BROLL_T2I_DRIVER=flux2`. Default fica
  no fal gerenciado. Sem nós de GPU neste deploy.
- Ambientes `uat`/`prod` separados (hoje um único ambiente serve o apex).
- Datastores gerenciados (RDS/ElastiCache) - in-cluster no MVP.

## 3. Princípios

**P1 (CRÍTICO) - Paridade local intocada.** O deploy é 100% aditivo. Zero
mudança no código de runtime e no fluxo do `docker compose`. Garantido por:
- 12-factor: config 100% via env (`DOPPEL_*`, `NEXT_PUBLIC_*`). Local injeta via
  compose + `floci` (S3 emulado); prod via ConfigMap/Secret + S3 real (IRSA).
  **Mesma imagem, só o env muda.**
- A imagem de prod é a mesma que pode rodar local -> comportamento idêntico.
- Migrations e bootstrap rodam automaticamente, sem novo passo manual.

**P2 - Mínima superfície de mudança.** Apenas arquivos novos. A única alteração de
código é `output: "standalone"` em `web/next.config.ts`, que só afeta o build de
produção (`next dev` ignora).

**P3 - Segredo no backend.** Nada sensível no frontend; toda key e lógica crítica
permanecem no FastAPI.

## 4. Topologia (namespace `kortes-dev`)

| Workload | Tipo | Imagem | Réplicas | Service | Porta |
|---|---|---|---|---|---|
| `kortes-web` | Deployment | `kortes-web` (Next standalone) | 2 | ClusterIP | 3000 |
| `kortes-api` | Deployment | `kortes-api` (backend) | 2 | ClusterIP | 8000 |
| `kortes-worker` | Deployment | `kortes-api` (mesma imagem, cmd `python -m workers.worker`) | 1 | - | - |
| `kortes-postgres` | StatefulSet | `postgres:17` | 1 | headless | 5432 |
| `kortes-redis` | StatefulSet | `redis:7` | 1 | ClusterIP | 6379 |

```
                       Internet
                          |
                 Route53  kortes.ai
                          |
        ALB  (ingress-group kortes-dev . ACM TLS)
            |                            |
   kortes.ai / www.kortes.ai      api.kortes.ai
            |                            |
     svc kortes-web:3000          svc kortes-api:8000
            |                            |
   Deploy kortes-web x2          Deploy kortes-api x2
                                         |
                            +------------+------------+
                       kortes-redis              kortes-postgres
                      (Streams+cache)             (StatefulSet)
                            |                            ^
                            v                            |
                   Deploy kortes-worker x1 --------------+
                            |
              S3 kortes-media-dev (IRSA)  +  Starya (opcional, por URL)
```

Novo vs. M0 (compose, front no host): `kortes-web` passa a ser um pod;
`postgres`/`redis` deixam de ser containers de compose e viram StatefulSets com
PVC. `api`/`worker` já existiam.

Cache de mídia (`CACHE_DIR=/app/cache`, content-addressed): `emptyDir` por-pod no
MVP (é só cache; a fonte durável é o S3). Evolução: EFS (RWX) se o re-trabalho
incomodar.

## 5. Imagens e build/CD (GitOps)

Duas imagens (ECR, tag = SHA do commit, nunca `latest`):
- `kortes-api` - de `backend/Dockerfile` (existente). Serve `api` e `worker`.
- `kortes-web` - de `web/Dockerfile` novo (target `runner`).

O ECR `kortes-worker` previsto na convenção fica **descartado** (worker reusa
`kortes-api:<SHA>` com command override).

Pipeline:
```
git push  (paths: backend/** ou web/**)
   -> GitHub Actions (assume IAM role via OIDC, sem chave estatica)
        role: kortes-ci-dev (push no ECR)
        - docker build + push  kortes-api:<SHA> / kortes-web:<SHA>
        - bump da tag em deploy/helm/values-dev.yaml + commit "[skip ci]"
   -> ArgoCD (Application kortes-dev -> deploy/helm, auto-sync no dev)
        - rollout dos deployments no namespace kortes-dev
```

- OIDC provider para `token.actions.githubusercontent.com` + role `kortes-ci-dev`.
- Path filters + `[skip ci]` evitam loop de CI e rebuild desnecessário.
- O chart Helm vive **neste repo** (`deploy/helm`); `mda-infra` só hospeda o
  `Application` apontando pra cá (app-of-apps).

## 6. Networking

- **Ingress `kortes`** via AWS Load Balancer Controller, `ingress-group: kortes-dev`
  (um ALB para as duas regras):
  - `kortes.ai`, `www.kortes.ai` -> `svc kortes-web:3000`
  - `api.kortes.ai` -> `svc kortes-api:8000`
- **TLS**: ACM cert (os 3 hosts) emitido na conta do ALB (`mydatagent-dev`),
  validado por CNAME na zone `kortes.ai` (`mydatagent-shared`); ARN na annotation
  do ingress + redirect HTTP->HTTPS.
- **DNS**: Route53 em `mydatagent-shared`. No MVP, registros ALIAS manuais
  apontando pro DNS name do ALB. `external-dns` cross-account fica como evolução.
- **SSE/streaming**: o app depende de SSE de longa duração (eventos de plan/vídeo).
  Subir o `idle_timeout` do ALB (>= 300s) e desabilitar buffering, senão os streams
  caem no meio.

## 7. Config, secrets e IRSA

- **ConfigMap `kortes-config`** (não-sensível, no git): modelos e drivers
  (`ANTHROPIC_MODEL`, `FAL_*_MODEL`, `RESEARCH_MODE`, `BROLL_T2I_DRIVER`...),
  tunables (`PIPELINE_CONCURRENCY`, `VIDEO_TARGET_SECONDS`, `MEDIA_*`),
  `DOPPEL_S3_BUCKET`/`REGION`, `DOPPEL_CORS_ORIGINS` com os hosts reais.
- **Secret `kortes-secrets`** (via `kubectl`, fora do git): API keys SaaS
  (`ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `FAL_KEY`, `SERPAPI_KEY`,
  `FISH_API_KEY` opcional) + connection strings internas com senha
  (`DOPPEL_DATABASE_URL`, `DOPPEL_REDIS_URL`) + `POSTGRES_PASSWORD`. Um
  `deploy/secrets/kortes-secrets.example.yaml` (placeholders) documenta as chaves;
  o real é gitignored. Nenhum valor de secret no git.
- **IRSA**: ServiceAccount `kortes-app` (annotation -> role `kortes-app-dev`,
  policy `kortes-s3-dev` no bucket `kortes-media-dev-us-east-1`). Apenas `api` e
  `worker` a usam. Em prod `DOPPEL_S3_ENDPOINT` fica vazio (= AWS real); local
  continua `floci` + `AWS_*=test`. Mesmo código, sem chave estática.

## 8. Storage e migrations

- **PVCs (EBS gp3)**: `kortes-postgres` (~20Gi, volumeClaimTemplate) e
  `kortes-redis` (~5Gi, AOF). Mitigação do Postgres in-cluster: snapshot EBS ou
  `pg_dump` agendado.
- **Alembic** (schema versionado), rodando sem ação manual:
  - Baseline autogerada dos models atuais (primeira migration cria o schema que o
    `create_all` criaria).
  - Prod: Helm hook Job `pre-upgrade` roda `alembic upgrade head` 1x e completa
    antes do rollout dos pods (sem corrida entre réplicas).
  - Local: o entrypoint do `api` roda `alembic upgrade head` no boot (idempotente).
    Em prod o mesmo comando no entrypoint vira no-op, pois o Job já aplicou.
  - O `create_all` de boot é substituído pelo upgrade do Alembic (fonte única).

## 9. Proteção do frontend (em camadas)

- **Arquitetural (principal)**: o web é thin client, sem segredos (só
  `NEXT_PUBLIC_*` = URLs). Toda lógica e keys ficam no FastAPI.
- **Build**: `next build` minifica (SWC) + `productionBrowserSourceMaps: false`
  (sem source maps no cliente).
- **Ofuscação**: passo no stage `runner` rodando `javascript-obfuscator` nos chunks
  da app, com config moderada (não quebrar o runtime do Next). Eleva a barra contra
  leitura/cópia casual.
- **Limite honesto**: JS client-side é sempre baixável; ofuscação dificulta, não
  impede. Proteção real = segredo no backend (já é o caso).

## 10. Desenvolvimento local (hot reload)

`web/Dockerfile` multi-stage:
- target `dev` -> `next dev` (Turbopack HMR) com bind mount do código.
- target `runner` -> `next start` standalone (+ ofuscação) pra prod.

Serviço `web` opcional adicionado ao `docker-compose.yml` (target `dev`): editar
arquivo recarrega no container, tudo junto. Aditivo, não altera os serviços
existentes.

## 11. Provisionamento AWS (Terraform + Terragrunt)

Recursos: ECR (`kortes-api`, `kortes-web`), OIDC provider + role `kortes-ci-dev`,
role/policy `kortes-app-dev`/`kortes-s3-dev`, ACM cert, bucket S3
`kortes-media-dev-us-east-1`.

Layout:
```
deploy/terraform/
  modules/            # ecr, irsa-app, oidc-ci, acm, s3-media
  live/
    dev/
      terragrunt.hcl  # config raiz (backend remoto, providers, tags padrao)
      ecr/terragrunt.hcl
      irsa-app/terragrunt.hcl
      oidc-ci/terragrunt.hcl
      acm/terragrunt.hcl
      s3-media/terragrunt.hcl
```
Terragrunt mantém DRY e prepara `uat`/`prod` por troca de `stage`. Tags padrão
(`Project`, `Environment`, `Component`, `ManagedBy=terraform`) aplicadas em todos.
Recursos já existentes (zone `kortes.ai`) entram como `data`/import, não recriados.

## 12. Estrutura de arquivos (tudo aditivo)

```
deploy/
  helm/
    Chart.yaml, values.yaml, values-dev.yaml
    templates/
      api-deployment.yaml, api-service.yaml
      web-deployment.yaml, web-service.yaml
      worker-deployment.yaml
      postgres-statefulset.yaml, postgres-service.yaml
      redis-statefulset.yaml, redis-service.yaml
      ingress.yaml, configmap.yaml, serviceaccount.yaml
      migrate-job.yaml (Helm hook pre-upgrade), _helpers.tpl
  terraform/{modules,live/dev}     # Terraform + Terragrunt
  secrets/kortes-secrets.example.yaml   # placeholders; real gitignored
web/Dockerfile                     # multi-stage: dev (HMR) + runner (standalone+obfuscate)
backend/Dockerfile                 # + entrypoint roda alembic upgrade
backend/alembic.ini, backend/alembic/  # baseline + versions
.github/workflows/deploy.yml       # build+push+bump (OIDC)
docker-compose.yml                 # + servico web (dev/HMR), opcional
.gitignore                         # + deploy/secrets/kortes-secrets.yaml real
```

## 13. Decisões (rastreabilidade do brainstorming)

| # | Decisão | Escolha |
|---|---------|---------|
| 1 | FLUX.2/Starya no escopo? | Fora (externo, opcional por URL) |
| 2 | Runtime do `kortes-web` | Pod Node `next start` (standalone) |
| 3 | Datastores | In-cluster (StatefulSet + PVC) |
| 4 | Build/push de imagens | GitHub Actions (OIDC -> ECR) |
| 5 | Migrations | Alembic desde já |
| 6 | Provisionamento AWS | Terraform + Terragrunt |
| 7 | Cache de mídia | `emptyDir` por-pod |
| 8 | ECR `kortes-worker` | Descartado (worker reusa `kortes-api`) |

## 14. Riscos e mitigações

- **Postgres in-cluster (PVC)**: ponto único de perda de dados. Mitigação:
  snapshot EBS / `pg_dump` agendado; upgrade futuro para RDS (híbrido) quando
  endurecer durabilidade.
- **Ofuscação não é proteção forte**: aceito; segredo real fica no backend.
- **DNS cross-account manual**: passo manual de 1 vez; risco de drift. Evolução:
  `external-dns` com role cross-account.
- **SSE atrás do ALB**: cair se `idle_timeout` baixo. Mitigação: timeout >= 300s,
  sem buffering.
- **Corrida de migration entre réplicas**: mitigada pelo Helm hook Job (1x antes
  do rollout) + idempotência do `alembic upgrade head`.

## 15. Critérios de sucesso

- `docker compose up` continua funcionando **sem nenhuma mudança de fluxo**, com a
  mesma experiência de hoje (incl. hot reload do web).
- `https://kortes.ai` serve o front e `https://api.kortes.ai` a API, com TLS válido.
- Push em `backend/**` ou `web/**` builda, publica no ECR e o Argo reconcilia o
  rollout sem ação manual.
- Geração de vídeo ponta a ponta funciona no cluster (mídia no S3 real via IRSA,
  SSE estável).
- Schema gerenciado por Alembic; subir uma migration nova aplica no deploy sem
  `kubectl exec psql`.

## 16. Fora de escopo / evoluções futuras

- FLUX.2 self-hosted (Starya) e nós de GPU.
- Static export do web + nginx (enxugar o pod).
- Datastores gerenciados (RDS/ElastiCache).
- `external-dns` cross-account; EFS para cache compartilhado.
- Ambientes `uat`/`prod` separados (apex vira `prod`, `dev` migra para subdomínio).
