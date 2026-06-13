# Doppel inference handoff (Starya cluster)

Handoff from `elvt-starya-inference` to the Doppel product repo. Inference is deployed; Doppel wires workers and drivers.

**Status:** 2026-06-13 — Cosmos3-Super-Image2Video and LatentSync-1.6 are live on `ai-cluster-dev` / namespace `eks-inference-stack`.

---

## 1. What inference provides

| Service | Doppel role | In-cluster URL | LiteLLM pass-through |
|---|---|---|---|
| **Cosmos3-Super-Image2Video** | `broll-worker` (image→video) | `http://cosmos3-super-image2video.eks-inference-stack.svc.cluster.local:8000` | `POST /cosmos3/v1/videos/sync` |
| **LatentSync-1.6** | `avatar-worker` (lip-sync) | `http://latentsync-1-6.eks-inference-stack.svc.cluster.local:8080` | `POST /latentsync/v1/lipsync` |

**LiteLLM ALB (external):** `http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com`

**Recommendation:** Workers running on EKS should call **cluster Services directly** (no LiteLLM hop). Use LiteLLM pass-through only for dev from outside the cluster or catalog discovery. Master key lives in Secret `litellm-master-key` (required only for ALB routes).

**Verified smoke (2026-06-13):**

- In-cluster Cosmos3: HTTP 200, valid MP4 (~11s with 17 frames / 8 steps).
- ALB `/cosmos3/v1/videos/sync`: HTTP 200, valid MP4 (~10s with 9 frames / 6 steps).

---

## 2. PDR updates required

The Doppel PDR (`2026-06-12-doppel-design.md`) still lists **LTX-Video 2B (T2V)** for b-roll. What is deployed is **Cosmos3-Super-Image2Video (I2V)** — it requires a **first-frame image** plus text, not prompt-only.

| PDR section | Change |
|---|---|
| §5.2 B-roll row | Selfhosted fast lane: Cosmos3-Super-Image2Video (I2V), not LTX T2V. Managed lane unchanged (Nova Reel). |
| §9.2 GPU layout | Cosmos runs on a **dedicated `g7e.12xlarge` (2× RTX PRO 6000, 96 GB)**. Heretic LLM on `g7e.4xlarge`. LatentSync on `g6e.2xlarge`. Not colocated on one GPU. |
| §5.1 Roteiro | Each `type: "broll"` scene needs a **reference image** source (see §4 below). |

---

## 3. Cosmos3 API contract

**Not** `/v1/chat/completions`. OpenAI-compatible vLLM-Omni video endpoint.

### Request

```
POST /v1/videos/sync
Accept: video/mp4
Content-Type: multipart/form-data
```

| Field | Type | Notes |
|---|---|---|
| `input_reference` | file (PNG/JPEG) | **Required** — first frame |
| `prompt` | string | Plain text works; JSON-upsampled prompts give best quality (see HF model repo `assets/example_prompt.json`) |
| `negative_prompt` | string | Maps from roteiro `scene.negative` |
| `size` | string | `WIDTHxHEIGHT`, e.g. `480x832` for 9:16 vertical |
| `num_frames` | int | `max(5, min(400, int(duration_sec * fps)))` |
| `fps` | float | Default 24 |
| `num_inference_steps` | int | 50 default; fast lane try 20–30 |
| `guidance_scale` | float | 6.0 |
| `flow_shift` | float | 5.0 |
| `extra_params` | JSON string | `{"use_resolution_template":false,"use_duration_template":false,"guardrails":false}` |

### Response

Raw MP4 bytes when `Accept: video/mp4`. No streaming.

### Supported resolutions (model card)

256p, 480p, 720p at aspect ratios 16:9, 4:3, 1:1, 3:4, **9:16**. Doppel fast lane target: **480×832** (9:16).

### Guardrails

Disabled server-side in inference (`guardrails: false` in deploy-config). Guardrails require gated `nvidia/Cosmos-1.0-Guardrail` on HF. Re-enable in production only after license review and staging that model.

---

## 4. First-frame strategy (I2V)

Roteiro b-roll scenes only carry `prompt` / `negative`. Cosmos needs `input_reference`.

Pick one for MVP:

1. **Session reference frame (recommended MVP):** During `avatar_prep`, extract and store one frame from the user's 40s recording → S3 `avatars/{avatar_id}/reference_frame.png`. Reuse for all b-rolls in that session.
2. **T2I → I2V chain:** Deploy `Cosmos3-Super-Text2Image` (not on cluster yet) to synthesize a still, then I2V.
3. **Managed fallback:** Bedrock Nova Reel remains T2V-only in the managed driver.

---

## 5. LatentSync API contract (avatar)

```
POST /v1/lipsync
Content-Type: multipart/form-data
```

| Field | Type |
|---|---|
| `video` | file (MP4 — user footage or avatar base) |
| `audio` | file (WAV/MP3 — TTS output) |
| `guidance_scale` | float (default 1.5) |
| `inference_steps` | int (default 20) |
| `seed` | int |

Response: MP4 bytes.

LiteLLM route: `/latentsync/v1/lipsync`. Health: `/latentsync/health` (via ALB, requires master key).

---

## 6. What to build in the Doppel repo

### 6.1 Driver interface

```python
# capabilities/broll.py
class BrollDriver(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        first_frame: bytes,
        duration_sec: float,
        width: int = 480,
        height: int = 832,
        seed: int | None = None,
    ) -> bytes:  # MP4
        ...
```

Implementations:

- `SelfHostedCosmosDriver` — HTTP to inference (§3)
- `ManagedNovaReelDriver` — Bedrock (existing PDR)

Env: `BROLL_DRIVER=selfhosted|managed`.

### 6.2 Reference driver (selfhosted)

```python
import httpx
import json

async def call_cosmos(
    base_url: str,
    *,
    prompt: str,
    negative_prompt: str,
    first_frame: bytes,
    num_frames: int,
    fps: float = 24,
    size: str = "480x832",
    steps: int = 30,
    api_key: str | None = None,
) -> bytes:
    headers = {"Accept": "video/mp4"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": size,
        "num_frames": str(num_frames),
        "fps": str(fps),
        "num_inference_steps": str(steps),
        "guidance_scale": "6.0",
        "flow_shift": "5.0",
        "extra_params": json.dumps({
            "use_resolution_template": False,
            "use_duration_template": False,
            "guardrails": False,
        }),
    }
    files = {"input_reference": ("frame.png", first_frame, "image/png")}

    async with httpx.AsyncClient(timeout=1800) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/videos/sync",
            data=data,
            files=files,
            headers=headers,
        )
        r.raise_for_status()
        return r.content
```

### 6.3 `broll-worker` job payload

```json
{
  "video_id": "uuid",
  "scene_id": "s2",
  "prompt": "drone shot de praia ao amanhecer...",
  "negative_prompt": "texto, logos, pessoas reconheciveis",
  "window": [7.5, 13.0],
  "first_frame_s3": "avatars/{avatar_id}/reference_frame.png",
  "lane": "fast",
  "seed": 42
}
```

Worker steps (PDR §4: inference holds the model; worker is thin HTTP+S3):

1. Download `first_frame` from S3.
2. Compute `num_frames = max(5, min(400, int((window[1] - window[0]) * fps)))`.
3. Call Cosmos → MP4 bytes.
4. Upload to `components/{video_id}/broll/{scene_id}.mp4`.
5. Upsert `components` row (cache hash = scene_id + prompt + seed + first_frame etag + lane).
6. Publish Redis `component_done` `{scene_id, n, m}`.
7. Record `timings.broll_{scene_id}` on job row.

Enqueue **one job per b-roll scene** as soon as that scene closes in the streaming roteiro (PDR §5.1).

### 6.4 Orchestration (M1+)

Replace M0 monolithic `fast_generate` stub:

```
fast_generate (orchestrator job)
  ├─ script-worker: finalize roteiro
  ├─ enqueue broll jobs (parallel, one per scene)
  ├─ enqueue avatar track job(s)
  ├─ enqueue music job
  └─ compose-worker: waits for components → ffmpeg montage by scene windows
```

`compose-worker` alternates avatar track and b-roll MP4s per roteiro `window` fields.

### 6.5 Progress / SSE

| Worker event | SSE `step` |
|---|---|
| B-roll scene *i* of *n* started | `component_{i}_of_{n}` |
| Compose begins | `composing` |

### 6.6 Regeneration (thumbs-down)

Cache key: `hash(prompt + negative + seed + first_frame_etag + lane)`. On feedback delta, re-enqueue only b-roll jobs whose prompt changed.

---

## 7. Environment variables

```bash
# B-roll (Cosmos I2V) — direct in-cluster (preferred on EKS)
BROLL_DRIVER=selfhosted
BROLL_API_BASE=http://cosmos3-super-image2video.eks-inference-stack.svc.cluster.local:8000
BROLL_FAST_STEPS=30
BROLL_FAST_FPS=24
BROLL_FAST_SIZE=480x832

# B-roll via LiteLLM (dev / external only)
# BROLL_API_BASE=http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com/cosmos3
# INFERENCE_API_KEY=<from secret litellm-master-key>

# Avatar (LatentSync)
AVATAR_DRIVER=selfhosted
AVATAR_API_BASE=http://latentsync-1-6.eks-inference-stack.svc.cluster.local:8080
```

Add to `docker-compose.yml` profile `selfhosted`. Worker pods are **CPU-only** (HTTP clients); GPU stays on inference Deployments.

---

## 8. Latency and scaling

| Profile | Hardware | Observed / expected |
|---|---|---|
| Smoke (9–17 frames, 6–8 steps) | 2× RTX PRO 6000 | ~10–11 s |
| Production (189 frames, 50 steps, 832×480) | 2× RTX PRO 6000 | ~2–3 min per clip (model card: ~3 min on 2×H200-class) |
| Production (8× H200 recipe) | Not deployed | ~55 s per clip |

**Reveal budget (< 2 min):** Full-quality Cosmos per b-roll will blow the budget with multiple scenes. Mitigations:

- Fast lane: fewer steps (20–30), frame count matched to scene window only.
- Generate b-rolls in parallel (multiple worker replicas) — **inference side currently has 1 Cosmos replica**; scaling needs additional `g7e.12xlarge` nodes.
- HQ lane: full quality on `jobs:background` after thumbs-up.
- Alternative: keep a lighter T2V model for fast lane, Cosmos for HQ only.

---

## 9. Infrastructure notes (EKS)

| Deployment | Instance | GPUs | Image |
|---|---|---|---|
| `cosmos3-super-image2video-decode` | `g7e.12xlarge` | 2 | `vllm/vllm-omni:cosmos3` |
| `latentsync-1-6-decode` | `g6e.2xlarge` | 1 | `910894225546.dkr.ecr.us-east-1.amazonaws.com/starya/latentsync-1.6:latentsync-1.6-20260607` |

Weights: `s3://starya-openweight-models-dev-us-east-1/models/Cosmos3-Super-Image2Video/` (~129 GB).

Cosmos serve flags: `--cfg-parallel-size=2 --use-hsdp --hsdp-shard-size=2`.

**IRSA (Doppel workers):** S3 read on `avatars/`, read/write on `components/` and `videos/`. No cluster GPU required on worker pods.

---

## 10. Doppel M1 checklist

- [ ] `workers/broll_worker.py` + `drivers/cosmos_i2v.py`
- [ ] `workers/avatar_worker.py` + `drivers/latentsync.py` (if not already stubbed)
- [ ] Avatar prep writes `reference_frame.png` to S3
- [ ] Split b-roll out of `handle_fast_generate` stub
- [ ] Env config in compose profile `selfhosted`
- [ ] Update PDR §5.2 / §9.2 per §2 above
- [ ] Unit test: mock HTTP driver
- [ ] Integration test: real Cosmos smoke with HF example assets

---

## 11. Inference repo scripts (ops reference)

| Script | Purpose |
|---|---|
| `scripts/stage_cosmos3_super_image2video_to_s3.sh` | HF → S3 staging |
| `scripts/patch_cosmos3_super_image2video_deploy.sh` | g7e.12xlarge deploy |
| `scripts/register_litellm_cosmos3_passthrough.sh` | LiteLLM `/cosmos3` route |
| `scripts/patch_latentsync_1_6_deploy.sh` | LatentSync deploy |
| `scripts/register_litellm_latentsync_passthrough.sh` | LiteLLM `/latentsync` route |

---

## 12. Example curl (ALB, for manual testing)

```bash
MASTER_KEY=$(kubectl -n eks-inference-stack get secret litellm-master-key -o jsonpath='{.data.master-key}' | base64 -d)
ALB=http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com

curl -H "Authorization: Bearer ${MASTER_KEY}" \
  -H "Accept: video/mp4" \
  -F "input_reference=@first_frame.png;type=image/png" \
  -F "prompt=drone shot over beach at sunrise, warm tones" \
  -F "negative_prompt=text, logos" \
  -F "size=480x832" \
  -F "num_frames=24" \
  -F "fps=24" \
  -F "num_inference_steps=20" \
  -F "guidance_scale=6.0" \
  -F "flow_shift=5.0" \
  -F 'extra_params={"use_resolution_template":false,"use_duration_template":false,"guardrails":false}' \
  -o out.mp4 \
  "${ALB}/cosmos3/v1/videos/sync"
```

Example prompts for best quality: upsample to JSON via [cosmos-framework](https://github.com/NVIDIA/cosmos-framework) (`assets/example_prompt.json` in the HF model repo).
