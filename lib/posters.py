"""Helpers for finding and removing poster files that the database no longer uses."""
from __future__ import annotations

from pathlib import Path

from lib.db.models import Movie
from lib.db.session import get_session

POSTER_SUBDIR = ("images", "movies")


def _as_posix(value: str | None) -> str | None:
    if not value:
        return None
    return str(value).replace("\\", "/").strip() or None


def referenced_poster_paths(db_path: str | Path) -> set[str]:
    """Return every non-empty ``movies.poster_path`` in normalized form."""
    with get_session(str(db_path)) as session:
        rows = (
            session.query(Movie.poster_path)
            .filter(Movie.poster_path.isnot(None))
            .all()
        )
    return {path for (value,) in rows if (path := _as_posix(value))}


def _poster_root(site_folder: str | Path) -> Path:
    return Path(site_folder).joinpath(*POSTER_SUBDIR).resolve()


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def prune_orphan_posters(
    db_path: str | Path,
    site_folder: str | Path,
    *,
    only: set[str] | None = None,
    dry_run: bool = False,
) -> tuple[list[str], int]:
    """Delete files under ``images/movies`` that no movie references.

    Args:
        only: optional set of normalized paths to consider (used after a sync so
            that only posters of deleted movies are touched).
        dry_run: report the files without deleting anything.

    Returns:
        ``(relative_paths, count)`` for the files deleted (or that would be).
    """
    root = _poster_root(site_folder)
    if not root.is_dir():
        return [], 0

    referenced = referenced_poster_paths(db_path)
    allowed: set[str] | None
    if only is None:
        allowed = None
    else:
        allowed = {path for value in only if (path := _as_posix(value))}
        if not allowed:
            return [], 0

    candidates: list[str] = []
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        resolved = file_path.resolve()
        if not _is_inside(resolved, root):
            continue
        relative = resolved.relative_to(root.parent.parent).as_posix()
        if allowed is not None and relative not in allowed:
            continue
        if relative in referenced:
            continue
        candidates.append(relative)
        if not dry_run:
            resolved.unlink()

    return candidates, len(candidates)
