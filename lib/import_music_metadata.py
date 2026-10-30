"""Import music metadata (title, album, artist, rating, cover art) from audio files."""
from __future__ import annotations

import os
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from PIL import Image

from lib.db import crud
from lib.db.models import Music
from lib.db.session import get_session

SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".m4a",
    ".mp4",
    ".wav",
    ".ogg",
    ".opus",
    ".aac",
    ".aiff",
    ".aif",
}

ART_SIZE = 240
ART_QUALITY = 80

# MusicBee / ID3 POPM values map to stars non-linearly.
_POPM_STARS = ((0, 0.0), (1, 1.0), (64, 2.0), (128, 3.0), (196, 4.0), (255, 5.0))


@dataclass
class MusicImportStats:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0


def _first(value: Any) -> Any:
    """Unwrap mutagen frames/lists down to a single scalar value."""
    if value is None:
        return None
    text = getattr(value, "text", None)
    if text is not None:
        value = text
    if isinstance(value, (list, tuple)):
        return _first(value[0]) if value else None
    return value


def _text(value: Any) -> str | None:
    value = _first(value)
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    text = str(value).strip()
    return text or None


def _strip(value: Any) -> str | None:
    return value.strip() or None if isinstance(value, str) else value


def _normalise_rating(value: Any) -> float | None:
    """Normalise a rating to the 0..5 star scale used for music."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        if "/" in text:
            numerator, _, denominator = text.partition("/")
            try:
                divisor = float(denominator)
                if divisor == 0:
                    return None
                return _clamp_stars(float(numerator) / divisor * 5.0)
            except ValueError:
                return None
        if text.endswith("%"):
            try:
                return _clamp_stars(float(text[:-1]) / 100.0 * 5.0)
            except ValueError:
                return None
        try:
            number = float(text.replace(",", "."))
        except ValueError:
            return None

    if number <= 0:
        return None
    if number <= 5:
        return round(number, 2)
    if number <= 10:
        return round(number / 2.0, 2)
    if number <= 100:
        return round(number / 100.0 * 5.0, 2)
    if number <= 255:
        return round(number / 255.0 * 5.0, 2)
    return None


def _clamp_stars(value: float) -> float | None:
    if value <= 0:
        return None
    return round(min(value, 5.0), 2)


def _popm_to_stars(frame: Any) -> float | None:
    raw = getattr(frame, "rating", None)
    if raw is None:
        raw = frame
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    for popm_value, stars in _POPM_STARS:
        if abs(value - popm_value) <= 8:
            return stars
    # Non-standard value (e.g. half stars): keep the continuous mapping.
    return _clamp_stars(value / 255.0 * 5.0)


def _rating_from_tags(tags: Any) -> float | None:
    if tags is None:
        return None

    getall = getattr(tags, "getall", None)
    if callable(getall):
        try:
            popm_frames = getall("POPM")
        except Exception:
            popm_frames = []
        for frame in popm_frames or []:
            stars = _popm_to_stars(frame)
            if stars is not None:
                return stars

    for key in (
        "fmps_rating",
        "FMPS_RATING",
        "rating",
        "RATING",
        "WM/PRATING",
        "REPLAYGAIN_RATING",
    ):
        try:
            value = tags.get(key)
        except Exception:
            continue
        if value is None:
            continue
        text = _text(value)
        if text is None:
            continue
        if key.lower() == "fmps_rating":
            try:
                return _clamp_stars(float(text) * 5.0)
            except ValueError:
                continue
        stars = _normalise_rating(text)
        if stars is not None:
            return stars
    return None


def compress_art(data: bytes | None) -> bytes | None:
    """Resize cover art to a small webp (jpeg fallback) payload."""
    if not data:
        return None
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception:
        return None

    try:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        image.thumbnail((ART_SIZE, ART_SIZE), Image.LANCZOS)
        output = BytesIO()
        try:
            image.save(output, format="WEBP", quality=ART_QUALITY, method=6)
            return output.getvalue()
        except Exception:
            output = BytesIO()
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                background.save(output, format="JPEG", quality=ART_QUALITY, optimize=True)
            else:
                image.convert("RGB").save(output, format="JPEG", quality=ART_QUALITY, optimize=True)
            return output.getvalue()
    except Exception:
        return None


def _apply_id3(tags: Any, meta: dict[str, Any]) -> None:
    if tags is None:
        return
    meta["title"] = _text(tags.get("TIT2")) or meta["title"]
    meta["album"] = _text(tags.get("TALB")) or meta["album"]
    meta["artist"] = _text(tags.get("TPE1")) or _text(tags.get("TPE2")) or meta["artist"]
    meta["rating"] = meta["rating"] or _rating_from_tags(tags)
    if meta["art"] is None:
        try:
            pictures = tags.getall("APIC")
        except Exception:
            pictures = []
        if pictures:
            meta["art"] = compress_art(pictures[0].data)


def extract_metadata(file_path: str | Path) -> dict[str, Any]:
    """Return ``title``, ``album``, ``artist``, ``rating`` (0..5) and ``art`` bytes."""
    path = Path(file_path)
    meta: dict[str, Any] = {
        "title": path.stem,
        "album": None,
        "artist": None,
        "rating": None,
        "art": None,
    }

    try:
        audio = MutagenFile(str(path))
    except Exception:
        audio = None
    tags = getattr(audio, "tags", None)
    suffix = path.suffix.lower()

    if suffix in {".mp3", ".wav", ".aiff", ".aif"}:
        id3_tags = None
        try:
            id3_tags = ID3(str(path))
        except Exception:
            id3_tags = tags if hasattr(tags, "getall") else None
        _apply_id3(id3_tags, meta)

    if suffix == ".flac" or isinstance(audio, FLAC):
        flac_tags = getattr(audio, "tags", None)
        if flac_tags:
            meta["title"] = _text(flac_tags.get("TITLE")) or meta["title"]
            meta["album"] = _text(flac_tags.get("ALBUM")) or meta["album"]
            meta["artist"] = (
                _text(flac_tags.get("ARTIST"))
                or _text(flac_tags.get("ALBUMARTIST"))
                or meta["artist"]
            )
            meta["rating"] = meta["rating"] or _rating_from_tags(flac_tags)
        pictures = getattr(audio, "pictures", None) or []
        if meta["art"] is None and pictures:
            meta["art"] = compress_art(pictures[0].data)

    if suffix in {".m4a", ".mp4", ".aac"} and tags:
        meta["title"] = _text(tags.get("\xa9nam")) or meta["title"]
        meta["album"] = _text(tags.get("\xa9alb")) or meta["album"]
        meta["artist"] = (
            _text(tags.get("\xa9ART"))
            or _text(tags.get("aART"))
            or meta["artist"]
        )
        covers = tags.get("covr")
        if covers and meta["art"] is None:
            try:
                meta["art"] = compress_art(bytes(covers[0]))
            except Exception:
                pass
        meta["rating"] = meta["rating"] or _rating_from_tags(tags)

    # Generic fallback: ogg/opus and files whose format-specific tags were empty.
    if not meta["artist"] or not meta["album"] or meta["art"] is None or meta["rating"] is None:
        try:
            easy = MutagenFile(str(path), easy=True)
        except Exception:
            easy = None
        easy_tags = getattr(easy, "tags", None) if easy is not None else None
        if easy_tags:
            meta["title"] = meta["title"] or _text(easy_tags.get("title"))
            meta["album"] = meta["album"] or _text(easy_tags.get("album"))
            meta["artist"] = (
                meta["artist"]
                or _text(easy_tags.get("artist"))
                or _text(easy_tags.get("albumartist"))
            )
            meta["rating"] = meta["rating"] or _rating_from_tags(easy_tags)

    if meta["artist"] is None and tags is not None:
        meta["artist"] = _text(tags.get("artist")) or _text(tags.get("ARTIST"))

    meta["title"] = meta["title"] or path.stem
    return meta


def import_music_folder(
    folder_path: str | Path,
    db_path: str,
    *,
    block_without_rating: bool = True,
    limit: int | None = None,
) -> MusicImportStats:
    """Scan a folder recursively and upsert tracks by (title, artist, album)."""
    root = Path(folder_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Music folder not found: {root}")

    stats = MusicImportStats()
    entries: list[dict[str, Any]] = []

    for directory, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for filename in sorted(filenames):
            if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                meta = extract_metadata(Path(directory) / filename)
            except Exception as exc:
                stats.errors += 1
                print(f"  ! cannot read {filename}: {exc}")
                continue

            if block_without_rating and meta.get("rating") is None:
                stats.skipped += 1
                continue

            entries.append(meta)
            if limit and len(entries) >= limit:
                break
        if limit and len(entries) >= limit:
            break

    if not entries:
        return stats

    with get_session(str(db_path)) as session:
        for meta in entries:
            filters = {
                "title": (meta.get("title") or "Unknown title").strip(),
                "artist": _strip(meta.get("artist")),
                "album": _strip(meta.get("album")),
            }
            values: dict[str, Any] = {}
            if meta.get("rating") is not None:
                values["rating"] = round(float(meta["rating"]), 2)
            if meta.get("art"):
                values["album_art"] = meta["art"]

            _, created = crud.upsert_by(session, Music, filters, **values)
            if created:
                stats.added += 1
            else:
                stats.updated += 1

    return stats
