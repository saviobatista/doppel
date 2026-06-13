# PDR: Doppel - Pipeline de geração real (fal.ai-centric)

| | |
|---|---|
| **Status** | Draft para revisão |
| **Data** | 2026-06-13 |
| **Antecede** | `2026-06-12-doppel-design.md` (PDR base), M0 walking skeleton (branch `feature/m0-walking-skeleton`) |
| **Escopo** | Substituir os stubs de geração (ffmpeg placeholder) por geração real via providers gerenciados, com fal.ai como ponto focal de vídeo |

## 1. Objetivo

Trocar a camada de geração do worker do M0 (que renderiza vídeos placeholder com `make_stub_video`) por geração real, usando o stack gerenciado que o Savio contratou, enquanto a inferência self-hosted na AWS não entra. Nada além da geração muda: banco, storage, fila, SSE, rotas e frontend permanecem como no M0 (verde).

## 2. Decisões travadas

- **Sem Supabase.** Mantém Postgres (compose) e floci/S3 (`S3Storage`). As variáveis `SUPABASE_*` presentes no `.env` ficam ignoradas neste trabalho.
- **Só a geração muda.** O esqueleto do worker (`process_one`, lanes, caminho de falha que marca a entidade `failed` e publica o evento) e o contrato de eventos SSE (`hello_ready`, `fast_ready`, `progress`, `failed`) ficam intactos.
- **Pontos de custo/qualidade aprovados:** FLUX schnell como fonte de imagem do b-roll (novo `FAL_T2I_MODEL`); Fabric a 480p no fast track; trilha sonora fora desta iteração.
- **Sem migração de schema.** O M0 usa `create_all` (sem Alembic). Campos novos (`voice_id`, key da imagem do rosto, keys intermediárias) entram no JSON `assets` das tabelas existentes, sem alterar colunas.

## 3. Stack de providers

| Capacidade | Provider | Modelo (`.env`) | I/O |
|---|---|---|---|
| Roteiro | Anthropic | `claude-sonnet-4-6` | transcript -> JSON do roteiro |
| Voz: clone | ElevenLabs | instant voice clone | amostra de áudio -> `voice_id` |
| Voz: TTS | ElevenLabs | `eleven_multilingual_v2` | `voice_id` + texto -> áudio (+ alignment p/ legenda) |
| Voz: STT | ElevenLabs | Scribe | áudio do briefing -> texto |
| Avatar falante | fal | `veed/fabric-1.0` | imagem + áudio -> vídeo falante (480p) |
| B-roll: imagem | fal | `FAL_T2I_MODEL` (FLUX schnell) | prompt -> imagem |
| B-roll: vídeo | fal | `fal-ai/kling-video/v2.1/standard/image-to-video` | imagem + prompt -> clipe |
| Legenda + composição | ffmpeg (local) | - | corte por janelas, legenda queimada (DejaVu Sans), H.264 540x960 |

Nota: legendas usam o **alignment do próprio TTS** da narração (ElevenLabs TTS-with-timestamps), evitando um segundo passe de STT. Scribe é usado só para o briefing.

## 4. Arquitetura

```
backend/
  src/doppel_api/
    config.py            # + campos dos providers (secrets via env)
    providers/           # NOVO pacote: um cliente fino por provider
      __init__.py
      script.py          # Anthropic: build_script(transcript) -> dict
      voice.py           # ElevenLabs: clone/tts/tts_with_timestamps/stt
      video.py           # fal: talking(image,audio) / image(prompt) / broll(image,prompt)
      media.py           # ffmpeg local: extract_frame, extract_audio, compose_timeline
  workers/
    stub_worker.py       # handlers reescritos para orquestrar os providers
```

- Cada provider é um módulo isolado com interface tipada, timeout e retry curto. Sem estado compartilhado; recebem config e bytes/paths, devolvem bytes/paths/dicts.
- O worker continua sendo o orquestrador: lê o job, chama os providers na ordem, sobe os assets via o `Storage` existente, publica eventos. A diferença é só o corpo de `handle_avatar_prep` e `handle_fast_generate`.
- fal usa `fal_client` (API de fila). Inputs locais (frame, áudio) são enviados via `fal_client.upload_file` para virar URLs antes do `subscribe`.

## 5. Pipeline `avatar_prep` (real)

Entrada: `avatar.assets["source"]` (gravação webm/mp4 já no storage).

1. `media.extract_frame(source)` -> melhor frame do rosto (imagem). `media.extract_audio(source)` -> áudio de referência limpo.
2. `voice.clone(ref_audio)` -> `voice_id`. Guarda em `avatar.assets["voice_id"]` e a key da imagem em `avatar.assets["face_image"]`.
3. `voice.tts(voice_id, HELLO_LINE)` e `voice.tts(voice_id, FEEDBACK_LINE)` -> áudios.
4. `video.talking(face_image, hello_audio)` -> `hello.mp4`; idem feedback -> `feedback.mp4`. Sobe ambos.
5. Marca `avatar.status = ready`, publica `hello_ready` com `hello_url` e `feedback_url` (contrato M0 inalterado).

`HELLO_LINE` e `FEEDBACK_LINE` são as frases fixas PT-BR do produto (já no frontend; espelhadas como constantes no backend).

## 6. Pipeline `fast_generate` (real)

Entrada: `video.assets["briefing"]` (áudio do briefing) + o avatar pronto (`voice_id`, `face_image`).

1. `voice.stt(briefing_audio)` -> transcript. Publica `progress: scripting`.
2. `script.build_script(transcript)` -> JSON (narração, cenas `avatar`/`broll` com prompt+janela, estilo de legenda). Guarda em `video.script`.
3. `voice.tts_with_timestamps(voice_id, narration)` -> áudio da narração (~30s) + alignment por palavra.
4. **Em paralelo** (semáforo = `PIPELINE_CONCURRENCY`), publicando `progress: component_n_of_m`:
   - `video.talking(face_image, narration_audio)` -> track do avatar (30s).
   - Por cena de b-roll: `video.image(prompt)` -> imagem; `video.broll(imagem, motion_prompt)` -> clipe.
5. `media.compose_timeline(...)` -> corta avatar/b-rolls pelas janelas do roteiro, queima legendas (alignment do passo 3, fonte `CAPTION_FONT`), encoda 540x960 H.264 -> `fast.mp4`. Sobe.
6. Marca `video.status_fast = ready`, publica `fast_ready` com `fast_url`.

## 7. Config

`Settings` ganha (secrets sempre via env, nunca commitados):

```
anthropic_api_key, anthropic_model
elevenlabs_api_key, elevenlabs_model
fal_key, fal_lipsync_model, fal_broll_model, fal_t2i_model
caption_font, pipeline_concurrency
```

`.env.example` documenta todas (com placeholders) e marca `SUPABASE_*` como não usadas neste escopo. `FAL_T2I_MODEL` é novo (não estava no `.env`); valor sugerido `fal-ai/flux/schnell`.

Os serviços `api` e `stub-worker` do compose recebem os secrets via `env_file: .env` (não via `environment:` inline), para que as chaves fluam do `.env` do host sem nunca serem commitadas. O `pydantic-settings` lê tanto `DOPPEL_*` quanto os nomes crus (`FAL_KEY`, `ANTHROPIC_API_KEY`, etc.); a config mapeia esses nomes diretamente. ffmpeg e `fonts-dejavu-core` já estão na imagem do backend (Dockerfile do M0), então `CAPTION_FONT=DejaVu Sans` resolve sem mudança de imagem.

## 8. Erros e custo

- **Degradação graciosa**: b-roll que falha (FLUX ou Kling) vira cena só-avatar - não derruba o vídeo; loga e segue. Falha de voz/avatar/roteiro (caminho crítico) usa o caminho de falha do M0: marca `failed` e publica `failed`.
- **Timeout + retry curto** por chamada fal (fila pode demorar): timeout configurável, 1-2 retries com backoff. Nenhum retry em erro de validação (4xx).
- **Custo**: Fabric ~US$0,08/s @480p (narração 30s ~US$2,40 + hello 6s + feedback 4s); FLUX schnell e Kling standard por b-roll. Mitigações: 480p, b-roll configurável (default 3), nada de música. Estimativa por vídeo documentada; kill-switch de orçamento por chave fica como nota operacional.

## 9. Testes

- **Drivers** (`providers/*`): unit test com HTTP mockado (respx) - valida shape da request e parsing da resposta. Zero rede real.
- **Handlers do worker**: providers monkeypatched (como o `make_stub_video` do M0) - valida orquestração, ordem, storage e eventos, sem chamada paga.
- **`media.py`**: ffmpeg sobre inputs sintéticos (testsrc/sine), valida que o output existe e tem duração/resolução esperadas.
- **Smoke ao vivo** (chaves reais): script opt-in atrás de flag (`DOPPEL_LIVE_SMOKE=1`), nunca em CI. Gera um vídeo real ponta a ponta.

## 10. Fora de escopo (desta iteração)

- Trilha sonora (sem provider configurado).
- Frontend no docker compose (`web`/Caddy) - segue rodando no host via Vite; decisão do Savio puxar para cá depois.
- Faixa HQ em background, upscale, multi-shot/`avatar_scene`, migração de banco/storage para qualquer serviço gerenciado.
- Self-hosted na AWS (este trabalho é a ponte gerenciada até lá).

## 11. Riscos

| Risco | Mitigação |
|---|---|
| Latência fal (fila) estoura a sensação "ao vivo" | Paralelismo, progresso por SSE, b-roll configurável; medir e ajustar. A meta de 120s do PDR base pode não ser atingível em managed - reportar números reais, não prometer. |
| Voz PT-BR fraca com amostra curta | `eleven_multilingual_v2` é referência; a gravação dá ~40s de amostra (bom). |
| Kling i2v sem imagem de origem | Resolvido: passo FLUX text-to-image antes (novo `FAL_T2I_MODEL`). |
| Custo descontrolado | Kill-switch por chave, b-roll/resolução configuráveis, estimativa por vídeo no dashboard de jobs (timings já existem). |
| Frame do rosto ruim (olhos fechados, desfoque) | `extract_frame` escolhe por heurística simples (nitidez/centralização); fallback para o primeiro frame estável. |
