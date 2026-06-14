# Video Agent — Session Handoff

A running log of what was built so this can be resumed in a fresh chat. The big
context: we built a **Video Agent** (HeyGen-style) in the `doppel` repo — a
chat-driven flow that researches a topic, streams a rich **video plan artifact**
(script + direction + transitions + audio + real sourced media/overlays), persists
it, and is about to gain a **generation** step that renders the plan into an MP4.

---

## 0. Repo layout & how to run

- `web/` — Next.js 16 app (App Router), dev server on **:3100**. Pure UI + thin API client.
- `backend/` — FastAPI (**:8200**) + a worker (`workers/worker.py`). Postgres + Redis + floci/S3.
- `frontend/` — legacy Vite app (reference only).
- Stack runs via `docker compose` (services: `api`, `stub-worker`, `postgres`, `redis`, `floci`).

Commands:
```bash
# backend stack
docker compose up -d --build api stub-worker        # rebuild after backend changes
docker logs --since 3m doppel-stub-worker-1          # worker logs
docker exec doppel-postgres-1 psql -U doppel -d doppel -t -A -c "select ..."

# web (dev server)
cd web && npm run dev -- --port 3100

# lint / typecheck
uv run --project backend ruff check backend/src/doppel_api backend/workers
cd web && npx tsc --noEmit -p .
```
Note: `docker compose up --build` rebuilds the image; the DB persists. New SQLAlchemy
**columns are NOT auto-added** to existing tables — add via `ALTER TABLE` (see §3).

Local generated assets are inspectable at `cache/renders/plan-<id>/` (bind-mounted).

---

## 1. First task — avatar identity prompt fix (done)

Problem: avatar look-generation rendered a **ginger beard** when the reference had an
ash-brown beard.
Root causes & fixes (in `backend/src/doppel_api/providers/`):
- `script.py` `_FACE_SYSTEM`: added **color discipline** (name a color once, conservative
  on warm tones, `distinguishing_features` is shape-only, negatives phrased as avoidances).
- `identity.py` `IDENTITY_TEMPLATE`: the edit models (`seedream/v4.5/edit`, `nano-banana-2/edit`)
  accept only a **positive** prompt — the old `=== NEGATIVE / AVOID ===` block was being
  read as things to render. Rewrote positive-only with "preserve source colors."
- `scripts/test_avatar_flow.py`: added `_MEDIA_TYPES` map (stdlib `mimetypes` misses `.webp`),
  fixed media-type detection for Claude vision.
Verified on two reference faces (blond-bearded + dark-haired João).

---

## 2. The Video Agent feature (the bulk — DONE through plan build & persistence)

### Flow
`POST /v1/plans` → worker `plan_build` → research → **streaming planner** → materialize
assets (media/overlays/footage/music) → `ready` → music streams in after.

### Backend pieces (all in `backend/src/doppel_api/`)
- **`models.py`** — added `Plan` table: `id, device_id, avatar_id, status, brief(json),
  plan(json), bundle(json), video_id, created_at`. Status:
  `researching → scripting → ready → generating → generated | failed`.
- **`routes/plans.py`** — endpoints:
  - `POST /v1/plans` (create + enqueue `plan_build`)
  - `GET /v1/plans` (lightweight list for projects grid; cover_url signed)
  - `GET /v1/plans/{id}` (full, **rehydrated** URLs)
  - `PATCH /v1/plans/{id}` (edit)
  - `GET /v1/plans/{id}/events` (SSE: status, progress, research, **plan_partial**, plan,
    bundle, ready, audio, failed)
  - `POST /v1/plans/{id}/generate` (enqueue `plan_generate`) ← **to be extended for §6**
  - `_rehydrate()` regenerates presigned URLs from durable S3 keys on every read (URLs
    expire in 1h; this makes revisits never break).
- **`routes/avatars.py`** — added `GET /v1/avatars` (picker source: id, status, preview, voice).
- **`providers/research.py`** — agent builds a **date-anchored** search query
  (`_agent_search_query`, one fast Claude call with today's date) → SerpAPI Google.
  Modes via `RESEARCH_MODE`: `serpapi_rest` (default, ~4s), `claude_mcp` (agent drives
  SerpAPI via Anthropic MCP connector — correct but ~100s+), `anthropic` (model-only).
  **Research is NOT cached** (time-sensitive).
- **`providers/plan.py`** — the planner. `emit_plan` tool with a big schema (title, style,
  research, script.scenes[direction+transition_out+overlays], audio.music, resources
  manifest, footage_query, meta.media_strategy). **Streams** via `client.messages.stream`;
  `_partial_json()` tolerant-parses the in-flight tool JSON → progressive `plan_partial`
  events (first content ~5s). `_normalize()` coerces stringy fields. Retry once if scenes empty.
- **`providers/sourcing.py`** — real media:
  - `search_images` (SerpAPI google_images, `tbs=itp:photo,isz:l`) → `filter_candidates`
    (drop products/stock/tiny/extreme-aspect) → `choose_image` (Claude **vision** picks best,
    + resolution gate `media_min_dimension`=900, cross-scene dedup).
  - `search_youtube` (SerpAPI youtube engine) → real recent video **links + thumbnails**
    (download deferred). `download_youtube` stub for generation time. (yt-dlp is IP-blocked
    from datacenter — footage download usually fails; thumbnails come from ytimg CDN.)
- **`providers/overlays.py`** — Pillow renders **dynamic** broadcast overlays from structured
  `content` (scoreboard/score_bug/stat_card/lower_third/title_card/ticker/timer/quote/
  bullet_list/logo_bug). Themed to the web palette.
- **`providers/music.py`** — 3 candidates: `fal_music` (Stable Audio 3), `elevenlabs_music`
  (`POST /v1/music`), `scraped_music` (yt-dlp, usually fails on datacenter IP).
- **`workers/worker.py`** — `handle_plan_build`:
  research → stream plan → `_materialize_resources` (media via choose_image, overlays via
  Pillow, footage via search_youtube — all parallel/best-effort, stored S3 + local + `key`
  on each) → `_build_bundle` (snapshot plan.json to S3 + manifest of all asset keys) →
  set `ready` → **`_generate_music` AFTER ready** (non-blocking; deepcopy + `flag_modified`
  to persist into `plan.resources.audio` + bundle; publishes `audio` SSE).
- **`queue.py`** — added `_claim_stale` / `XAUTOCLAIM`: a live worker reclaims jobs stranded
  by a crashed/restarted worker after `STALE_MS` (8 min) — plans never hang forever.

### Frontend pieces (all in `web/src/`)
- **`lib/videoPlan.ts`** — types mirroring the artifact: VideoPlan, Scene, Direction,
  Transition, AudioDesign, MediaAsset, DesignElement, AudioTrack, Resources, Bundle,
  PlanRecord, PlanSummary.
- **`lib/api.ts`** — client: ensureSession (device token in localStorage), listAvatars,
  createPlan, getPlan, listPlans, patchPlan, generatePlan, SSE (`subscribePlan`,
  `subscribeVideo` via fetch ReadableStream).
- **`app/agente/page.tsx`** + `components/agent/NewAgentStarter.tsx` — starter screen.
- **`app/agente/[id]/page.tsx`** + `components/agent/AgentScreen.tsx` — main screen:
  left `AgentTimeline` (phases driven by **buildStep/status**, NOT hasPlan — fixes false
  "done" during streaming), right `ArtifactPanel` (hero, style, research+sources, script
  scenes with direction tags + transitions, audio + music players, resources: media grid
  w/ video, dynamic overlay thumbnails, YouTube footage cards), `ResultView` (video tab).
  Handles SSE: plan_partial/plan/bundle/audio. Edit mode + Generate button.
- **`app/projetos/page.tsx`** + `components/projects/ProjectsGrid.tsx` — sessions list
  (each plan IS a session; click reopens `/agente/[id]`).
- **`components/home/PromptBar.tsx`** + `components/scenarios/CategoryGrid.tsx` — entry points
  wired to createPlan → `/agente/[id]`.

### Persistence / sessions / bundle (DONE)
- A **session = a plan**; device token persists → `/projetos` lists them, reopen by id.
- **Bundle** = durable manifest (plan.json snapshot in S3 + all asset keys + counts), stored
  on `plan.bundle`, shown as an "Artefato salvo" card. Rehydrated on read.

---

## 3. Schema migration note (IMPORTANT)
The `bundle` column was added to an existing `plans` table manually:
```sql
ALTER TABLE plans ADD COLUMN IF NOT EXISTS bundle JSON;
```
Any future new column on an existing table needs the same (SQLAlchemy `create_all` only
creates missing *tables*).

---

## 4. Models & config (`backend/src/doppel_api/config.py` + `.env`)

| Capability | Model / driver | Env |
|---|---|---|
| Script/plan author | `claude-sonnet-4-6` | `ANTHROPIC_PLANNER_MODEL` |
| Research query + synth | `claude-sonnet-4-6` + SerpAPI | `ANTHROPIC_MODEL`, `SERPAPI_KEY`, `RESEARCH_MODE` |
| Face/identity extract | `claude-opus-4-7` | `ANTHROPIC_PROMPT_MODEL` |
| TTS (voice clone) | ElevenLabs `eleven_multilingual_v2` | `ELEVENLABS_*` |
| Lip-sync | fal `veed/fabric-1.0` | `FAL_LIPSYNC_MODEL` |
| B-roll still (gen) | fal `flux/schnell` / self-hosted FLUX.2 | `FAL_T2I_MODEL`, `BROLL_T2I_DRIVER`, `BROLL_FLUX_API_BASE` |
| Still→video | fal `kling-video/v2.1` | `FAL_BROLL_MODEL` |
| Music | fal `stable-audio-3` + ElevenLabs Music | `FAL_MUSIC_MODEL` |
| Self-hosted cluster (Starya) | OpenAI-style `/v1/images/generations` | `INFERENCE_API_KEY` (+ base url) |

Other: `MEDIA_VISION_SELECT=true`, `MEDIA_MIN_DIMENSION=900`, `YOUTUBE_SHORTS_COUNT=2`,
`PIPELINE_CONCURRENCY=4`, `VIDEO_TARGET_SECONDS`, `CORS_ORIGINS` includes `:3100`.

**Note:** earlier debate — `ANTHROPIC_PLANNER_MODEL` and `ANTHROPIC_RESEARCH_MODEL` were
briefly set to `claude-opus-4-8` per user request, then planner reverted to Sonnet for
speed (Opus planner ~76s + truncation). Research is Sonnet (fast).

---

## 5. Performance work (DONE)
- Planner: Opus→**Sonnet**, fewer scenes (`duration/8`, cap 6), `max_tokens=8000`.
- **Music non-blocking** (streams after `ready`).
- **Plan streaming** (progressive `plan_partial`, first content ~5s).
- Research: fast `serpapi_rest` default (~4s); `claude_mcp` available but ~100s.
- Measured: full build to `ready` ~75–100s (planner-bound ~50s + materialize ~18s);
  feels instant due to streaming. Music arrives ~50s after ready.

---

## 6. GENERATION — Phase 1 BUILT & verified ✅

Real MP4 out of the test plan end-to-end (1080x1920, 30fps, h264 + AAC, ~29s, ~68s render).
Managed models + mixed motion (Fabric lip-sync on avatar scenes, Ken-Burns on scraped
stills for b-roll), per-scene narration, overlays, captions, transitions, ducked music.

### What was built
- **`providers/compose.py`** (NEW, pure ffmpeg/ffprobe — no network): `W,H=1080,1920`,
  `FPS=30`, `SAR=44100`.
  - `probe_duration` (ffprobe).
  - `render_scene(SceneSpec)` — one normalized scene clip: base = Ken-Burns on a still
    (`_ken_burns`, slow zoom + alternating pan via zoompan) **or** an avatar lip-sync video
    (cover-crop to vertical); overlay PNG composited at `overlay_y`; word-timed captions
    burned (libass `subtitles`, white + heavy outline); audio = the scene VO (or `anullsrc`).
    Everything pinned to W×H / FPS / SAR so xfade/acrossfade can chain.
  - `concat_transitions(segments, out)` — `xfade` per scene's `transition_out` + `acrossfade`
    on audio; offsets are cumulative `(Σdur − Σtrans)`. `_XFADE` maps plan transition types
    (whip→slideleft, cut→fade@0.06s, zoom→zoomin, crossfade→dissolve, fade→fadeblack).
  - `mix_music(video, music, out, gain, duck)` — loops/trims the bed (`-stream_loop -1`),
    `sidechaincompress` ducks it under the VO, `amix`.
- **`workers/worker.py`** — `handle_plan_generate` rewritten (old `_plan_to_script` removed):
  - `GenConfig` + `_gen_config(overrides)` resolve the **driver seam** from settings then
    per-request `model_overrides`.
  - `_render_plan` — fans scenes out in parallel (semaphore = `PIPELINE_CONCURRENCY`),
    concats with transitions, mixes the chosen music, stores `videos/{id}/fast.mp4` → S3 +
    local render, sets `Video.status_fast=ready`, publishes `fast_ready` SSE (same contract
    as the briefing path, so the existing `ResultView` just works).
  - `_build_scene` — per scene: `_scene_tts` (cloned voice, word timestamps, **gated by a
    dedicated `Semaphore(2)`** — ElevenLabs caps at 3 concurrent) → real duration + cues;
    avatar+lipsync → cached Fabric clip; else `_scene_still` (scene's scraped media key →
    fal-generated → avatar frame fallback) for Ken-Burns. Overlay PNG + music pulled from
    the materialized S3 keys (`_key_to_tmp`). All asset fetches best-effort (`_safe`).
  - On generate failure the plan reverts to `ready` (the artifact is still good), job → failed.
- **`routes/plans.py`** — `POST /v1/plans/{id}/generate` now takes an optional body
  `PlanGenerate {avatar_id?, selections?, model_overrides?}`; `avatar_id` attaches/overrides
  the plan's avatar (the test plan was built without one); `selections`/`model_overrides`
  flow into the job payload. `selections.music_key` pins the bed.
- **`config.py`** — driver settings: `TTS_DRIVER` (elevenlabs), `LIPSYNC_DRIVER` (fabric|none),
  `I2V_DRIVER` (kenburns|kling|selfhosted), `MUSIC_DRIVER`, `T2I_DRIVER`, `MUSIC_GAIN`.
- **`web/src/lib/api.ts`** — `generatePlan(planId, opts?)` sends the JSON body (UI unchanged;
  the browser flow creates plans with an avatar already, so it sends `{}`).

### The swappable seam (for the open-weight Starya models, later)
Each capability picks an implementation by name in `GenConfig`; drop a new branch into
`_build_scene` (lipsync / i2v) or a provider call behind the existing driver string. The
user's open-weight endpoints/specs are still TBD — when they arrive, add e.g.
`i2v_driver="selfhosted"` + a `video.broll`-style call, no orchestration changes.

### Verified
Rendered `43ecbab48f3647a997155d34d2e69f66` with avatar
`50e449e795e24ecb90e3addd59ef035a` (only ready avatar whose `face.png`/`voice_id` are in
floci S3 — `2c4c80c7…`'s assets are gone). Frame-checked all 5 scenes: avatar lip-sync +
title/stat cards on 1/3/5, Ken-Burns match photos + scoreboard/lower-third on 2/4, captions,
transitions, music. ⚠️ The plan's device ≠ the avatar's device, so the **API** generate
path can't attach those avatars (device-scoped) — verified by calling `_render_plan`
directly in the worker container. The normal browser flow (plan + own ready avatar) is fine.

### Still open / Phase 2
- Real **YouTube footage** clips: `I2V_DRIVER` default is `kenburns`; footage download is
  still deferred and yt-dlp is datacenter-blocked, so b-roll uses the scraped still today.
- Open-weight endpoints (lipsync / I2V / TTS) not wired yet — seam is ready.
- A frontend selections UI (pick music track / per-scene media) — backend accepts it already.

---

## 7. Known issues / gotchas
- Overlay PNGs render emoji (e.g. 🇧🇷) as tofu boxes — `overlays.py` uses DejaVu, which has
  no emoji glyphs. Cosmetic, pre-existing, lives in another lane's file. Fix later by
  stripping emoji from overlay `content` or adding a fallback emoji font.
- yt-dlp (footage + scraped music) is **bot-blocked from datacenter IPs** → those degrade
  gracefully (footage = links+thumbnails only; scraped music usually absent → 2 tracks).
- Worker rebuilds strand in-flight jobs briefly → `XAUTOCLAIM` reclaims after 8 min.
- Research not cached (intentional). Other provider artifacts ARE content-addressed in `cache/`.
- The web dev server runs in a background shell; relaunch with `cd web && npm run dev -- --port 3100` if it stops.

---

## 8. Quick test recipe
```bash
TOKEN=$(curl -s -X POST http://localhost:8200/v1/sessions | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
PLAN=$(curl -s -X POST http://localhost:8200/v1/plans -H "X-Device-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"prompt":"Um podcast sobre o jogo do Brasil na Copa 2026","duration_seconds":40,"language":"pt-BR","avatar_label":"Bruno Valerio"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['plan_id'])")
# poll: select status from plans where id='$PLAN';  → ready in ~90s
```
Or just use the browser at **http://localhost:3100** (home prompt bar or `/agente`).
