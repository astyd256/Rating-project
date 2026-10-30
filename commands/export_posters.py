"""Move legacy ``movies.poster_blob`` data into files under images/movies."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text, update

from lib.config import Config
from lib.db.engine import get_engine
from lib.db.models import Movie
from lib.db.session import get_session
from lib.media import image_extension, slugify, unique_filename


def _normalise_poster_path(value: Any, site_folder: Path) -> str | None:
    """Turn stored paths into ``images/movies/<file>`` form."""
    if value is None:
        return None
    path = str(value).replace("\\", "/").strip()
    if not path:
        return None
    while path.startswith("./"):
        path = path[2:]

    marker = "images/"
    index = path.find(marker)
    if index > 0:
        path = path[index:]
    elif path.startswith(site_folder.name + "/"):
        path = path[len(site_folder.name) + 1:]
    return path or None


def _base_name(title: str | None, year: Any) -> str:
    name = f"{title} {year}" if year else (title or "poster")
    return slugify(name)


def main(config: Config, *, dry_run: bool = False) -> int:
    if not config.db_path.is_file():
        print(f"Database not found: {config.db_path}")
        return 2

    engine = get_engine(str(config.db_path))
    columns = {column["name"] for column in inspect(engine).get_columns("movies")}
    has_blob = "poster_blob" in columns

    select_columns = "id, title, year, imdb_const, poster_path"
    if has_blob:
        select_columns += ", poster_blob"
    query = f"SELECT {select_columns} FROM movies ORDER BY id"

    image_dir = config.movies_image_dir
    stats = {"exported": 0, "kept": 0, "repaired": 0, "cleared": 0, "missing": 0}

    with get_session(str(config.db_path)) as session:
        rows = session.execute(text(query)).all()
        for row in rows:
            data = row._mapping
            movie_id = data["id"]
            current = _normalise_poster_path(data["poster_path"], config.site_folder)

            if current is not None and (config.site_folder / current).is_file():
                if current != data["poster_path"]:
                    if not dry_run:
                        session.execute(
                            update(Movie).where(Movie.id == movie_id).values(poster_path=current)
                        )
                    stats["repaired"] += 1
                else:
                    stats["kept"] += 1
                continue

            blob = bytes(data["poster_blob"]) if has_blob and data["poster_blob"] else None
            if blob is None:
                if data["poster_path"] and not dry_run:
                    session.execute(
                        update(Movie).where(Movie.id == movie_id).values(poster_path=None)
                    )
                stats["cleared" if data["poster_path"] else "missing"] += 1
                continue

            base_name = _base_name(data["title"], data["year"])
            filename = unique_filename(
                image_dir, base_name, image_extension(blob), suffix=data["imdb_const"]
            )
            if not dry_run:
                image_dir.mkdir(parents=True, exist_ok=True)
                (image_dir / filename).write_bytes(blob)
                session.execute(
                    update(Movie)
                    .where(Movie.id == movie_id)
                    .values(poster_path=f"images/movies/{filename}")
                )
            stats["exported"] += 1

    prefix = "[dry-run] " if dry_run else ""
    print(
        f"{prefix}Posters: {stats['exported']} exported from blobs, "
        f"{stats['repaired']} paths repaired, {stats['kept']} already on disk, "
        f"{stats['cleared']} broken paths cleared, {stats['missing']} without an image"
    )
    return 0
