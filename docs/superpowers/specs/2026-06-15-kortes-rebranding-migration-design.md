# Rebranding Doppel -> Kortes + migração para dois repositórios

**Data:** 2026-06-15
**Status:** aprovado para planejamento

## Objetivo

Eliminar o nome "Doppel" de todo o produto (marca, código, configuração, banco),
aplicar a identidade visual da Kortes, e migrar o monorepo atual
(`saviobatista/doppel`) para dois repositórios novos na org `kortes-ai`:
`kortes-platform` (aplicação) e `kortes-infrastructure` (deploy/infra), mantendo
o ambiente `kortes-dev` no cluster `mda-development` funcional ao final.

## Escopo por camada

| Camada | De | Para | Observação |
|--------|----|----|------------|
| Marca visível | "Doppel" (web, docs, README) | "Kortes" + identidade visual nova | title, tagline, cores, símbolo, favicon |
| Pacote Python | `doppel_api` (`pyproject` `doppel-api`) | `kortes_api` (`kortes-api`) | dir + 42 arquivos + Dockerfile + entrypoint + alembic |
| Env vars | `DOPPEL_*` | `KORTES_*` | `env_prefix` no `config.py` + configmap + values + secret vivo |
| localStorage | `doppel_token` | `kortes_token` | desloga devices de dev (aceito) |
| Banco | user/db `doppel` | user/db `kortes` | recriar Postgres (descarta dados de teste) |
| Repositório | `saviobatista/doppel` | `kortes-ai/kortes-platform` + `kortes-ai/kortes-infrastructure` | snapshot limpo; antigo arquivado |

Fora de escopo: o nome `mda` (conta/cluster AWS, não é o produto). As imagens ECR
já são `kortes-api`/`kortes-web` (sem mudança).

## Arquitetura alvo

Dois repositórios, GitOps cross-repo:

- **kortes-platform**: `backend/` (`kortes_api`), `web/`, `.github/workflows/`
  (CI de build), `docker-compose.yml`, `.env.example`, `docs/`, `CLAUDE.md`.
- **kortes-infrastructure**: `deploy/` (helm, terraform, terragrunt, argocd),
  com README/CLAUDE próprios.

Fluxo de deploy (igual em espírito ao atual, agora cross-repo):

```
push em kortes-platform
  -> GitHub Actions (OIDC -> kortes-ci-dev) builda api+web amd64, push ECR (tag=SHA)
  -> bump da tag em values-dev.yaml NO repo kortes-infrastructure (commit cross-repo)
  -> Argo CD (aponta para kortes-infrastructure) sincroniza o cluster
```

Divisão confirmada como "por hora" (pode evoluir depois). A estrutura `deploy/`
é mantida dentro do `kortes-infrastructure` para não mexer em paths do Argo/CI
nesta etapa.

## Decisões-chave

1. **Env vars via `env_prefix`**: trocar `env_prefix="DOPPEL_"` -> `"KORTES_"`
   em `config.py` renomeia de uma vez `database_url`, `redis_url`, `s3_*`,
   `cors_origins`, `live_smoke`. As demais (API keys) têm `validation_alias`
   próprio e não mudam.
2. **Banco recriado**: `POSTGRES_USER`/`POSTGRES_DB` passam a `kortes`; o PVC do
   Postgres é descartado e o Alembic recria o schema vazio. Os dados de teste
   atuais (avatares/vozes/vídeos) são perdidos - aceito por ser dev/MVP.
3. **Snapshot limpo**: cada repo novo começa com um commit inicial. O histórico
   antigo permanece preservado em `saviobatista/doppel`, que é **arquivado**
   (não deletado).
4. **CI cross-repo**: o workflow no `kortes-platform` faz o bump da tag no
   `kortes-infrastructure` usando uma deploy key de escrita do repo de infra,
   guardada como secret de Actions no `kortes-platform`.
5. **Identidade visual**: aplicada na Fase 1 a partir de `web/public/brand/` e
   `docs/brand/brand-guidelines.md` (paleta roxa, símbolo tesoura-K, tagline
   "IA que corta. Você viraliza."). Vetores oficiais substituem a recriação
   quando disponíveis.

## Fases

### Fase 1 - Rebranding de conteúdo (working tree atual)

Sem tocar repositórios novos nem cluster ainda.

- Backend: renomear `backend/src/doppel_api/` -> `kortes_api/`; atualizar imports
  (42 arquivos), `pyproject.toml`, `Dockerfile` (`uvicorn kortes_api.main:app`),
  `docker-entrypoint.sh`, `alembic.ini`/`alembic/env.py`; `config.py` env_prefix.
- Tests: imports + `DOPPEL_LIVE_SMOKE` -> `KORTES_LIVE_SMOKE`.
- Web: title/tagline/textos (12x), `doppel_token` -> `kortes_token`, comentário
  `doppel_api`; identidade visual (tokens de cor em `globals.css`, símbolo no
  header, favicon, tagline).
- Manifestos (deploy, ainda no working tree): configmap/values `DOPPEL_*` ->
  `KORTES_*`; Postgres statefulset user/db `kortes`; `.env.example` e
  `docker-compose.yml`.
- Docs/README: Doppel -> Kortes.
- **Validação**: suíte de testes do backend verde; `helm template -f
  values-dev.yaml` sem erro; build do web (`npm run build`) verde.

### Fase 2 - Split e push para os dois repos

- Montar duas árvores a partir do working tree rebrandeado conforme a divisão.
- `git init` / commit inicial / push para `kortes-ai/kortes-platform` e
  `kortes-ai/kortes-infrastructure` (repos já existem, vazios, privados).
- Ajustar referências internas que assumam monorepo, se houver.

### Fase 3 - GitOps cross-repo

- Terraform `env.hcl`: `github_repo` -> `kortes-ai/kortes-platform`;
  `terragrunt apply` do módulo `oidc-ci` para atualizar o trust do role
  `kortes-ci-dev`.
- Argo `application.yaml`: `repoURL` -> `kortes-infrastructure`; deploy key de
  leitura no Argo para o repo de infra.
- Deploy keys: gerar leitura (Argo -> infra) e escrita (CI bump -> infra);
  cadastrar secrets de Actions no `kortes-platform`.
- CI: ajustar o passo de bump para commitar no repo de infra.

### Fase 4 - Cutover no cluster

- Secret `kortes-secrets`: gravar `KORTES_DATABASE_URL`/`KORTES_REDIS_URL`
  (connection string com user/db `kortes`); remover as chaves `DOPPEL_*` antigas
  após validação.
- Recriar o Postgres com `POSTGRES_USER`/`DB` = `kortes` (descarta PVC).
- Apontar o Argo para o `kortes-infrastructure` e sincronizar; entrypoint roda
  `alembic upgrade head` no schema novo.
- **Validação**: pods Running, migrations aplicadas, target groups healthy,
  gate de Basic Auth funcionando, fluxo do app (sessão/avatar) operacional.
- Arquivar `saviobatista/doppel`; remover o Argo Application antigo se duplicado.

## Ordem e dependências

Sequencial: 1 -> 2 -> 3 -> 4. A Fase 4 depende de a Fase 3 (OIDC + Argo + CI
cross-repo) estar pronta, senão o primeiro deploy do repo novo não autentica no
ECR nem sincroniza. O cutover de env vars/banco (Fase 4) deve aplicar o secret
`KORTES_*` e o banco `kortes` **antes** de o pod novo subir, para a app não
iniciar sem DB/Redis/S3.

## Riscos e mitigações

| Risco | Mitigação |
|-------|-----------|
| Pod novo sobe sem `KORTES_*` no secret/configmap | Aplicar secret + configmap antes do sync; validar `kubectl get` |
| OIDC trust desatualizado -> CI não acessa ECR | `terragrunt apply` do `oidc-ci` antes do 1º run do platform |
| Bump cross-repo sem credencial | Deploy key de escrita do infra como secret no platform |
| Dois Argo apps (doppel + kortes) conflitando | Migrar o mesmo Application (mudar repoURL) ou remover o antigo |
| Recriação do banco perde dados | Confirmado dev; schema recriado por Alembic |
| Renome de pacote quebra imports | Testes do backend cobrem; rodar suíte completa na Fase 1 |

## Validação final (definição de pronto)

- Nenhuma ocorrência de "doppel"/"Doppel" no código, marca, env e banco
  (`grep -ri doppel` limpo, exceto histórico/arquivos de terceiros).
- `kortes.ai` no ar, com a identidade Kortes, atrás do gate de senha.
- Pipeline push -> CI -> bump cross-repo -> Argo -> cluster funcional.
- Repos `kortes-platform` e `kortes-infrastructure` populados; `doppel` arquivado.
