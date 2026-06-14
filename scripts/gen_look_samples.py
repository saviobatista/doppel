"""Benchmark: generate look samples from a face frame using the FLOW prompt.

The flow prompt = identity-lock template (filled from the reference frame's facial
attributes) with the scenario scene block swapped in. Models:
  - fal-ai/nano-banana-2/edit            (image-to-image, face frame)
  - fal-ai/bytedance/seedream/v4.5/edit  (image-to-image, face frame)
  - Cosmos3-Super-Text2Image (ALB)       (text-to-image, identity from prompt only)

Run:  uv run --project backend python scripts/gen_look_samples.py
Outputs: benchmark-looks/<model>/NN.png  (+ _flow_prompt.txt, _face_attributes.json)
"""
import asyncio
import base64
import json
import os
import pathlib

import fal_client
import httpx

REPO = pathlib.Path(__file__).resolve().parent.parent
FACE = REPO / "geUHU_sgdXg4IXe4BMG2g_image (1).png"
OUT = REPO / "benchmark-looks"
N = 10
FAL_CONCURRENCY = 4
COSMOS_CONCURRENCY = 1
COSMOS_STEPS = 20

ALB = "http://k8s-eksinferencestack-7ea3c82c23-2009427571.us-east-1.elb.amazonaws.com"

# Scenario scene block (what the wizard's buildPrompt emits — becomes {{scene_block}}).
SCENE = (
    "Create a viral vertical avatar image for short-form video, featuring a confident "
    "successful entrepreneur conveying professionalism. The scenario is the main focus: a "
    "background with shelves and neon, with an elegant plant, a coffee cup. Viral and "
    "eye-catching look. The character appears in a half-body Reels/TikTok-style composition, "
    "with the background slightly blurred. Clean studio lighting, high contrast, realistic "
    "professional atmosphere, viral social media thumbnail style, ultra realistic, sharp "
    "details, clean composition. Avoid: cluttered background, artificial look, low-detail "
    "scene, too many colors, logos or brands, text in the image, deformed objects, "
    "blown-out lighting, cartoonish look, generic scene, flat background, overly artificial "
    "face."
)

COSMOS_NEG = (
    "different person, face swap, altered facial structure, changed bone structure, "
    "deformed features, extra fingers, plastic/airbrushed skin, cartoonish, 3D-render look, "
    "waxy skin, text or watermark, logos or brands, cluttered background, blown-out lighting"
)

# Used when the in-pipeline Claude vision extraction is unavailable (e.g. no/expired
# ANTHROPIC_API_KEY). Hand-authored from the reference frame; production uses Claude.
FALLBACK_ATTRS = {
    "age_range": "mid 30s to early 40s",
    "gender_presentation": "male",
    "ethnicity_appearance": "white / European",
    "skin_tone": "fair",
    "skin_undertone": "neutral-to-warm",
    "body_frame": "broad, solid build",
    "shoulders": "broad shoulders",
    "face_shape": "round-to-square",
    "hair_length": "short",
    "hair_color": "dark blond / light brown",
    "hair_style": "short cropped, textured on top",
    "hairline": "slightly receding at the temples",
    "facial_hair": "full medium-length brown beard and mustache",
    "eye_color": "blue",
    "eye_shape": "almond",
    "eye_set": "evenly set",
    "eyebrow_description": "medium thickness, fairly straight, light brown",
    "nose_description": "straight, medium width",
    "mouth_description": "medium-full lips, neutral relaxed set",
    "distinguishing_features": "full beard, bright blue eyes",
    "expression": "neutral and calm",
    "identity_specific_negatives": ["full beard", "blue eyes", "receding hairline"],
}


def _load_env() -> None:
    for line in (REPO / ".env").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


async def _save(url: str, path: pathlib.Path) -> None:
    async with httpx.AsyncClient(timeout=240) as c:
        r = await c.get(url)
        r.raise_for_status()
        path.write_bytes(r.content)


async def _fal_edit(model_id, args, outdir, i, sem, ok) -> None:
    dest = outdir / f"{i:02d}.png"
    if dest.exists():
        ok.append(1)
        return
    async with sem:
        try:
            res = await fal_client.subscribe_async(model_id, arguments=args)
            await _save(res["images"][0]["url"], outdir / f"{i:02d}.png")
            ok.append(1)
            print(f"  {outdir.name}/{i:02d}.png  ok")
        except Exception as e:
            print(f"  {outdir.name}/{i:02d}  FAILED: {type(e).__name__}: {getattr(e, 'body', e)}")


async def _cosmos(prompt, outdir, i, sem, ok) -> None:
    dest = outdir / f"{i:02d}.png"
    if dest.exists():
        ok.append(1)
        return
    key = os.environ["INFERENCE_API_KEY"]
    payload = {
        "prompt": prompt,
        "negative_prompt": COSMOS_NEG,
        "size": "480x832",
        "n": 1,
        "num_inference_steps": COSMOS_STEPS,
        "guidance_scale": 4.0,
        "flow_shift": 3.0,
        "seed": 1000 + i,
        "extra_args": {"use_resolution_template": False, "guardrails": False},
    }
    async with sem:
        try:
            async with httpx.AsyncClient(timeout=600) as c:
                r = await c.post(
                    f"{ALB}/cosmos3-t2i/v1/images/generations",
                    json=payload,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                )
                r.raise_for_status()
                data = base64.b64decode(r.json()["data"][0]["b64_json"])
            dest.write_bytes(data)
            ok.append(1)
            print(f"  {outdir.name}/{i:02d}.png  ok")
        except httpx.HTTPStatusError as e:
            print(f"  {outdir.name}/{i:02d}  FAILED: HTTP {e.response.status_code}: "
                  f"{e.response.text[:120]!r}")
        except Exception as e:
            print(f"  {outdir.name}/{i:02d}  FAILED: {type(e).__name__}: {e}")


async def main() -> None:
    _load_env()
    from doppel_api.providers import identity, script

    # 1. Build the flow prompt (identity lock + scene block).
    print("extracting facial attributes from the reference frame...")
    try:
        attrs = await script.extract_face_attributes(FACE.read_bytes())
    except Exception as e:
        print(f"  Claude extraction unavailable ({type(e).__name__}); using fallback attrs")
        attrs = FALLBACK_ATTRS
    flow_prompt = identity.apply_scene(identity.build_identity_prompt(attrs), SCENE)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "_face_attributes.json").write_text(json.dumps(attrs, indent=2, ensure_ascii=False))
    (OUT / "_flow_prompt.txt").write_text(flow_prompt)
    print(f"flow prompt ready ({len(flow_prompt)} chars) -> benchmark-looks/_flow_prompt.txt\n")

    # 2. Upload the face frame for the image-to-image models.
    img_url = await fal_client.upload_file_async(str(FACE))

    fal_sem = asyncio.Semaphore(FAL_CONCURRENCY)
    cosmos_sem = asyncio.Semaphore(COSMOS_CONCURRENCY)
    ok: list[int] = []
    tasks = []

    nano_dir = OUT / "nano-banana-2"
    seed_dir = OUT / "seedream-v4.5"
    cosmos_dir = OUT / "cosmos3-t2i"
    for d in (nano_dir, seed_dir, cosmos_dir):
        d.mkdir(parents=True, exist_ok=True)

    for i in range(1, N + 1):
        tasks.append(_fal_edit(
            "fal-ai/nano-banana-2/edit",
            {"prompt": flow_prompt, "image_urls": [img_url], "num_images": 1,
             "aspect_ratio": "9:16", "output_format": "png", "resolution": "2K"},
            nano_dir, i, fal_sem, ok,
        ))
        tasks.append(_fal_edit(
            "fal-ai/bytedance/seedream/v4.5/edit",
            {"prompt": flow_prompt, "image_urls": [img_url], "num_images": 1,
             "image_size": {"width": 1080, "height": 1920}, "seed": 1000 + i},
            seed_dir, i, fal_sem, ok,
        ))
        tasks.append(_cosmos(flow_prompt, cosmos_dir, i, cosmos_sem, ok))

    await asyncio.gather(*tasks)
    print(f"\ndone: {len(ok)}/{len(tasks)} images saved under {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
