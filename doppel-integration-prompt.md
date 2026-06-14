# Doppel ↔ Starya inference — integration prompt

Use this document when wiring the Doppel app to the Starya inference cluster. Workers on EKS should call **cluster Services directly** (no LiteLLM hop). LiteLLM pass-through is for local dev / ALB access from outside the cluster.

**Namespace:** `eks-inference-stack`  
**ALB (external):** `http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com`  
**Master key:** Kubernetes Secret `litellm-master-key` (required only for ALB routes)

---

## Service map

| Doppel worker | Model | In-cluster base URL | Endpoint |
|---|---|---|---|
| `broll-worker` (I2V) | Cosmos3-Super-Image2Video | `http://cosmos3-super-image2video.eks-inference-stack.svc.cluster.local:8000` | `POST /v1/videos/sync` |
| `broll-worker` (T2I still) | Cosmos3-Super-Text2Image | `http://cosmos3-super-text2image.eks-inference-stack.svc.cluster.local:8000` | `POST /v1/images/generations` |
| `broll-worker` (alt I2V) | HunyuanVideo-1.5 720p I2V | `http://hunyuanvideo-1-5-720p-i2v.eks-inference-stack.svc.cluster.local:8000` | `POST /v1/videos/sync` |
| `avatar-worker` | LatentSync-1.6 | `http://latentsync-1-6.eks-inference-stack.svc.cluster.local:8080` | `POST /v1/lipsync` |

**LiteLLM pass-through (external dev):**

| Path prefix | Backend |
|---|---|
| `/cosmos3/v1/videos/sync` | Cosmos I2V |
| `/cosmos3-t2i/v1/images/generations` | Cosmos T2I |
| `/hunyuanvideo/v1/videos/sync` | Hunyuan I2V |
| `/latentsync/v1/lipsync` | LatentSync |

Health: `GET /health` on each service (no auth in-cluster).

---

## Recommended b-roll pipeline

Cosmos **I2V requires a first frame**. Two self-hosted options:

```
Option A (MVP — session frame):
  avatar_prep → extract reference_frame.png from user video
  → Cosmos I2V with that frame + scene prompt

Option B (T2I → I2V chain):
  Cosmos T2I (prompt only) → PNG still
  → Cosmos I2V or Hunyuan I2V with that still + prompt
```

Managed fallback (Bedrock Nova Reel) remains T2V-only — no first frame needed.

---

## 1. Cosmos3 Image→Video (primary b-roll)

**Multipart POST** — not chat completions.

```python
import httpx
import json


async def cosmos_i2v(
    base_url: str,
    *,
    prompt: str,
    negative_prompt: str,
    first_frame: bytes,
    num_frames: int,
    size: str = "480x832",      # 9:16 fast lane
    fps: float = 24,
    steps: int = 30,            # fast: 20–30; HQ: 50
    seed: int | None = None,
    timeout: float = 1800,
) -> bytes:
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
    if seed is not None:
        data["seed"] = str(seed)

    files = {"input_reference": ("frame.png", first_frame, "image/png")}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/videos/sync",
            data=data,
            files=files,
            headers={"Accept": "video/mp4"},
        )
        r.raise_for_status()
        return r.content
```

**Roteiro → params:**

```python
num_frames = max(5, min(400, int((window[1] - window[0]) * fps)))
```

**Supported resolutions:** 256p, 480p, 720p at 16:9, 4:3, 1:1, 3:4, **9:16**. Fast lane target: **480×832**.

**Latency (2× RTX PRO 6000):** smoke ~10s (few frames); production ~2–3 min per clip at 480×832 / 50 steps.

---

## 2. Cosmos3 Text→Image (first-frame generator)

**JSON POST** — response is base64 PNG in OpenAI-style envelope.

Model: [nvidia/Cosmos3-Super-Text2Image](https://huggingface.co/nvidia/Cosmos3-Super-Text2Image)

```python
import base64
import httpx


async def cosmos_t2i(
    base_url: str,
    *,
    prompt: str,
    negative_prompt: str = "",
    size: str = "832x480",
    steps: int = 50,
    guidance_scale: float = 4.0,
    flow_shift: float = 3.0,
    seed: int = 1143,
) -> bytes:
    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "size": size,
        "n": 1,
        "num_inference_steps": steps,
        "guidance_scale": guidance_scale,
        "flow_shift": flow_shift,
        "seed": seed,
        "extra_args": {
            "use_resolution_template": False,
            "guardrails": False,
        },
    }
    async with httpx.AsyncClient(timeout=600) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/images/generations",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        r.raise_for_status()
        b64 = r.json()["data"][0]["b64_json"]
        return base64.b64decode(b64)
```

**T2I → I2V chain:**

```python
still = await cosmos_t2i(T2I_BASE, prompt=scene.prompt, size="832x480")
mp4 = await cosmos_i2v(I2V_BASE, prompt=scene.prompt, first_frame=still, ...)
```

JSON-upsampled prompts give best quality — see HF model repo `assets/example_caption.json`.

---

## 3. HunyuanVideo 720p I2V (alternative b-roll)

Same multipart shape as Cosmos I2V, different defaults.

Model: [hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v](https://huggingface.co/hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v)

```python
async def hunyuan_i2v(
    base_url: str,
    *,
    prompt: str,
    first_frame: bytes,
    negative_prompt: str = "",
    num_frames: int = 121,
    steps: int = 50,
    height: int = 720,
    width: int = 1280,
    seed: int = 1,
    fps: int = 24,
    timeout: float = 3600,
) -> bytes:
    data = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "num_frames": str(num_frames),
        "num_inference_steps": str(steps),
        "height": str(height),
        "width": str(width),
        "seed": str(seed),
        "fps": str(fps),
    }
    files = {"input_reference": ("frame.png", first_frame, "image/png")}
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/videos/sync",
            data=data,
            files=files,
            headers={"Accept": "video/mp4"},
        )
        r.raise_for_status()
        return r.content
```

---

## 4. LatentSync (avatar lip-sync)

```python
async def latentsync(
    base_url: str,
    *,
    video: bytes,
    audio: bytes,
    guidance_scale: float = 1.5,
    inference_steps: int = 20,
    seed: int = 0,
    timeout: float = 3600,
) -> bytes:
    files = {
        "video": ("input.mp4", video, "video/mp4"),
        "audio": ("tts.wav", audio, "audio/wav"),
    }
    data = {
        "guidance_scale": str(guidance_scale),
        "inference_steps": str(inference_steps),
        "seed": str(seed),
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/v1/lipsync",
            data=data,
            files=files,
        )
        r.raise_for_status()
        return r.content
```

Responses include `X-Request-ID` for log correlation.

---

## Driver interface (suggested)

```python
# capabilities/broll.py
from typing import Protocol


class BrollDriver(Protocol):
    async def generate(
        self,
        *,
        prompt: str,
        negative_prompt: str,
        first_frame: bytes | None,  # None → T2I chain or managed T2V
        duration_sec: float,
        width: int = 480,
        height: int = 832,
        seed: int | None = None,
    ) -> bytes: ...


# drivers/cosmos_i2v.py      → SelfHostedCosmosI2VDriver
# drivers/cosmos_t2i.py      → SelfHostedCosmosT2IDriver (for chain)
# drivers/hunyuan_i2v.py     → SelfHostedHunyuanI2VDriver (optional)
# drivers/managed_nova.py    → ManagedNovaReelDriver
```

---

## Environment variables

```bash
# B-roll
BROLL_DRIVER=selfhosted          # selfhosted | managed
BROLL_I2V_API_BASE=http://cosmos3-super-image2video.eks-inference-stack.svc.cluster.local:8000
BROLL_T2I_API_BASE=http://cosmos3-super-text2image.eks-inference-stack.svc.cluster.local:8000
BROLL_HUNYUAN_API_BASE=http://hunyuanvideo-1-5-720p-i2v.eks-inference-stack.svc.cluster.local:8000
BROLL_FAST_STEPS=30
BROLL_FAST_FPS=24
BROLL_FAST_SIZE=480x832
BROLL_USE_T2I_CHAIN=false        # true → generate still before I2V when no reference frame

# Avatar
AVATAR_DRIVER=selfhosted
AVATAR_API_BASE=http://latentsync-1-6.eks-inference-stack.svc.cluster.local:8080

# External dev only (LiteLLM ALB)
# INFERENCE_ALB=http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com
# INFERENCE_API_KEY=<litellm-master-key>
# BROLL_I2V_API_BASE=${INFERENCE_ALB}/cosmos3
# BROLL_T2I_API_BASE=${INFERENCE_ALB}/cosmos3-t2i
# BROLL_HUNYUAN_API_BASE=${INFERENCE_ALB}/hunyuanvideo
# AVATAR_API_BASE=${INFERENCE_ALB}/latentsync
```

Worker pods are **CPU-only** HTTP clients; GPU stays on inference Deployments.

---

## `broll-worker` job payload

```json
{
  "video_id": "uuid",
  "scene_id": "s2",
  "prompt": "drone shot de praia ao amanhecer...",
  "negative_prompt": "texto, logos",
  "window": [7.5, 13.0],
  "first_frame_s3": "avatars/{avatar_id}/reference_frame.png",
  "lane": "fast",
  "seed": 42
}
```

**Worker steps:**

1. Download `first_frame` from S3 (or run T2I if `first_frame_s3` absent and `BROLL_USE_T2I_CHAIN=true`).
2. `num_frames = max(5, min(400, int((window[1] - window[0]) * fps)))`.
3. Call I2V → MP4 bytes.
4. Upload `components/{video_id}/broll/{scene_id}.mp4`.
5. Upsert `components` row; cache key = `hash(prompt + negative + seed + first_frame_etag + lane)`.
6. Publish Redis `component_done`; record `timings.broll_{scene_id}`.

Enqueue **one job per b-roll scene** as the roteiro closes each scene.

---

## Orchestration sketch

```
fast_generate (orchestrator)
  ├─ script-worker → finalize roteiro
  ├─ avatar_prep → reference_frame.png on S3
  ├─ enqueue broll jobs (parallel, 1/scene)
  ├─ enqueue avatar track job(s)
  ├─ enqueue music job
  └─ compose-worker → ffmpeg montage by scene windows
```

`compose-worker` alternates avatar track + b-roll MP4s per roteiro `window`.

---

## Timeouts and errors

| Service | Suggested timeout | Notes |
|---|---|---|
| Cosmos I2V | 1800s | Long clips / 50 steps |
| Cosmos T2I | 600s | Single image |
| Hunyuan I2V | 3600s | 720p / 121 frames |
| LatentSync | 3600s | Returns `X-Request-ID` on errors |

| HTTP | Meaning |
|---|---|
| 400 | Bad params |
| 500 | Inference failed — check pod logs |
| 504 | Inference timeout (LatentSync) |

```bash
kubectl -n eks-inference-stack logs -f deploy/cosmos3-super-image2video-decode -c vllm-omni
kubectl -n eks-inference-stack logs -f deploy/cosmos3-super-text2image-decode -c vllm-omni
kubectl -n eks-inference-stack logs -f deploy/hunyuanvideo-1-5-720p-i2v-decode -c hunyuanvideo
kubectl -n eks-inference-stack logs -f deploy/latentsync-1-6-decode -c latentsync
```

---

## Manual smoke (ALB, from laptop)

```bash
MASTER_KEY=$(kubectl -n eks-inference-stack get secret litellm-master-key \
  -o jsonpath='{.data.master-key}' | base64 -d)
ALB=http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com

# Cosmos I2V
curl -H "Authorization: Bearer ${MASTER_KEY}" -H "Accept: video/mp4" \
  -F "input_reference=@frame.png;type=image/png" \
  -F "prompt=drone shot over beach at sunrise" \
  -F "negative_prompt=text, logos" \
  -F "size=480x832" -F "num_frames=24" -F "fps=24" \
  -F "num_inference_steps=20" -F "guidance_scale=6.0" -F "flow_shift=5.0" \
  -F 'extra_params={"use_resolution_template":false,"use_duration_template":false,"guardrails":false}' \
  -o out.mp4 "${ALB}/cosmos3/v1/videos/sync"

# Cosmos T2I
curl -H "Authorization: Bearer ${MASTER_KEY}" -H "Content-Type: application/json" \
  -d '{"prompt":"sunset beach, cinematic","size":"832x480","n":1,"num_inference_steps":30,"guidance_scale":4.0,"flow_shift":3.0,"seed":42,"extra_args":{"guardrails":false}}' \
  "${ALB}/cosmos3-t2i/v1/images/generations" | jq -r '.data[0].b64_json' | base64 -d > still.png

# LatentSync
curl -H "Authorization: Bearer ${MASTER_KEY}" \
  -F "video=@input.mp4;type=video/mp4" \
  -F "audio=@tts.wav;type=audio/wav" \
  -F "inference_steps=20" -F "guidance_scale=1.5" \
  -o lipsync.mp4 "${ALB}/latentsync/v1/lipsync"
```

---

## Infrastructure (EKS)

| Deployment | Instance | GPUs | Image |
|---|---|---|---|
| `cosmos3-super-image2video-decode` | `g7e.12xlarge` | 2 | `vllm/vllm-omni:cosmos3` |
| `cosmos3-super-text2image-decode` | `g7e.12xlarge` | 2 | `vllm/vllm-omni:cosmos3` |
| `hunyuanvideo-1-5-720p-i2v-decode` | `g7e.4xlarge` | 1 | `starya/hunyuanvideo-1.5-720p-i2v:hunyuanvideo-1.5-720p-i2v-20260613` |
| `latentsync-1-6-decode` | `g6e.2xlarge` | 1 | `starya/latentsync-1.6:latentsync-1.6-20260613` |

Cosmos serve flags: `--cfg-parallel-size=2 --use-hsdp --hsdp-shard-size=2`. Guardrails disabled server-side.

**IRSA (Doppel workers):** S3 read on `avatars/`, read/write on `components/` and `videos/`. No cluster GPU on worker pods.

---

## M1 checklist (Doppel repo)

- [ ] `drivers/cosmos_i2v.py`, `drivers/cosmos_t2i.py`, `drivers/latentsync.py`
- [ ] `workers/broll_worker.py` — thin HTTP + S3
- [ ] `workers/avatar_worker.py`
- [ ] Avatar prep writes `avatars/{id}/reference_frame.png`
- [ ] Env block in `docker-compose.yml` profile `selfhosted`
- [ ] Unit tests with mocked HTTP; one integration smoke per driver
- [ ] Update PDR §5.2 / §9.2: Cosmos I2V + T2I (not LTX T2V)

---

## Ops scripts (inference repo)

| Script | Purpose |
|---|---|
| `scripts/stage_cosmos3_super_image2video_to_s3.sh` | Cosmos I2V HF → S3 |
| `scripts/patch_cosmos3_super_image2video_deploy.sh` | Cosmos I2V deploy |
| `scripts/stage_cosmos3_super_text2image_to_s3.sh` | Cosmos T2I HF → S3 |
| `scripts/patch_cosmos3_super_text2image_deploy.sh` | Cosmos T2I deploy |
| `scripts/register_litellm_cosmos3_passthrough.sh` | LiteLLM `/cosmos3` |
| `scripts/register_litellm_cosmos3_t2i_passthrough.sh` | LiteLLM `/cosmos3-t2i` |
| `scripts/stage_hunyuanvideo_1_5_720p_i2v_to_s3.sh` | Hunyuan HF → S3 |
| `scripts/patch_hunyuanvideo_1_5_720p_i2v_deploy.sh` | Hunyuan deploy |
| `scripts/register_litellm_hunyuanvideo_passthrough.sh` | LiteLLM `/hunyuanvideo` |
| `scripts/patch_latentsync_1_6_deploy.sh` | LatentSync deploy |
| `scripts/register_litellm_latentsync_passthrough.sh` | LiteLLM `/latentsync` |
