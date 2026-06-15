"""Real-media sourcing: SerpAPI image search + yt-dlp YouTube Shorts download.

For topics with trustworthy media (a real match, a news event) we scrape real
artifacts instead of generating them. Image selection is a 3-stage funnel:
search (many candidates) -> deterministic filter (resolution, aspect, stock/
watermark/product junk, dedup) -> vision pick (Claude chooses the single best,
most relevant, watermark-free photo). Everything is best-effort and returns
empty/None on failure so the worker can fall back to generation.
"""
import asyncio
import base64
import io

import anthropic
import anyio
import httpx
from PIL import Image

from doppel_api.config import get_settings

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
)

# Stock/watermark/aggregator domains whose previews are watermarked or low-trust.
_BAD_SOURCES = (
    "gettyimages", "alamy", "shutterstock", "istockphoto", "dreamstime", "123rf",
    "depositphotos", "stock.adobe", "vecteezy", "freepik", "lookaside", "fbsbx",
    "pinterest", "pinimg", "redbubble", "ebay", "aliexpress", "etsy",
)
_MAX_ASPECT = 3.0       # drop banners / logos (very wide or very tall)


def _locale(language: str) -> tuple[str, str]:
    """(hl, gl) for SerpAPI from a BCP-47-ish language tag."""
    if language.startswith("pt"):
        return "pt", "br"
    if language.startswith("es"):
        return "es", "mx"
    return "en", "us"


def _meets_resolution(data: bytes, min_dim: int) -> bool:
    """True if the decoded image's short side is at least `min_dim` px."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        return min(w, h) >= min_dim
    except Exception:
        return False


async def search_images(query: str, n: int = 24) -> list[dict]:
    """Google Images via SerpAPI (large photos). Returns raw candidate dicts with
    url, thumbnail, title, source, link, width, height, is_product.

    Empty list when no SERPAPI_KEY is configured (caller falls back to generation).
    """
    key = get_settings().serpapi_key
    if not key or not query:
        return []
    params = {
        "engine": "google_images", "q": query, "api_key": key,
        "ijn": "0", "safe": "active",
        # photos only, large size — biases away from clip-art/icons/logos.
        "tbs": "itp:photo,isz:l",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://serpapi.com/search.json", params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        print(f"serpapi image search failed for {query!r}: {exc!r}")
        return []
    out: list[dict] = []
    for im in data.get("images_results") or []:
        url = im.get("original") or im.get("thumbnail")
        if not url:
            continue
        out.append({
            "url": url, "thumbnail": im.get("thumbnail"),
            "title": im.get("title"), "source": im.get("source"), "link": im.get("link"),
            "width": im.get("original_width"), "height": im.get("original_height"),
            "is_product": bool(im.get("is_product")),
        })
        if len(out) >= n:
            break
    return out


def filter_candidates(cands: list[dict], exclude_urls: set[str] | None = None) -> list[dict]:
    """Deterministic pre-filter: drop products, tiny images, extreme aspect ratios,
    stock/watermark/aggregator sources, and already-used or duplicate URLs."""
    exclude = exclude_urls or set()
    min_dim = get_settings().media_min_dimension
    seen: set[str] = set()
    kept: list[dict] = []
    for c in cands:
        url = c.get("url")
        if not url or url in seen or url in exclude:
            continue
        if c.get("is_product"):
            continue
        src = (c.get("source") or "").lower() + " " + (url or "").lower()
        if any(bad in src for bad in _BAD_SOURCES):
            continue
        w, h = c.get("width"), c.get("height")
        if isinstance(w, int) and isinstance(h, int) and w and h:
            # Reject on known metadata; unknown dims are verified post-download.
            if min(w, h) < min_dim or max(w, h) / min(w, h) > _MAX_ASPECT:
                continue
        seen.add(url)
        kept.append(c)
    return kept


async def download_image(candidate: dict) -> bytes | None:
    """Fetch a SerpAPI image, trying the original then the cached thumbnail."""
    urls = [candidate.get("url"), candidate.get("thumbnail")]
    async with httpx.AsyncClient(timeout=40, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as c:
        for url in [u for u in urls if u]:
            try:
                r = await c.get(url)
                r.raise_for_status()
                if r.content and r.headers.get("content-type", "").startswith("image"):
                    return r.content
            except Exception:
                continue
    return None


async def _thumb_bytes(candidate: dict) -> bytes | None:
    """Small preview bytes for vision ranking (prefer the cached thumbnail)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as c:
        for url in [candidate.get("thumbnail"), candidate.get("url")]:
            if not url:
                continue
            try:
                r = await c.get(url)
                r.raise_for_status()
                if r.content and r.headers.get("content-type", "").startswith("image"):
                    return r.content
            except Exception:
                continue
    return None


def _vision_pick(images: list[bytes], description: str) -> int:
    """Claude vision: choose the best candidate index for `description`. -1 on abstain."""
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=90.0)
    content: list[dict] = [{
        "type": "text",
        "text": (
            f"Pick the single BEST photo to use as b-roll for: \"{description}\".\n"
            "Requirements: a real photograph (not a logo, graphic, collage, meme, or "
            "screenshot), clearly on-topic, high quality, NO visible watermark or stock "
            "overlay, and usable in a vertical 9:16 social video. If none are acceptable, "
            "return index -1. Call pick_image with the 0-based index."
        ),
    }]
    for i, data in enumerate(images):
        content.append({"type": "text", "text": f"Image {i}:"})
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg",
                       "data": base64.b64encode(data).decode("ascii")},
        })
    resp = client.messages.create(
        model=settings.anthropic_prompt_model,
        max_tokens=300,
        messages=[{"role": "user", "content": content}],
        tools=[{
            "name": "pick_image",
            "description": "Select the best image index (or -1 if none are acceptable).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["index"],
            },
        }],
        tool_choice={"type": "tool", "name": "pick_image"},
    )
    block = next((b for b in resp.content if b.type == "tool_use"), None)
    idx = int(block.input.get("index", -1)) if block else -1
    return idx if 0 <= idx < len(images) else -1


async def choose_image(
    query: str, description: str, *, exclude_urls: set[str] | None = None,
    vision: bool = True, pool: int = 8,
) -> tuple[bytes, dict] | None:
    """Search -> filter -> (vision) pick -> download. Returns (image_bytes, candidate)
    for the best on-topic, watermark-free photo, or None to fall back to generation."""
    settings = get_settings()
    min_dim = settings.media_min_dimension
    cands = filter_candidates(await search_images(query), exclude_urls)
    if not cands:
        return None

    # Build a preference order: the vision-chosen candidate first, then the rest by rank.
    order: list[dict] = []
    if vision and settings.serpapi_key:
        pool_cands = cands[:pool]
        thumbs = await asyncio.gather(*[_thumb_bytes(c) for c in pool_cands])
        paired = [(c, t) for c, t in zip(pool_cands, thumbs, strict=False) if t]
        if paired:
            try:
                idx = await anyio.to_thread.run_sync(
                    lambda: _vision_pick([t for _, t in paired], description)
                )
            except Exception as exc:
                print(f"vision image pick failed, using heuristic: {exc!r}")
                idx = -1
            if idx >= 0:
                order.append(paired[idx][0])
    order += [c for c in cands if c not in order]

    # Download in order and return the first that actually meets the resolution bar.
    for c in order:
        data = await download_image(c)
        if data and await anyio.to_thread.run_sync(lambda d=data: _meets_resolution(d, min_dim)):
            return data, c
    return None


async def search_youtube(query: str, n: int = 4, *, language: str = "pt-BR") -> list[dict]:
    """Real, ranked, recent YouTube results via SerpAPI — LINKS + metadata only, no
    download. Returns [{title, link, video_id, thumbnail, channel, published, views,
    length}]."""
    key = get_settings().serpapi_key
    if not key or not query:
        return []
    hl, gl = _locale(language)
    params = {"engine": "youtube", "search_query": query, "api_key": key, "gl": gl, "hl": hl}
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get("https://serpapi.com/search.json", params=params)
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        print(f"serpapi youtube search failed for {query!r}: {exc!r}")
        return []
    out: list[dict] = []
    for v in data.get("video_results") or []:
        link = v.get("link")
        if not link:
            continue
        vid = v.get("video_id")
        # Canonical JPEG thumbnail from the video id (the SerpAPI `static` URL carries
        # sqp params that return AVIF/WebP, which we'd then mislabel as jpeg).
        thumb = v.get("thumbnail")
        thumb = thumb.get("static") if isinstance(thumb, dict) else thumb
        if vid:
            thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
        ch = v.get("channel")
        ch = ch.get("name") if isinstance(ch, dict) else ch
        out.append({
            "title": v.get("title"), "link": link, "video_id": vid,
            "thumbnail": thumb, "channel": ch, "published": v.get("published_date"),
            "views": v.get("views"), "length": v.get("length"),
        })
        if len(out) >= n:
            break
    return out


async def fetch_thumbnail(url: str | None) -> bytes | None:
    """Fetch a thumbnail image (ytimg CDN is fast and reachable). Best-effort."""
    if not url:
        return None
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                 headers={"User-Agent": _UA}) as c:
        try:
            r = await c.get(url)
            r.raise_for_status()
            if r.content and r.headers.get("content-type", "").startswith("image"):
                return r.content
        except Exception:
            return None
    return None
