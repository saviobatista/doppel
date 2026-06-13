"""fal.ai video generation: Fabric talking avatar, FLUX text-to-image, Kling image-to-video."""
import fal_client

from doppel_api.config import get_settings


async def upload(path: str) -> str:
    return await fal_client.upload_file_async(path)


async def talking(image_url: str, audio_url: str, resolution: str = "480p") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_lipsync_model,
        arguments={"image_url": image_url, "audio_url": audio_url, "resolution": resolution},
    )
    return result["video"]["url"]


async def image(prompt: str, image_size: str = "portrait_16_9") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_t2i_model,
        arguments={"prompt": prompt, "image_size": image_size, "num_images": 1},
    )
    return result["images"][0]["url"]


async def broll(image_url: str, prompt: str, duration: str = "5") -> str:
    result = await fal_client.subscribe_async(
        get_settings().fal_broll_model,
        arguments={"prompt": prompt, "image_url": image_url, "duration": duration},
    )
    return result["video"]["url"]
