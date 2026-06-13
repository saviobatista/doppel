# PDR: Doppel

| | |
|---|---|
| **Status** | Draft para revisão |
| **Data** | 2026-06-12 |
| **Autores** | Savio (produto/arquitetura), Claude (espec) |
| **Handoff de infra** | Bruno (seções 9.2 e 9.3) |
| **Working title** | Doppel (de doppelgänger; validar marca/domínio antes do go-live) |

## 1. Visão

Doppel transforma uma única gravação de ~40 segundos do usuário (rosto + voz) em um avatar digital que estrela vídeos curtos verticais (formato Instagram/TikTok). O usuário descreve por voz o vídeo que quer, e o sistema gera: narração com a voz clonada, avatar falando em vídeo, b-rolls ilustrativos, trilha sonora e legendas, tudo montado em um vídeo de ~30 segundos. A experiência inteira acontece em uma sessão contínua, cinematográfica, sem formulários.

O diferencial não é nenhum modelo individual: é a experiência costurada com latência escondida e o reveal na mesma sessão.

### 1.1 Posicionamento competitivo (referência: HeyGen)

HeyGen é a referência de mercado e também um driver managed deste design (matriz 5.2). A sobreposição tecnológica é grande; a de produto é pequena: HeyGen é uma plataforma de produção (dashboard B2B, editor, templates, tradução em 175 idiomas), Doppel é uma experiência consumer de sessão única com a voz como única interface.

| Dimensão | HeyGen (2026) | Doppel |
|---|---|---|
| Criação do avatar | Digital Twins: foto/vídeo curto + vídeo de consentimento, etapa de setup em dashboard | Gravação de 40s que já é consentimento + voz + footage; o hello em 10-20s é o primeiro ato da experiência |
| Ideia para vídeo completo | Video Agent: prompt de texto gera vídeo com avatar, b-roll, trilha e legendas (o paralelo mais próximo do nosso pipeline) | Briefing falado gera o mesmo pacote; regeneração conversacional com o próprio avatar |
| Latência | Assíncrona por design (10-30 min em pico nos planos baixos) | Reveal ao vivo < 2 min; HQ em background |
| Custo por vídeo de 30s | Avatar IV API ~US$ 4/min; Video Agent ~US$ 1-2/min (pay-as-you-go) | GPU-minuto coberto por créditos AWS; marginal ~zero no selfhosted |
| Dados | Biometria no vendor, sem self-host | Pipeline e biometria sob nosso controle (LGPD) |

Leituras estratégicas:

1. **Validação técnica**: o Instant Avatar deles usa a mesma técnica da nossa faixa rápida (re-sync de footage real) e o Avatar IV equivale à nossa faixa HQ. A arquitetura de duas faixas espelha o melhor deles, entregando a primeira ao vivo.
2. **Uso como driver**: Avatar IV API serve para bake-off de qualidade no M1 (dinheiro real, fora dos créditos). O Video Agent não serve como driver: entrega pacote fechado e destruiria o contrato de roteiro, o cache por componente e o loop de feedback por voz.
3. **Risco competitivo**: eles podem empacotar experiência consumer semelhante. Defesas: sessão única webcam-ao-uau, PT-BR first, regeneração conversacional e custo marginal ~zero.

Referências: [Avatar IV API](https://www.heygen.com/blog/announcing-the-avatar-iv-api), [API pricing](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained), [planos 2026](https://www.eesel.ai/blog/heygen-pricing).

## 2. A experiência (requisito mestre)

Toda decisão técnica deste documento serve a esta sequência. Qualquer mudança que degrade este fluxo é regressão.

| # | Cena | O que acontece |
|---|---|---|
| 1 | Chegada | Página pede permissão de câmera e microfone. Ao permitir, a tela faz fade para preto. |
| 2 | Typewriter | Texto digitado na tela: "Agora leia em voz alta o texto a seguir...". Após 2-3s, limpa. |
| 3 | Leitura | Aparece o texto de leitura (~40s de fala): termo de consentimento + frases foneticamente ricas + código da sessão. Gravação e upload acontecem em streaming durante a leitura. Validação de enquadramento e nível de áudio em tempo real, com refazer imediato se falhar. |
| 4 | Processamento | Tela escura com animação futurista (engrenagens). Alvo: 10 a 20 segundos. |
| 5 | Hello (o punch) | Vídeo de 6s: o próprio usuário olhando para baixo, levanta o olhar e diz "Oi! Eu sou você aprimorado! O que vamos fazer hoje?". |
| 6 | Briefing | Captura só de áudio: o usuário descreve o vídeo que quer (onde, por quê, contexto). STT em streaming. |
| 7 | Geração | Animação de engrenagens com feedback de progresso real (etapas aparecendo). Alvo: menos de 2 minutos. |
| 8 | Reveal | Efeito de TV estática estabilizando, fade para o vídeo gerado tocando. |
| 9 | Veredito | Thumbs up: vai para a galeria. Thumbs down: vídeo cacheado do avatar pergunta "Não gostou? O que quer mudar?", captura o delta por voz e re-gera só o que mudou (volta à cena 7). |
| 10 | Galeria | Vídeos do próprio usuário (por dispositivo). Itens ganham badge "HD" quando a faixa de qualidade termina em background. |

Frases fixas do produto (PT-BR, MVP): as três acima, mais microcopy de erro e da galeria. Centralizadas em um único módulo de strings.

## 3. Princípios de design

1. **Latência escondida atrás de interação** (padrão Instagram upload): nenhum trabalho espera um clique se já pode começar; todo tempo de interação do usuário (ler, falar, assistir) é tempo de processamento gratuito.
2. **Duas faixas de geração**: a faixa rápida entrega o reveal na sessão (540x960, modelos rápidos); a faixa HQ regenera em background (1080x1920) e substitui o item na galeria, como o YouTube libera resoluções progressivamente.
3. **Um contrato central**: o roteiro estruturado (JSON) é a única fonte de verdade entre briefing e vídeo final. Tudo downstream (TTS, b-roll, trilha, legendas, composição) consome esse contrato.
4. **Driver por capacidade**: cada capacidade de IA tem interface única com dois drivers, `selfhosted` e `managed`, escolhidos por configuração, por capacidade (pode misturar).
5. **Anônimo primeiro**: identidade por dispositivo, sem cadastro. Consentimento explícito e botão real de apagar tudo.
6. **Compose para K8s sem reescrita**: cada serviço do compose mapeia 1:1 para um Deployment no EKS.

## 4. Arquitetura

Monolito modular com fila de jobs e workers especializados.

```
 Browser (SPA Vite/TS vanilla)
   |  WS (upload streaming) + HTTPS + SSE (progresso)
   v
 api (FastAPI) ----------------- Postgres (estado, roteiros, jobs, consentimento)
   |                             S3 via AWS SDK (floci no dev / S3 na prod)
   v
 Redis Streams (lanes: interactive | background) + pub/sub (progresso)
   |
   +--> voice-worker    (TTS clonado)            GPU
   +--> avatar-worker   (lip-sync / talking head) GPU
   +--> broll-worker    (texto-para-video)        GPU
   +--> music-worker    (trilha)                  GPU
   +--> script-worker   (STT + LLM de roteiro)    GPU (ou managed)
   +--> compose-worker  (ffmpeg: cortes, mix, legendas, encode) CPU
```

- Workers consomem a lane `interactive` com prioridade absoluta; `background` só drena quando a interactive está vazia.
- Cada worker mantém o modelo fixo na VRAM (pin + warmup no boot). Nunca carregar modelo por request.
- Progresso: workers publicam eventos no Redis pub/sub; a api retransmite por SSE.
- No perfil `managed`, os workers GPU viram clientes finos de APIs (Bedrock, ElevenLabs, HeyGen) com a mesma interface de job.

## 5. Pipeline de geração

### 5.1 Contrato de roteiro

Gerado pelo LLM a partir do briefing transcrito. Os campos são emitidos em streaming **nesta ordem**, porque o downstream consome conforme fecham:

```json
{
  "narration": {
    "text": "Texto completo da narracao de ~30s em PT-BR...",
    "tone": "confiante, energetico"
  },
  "scenes": [
    { "id": "s1", "window": [0.0, 7.5],  "type": "avatar" },
    { "id": "s2", "window": [7.5, 13.0], "type": "broll",
      "prompt": "drone shot de praia ao amanhecer, tons quentes...",
      "negative": "texto, logos, pessoas reconheciveis" },
    { "id": "s3", "window": [13.0, 21.0], "type": "avatar" },
    { "id": "s4", "window": [21.0, 26.0], "type": "broll", "prompt": "..." },
    { "id": "s5", "window": [26.0, 30.0], "type": "avatar" }
  ],
  "music": { "mood": "eletronica leve, inspiradora", "bpm_hint": 110 },
  "captions": { "style": "tiktok_word_by_word" }
}
```

Linha do tempo: o áudio da narração corre contínuo por ~30s; o vídeo alterna entre o avatar falando e b-rolls cobrindo a narração (estilo documentário). O avatar track é gerado inteiro (30s) e o compositor corta pelas janelas.

O campo `type` reserva um terceiro valor, `avatar_scene` (com `setting` e `framing`), descrito em 5.5. O LLM do MVP é instruído a emitir apenas `avatar` e `broll`: quando o briefing declara um ambiente ("num podcast famoso", "apresentando um parque"), o contexto entra via b-rolls e establishing shots do cenário.

### 5.2 Matriz de capacidades

| Capacidade | Driver selfhosted (g7e) | Licença (selfhosted) | Driver managed |
|---|---|---|---|
| STT | faster-whisper large-v3 | MIT (código); pesos OpenAI | Amazon Transcribe streaming (PT-BR) |
| Roteiro (LLM) | Qwen2.5-32B-Instruct-AWQ via vLLM | Apache 2.0 | Claude Sonnet (Bedrock), structured output em streaming |
| Voz clonada (TTS) | Protótipo: XTTS-v2 (zero-shot PT-BR, 6-10s de referência). Rota comercial: F5-TTS com checkpoint PT-BR | XTTS-v2: CPML, **não comercial**. F5-TTS: MIT (validar licença do checkpoint PT-BR) | ElevenLabs (instant voice clone, PT-BR excelente). AWS não tem clonagem self-service |
| Avatar falante | Faixa rápida: LatentSync (lip-sync sobre o vídeo gravado). HQ: EchoMimic-v2 (a partir de frame de referência) | LatentSync: Apache 2.0. EchoMimic-v2: Apache 2.0 | HeyGen API (avatar de vídeo); alternativa D-ID. Atenção: render em minutos, é o gargalo de latência do perfil managed; as metas plenas da seção 6 exigem o driver selfhosted |
| B-roll (T2V) | Faixa rápida: LTX-Video 2B destilado. HQ: Wan 2.2 14B 720p | LTX: licença própria (comercial ok abaixo de US$ 10M de receita; validar). Wan: Apache 2.0 | Amazon Nova Reel (Bedrock, clipes de 6s) |
| Trilha | ACE-Step (30s por mood). Alternativa: Stable Audio Open | ACE-Step: Apache 2.0. MusicGen descartado para produção (CC-BY-NC) | ElevenLabs Music; fallback pragmático: biblioteca licenciada curada por mood |
| Legendas | whisperX (alinhamento palavra a palavra) + ffmpeg (queimadas) | BSD | idêntico (CPU, sem variante managed) |
| Composição | ffmpeg: cortes por janela, ducking da trilha sob a narração, legendas, H.264 9:16 | LGPL/GPL (uso ok) | idêntico |
| Upscale (HQ) | Real-ESRGAN + GFPGAN (restauração de rosto) + RIFE (interpolação) | BSD / Apache / MIT | sem variante managed no MVP |

Decisões embutidas:

- **O truque da faixa rápida do avatar**: já temos ~40s de vídeo real do usuário (a leitura). A faixa rápida não gera um humano sintético do zero; re-sincroniza os lábios desse footage com a nova narração (LatentSync). Mais rápido, mais barato e mais realista. Geração a partir de frame de referência (cabeça expressiva, enquadramentos novos) fica na faixa HQ.
- O vídeo "hello" (6s) e o vídeo de feedback "Não gostou? O que quer mudar?" usam o mesmo caminho de TTS + lip-sync com frases fixas. O hello tem prioridade absoluta; o de feedback é enfileirado em `background` no instante em que o hello é entregue, com o worker ainda quente.

### 5.3 Faixa HQ (background)

Disparada após thumbs up (não desperdiçar GPU em vídeo rejeitado):

1. Avatar track: upscale 540p para 1080p (Real-ESRGAN) + restauração de rosto (GFPGAN) + interpolação se necessário (RIFE). Preserva o conteúdo aprovado.
2. B-rolls: re-render com Wan 2.2 14B usando os mesmos prompts e seeds (conteúdo pode variar levemente; é a parte que mais ganha qualidade).
3. Re-composição em 1080x1920, substitui o asset na galeria com badge "HD". Evento SSE se o usuário estiver com a galeria aberta.

### 5.4 Ciclo de thumbs down

1. Toca o vídeo de feedback cacheado.
2. Captura o delta por voz, STT, e o LLM **edita** o roteiro existente (diff semântico, não recriação).
3. Re-gera apenas componentes afetados: assets intermediários são cacheados por hash do nó do roteiro (b-roll por hash do prompt+seed, narração por hash do texto). Mudou a cena 2: re-gera 1 b-roll e re-compõe. Mudou o texto: re-gera narração + lip-sync + re-compõe.

### 5.5 Extensão reservada: avatar em cena (pós-MVP)

Briefings como "falando sobre cibersegurança num podcast famoso" pedem o avatar dentro do ambiente, com enquadramento livre (diagonal, wide), e não o talking head frontal. O contrato já reserva `type: "avatar_scene"` com `setting` (descrição do ambiente) e `framing` (`frontal | diagonal | wide`) para que a ativação futura não exija migração. Caminho técnico documentado:

- **Aproximação na faixa rápida**: background replacement por matting de vídeo (RVM/MODNet) sobre o footage real + fundo gerado a partir do `setting`; vale apenas para `framing: frontal` (caso "parque olhando para a câmera").
- **Cena real na faixa HQ**: speech-to-video com referência de identidade. Selfhosted: Wan 2.2 S2V-14B (Apache 2.0), alimentado com frames de referência extraídos do vídeo de leitura + narração clonada + prompt de cena; alternativa HunyuanVideo-Avatar (validar licença Tencent). Managed: Runway Gen-4 References + lip-sync via API (ex.: sync.so), já que Nova Reel não preserva identidade de pessoa específica.
- **Multi-shot**: o LLM quebra cenas `avatar_scene` em takes de 5 a 8s alternando ângulos (wide do estúdio, diagonal falando, close), o que melhora a qualidade dos modelos e reproduz a linguagem de cortes de um podcast real.
- **Limitações conhecidas**: identidade "muito parecida" (não idêntica) em ângulos acentuados, artefatos de mãos/gestos, e latência incompatível com o reveal de 120s (recurso da faixa HQ ou de um reveal estendido opt-in).

## 6. Engenharia de latência

Metas (north star, instrumentadas desde o primeiro commit):

| Métrica | Alvo |
|---|---|
| Fim da gravação até hello na tela | 10 a 20s |
| Fim do briefing até reveal (faixa rápida) | menos de 120s |
| Upload percebido após fim da leitura | ~0s (streaming durante a leitura) |

Overlaps que sustentam as metas:

1. **Durante a leitura (~40s grátis)**: chunks do MediaRecorder (~1s) sobem por WebSocket; o backend extrai em paralelo a referência de voz (primeiros 10s limpos), o crop/tracking de rosto e o melhor segmento-base para lip-sync. O TTS do hello (frase fixa) dispara assim que a referência de voz existe, ainda durante a leitura.
2. **Hello**: ao fim da gravação restam o lip-sync de 6s (LatentSync, segundos numa g7e) e a entrega. 
3. **Durante o briefing**: STT em streaming; contexto do LLM pré-montado, só anexa a transcrição final.
4. **Geração**: o LLM emite o roteiro em streaming na ordem do contrato; o TTS da narração começa enquanto o LLM ainda escreve as cenas; cada b-roll é despachado quando seu nó fecha; a trilha quando o mood sai. Caminho crítico: LLM (~10s) -> TTS 30s (~20s) -> lip-sync 30s (~40-60s) -> composição (~15s). B-rolls e trilha rodam em paralelo, escondidos no caminho do avatar.
5. **Degradação graciosa**: se o orçamento de tempo estoura, reduzir de 3 b-rolls para 2 ou 1 (cenas viram avatar), nunca estourar o reveal.
6. **Frontend**: SSE conectado desde o início, player pré-instanciado, reveal só dispara no `canplaythrough` (o fade de TV estática esconde o buffering).

## 7. Frontend

- **Stack**: Vite + TypeScript vanilla. Zero framework de UI. Justificativa: a interface é uma sequência de cenas em tela escura, não uma árvore de componentes.
- **State machine explícita** (módulo próprio, sem lib): `idle, permission, fade-in, reading, uploading, processing, hello, briefing, scripting, generating, reveal, feedback, gallery, error`.
- **Efeitos**: CSS keyframes (fades, typewriter via clip + caret), canvas 2D (engrenagens, TV static com ruído procedural). Sem WebGL/Three.js no MVP.
- **Captura**: `getUserMedia` 540x960@30 (ou nativo do device com crop), `MediaRecorder` (VP9/H.264 conforme suporte; Safari grava H.264/MP4), chunks de ~1s via WebSocket.
- **Validação na leitura**: MediaPipe Face Detector (WASM, leve) para presença/enquadramento do rosto + medidor de nível de áudio. Falhou: refaz na hora, antes de qualquer upload completo.
- **Rotas**: `/` (a experiência), `/galeria`, `/privacidade` (apagar meus dados).
- **Entrega de vídeo**: URLs pré-assinadas, `<video>` nativo com `playsinline`.

## 8. Modelo de dados e API

### Tabelas (Postgres)

| Tabela | Conteúdo |
|---|---|
| `devices` | ID anônimo (token no localStorage), criado no primeiro acesso, `deleted_at` para LGPD |
| `avatars` | status do preparo; refs S3: vídeo fonte, referência de voz, crop de rosto, segmento-base, hello, vídeo de feedback; ref da gravação de consentimento + código de sessão validado + timestamp |
| `videos` | roteiro (JSONB), `fast_status`, `hq_status`, refs dos assets finais, rating, briefing transcrito |
| `jobs` | tipo, lane, status, payload, video/avatar ref, `timings` JSONB por etapa (base da observabilidade) |
| `components` | assets intermediários cacheados: tipo, hash do nó do roteiro, ref S3, modelo+seed usados |

### API (FastAPI, prefixo /v1)

```
POST   /sessions                 cria device anonimo, retorna token
WS     /avatars/stream           chunks da gravacao em streaming
GET    /avatars/{id}/events      SSE: processing, hello_ready
POST   /videos                   audio do briefing -> video_id
GET    /videos/{id}/events       SSE: scripting, component_done(n/m), fast_ready, hq_ready
POST   /videos/{id}/feedback     thumbs up | down (+ audio do delta)
GET    /gallery
DELETE /me                       apaga dados, assets e avatar (LGPD)
```

- Fila: Redis Streams, streams `jobs:interactive` e `jobs:background`, consumer groups por tipo de worker, `XAUTOCLAIM` para retomada de jobs órfãos. Jobs idempotentes (re-enfileirar é seguro; pré-requisito para spot na lane background).
- Progresso: Redis pub/sub canal `video:{id}` -> SSE.

## 9. Infra e ambientes

### 9.1 Dev no Mac (sem GPU): compose profile `managed`

Serviços: `api`, `web` (Caddy servindo o build do Vite), `postgres`, `redis`, `floci`, `compose-worker` (ffmpeg, CPU) e os workers em modo cliente de API.

- **floci** (emulador AWS open-source, porta 4566) emula o S3: o código usa AWS SDK em todo lugar e só troca `endpoint_url` por ambiente. Sem MinIO no projeto.
- O que o floci não emula (Bedrock, Transcribe, ElevenLabs, HeyGen): os drivers managed chamam os endpoints reais com credenciais de dev e um kill-switch de orçamento (seção 11). Para trabalhar offline, STT pode usar o driver selfhosted com faster-whisper `small` em CPU.
- Profile `selfhosted` (mesmo arquivo): adiciona `vllm`, `voice-worker`, `avatar-worker`, `broll-worker`, `music-worker` com runtime NVIDIA. Não roda no Mac; é o mesmo compose usado na g7e (9.2).

### 9.2 Inferência self-hosted na g7e (handoff: Bruno)

Família confirmada: g7e = NVIDIA RTX PRO 6000 Blackwell Server Edition, 96 GB VRAM por GPU, Intel Emerald Rapids, NVMe local. Quota disponível: 192 vCPUs para a família G.

| Tamanho | vCPU | GPUs | RAM | NVMe |
|---|---|---|---|---|
| g7e.2xlarge | 8 | 1 | 64 GiB | 1.9 TB |
| g7e.4xlarge | 16 | 1 | 128 GiB | 1.9 TB |
| g7e.12xlarge | 48 | 2 | 512 GiB | 3.8 TB |

**Fase selfhosted-dev (uma caixa, validação do pipeline): 1x g7e.4xlarge.** Uma GPU de 96 GB segura todos os modelos da faixa rápida residentes:

| Modelo | VRAM estimada |
|---|---|
| Qwen2.5-32B-AWQ (vLLM, max_model_len curto) | ~22 GB |
| faster-whisper large-v3 | ~3 GB |
| XTTS-v2 / F5-TTS | ~3 GB |
| LatentSync | ~5 GB |
| LTX-Video 2B (fp8) | ~12 GB |
| ACE-Step | ~8 GB |
| Total + ativações/headroom | ~55-65 GB de 96 GB |

Deploy: o mesmo docker compose com profile `selfhosted`. NVMe local como `HF_HOME` (cache de pesos) e workdir do ffmpeg. AMI: Deep Learning AMI ou Ubuntu + driver NVIDIA 5xx + container toolkit.

**Fase produção MVP: 1x g7e.12xlarge (2 GPUs, 48 vCPUs).**

- GPU 0 ("fala e cérebro"): vLLM Qwen 32B + whisper + TTS
- GPU 1 ("vídeo"): LatentSync + LTX-Video + ACE-Step
- 48 vCPUs folgam para `compose-worker` e a api no mesmo nó (no EKS, separados).
- Quota restante: 144 vCPUs = até 18x g7e.2xlarge de burst para b-roll paralelo e faixa HQ (Wan 2.2 14B fp8 cabe em 1 GPU de 96 GB com folga).
- MIG (a RTX PRO 6000 Blackwell suporta particionamento): otimização futura para isolar workers leves; no MVP, workers compartilham GPU via processo (cuidado com fragmentação de VRAM; medir antes de otimizar).

### 9.3 EKS (handoff: Bruno)

- **Cluster**: EKS 1.33+, VPC com 3 AZs, nodes em subnets privadas, NAT por AZ. IaC 100% Terraform (módulos: vpc, eks, karpenter, rds, elasticache, s3-cdn, ecr, iam-irsa).
- **Node groups fixos**: `system` (2x m7i.large: ingress, observabilidade, KEDA, Karpenter controller) e `apps` (m7i.xlarge com HPA: api, web, compose-worker).
- **GPU via Karpenter NodePool**: família g7e, on-demand (créditos AWS dispensam spot), NodePools com labels `lane=interactive` e `lane=background`, taint `nvidia.com/gpu=true:NoSchedule`, limites respeitando a quota de 192 vCPUs. NVIDIA device plugin via addon/DaemonSet.
- **Workers**: 1 Deployment por worker, requests de GPU inteira para os pesados (broll, avatar) e time-slicing para os leves (voice, stt) numa GPU compartilhada, se a medição da fase selfhosted-dev validar.
- **Autoscaling**: KEDA ScaledObjects sobre lag das Redis Streams; `interactive` escala 1 para N agressivo; `background` escala 0 para N (scale-to-zero fora de pico).
- **Dados gerenciados**: RDS Postgres (db.t4g.medium, single-AZ no MVP), ElastiCache Redis (node m7g.large; Streams precisam de memória e persistência AOF), S3 + CloudFront para entrega dos vídeos (URLs assinadas), ECR para imagens.
- **Ingress**: AWS Load Balancer Controller, ALB com idle timeout 600s (SSE) e suporte a WebSocket (upload streaming).
- **Identidade**: IRSA por serviço (api: S3+Transcribe+Bedrock; workers: S3; sem credenciais estáticas).
- **Observabilidade**: OTel (ADOT) com traces por job atravessando api -> fila -> worker -> compose; dashboards das duas métricas north star; alarme quando p95 do reveal passa de 120s.
- **Modelos nos nodes GPU**: pesos baixados no provisioning para o NVMe local (init container com `HF_HOME` no hostPath); avaliar snapshot de AMI customizada se o cold start de node passar de ~5 min.

## 10. Segurança, consentimento e LGPD

- **Consentimento gravado**: o texto lido em voz alta é o termo de consentimento. Rascunho: "Eu, em sã consciência, autorizo a criação de um avatar digital com meu rosto e minha voz, para gerar vídeos sob meu comando dentro deste aplicativo. Sei que posso apagar meus dados a qualquer momento. Minha palavra-chave de hoje é {codigo}. O vento sopra forte sobre o juazeiro enquanto doze garotos observam o equilibrista." (consentimento + código anti-replay + frase foneticamente rica; redação final com revisão jurídica).
- **Anti-replay barato**: o código `{codigo}` é gerado por sessão e validado via STT; impede usar vídeo de terceiros gravado fora da sessão. Liveness real (desafios de movimento) fica fora do MVP.
- **Biometria (dado sensível, LGPD art. 5º II)**: consentimento explícito e auditável (gravação + timestamp + IP), `DELETE /v1/me` apaga tudo (linhas + objetos S3), retenção: vídeo fonte bruto apagado após o preparo do avatar (ficam crop, embeddings e segmento-base), avatar inteiro expira após 30 dias sem uso.
- **Procedência**: watermark visual discreto + metadados C2PA no MP4 final, identificando conteúdo sintético.
- **Escopo de geração**: o avatar só existe para quem gravou ao vivo na sessão; prompts de b-roll passam pelo filtro de conteúdo do LLM de roteiro (negative prompts + recusa de temas vetados).
- **Transporte e storage**: TLS em tudo, buckets privados com presigned URLs curtas, criptografia at rest (SSE-S3/KMS).

## 11. Custos e créditos

A AWS está coberta por créditos amplos do projeto: **dimensionamento (seção 9) é a variável de engenharia, não preço**.

- **Coberto por créditos** (EC2 g7e, Bedrock/Nova Reel, Transcribe, S3/CloudFront, EKS, RDS, ElastiCache): sem restrição de uso. Manter a 12xlarge de produção ligada é aceitável; o scale-to-zero da lane background continua valendo por higiene de capacidade (quota de 192 vCPUs), não por dinheiro.
- **Dinheiro real** (terceiros fora da AWS: ElevenLabs, HeyGen): kill-switch de orçamento e quotas por device aplicam-se somente a esses drivers. Com créditos, vale antecipar os drivers selfhosted de voz e avatar (M2) e usar os terceiros apenas como referência de qualidade em bake-offs.
- **Eficiência medida em GPU-minuto por vídeo**, instrumentada por job: é o indicador de capacidade que alimenta o sizing do Bruno, no lugar de custo por vídeo.

## 12. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Reveal estourar 120s | Quebra o punch | Telemetria por etapa desde o 1º commit; degradação graciosa (menos b-rolls); modelos fast por padrão |
| Lip-sync ruim sobre vídeo gravado (movimento, oclusão) | Hello sem "uau" | Validação de enquadramento na gravação; seleção automática do segmento-base; fallback frame estático + EchoMimic |
| Voz PT-BR fraca com 6-10s de referência | Avatar não soa como o usuário | ElevenLabs no managed como referência de qualidade; F5-TTS PT-BR no selfhosted; coletar 2x mais áudio (o texto de leitura já dá ~40s) |
| Licenças de pesos (XTTS CPML, MusicGen CC-BY-NC, LTX condicionada) | Bloqueio comercial | Matriz 5.2 já segrega protótipo vs rota comercial; auditoria de licenças como gate do M2 (questão aberta Q1) |
| Disponibilidade g7e (família nova, poucas regiões) | Sem capacidade | us-east-1/us-west-2 confirmadas; fallback g6e (L40S 48GB, cabe tudo exceto Qwen 32B + vídeo na mesma GPU; usar 2 instâncias) |
| Gasto real com terceiros não-AWS (ElevenLabs/HeyGen) | Queima de caixa (créditos não cobrem) | Kill-switch de orçamento e quotas por device nesses drivers; preferir drivers AWS/selfhosted cobertos por créditos |
| Abuso (deepfake de terceiros) | Dano reputacional/legal | Código anti-replay validado por STT, consentimento gravado, watermark + C2PA, avatar restrito à sessão ao vivo |

## 13. Fases de entrega

| Fase | Entrega | Critério de aceite |
|---|---|---|
| M0 | Walking skeleton no Mac: compose `managed` + floci, fluxo inteiro com stubs (vídeo placeholder), state machine do front completa com as animações | Experiência navegável de ponta a ponta com assets fake |
| M1 | Experiência real no perfil managed (Bedrock/ElevenLabs/HeyGen/Nova Reel), faixa rápida única | Hello < 60s; reveal < 3 min (limites do managed, ver 5.2); ciclo thumbs down funcional |
| M2 | Perfil selfhosted na g7e.4xlarge (Bruno: 9.2), paridade com M1, metas de latência plenas | Hello 10-20s; reveal < 120s; GPU-min/vídeo medido |
| M3 | EKS (Bruno: 9.3), Karpenter + KEDA, RDS/ElastiCache/S3+CloudFront, Terraform | Pipeline completo no cluster; scale-to-zero da lane background |
| M4 | Faixa HQ em background + badge HD na galeria + burst de b-roll paralelo | Item da galeria atualiza para 1080p sem ação do usuário |

## 14. Fora de escopo do MVP

Contas e login (desenho B fica documentado), multi-idioma, feed público/social, edição manual de timeline, export direto para redes sociais, liveness com desafio de movimento, fine-tuning de voz por usuário, mobile nativo, avatar em cena (reservado no contrato, caminho documentado em 5.5).

## 15. Questões em aberto

1. **Auditoria de licenças** dos pesos (XTTS-v2, checkpoint F5-TTS PT-BR, LTX-Video, ACE-Step) antes do M2; decide a rota comercial final do TTS e do T2V.
2. **Qualidade real do F5-TTS PT-BR vs XTTS-v2** com 40s de referência: bake-off na fase selfhosted-dev.
3. **MIG vs time-slicing** na RTX PRO 6000 para os workers leves: medir fragmentação de VRAM no M2.
4. **Marca/domínio Doppel**: verificação de disponibilidade e conflitos antes do go-live público.
5. **Disponibilidade de capacidade g7e** nas regiões alvo: família recente; validar capacity on-demand para o burst de até 18 instâncias.
