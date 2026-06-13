"""Content-addressed local cache for paid provider artifacts.

Keyed by a sha256 of each call's logical inputs and stored under CACHE_DIR on a
host bind-mounted directory, so re-runs reuse already-generated artifacts (and
the files are inspectable locally). A cache-write failure never fails the job -
the artifact was still produced this run.
"""
import hashlib
import json
import os
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from doppel_api.config import get_settings


def _key(parts: list[str | bytes]) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else str(part).encode("utf-8"))
        h.update(b"\x00")  # separator so ["a","b"] != ["ab"]
    return h.hexdigest()


def _path(namespace: str, key: str, ext: str) -> Path:
    return Path(get_settings().cache_dir) / namespace / f"{key}.{ext}"


def _safe_write(path: Path, data: bytes, ext: str) -> str:
    """Atomically write to the cache; on failure fall back to a temp file.

    Returns the path that actually holds the bytes, so the current run always
    has a usable file even if the cache dir is not writable.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return str(path)
    except OSError as exc:
        print(f"cache write failed for {path}: {exc!r}")
        fd, fallback = tempfile.mkstemp(suffix=f".{ext}")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return fallback


async def blob(
    namespace: str, parts: list, ext: str, producer: Callable[[], Awaitable[bytes]]
) -> str:
    path = _path(namespace, _key(parts), ext)
    if path.exists():
        return str(path)
    data = await producer()
    return _safe_write(path, data, ext)


async def value(namespace: str, parts: list, producer: Callable[[], Awaitable[Any]]) -> Any:
    path = _path(namespace, _key(parts), "json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (ValueError, OSError):
            pass  # corrupt/unreadable -> re-produce
    obj = await producer()
    _safe_write(path, json.dumps(obj).encode("utf-8"), "json")
    return obj


async def blob_with_meta(
    namespace: str, parts: list, ext: str,
    producer: Callable[[], Awaitable[tuple[bytes, Any]]],
) -> tuple[str, Any]:
    key = _key(parts)
    blob_path = _path(namespace, key, ext)
    meta_path = _path(namespace, key, "json")
    if blob_path.exists() and meta_path.exists():
        try:
            return str(blob_path), json.loads(meta_path.read_text())
        except (ValueError, OSError):
            pass
    data, meta = await producer()
    actual = _safe_write(blob_path, data, ext)
    _safe_write(meta_path, json.dumps(meta).encode("utf-8"), "json")
    return actual, meta


def put_blob(namespace: str, parts: list, ext: str, data: bytes) -> str:
    path = _path(namespace, _key(parts), ext)
    if path.exists():
        return str(path)
    return _safe_write(path, data, ext)


def save_render(name: str, ext: str, data: bytes) -> str:
    """Save a final deliverable under renders/ with a human-friendly name.

    Unlike the content-addressed helpers, this uses the given name verbatim and
    overwrites, so the user can find the finished videos on disk by name.
    """
    path = Path(get_settings().cache_dir) / "renders" / f"{name}.{ext}"
    return _safe_write(path, data, ext)
