# M0 Smoke Checklist

Walking skeleton acceptance gate. Backend runs in docker compose (api on host port 8200,
floci S3 emulator, stub worker producing placeholder ffmpeg videos). Frontend runs via
`npm run dev` (vite, http://localhost:5173).

## Pre-requisites

- `docker compose up -d --build` is healthy (api, postgres, redis, floci, stub-worker).
- `cd frontend && npm run dev` is running.
- Browser access to presigned video URLs requires resolving the floci hostname once:
  `127.0.0.1 floci` in `/etc/hosts` (presigns point at `http://floci:4566`). Without it,
  the flow still advances (video error handlers resolve scenes) but the placeholder videos
  show black instead of the "HELLO" / "DOPPEL FAST STUB" frames.

## Checklist (Chrome, http://localhost:5173)

- [ ] Tela inicial "doppel" com botoes Comecar e Galeria
- [ ] Comecar pede camera/mic; negar leva a cena de erro com Recomecar
- [ ] Permitir: fade para preto, typewriter "Agora leia em voz alta..."
- [ ] Texto de leitura aparece com REC piscando; upload corre durante a leitura
      (Network: frames WS a cada ~1s para /v1/avatars/stream)
- [ ] "Terminei a leitura": engrenagens girando com label
- [ ] Em ~5-15s o hello stub (6s, "HELLO") toca sozinho
- [ ] Ao fim do hello, prompt de briefing com REC; falar e clicar Pronto
- [ ] Engrenagens com steps trocando (roteiro, cena 1/2/3)
- [ ] TV static estabiliza e o video de 30s ("DOPPEL FAST STUB") toca
- [ ] Thumbs down: video FEEDBACK toca, gera de novo, novo reveal
- [ ] Thumbs up: galeria mostra o video com controls
- [ ] Criar outro video: volta ao briefing sem regravar avatar
- [ ] Apagar meus dados: volta ao inicio; galeria vazia (token novo)
- [ ] Recarregar a pagina no meio: volta ao idle sem erro de console

## Automated run notes (2026-06-13)

Two automated passes covered everything except real-camera capture and on-screen
video playback (which need a human + the `/etc/hosts` floci entry).

**1. End-to-end pipeline against the live compose stack** (`/tmp/doppel_smoke.py`,
driving the exact HTTP+WS contract the frontend uses): ALL GREEN.
- session mint -> WS streaming avatar upload -> `hello_ready`
- worker rendered hello.mp4 (1.32 MB) and fast.mp4 (6.66 MB), both valid MP4s,
  both fetchable from floci (proves real Postgres + Redis + floci S3 + ffmpeg worker)
- video create with briefing -> progress steps -> `fast_ready`
- thumbs up -> gallery lists the video -> LGPD delete -> token revoked (gallery 401)

**2. Frontend bundle in a real browser** (Playwright/Chromium, http://localhost:5173):
- page loads, title "Doppel"
- `ensureSession()` succeeds cross-origin (5173 -> 8200 -> CORS ok); idle scene only
  renders after it resolves
- idle scene renders "doppel" + "Começar" + "Galeria" (PT-BR accents intact)
- only console error is a benign `favicon.ico` 404

**Still requires a human pass** (camera-dependent, with `127.0.0.1 floci` in /etc/hosts):
the reading face-capture, hello/reveal video playback on screen, thumbs-down regen
loop visuals, and the mid-flow page-reload recovery. Use the checklist above.
