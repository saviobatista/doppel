"""End-to-end test of the avatar LOOKS flow from a single face frame.

Mirrors worker._generate_looks, but with image-to-image EDIT models (the only
ones that take the face frame as input and preserve identity — cosmos/flux2 are
text-to-image and can't edit):

  1. extract_face_attributes(face)        -> facial attribute dict   (Claude vision)
  2. build_identity_prompt(attrs)         -> identity-lock base prompt
  3. apply_scene(base, LOOK_SCENES[i])    -> final per-look prompt
  4. nano-banana-2/edit + seedream/v4.5/edit (face frame as input) -> look images

Every step is logged to the console AND flow-test/run-<timestamp>.log.

Run:
  uv run --project backend python scripts/test_avatar_flow.py [path/to/face.png]

Outputs: each run lands in its own folder flow-test/run-<ts>/ containing
  _input.png, run.log, _face_attributes.json, _identity_prompt.txt, and
  <look-slug>/{nano-banana-2.png, seedream-v4.5.png, _prompt.txt}
"""
import asyncio
import json
import logging
import os
import pathlib
import shutil
import sys
import time
import unicodedata
from datetime import UTC, datetime

import fal_client
import httpx

REPO = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_FACE = REPO / "geUHU_sgdXg4IXe4BMG2g_image (1).png"
OUT = REPO / "flow-test"

# Claude vision accepts these; stdlib mimetypes misses .webp, so map explicitly.
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# Image-to-image edit models (face frame in -> identity-preserving look out).
MODELS = [
    {
        "name": "nano-banana-2",
        "id": "fal-ai/nano-banana-2/edit",
        "args": lambda url: {
            "image_urls": [url], "num_images": 1,
            "aspect_ratio": "9:16", "output_format": "png", "resolution": "2K",
        },
    },
    {
        "name": "seedream-v4.5",
        "id": "fal-ai/bytedance/seedream/v4.5/edit",
        "args": lambda url: {
            "image_urls": [url], "num_images": 1,
            "image_size": {"width": 1080, "height": 1920},
        },
    },
]

# Used when Claude vision is unavailable (no/expired ANTHROPIC_API_KEY).
# Hand-authored from the reference frame; production always uses Claude.
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
    "facial_hair": "full medium-length brown beard and mustache, slightly darker than the hair",
    "eye_color": "blue",
    "eye_shape": "almond",
    "eye_set": "evenly set",
    "eyebrow_description": "medium thickness, fairly straight, light brown",
    "nose_description": "straight, medium width",
    "mouth_description": "medium-full lips, neutral relaxed set",
    "distinguishing_features": "bright blue eyes contrasting with a darker beard; broad face",
    "expression": "neutral and calm",
    "identity_specific_negatives": [
        "do not tint the beard ginger/red/auburn",
        "do not change eye color from blue",
        "do not lower or thicken the hairline",
    ],
}

log = logging.getLogger("flow-test")


def _setup_run() -> tuple[pathlib.Path, pathlib.Path]:
    """Create a fresh per-run output folder and wire logging into it."""
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = OUT / f"run-{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    logfile = run_dir / "run.log"
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s", "%H:%M:%S")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(logfile)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    return run_dir, logfile


def _load_env() -> None:
    # .env is authoritative for this harness: override any stale/placeholder vars
    # already exported in the shell (e.g. ANTHROPIC_API_KEY=your-...-here).
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"').strip("'")


def _slug(label: str) -> str:
    norm = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return "".join(c if c.isalnum() else "-" for c in norm.lower()).strip("-")


async def _save(url: str, path: pathlib.Path) -> int:
    async with httpx.AsyncClient(timeout=240) as c:
        r = await c.get(url)
        r.raise_for_status()
        path.write_bytes(r.content)  # noqa: ASYNC240
    return len(r.content)


async def _gen(model: dict, img_url: str, prompt: str, dest: pathlib.Path, tag: str,
               sem: asyncio.Semaphore, results: list[dict]) -> None:
    async with sem:
        t0 = time.monotonic()
        args = {"prompt": prompt, **model["args"](img_url)}
        log.info("[%s] -> %s submitting (prompt=%d chars)", tag, model["id"], len(prompt))
        try:
            res = await fal_client.subscribe_async(model["id"], arguments=args)
            url = res["images"][0]["url"]
            size = await _save(url, dest)
            dt = time.monotonic() - t0
            log.info("[%s] OK in %.1fs -> %s (%d KB)", tag, dt, dest.name, size // 1024)
            results.append({"tag": tag, "ok": True, "seconds": round(dt, 1), "path": str(dest)})
        except Exception as e:
            dt = time.monotonic() - t0
            detail = getattr(e, "body", None) or e
            log.error("[%s] FAILED in %.1fs: %s: %s", tag, dt, type(e).__name__, detail)
            results.append({"tag": tag, "ok": False, "seconds": round(dt, 1), "error": str(detail)})


async def main() -> None:
    run_dir, logfile = _setup_run()
    _load_env()

    face = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_FACE  # noqa: ASYNC240
    if not face.exists():
        log.error("face frame not found: %s", face)
        sys.exit(1)
    shutil.copy(face, run_dir / f"_input{face.suffix.lower()}")  # keep input next to outputs

    from doppel_api.config import get_settings
    from doppel_api.providers import identity, script

    prompt_model = get_settings().anthropic_prompt_model
    log.info("=== avatar looks flow test ===")
    log.info("face frame : %s (%d KB)", face.name, face.stat().st_size // 1024)
    log.info("output dir : %s", run_dir)
    log.info("logfile    : %s", logfile)
    log.info("looks      : %s", ", ".join(s["label"] for s in identity.LOOK_SCENES))
    log.info("models     : %s", ", ".join(m["name"] for m in MODELS))
    log.info("prompt prep: %s", prompt_model)

    # 1. Facial attributes (Claude vision, with hand-authored fallback).
    log.info("step 1/4: extracting facial attributes via %s...", prompt_model)
    t0 = time.monotonic()
    media_type = _MEDIA_TYPES.get(face.suffix.lower(), "image/png")
    try:
        attrs = await script.extract_face_attributes(face.read_bytes(), media_type=media_type)
        log.info("  attributes extracted via Claude in %.1fs", time.monotonic() - t0)
    except Exception as e:
        log.warning("  Claude unavailable (%s: %s); using FALLBACK_ATTRS",
                    type(e).__name__, getattr(e, "body", None) or e)
        attrs = FALLBACK_ATTRS
    for k, v in attrs.items():
        log.info("    %-28s %s", k, v)
    (run_dir / "_face_attributes.json").write_text(
        json.dumps(attrs, indent=2, ensure_ascii=False))

    # 2. Identity-lock base prompt.
    log.info("step 2/4: building identity-lock base prompt...")
    base_prompt = identity.build_identity_prompt(attrs)
    (run_dir / "_identity_prompt.txt").write_text(base_prompt)
    log.info("  base prompt: %d chars -> flow-test/_identity_prompt.txt", len(base_prompt))

    # 3. Upload face once for the image-to-image edit models.
    log.info("step 3/4: uploading face frame to fal...")
    img_url = await fal_client.upload_file_async(str(face))
    log.info("  uploaded -> %s", img_url)

    # 4. Per-look x per-model generation.
    log.info("step 4/4: generating %d looks x %d models = %d images...",
             len(identity.LOOK_SCENES), len(MODELS), len(identity.LOOK_SCENES) * len(MODELS))
    sem = asyncio.Semaphore(4)
    results: list[dict] = []
    tasks = []
    for scene in identity.LOOK_SCENES:
        slug = _slug(scene["label"])
        look_dir = run_dir / slug
        look_dir.mkdir(parents=True, exist_ok=True)
        final_prompt = identity.apply_scene(base_prompt, scene["scene_block"])
        (look_dir / "_prompt.txt").write_text(final_prompt)
        for model in MODELS:
            dest = look_dir / f"{model['name']}.png"
            tag = f"{slug}/{model['name']}"
            tasks.append(_gen(model, img_url, final_prompt, dest, tag, sem, results))
    await asyncio.gather(*tasks)

    ok = [r for r in results if r["ok"]]
    log.info("=== done: %d/%d images saved under %s ===", len(ok), len(results), run_dir)
    for r in results:
        mark = "ok " if r["ok"] else "ERR"
        log.info("  %-28s %s %5.1fs", r["tag"], mark, r["seconds"])
    if len(ok) < len(results):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
