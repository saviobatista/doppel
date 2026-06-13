"""Shared logging setup for api and worker processes."""
from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger("doppel")
    if root.handlers:
        root.setLevel(_level(level))
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(name)s] %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(_level(level))
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_logger(component: str) -> logging.Logger:
    return logging.getLogger(f"doppel.{component}")


def _level(name: str) -> int:
    return getattr(logging, name.upper(), logging.INFO)


def kv(**fields: Any) -> str:
    """Format key=value pairs for grep-friendly structured logs."""
    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").strip()
        if " " in text or "=" in text:
            text = repr(text)
        parts.append(f"{key}={text}")
    return " ".join(parts)
