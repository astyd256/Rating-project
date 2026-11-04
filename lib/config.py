"""Application configuration loaded from .env and CLI overrides.

All paths are resolved against the project root, so commands behave the same
no matter which directory they are started from.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    project_root: Path
    db_path: Path
    site_folder: Path
    html_path: Path
    omdb_api_key: str | None
    omdb_url: str
    lastfm_user: str | None = None
    lastfm_api_key: str | None = None
    lastfm_refresh_seconds: int = 60

    @property
    def movies_image_dir(self) -> Path:
        return self.site_folder / "images" / "movies"

    @property
    def games_image_dir(self) -> Path:
        return self.site_folder / "images" / "games"

    @property
    def anime_image_dir(self) -> Path:
        return self.site_folder / "images" / "anime"

    @property
    def manga_image_dir(self) -> Path:
        return self.site_folder / "images" / "manga"


def _resolve(value: str | os.PathLike[str], base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def load_config(
    *,
    db_path: str | None = None,
    site_folder: str | None = None,
    html_path: str | None = None,
) -> Config:
    load_dotenv(PROJECT_ROOT / ".env")

    db_value = db_path or os.getenv("DB_PATH") or "ratings.db"
    site_value = site_folder or os.getenv("SITE_FOLDER") or "personal-site"

    resolved_site = _resolve(site_value, PROJECT_ROOT)
    html_value = html_path or os.getenv("HTML_PATH") or str(resolved_site / "index.html")

    refresh_raw = (os.getenv("LASTFM_REFRESH_SECONDS") or "60").strip()
    try:
        refresh_seconds = max(30, int(refresh_raw))
    except ValueError:
        refresh_seconds = 60

    return Config(
        project_root=PROJECT_ROOT,
        db_path=_resolve(db_value, PROJECT_ROOT),
        site_folder=resolved_site,
        html_path=_resolve(html_value, PROJECT_ROOT),
        omdb_api_key=(os.getenv("OMDB_API_KEY") or "").strip() or None,
        omdb_url=(os.getenv("OMDB_URL") or "https://www.omdbapi.com/").strip(),
        lastfm_user=(os.getenv("LASTFM_USER") or "").strip() or None,
        lastfm_api_key=(os.getenv("LASTFM_API_KEY") or "").strip() or None,
        lastfm_refresh_seconds=refresh_seconds,
    )
