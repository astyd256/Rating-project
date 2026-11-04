"""Import rated movies from IMDb CSV exports and store posters on disk.

Poster files live in ``<site_folder>/images/movies`` and the database keeps the
path relative to the site folder (``images/movies/<file>``), so the generated
HTML can reference them directly.

With ``sync=True`` the CSV is treated as the full desired list of movies:
rows present in the file are inserted/updated, rows missing from it are
deleted, and posters of deleted rows are removed from disk. Music is never
touched.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

import requests

from lib.config import Config
from lib.db import crud
from lib.db.backup import backup_database
from lib.db.models import Movie
from lib.db.session import get_session
from lib.media import guess_image_mime, image_extension, slugify, unique_filename
from lib.posters import prune_orphan_posters, referenced_poster_paths

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

# Refuse a sync that would delete more than half of the movie table. This
# catches truncated or wrong CSV files; --force overrides it.
MAX_DELETE_RATIO = 0.5


@dataclass
class ImportStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    csv_rows: int = 0
    posters_downloaded: int = 0
    deleted: int = 0
    deleted_titles: list[str] = field(default_factory=list)
    posters_deleted: int = 0
    poster_files: list[str] = field(default_factory=list)
    backup_path: str | None = None
    dry_run: bool = False

    @property
    def total(self) -> int:
        return self.inserted + self.updated + self.unchanged + self.deleted


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


def _poster_relative(value: Any) -> str | None:
    if not value:
        return None
    return str(value).replace("\\", "/").strip() or None


def _movie_label(movie: Movie) -> str:
    year = f" ({movie.year})" if movie.year else ""
    const = f" [{movie.imdb_const}]" if movie.imdb_const else ""
    return f"{movie.title}{year}{const}"


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


def _plan_deletions(existing: list[Movie], rows: list[dict[str, Any]]) -> list[Movie]:
    """Return movies that are not part of the CSV (matched by IMDb id)."""
    csv_consts = {
        payload["imdb_const"]
        for payload in rows
        if payload.get("imdb_const")
    }
    # Rows without an IMDb id are kept: deleting them by title+year would be
    # guesswork. All rows imported by this tool carry an id.
    return [
        movie
        for movie in existing
        if movie.imdb_const and movie.imdb_const not in csv_consts
    ]


def import_movies_csv(
    file_path: str | Path,
    config: Config,
    *,
    download_posters: bool = True,
    limit: int | None = None,
    sync: bool = False,
    dry_run: bool = False,
    force: bool = False,
) -> ImportStats:
    """Upsert movies from an IMDb CSV export.

    Args:
        sync: treat the CSV as the authoritative movie list and delete rows
            that are missing from it.
        dry_run: only compute the sync plan; no database or file changes.
        force: allow a sync that deletes more than ``MAX_DELETE_RATIO`` of the
            table (protection against truncated CSV files).
    """
    if dry_run and not sync:
        raise ValueError("dry_run requires sync=True")

    stats = ImportStats(dry_run=dry_run)
    rows = read_csv_movies(file_path, limit=limit)
    stats.csv_rows = len(rows)
    if not rows:
        return stats

    image_dir = config.movies_image_dir
    http = requests.Session()
    http.headers.update({"User-Agent": USER_AGENT})

    doomed: list[Movie] = []
    existing_count = 0
    if sync:
        with get_session(str(config.db_path)) as session:
            existing = session.query(Movie).all()
        existing_count = len(existing)
        doomed = _plan_deletions(existing, rows)
        if doomed and not force and len(doomed) > max(1, int(existing_count * MAX_DELETE_RATIO)):
            http.close()
            raise RuntimeError(
                f"Refusing to delete {len(doomed)} of {existing_count} movies "
                f"(more than {int(MAX_DELETE_RATIO * 100)}%): check the CSV, "
                "or pass --force if this is intentional."
            )
        stats.deleted = len(doomed)
        stats.deleted_titles = [_movie_label(movie) for movie in doomed]
        deleted_posters = [
            path for movie in doomed if (path := _poster_relative(movie.poster_path))
        ]

        if dry_run:
            referenced = referenced_poster_paths(config.db_path)
            still_referenced = referenced - set(deleted_posters)
            pending = [
                path
                for path in sorted(set(deleted_posters))
                if path not in still_referenced
                and (config.site_folder / path).is_file()
            ]
            stats.posters_deleted = len(pending)
            stats.poster_files = pending
            http.close()
            return stats

        if doomed:
            stats.backup_path = str(backup_database(config.db_path))
    else:
        deleted_posters = []

    touched: set[int] = set()
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

            touched.add(record.id)
            poster_added = False
            if download_posters:
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

        if sync and doomed:
            delete_ids = [movie.id for movie in doomed if movie.id not in touched]
            if delete_ids:
                deleted_movies = (
                    session.query(Movie).filter(Movie.id.in_(delete_ids)).all()
                )
                stats.deleted = len(deleted_movies)
                stats.deleted_titles = [_movie_label(movie) for movie in deleted_movies]
                deleted_posters = [
                    path
                    for movie in deleted_movies
                    if (path := _poster_relative(movie.poster_path))
                ]
                for movie in deleted_movies:
                    session.delete(movie)
                session.flush()

    http.close()

    if sync and deleted_posters:
        pruned, count = prune_orphan_posters(
            config.db_path,
            config.site_folder,
            only=set(deleted_posters),
        )
        stats.posters_deleted = count
        stats.poster_files = pruned

    return stats
