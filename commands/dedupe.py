"""Merge movies that are exact duplicates (same title and year)."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from lib.config import Config
from lib.db.models import Movie
from lib.db.session import get_session

_MERGE_FIELDS = (
    "poster_url",
    "poster_path",
    "year",
    "imdb_const",
    "imdb_rating",
    "imdb_votes",
    "tomatoes_rating",
    "rating",
    "title_type",
    "genres",
    "directors",
)


def _poster_on_disk(movie: Movie, site_folder) -> bool:
    return bool(movie.poster_path) and (site_folder / movie.poster_path).is_file()


def _score(movie: Movie, site_folder) -> tuple:
    filled = sum(1 for field in _MERGE_FIELDS if getattr(movie, field) not in (None, ""))
    return (_poster_on_disk(movie, site_folder), movie.poster_path is not None, filled, -movie.id)


def _key(movie: Movie) -> tuple[str, Any]:
    return ((movie.title or "").strip().casefold(), movie.year)


def main(config: Config, *, dry_run: bool = False) -> int:
    if not config.db_path.is_file():
        print(f"Database not found: {config.db_path}")
        return 2

    groups: defaultdict[tuple, list[Movie]] = defaultdict(list)
    with get_session(str(config.db_path)) as session:
        for movie in session.query(Movie).order_by(Movie.id).all():
            groups[_key(movie)].append(movie)

        merged_groups = 0
        removed = 0
        conflicts = 0

        for (title, year), group in groups.items():
            if len(group) < 2:
                continue

            imdb_ids = {movie.imdb_const for movie in group if movie.imdb_const}
            if len(imdb_ids) > 1:
                conflicts += 1
                print(f"  ! skipped '{title}' ({year}): {len(imdb_ids)} different IMDb ids")
                continue

            keeper = max(group, key=lambda movie: _score(movie, config.site_folder))
            for duplicate in group:
                if duplicate is keeper:
                    continue
                for field in _MERGE_FIELDS:
                    if getattr(keeper, field) in (None, "") and getattr(duplicate, field) not in (None, ""):
                        setattr(keeper, field, getattr(duplicate, field))
                if not dry_run:
                    session.delete(duplicate)
                removed += 1

            merged_groups += 1
            print(f"  - '{title}' ({year}): kept id={keeper.id}, removed {len(group) - 1} duplicate(s)")

    prefix = "[dry-run] " if dry_run else ""
    print(
        f"{prefix}Dedup: {merged_groups} group(s) merged, {removed} row(s) removed, "
        f"{conflicts} conflict(s) left untouched"
    )
    return 0
