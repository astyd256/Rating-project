"""Import rated movies from IMDb CSV exports and store posters on disk.

Poster files live in ``<site_folder>/images/movies`` and the database keeps the
path relative to the site folder (``images/movies/<file>``), so the generated
HTML can reference them directly.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import requests
from sqlalchemy import inspect, text

from lib.config import Config
from lib.db import crud
from lib.db.engine import get_engine
from lib.db.models import Movie
from lib.db.session import get_session
from lib.media import guess_image_mime, image_extension, slugify, unique_filename

USER_AGENT = "rating-project/1.0"
OMDB_TYPES = {
    "movie": "movie",
    "tv movie": "movie",
    "video": "movie",
    "series": "series",
    "tv series": "series",
    "tv mini series": "series",
    "episode": "episode",
    "tv episode": "episode",
    "game": "game",
    "video game": "game",
}
_EMPTY_VALUES = {"", "n/a", "na", "nan", "none", "null", "-"}


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    posters_downloaded: int = 0

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip().strip('"').strip()
    if text_value.lower() in _EMPTY_VALUES:
        return None
    return text_value


def _first(raw: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        if key in raw:
            value = _clean(raw.get(key))
            if value is not None:
                return value
    return None


def _to_int(value: Any) -> int | None:
    text_value = _clean(value)
    if text_value is None:
        return None
    try:
        return int(float(text_value.replace(",", "")))
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    text_value = _clean(value)
    if text_value is None:
        return None
    try:
        return float(text_value.replace(",", "."))
    except ValueError:
        return None


def _normalise_imdb_const(value: str | None) -> str | None:
    if value is None:
        return None
    const = value.strip().lower()
    if not const:
        return None
    if const.isdigit():
        const = f"tt{const}"
    return const


def parse_csv_row(raw: Mapping[str, Any], data_type: str = "movie") -> dict[str, Any] | None:
    """Convert one IMDb CSV row into a ``Movie`` payload.

    Returns ``None`` for rows that cannot be imported (no title / wrong type).
    """
    if data_type != "movie":
        return None

    title = _first(raw, "Title", "title")
    if not title:
        return None

    return {
        "title": title,
        "year": _to_int(_first(raw, "Year", "year")),
        "imdb_const": _normalise_imdb_const(_first(raw, "Const", "const", "tconst")),
        "imdb_rating": _to_float(_first(raw, "IMDb Rating", "imdb_rating")),
        "imdb_votes": _to_int(_first(raw, "Num Votes", "num_votes", "votes")),
        "rating": _to_int(_first(raw, "Your Rating", "your_rating", "rating")),
        "title_type": _first(raw, "Title Type", "title_type"),
        "genres": _first(raw, "Genres", "genres"),
        "directors": _first(raw, "Directors", "directors"),
    }


def read_csv_movies(file_path: str | Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Read an IMDb CSV export into a list of movie payloads."""
    rows: list[dict[str, Any]] = []
    with Path(file_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for raw in csv.DictReader(handle):
            if not any(_clean(value) for value in raw.values()):
                continue
            payload = parse_csv_row(raw, "movie")
            if payload is None:
                continue
            rows.append(payload)
            if limit and len(rows) >= limit:
                break
    return rows


def _omdb_type(title_type: str | None) -> str | None:
    if not title_type:
        return None
    return OMDB_TYPES.get(title_type.strip().lower())


def fetch_poster_url(
    config: Config,
    *,
    imdb_const: str | None = None,
    title: str | None = None,
    year: int | None = None,
    title_type: str | None = None,
    http: requests.Session | None = None,
) -> str | None:
    """Ask OMDB for a poster URL, preferring the exact IMDb id."""
    if not config.omdb_api_key:
        return None

    attempts: list[dict[str, str]] = []
    if imdb_const:
        attempts.append({"i": imdb_const})
    if title:
        base: dict[str, str] = {"t": title}
        if year:
            base["y"] = str(year)
        omdb_type = _omdb_type(title_type)
        if omdb_type:
            base["type"] = omdb_type
        attempts.append(dict(base))
        attempts.append({key: value for key, value in base.items() if key != "type"})
        attempts.append({key: value for key, value in base.items() if key not in {"type", "y"}})

    client = http or requests
    for attempt in attempts:
        params = {**attempt, "apikey": config.omdb_api_key}
        try:
            response = client.get(config.omdb_url, params=params, timeout=20)
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            continue
        if data.get("Response") != "True":
            continue
        poster = (data.get("Poster") or "").strip()
        if poster and poster.lower() not in _EMPTY_VALUES:
            return poster
    return None


def download_poster(
    url: str,
    directory: Path,
    base_name: str,
    *,
    suffix: str | None = None,
    http: requests.Session | None = None,
) -> Path | None:
    """Download an image into ``directory`` and return the written path."""
    client = http or requests
    try:
        response = client.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ! poster download failed ({base_name}): {exc}")
        return None

    data = response.content
    if not data or guess_image_mime(data) is None:
        print(f"  ! poster is not an image ({base_name})")
        return None

    directory.mkdir(parents=True, exist_ok=True)
    filename = unique_filename(directory, base_name, image_extension(data), suffix=suffix)
    target = directory / filename
    target.write_bytes(data)
    return target


def _poster_base_name(record: Movie) -> str:
    if record.year:
        return slugify(f"{record.title} {record.year}")
    return slugify(record.title)


def _is_http_url(value: Any) -> bool:
    if not value:
        return False
    return str(value).strip().lower().startswith(("http://", "https://"))


def _poster_path(record: Movie, config: Config) -> str | None:
    if not record.poster_path:
        return None
    path = config.site_folder / record.poster_path
    if path.is_file():
        return record.poster_path
    return None


def _find_movie(session, payload: Mapping[str, Any]) -> Movie | None:
    imdb_const = payload.get("imdb_const")
    if imdb_const:
        record = crud.find_one(session, Movie, imdb_const=imdb_const)
        if record is not None:
            return record

    title = payload.get("title")
    if not title:
        return None
    query = session.query(Movie).filter(Movie.title == title)
    year = payload.get("year")
    query = query.filter(Movie.year.is_(None)) if year is None else query.filter(Movie.year == year)
    return query.order_by(Movie.id).first()


def _ensure_poster(
    session,
    record: Movie,
    config: Config,
    http: requests.Session,
    image_dir: Path,
    *,
    allow_download: bool,
) -> bool:
    """Make sure the movie has a poster file, downloading it when allowed."""
    if _poster_path(record, config):
        return False
    if not allow_download or not config.omdb_api_key:
        return False

    # Old imports stored the literal string "None" when no poster was found.
    if record.poster_url and not _is_http_url(record.poster_url):
        crud.update_record(session, record, poster_url=None)

    candidates: list[str] = []
    if _is_http_url(record.poster_url):
        candidates.append(str(record.poster_url).strip())

    fetched = fetch_poster_url(
        config,
        imdb_const=record.imdb_const,
        title=record.title,
        year=record.year,
        title_type=record.title_type,
        http=http,
    )
    if fetched and fetched not in candidates:
        candidates.append(fetched)

    if not candidates:
        return False

    for url in candidates:
        downloaded = download_poster(
            url,
            image_dir,
            _poster_base_name(record),
            suffix=record.imdb_const or str(record.id),
            http=http,
        )
        if downloaded is None:
            continue
        relative = downloaded.relative_to(config.site_folder).as_posix()
        crud.update_record(session, record, poster_path=relative, poster_url=url)
        return True
    return False


def _ids_with_blob(db_path: str) -> set[int]:
    """Return movie ids whose legacy ``poster_blob`` column has data."""
    engine = get_engine(db_path)
    columns = {column["name"] for column in inspect(engine).get_columns("movies")}
    if "poster_blob" not in columns:
        return set()
    with engine.connect() as connection:
        rows = connection.execute(text("SELECT id FROM movies WHERE poster_blob IS NOT NULL"))
        return {row[0] for row in rows}


def import_movies_csv(
    file_path: str | Path,
    config: Config,
    *,
    download_posters: bool = True,
    limit: int | None = None,
) -> ImportStats:
    """Upsert movies from an IMDb CSV export."""
    stats = ImportStats()
    rows = read_csv_movies(file_path, limit=limit)
    if not rows:
        return stats

    image_dir = config.movies_image_dir
    blob_ids = _ids_with_blob(str(config.db_path))
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    with get_session(str(config.db_path)) as session:
        for payload in rows:
            record = _find_movie(session, payload)
            created = record is None
            if created:
                record = crud.create_record(session, Movie, **payload)
                stats.inserted += 1
                changes: dict[str, Any] = {}
            else:
                changes = {
                    key: value
                    for key, value in payload.items()
                    if value is not None and getattr(record, key) != value
                }
                if changes:
                    crud.update_record(session, record, **changes)

            has_blob = record.id in blob_ids
            poster_added = False
            if download_posters and not has_blob:
                poster_added = _ensure_poster(
                    session,
                    record,
                    config,
                    http,
                    image_dir,
                    allow_download=True,
                )
                if poster_added:
                    stats.posters_downloaded += 1

            if not created:
                if changes or poster_added:
                    stats.updated += 1
                else:
                    stats.unchanged += 1
            session.flush()

    http.close()
    return stats
