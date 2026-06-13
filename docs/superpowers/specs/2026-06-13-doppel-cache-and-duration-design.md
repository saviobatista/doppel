# PDR: Doppel - cache de artefatos + duração configurável

| | |
|---|---|
| **Status** | Draft para revisão |
| **Data** | 2026-06-13 |
| **Antecede** | `2026-06-13-doppel-fal-pipeline-design.md` (pipeline gerenciado fal.ai-centric) |
| **Motivação** | fal.ai é caro; validar conceito sem re-pagar artefatos já gerados e com vídeos curtos |

## 1. Objetivo

Duas camadas/knobs que reduzem custo de validação sem mudar a lógica do pipeline:

1. **Cache content-addressed local** das chamadas pagas (ElevenLabs clone/TTS/STT, Claude, fal Fabric/FLUX/Kling). Um re-run reusa o que já foi gerado: dá pra "ir por partes que funcionam", retomar do último passo bom, e pagar uma vez por input único. Os arquivos ficam num diretório local inspecionável. É o cache por componente que o PDR base já previa (tabela `components`, adiada no M0), implementado como cache content-addressed em vez de tabela.
2. **`VIDEO_TARGET_SECONDS` configurável**: vídeo curto (~10s) para validar barato; 30s (ou o que for) quando estiver 100%. É só um knob no prompt do roteiro.

## 2. Decisões travadas

- **Cache em diretório no host (bind-mounted)**, não no floci/S3. Os arquivos ficam inspecionáveis direto na máquina. O floci segue guardando só os entregáveis finais (hello/feedback/fast.mp4).
- **Cacheia todas as chamadas externas pagas**, inclusive as baratas (STT, Claude) - é o que torna o "resume" determinístico e grátis.
- **`VIDEO_TARGET_SECONDS` default = 10** (ponto doce que ainda exercita o b-roll; 5 tende a virar só-avatar).
- **Providers continuam puros** (clientes finos). O cache vive no worker, que conhece as chaves lógicas e já faz os downloads do fal.
- Sem mudança no contrato do pipeline, no compose da timeline, nem nas rotas/SSE/frontend.

## 3. Módulo `cache.py`

Novo `backend/src/doppel_api/cache.py`, content-addressed sobre `CACHE_DIR` (default `/app/cache`):

```
def _key(parts: list[str | bytes]) -> str        # sha256 hex de parts (str -> utf8, bytes as-is, com separador)
async def blob(namespace, parts, ext, producer) -> str   # producer() -> bytes; retorna path do arquivo cacheado
async def value(namespace, parts, producer) -> Any       # producer() -> objeto json-serializavel; retorna o objeto
def put_blob(namespace, parts, ext, data: bytes) -> str   # grava bytes ja em maos (ex.: copia da gravacao)
```

- Layout: `CACHE_DIR/<namespace>/<hash>.<ext>` (blobs) e `CACHE_DIR/<namespace>/<hash>.json` (values).
- **Escrita atômica**: grava em `<hash>.<ext>.tmp` e `os.replace` para o destino (evita entrada parcial em caso de crash).
- **Hit**: arquivo existe -> retorna sem chamar `producer`. **Miss**: chama `producer`, grava, retorna.
- **Resiliência**: falha de escrita no cache só loga e segue (o artefato ainda foi produzido nesta run); uma entrada `value` que não decodifica como JSON é tratada como miss (re-produz).
- `producer` é async (envolve a chamada do provider e, no caso fal, o download dos bytes).

## 4. O que é cacheado e a chave

| namespace | chave (parts) | conteúdo | substitui |
|---|---|---|---|
| `source` | `[avatar_id]` | a gravação do usuário (cópia local) | - (novo: "salvar local") |
| `clone` | `[ref_audio_bytes]` | voice_id (value) | nova clonagem + slot de voz |
| `tts` | `[voice_id, text, model]` | mp3 | re-TTS |
| `tts_ts` | `[voice_id, text, model]` | mp3 + cues (blob + value) | re-TTS-timestamps |
| `stt` | `[briefing_bytes]` | texto (value) | re-STT |
| `script` | `[transcript, str(target_seconds)]` | roteiro (value) | re-Claude |
| `fabric` | `[face_bytes, audio_bytes, resolution]` | mp4 | re-Fabric (o item mais caro) |
| `flux` | `[prompt, image_size]` | imagem | re-FLUX |
| `kling` | `[image_bytes, prompt, duration]` | mp4 | re-Kling |

Os hashes compõem naturalmente: TTS cacheado -> mesmos bytes de áudio -> mesma chave de Fabric -> hit no Fabric. Mudar um input invalida só aquele ramo.

## 5. Integração no worker

`handle_avatar_prep` e `handle_fast_generate` passam cada passo caro pelo cache. Exemplo (avatar_prep):

- `cache.put_blob("source", [avatar_id], ext, source_bytes)` logo após baixar a gravação do storage.
- `voice_id = await cache.value("clone", [ref_audio_bytes], lambda: voice.clone(ref_audio, name))`
- por linha fixa: `audio_path = await cache.blob("tts", [voice_id, line, model], "mp3", lambda: voice.tts(voice_id, line))`
- `talk_path = await cache.blob("fabric", [face_bytes, audio_bytes, "480p"], "mp4", lambda: _fal_fabric_bytes(face_path, audio_path))` onde `_fal_fabric_bytes` faz upload + `video.talking` + download e devolve bytes.

`handle_fast_generate` é análogo (stt, script com `target_seconds`, tts_ts, fabric da narração, flux->kling por cena). A geração paralela de b-roll e a degradação graciosa continuam iguais; cada b-roll passa pelo cache (`flux` e `kling`).

A composição (`media.compose_timeline`) e o upload dos entregáveis ao floci continuam exatamente como hoje - o cache fica antes deles.

## 6. `VIDEO_TARGET_SECONDS`

- Campo em `Settings`: `video_target_seconds: int = 10` (validation_alias `VIDEO_TARGET_SECONDS`, igual aos outros raw env names).
- `script.build_script(transcript, target_seconds)` ganha o parâmetro; o `_SYSTEM`/prompt passa a pedir narração de ~`target_seconds` segundos (~`target_seconds*2.5` palavras), 2-4 cenas cobrindo `0..target_seconds` com cortes curtos (janelas de 2-4s).
- O worker passa `get_settings().video_target_seconds` para `build_script`, e usa o mesmo valor na chave de cache `script` (para que mudar a duração invalide o roteiro cacheado).
- `.env.example` documenta `VIDEO_TARGET_SECONDS=10`.

## 7. Infra

- `docker-compose.yml`: volume `./cache:/app/cache` em `api` e `stub-worker`. `CACHE_DIR=/app/cache` no env compartilhado (ou default em Settings).
- `.gitignore`: `cache/` (nunca commitar artefatos/mídia gerada).
- `Settings`: `cache_dir: str = "/app/cache"` (raw env `CACHE_DIR`).

## 8. Erros

- Cache miss/escrita falha: loga, produz/segue (nunca derruba o job por causa do cache).
- Entrada corrompida: tratada como miss.
- O cache não altera os caminhos de falha do pipeline (b-roll degrada, falha crítica marca `failed` + evento) nem a blindagem de timeout do fal.

## 9. Testes

- `cache.py`: hit reusa sem chamar producer; miss chama e grava; escrita atômica (sem `.tmp` órfão no hit); value corrompido re-produz; falha de escrita não propaga. Tudo em `tmp_path`, sem rede.
- Worker: com providers mockados, uma 2ª chamada do handler **não** invoca o provider (contador de chamadas) - prova o cache. Zero chamada paga em CI.
- `script.build_script`: recebe `target_seconds` e o injeta no prompt (assert no payload mockado do Claude); a chave de cache `script` inclui `target_seconds`.

## 10. Fora de escopo

- Tabela `components` no Postgres (o cache local cobre a necessidade de validação; a tabela é otimização futura para multi-instância/galeria HQ).
- Invalidação por TTL / limpeza automática do cache (por ora é manual: apagar a pasta `cache/`).
- Compartilhamento do cache entre máquinas (é local por design).
- Faixa HQ/HD, trilha sonora, avatar em cena - seguem fora.

**Nota sobre a faixa HD**: ela NÃO existe no código hoje (não há handler `hq_generate`, nem campo `status_hq`, nem upscale - o pipeline gera só a faixa fast 540x960 e para). Não há nada rodando nem custando por ela. Quando for construída, entra atrás de uma **feature flag default-OFF** (ex.: `HQ_ENABLED=false`), para só rodar quando o fast estiver 100%.
