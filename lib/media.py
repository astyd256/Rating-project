"""Helpers for image payloads and filesystem-safe names."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WHITESPACE = re.compile(r"\s+")


def guess_image_mime(data: bytes | None) -> str | None:
    """Return the MIME type of an image payload based on its magic bytes."""
    if not data:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def image_extension(data: bytes | None, default: str = ".jpg") -> str:
    return _EXTENSION_BY_MIME.get(guess_image_mime(data) or "", default)


def slugify(value: str, *, max_length: int = 80) -> str:
    """Turn a title into a lowercase, filename-safe slug (unicode letters kept)."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = _INVALID_FILENAME_CHARS.sub("", text)
    text = _WHITESPACE.sub("-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-.")
    return text[:max_length].rstrip("-.") or "untitled"


def unique_filename(
    directory: Path,
    base_name: str,
    extension: str,
    suffix: str | None = None,
) -> str:
    """Return a filename that does not exist yet in ``directory``."""
    candidate = f"{base_name}{extension}"
    if not (directory / candidate).exists():
        return candidate
    if suffix:
        alternative = f"{base_name}-{slugify(suffix, max_length=24)}{extension}"
        if not (directory / alternative).exists():
            return alternative
    index = 2
    while (directory / f"{base_name}-{index}{extension}").exists():
        index += 1
    return f"{base_name}-{index}{extension}"
