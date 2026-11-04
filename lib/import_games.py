"""Import rated games from a Yamtrack CSV export."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import requests

from lib.config import Config
from lib.db import crud
from lib.db.models import Game
from lib.db.session import get_session
from lib.import_movies import download_poster
from lib.media import slugify

USER_AGENT = "rating-project/1.0"


@dataclass
class GameImportStats:
    added: int = 0
    updated: int = 0
    posters: int = 0


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().strip('"')
    return text or None


def _to_float(value: Any) -> float | None:
    text = _clean(value)
    if text is None:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _poster_ok(game: Game, config: Config) -> bool:
    return bool(game.poster_path) and (config.site_folder / game.poster_path).is_file()


def _rows(path: str | Path) -> Iterator[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            if (_clean(raw.get("media_type")) or "game").lower() != "game":
                continue
            rating = _to_float(raw.get("score"))
            if rating is None or rating <= 0:
                continue
            external_id = _clean(raw.get("media_id"))
            title = _clean(raw.get("title"))
            if not external_id or not title:
                continue
            yield {
                "external_id": external_id,
                "title": title,
                "rating": round(rating, 2),
                "poster_url": _clean(raw.get("image")),
            }


def import_games_csv(
    path: str | Path,
    config: Config,
    *,
    download_posters: bool = True,
) -> GameImportStats:
    stats = GameImportStats()
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    with get_session(str(config.db_path)) as session:
        for index, payload in enumerate(_rows(path), start=1):
            game = crud.find_one(session, Game, external_id=payload["external_id"])
            created = game is None
            if created:
                game = crud.create_record(
                    session,
                    Game,
                    external_id=payload["external_id"],
                    title=payload["title"],
                    rating=payload["rating"],
                    poster_url=payload["poster_url"],
                )
                stats.added += 1
            else:
                changes = {
                    key: payload[key]
                    for key in ("title", "rating", "poster_url")
                    if payload[key] is not None and getattr(game, key) != payload[key]
                }
                if changes:
                    crud.update_record(session, game, **changes)
                stats.updated += 1

            if (
                download_posters
                and payload["poster_url"]
                and not _poster_ok(game, config)
            ):
                downloaded = download_poster(
                    payload["poster_url"],
                    config.games_image_dir,
                    slugify(f"{game.title} {game.external_id}"),
                    suffix=game.external_id,
                    http=http,
                )
                if downloaded is not None:
                    relative = downloaded.relative_to(config.site_folder).as_posix()
                    crud.update_record(session, game, poster_path=relative)
                    stats.posters += 1
            session.flush()
            if index % 50 == 0:
                session.commit()
                print(f"Games: {index} rows", flush=True)

    http.close()
    return stats
