"""fal.ai video generation: Fabric talking avatar, FLUX text-to-image, Kling image-to-video."""
import asyncio

import fal_client

from doppel_api.config import get_settings

# A locked/down fal hangs fal_client in an internal retry loop; an explicit
# timeout makes the call fail fast so one bad request cannot pin the worker
# (and with it the whole job lane). Generation is genuinely slow, so it gets a
# generous budget; uploads should be quick.
UPLOAD_TIMEOUT = 120.0
GENERATE_TIMEOUT = 300.0


async def upload(path: str) -> str:
    return await asyncio.wait_for(fal_client.upload_file_async(path), timeout=UPLOAD_TIMEOUT)


async def talking(image_url: str, audio_url: str, resolution: str = "480p") -> str:
    result = await asyncio.wait_for(
        fal_client.subscribe_async(
            get_settings().fal_lipsync_model,
            arguments={"image_url": image_url, "audio_url": audio_url, "resolution": resolution},
        ),
        timeout=GENERATE_TIMEOUT,
    )
    return result["video"]["url"]


async def image(prompt: str, image_size: str = "portrait_16_9") -> str:
    result = await asyncio.wait_for(
        fal_client.subscribe_async(
            get_settings().fal_t2i_model,
            arguments={"prompt": prompt, "image_size": image_size, "num_images": 1},
        ),
        timeout=GENERATE_TIMEOUT,
    )
    return result["images"][0]["url"]


async def edit_image(image_url: str, prompt: str, width: int = 1080, height: int = 1920) -> str:
    """Identity-lock image edit: restyle the scene around the person in `image_url`."""
    result = await asyncio.wait_for(
        fal_client.subscribe_async(
            get_settings().fal_edit_model,
            arguments={
                "prompt": prompt,
                "image_urls": [image_url],
                "image_size": {"width": width, "height": height},
                "num_images": 1,
            },
        ),
        timeout=GENERATE_TIMEOUT,
    )
    return result["images"][0]["url"]


async def broll(image_url: str, prompt: str, duration: str = "5") -> str:
    result = await asyncio.wait_for(
        fal_client.subscribe_async(
            get_settings().fal_broll_model,
            arguments={"prompt": prompt, "image_url": image_url, "duration": duration},
        ),
        timeout=GENERATE_TIMEOUT,
    )
    return result["video"]["url"]
