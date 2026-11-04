"""Import anime and manga ratings from MyAnimeList-format XML exports.

Poster images are looked up on Jikan (free, no API key, rate limited) only when
a title does not have a local poster yet.
"""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

from lib.config import Config
from lib.db import crud
from lib.db.models import Anime, Manga
from lib.db.session import get_session
from lib.import_movies import download_poster
from lib.media import slugify

USER_AGENT = "rating-project/1.0"
JIKAN_URL = "https://api.jikan.moe/v4"
SHIKIMORI_URL = "https://shikimori.io/api"
ANILIST_URL = "https://graphql.anilist.co"
REQUEST_DELAY = 0.7


@dataclass
class MalImportStats:
    added: int = 0
    updated: int = 0
    posters: int = 0


def _text(node: ET.Element, tag: str) -> str | None:
    child = node.find(tag)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _anime_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    root = ET.parse(path).getroot()
    for node in root.findall(".//anime"):
        mal_id = _to_int(_text(node, "series_animedb_id"))
        title = _text(node, "series_title")
        rating = _to_float(_text(node, "my_score"))
        if not mal_id or not title or rating is None or rating <= 0:
            continue
        yield {
            "mal_id": mal_id,
            "title": title,
            "title_type": _text(node, "series_type"),
            "episodes": _to_int(_text(node, "series_episodes")),
            "rating": round(rating, 2),
        }


def _manga_rows(path: str | Path) -> Iterator[dict[str, Any]]:
    root = ET.parse(path).getroot()
    for node in root.findall(".//manga"):
        mal_id = _to_int(_text(node, "manga_mangadb_id"))
        title = _text(node, "series_title")
        rating = _to_float(_text(node, "my_score"))
        if not mal_id or not title or rating is None or rating <= 0:
            continue
        yield {
            "mal_id": mal_id,
            "title": title,
            "title_type": _text(node, "series_type"),
            "chapters": _to_int(_text(node, "series_chapters")),
            "volumes": _to_int(_text(node, "series_volumes")),
            "rating": round(rating, 2),
        }


def _poster_ok(record: Any, config: Config) -> bool:
    return bool(record.poster_path) and (config.site_folder / record.poster_path).is_file()


def _shikimori_poster_url(kind: str, mal_id: int, http: requests.Session) -> str | None:
    """Return the Shikimori cover URL; their ids match MAL ids."""
    try:
        response = http.get(
            f"{SHIKIMORI_URL}/{kind}s/{mal_id}",
            timeout=8,
        )
    except requests.RequestException:
        return None

    time.sleep(REQUEST_DELAY)
    if not response.ok:
        return None
    try:
        data = response.json() or {}
    except ValueError:
        return None
    image = str((data.get("image") or {}).get("original") or "")
    if not image or "missing" in image.lower():
        return None
    return image if image.startswith("http") else f"https://shikimori.io{image}"


def _jikan_poster_url(kind: str, mal_id: int, http: requests.Session) -> str | None:
    """Return the Jikan cover URL for ``kind`` ('anime' or 'manga').

    A single attempt only: the caller stops the whole poster phase after a few
    consecutive failures, so a rate-limited API never stalls the import.
    """
    try:
        response = http.get(f"{JIKAN_URL}/{kind}/{mal_id}", timeout=5)
    except requests.RequestException:
        return None

    time.sleep(REQUEST_DELAY)
    if not response.ok:
        return None
    try:
        data = (response.json() or {}).get("data") or {}
    except ValueError:
        return None
    images = (data.get("images") or {}).get("jpg") or {}
    return images.get("large_image_url") or images.get("image_url")


def _anilist_poster_url(kind: str, mal_id: int, http: requests.Session) -> str | None:
    """Last-resort cover lookup on AniList GraphQL (no API key)."""
    media_type = "ANIME" if kind == "anime" else "MANGA"
    query = (
        "query ($idMal: Int, $type: MediaType) {"
        " Media(idMal: $idMal, type: $type) { coverImage { extraLarge large } }"
        "}"
    )
    try:
        response = http.post(
            ANILIST_URL,
            json={"query": query, "variables": {"idMal": mal_id, "type": media_type}},
            timeout=8,
        )
    except requests.RequestException:
        return None

    time.sleep(REQUEST_DELAY)
    if not response.ok:
        return None
    try:
        media = ((response.json() or {}).get("data") or {}).get("Media") or {}
    except ValueError:
        return None
    cover = media.get("coverImage") or {}
    return cover.get("extraLarge") or cover.get("large")


def _jikan_reachable(http: requests.Session) -> bool:
    try:
        response = http.get(f"{JIKAN_URL}/anime/1", timeout=5)
    except requests.RequestException:
        return False
    return response.status_code < 500


def _cover_sources(http: requests.Session) -> dict[str, bool]:
    shikimori = False
    try:
        response = http.get(f"{SHIKIMORI_URL}/animes/121", timeout=8)
        shikimori = response.status_code < 500
    except requests.RequestException:
        pass

    jikan = False
    try:
        response = http.get(f"{JIKAN_URL}/anime/1", timeout=5)
        jikan = response.status_code < 500
    except requests.RequestException:
        pass

    # AniList has no cheap preflight; a failed call is handled by the normal
    # consecutive-failure stop in the cover phase.
    return {"shikimori": shikimori, "jikan": jikan, "anilist": True}


def _cover_url(
    kind: str,
    mal_id: int,
    http: requests.Session,
    sources: dict[str, bool],
) -> str | None:
    if sources.get("shikimori"):
        url = _shikimori_poster_url(kind, mal_id, http)
        if url:
            return url
    if sources.get("jikan"):
        url = _jikan_poster_url(kind, mal_id, http)
        if url:
            return url
    if sources.get("anilist"):
        return _anilist_poster_url(kind, mal_id, http)
    return None


def import_mal_xml(
    path: str | Path,
    config: Config,
    kind: str,
    *,
    download_posters: bool = True,
) -> MalImportStats:
    if kind not in {"anime", "manga"}:
        raise ValueError(f"Unsupported kind: {kind}")

    stats = MalImportStats()
    model = Anime if kind == "anime" else Manga
    rows = list(_anime_rows(path) if kind == "anime" else _manga_rows(path))
    image_dir = config.anime_image_dir if kind == "anime" else config.manga_image_dir
    label = "Anime" if kind == "anime" else "Manga"
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    with get_session(str(config.db_path)) as session:
        # Phase 1: database rows. Committed in batches, so a network failure or
        # an interrupted run never loses the whole import.
        for index, payload in enumerate(rows, start=1):
            record = crud.find_one(session, model, mal_id=payload["mal_id"])
            created = record is None
            if created:
                values = {
                    "mal_id": payload["mal_id"],
                    "title": payload["title"],
                    "title_type": payload.get("title_type"),
                    "rating": payload["rating"],
                }
                if kind == "anime":
                    values["episodes"] = payload.get("episodes")
                else:
                    values["chapters"] = payload.get("chapters")
                    values["volumes"] = payload.get("volumes")
                crud.create_record(session, model, **values)
                stats.added += 1
            else:
                changes = {
                    key: payload[key]
                    for key in ("title", "title_type", "episodes", "chapters", "volumes", "rating")
                    if key in payload
                    and payload[key] is not None
                    and getattr(record, key) != payload[key]
                }
                if changes:
                    crud.update_record(session, record, **changes)
                stats.updated += 1

            if index % 50 == 0:
                session.commit()
                print(f"{label}: {index}/{len(rows)} rows", flush=True)
        session.commit()
        print(f"{label}: {len(rows)} rows imported", flush=True)

        if not download_posters:
            http.close()
            return stats

        sources = _cover_sources(http)
        if not any(sources.values()):
            print(f"{label}: cover APIs are unreachable, covers skipped", flush=True)
            http.close()
            return stats
        print(
            f"{label}: cover sources "
            + ", ".join(name for name, ok in sources.items() if ok),
            flush=True,
        )

        # Phase 2: covers one by one. A few consecutive failures mean the API
        # is rate limited; stop the phase and keep the imported rows.
        targets = (
            session.query(model)
            .filter(model.poster_path.is_(None))
            .order_by(model.id)
            .all()
        )
        consecutive_failures = 0
        for index, record in enumerate(targets, start=1):
            poster_url = record.poster_url or _cover_url(
                kind, record.mal_id, http, sources
            )
            if not poster_url:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(
                        f"{label}: Jikan is rate limited, stopping covers "
                        f"({index - 1}/{len(targets)} tried)",
                        flush=True,
                    )
                    break
                continue

            downloaded = download_poster(
                poster_url,
                image_dir,
                slugify(f"{record.title} {record.mal_id}"),
                suffix=str(record.mal_id),
                http=http,
            )
            if downloaded is None:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(f"{label}: too many cover failures, stopping", flush=True)
                    break
                continue

            consecutive_failures = 0
            relative = downloaded.relative_to(config.site_folder).as_posix()
            crud.update_record(
                session,
                record,
                poster_url=poster_url,
                poster_path=relative,
            )
            session.commit()
            stats.posters += 1
            if index % 10 == 0:
                print(
                    f"{label}: covers {index}/{len(targets)}",
                    flush=True,
                )

    http.close()
    return stats
