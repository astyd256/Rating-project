"""HTML card renderers for movies, music, games, anime and manga."""
from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from lib.db.models import Anime, Manga, Movie, Music


def format_number(value: Any) -> str | None:
    if value is None:
        return None
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def poster_src(record: Any, html_dir: Path) -> str | None:
    """Return the poster path if the file exists next to the generated page."""
    if not record.poster_path:
        return None
    relative = Path(record.poster_path)
    if relative.is_absolute():
        return None
    if (html_dir / relative).is_file():
        return record.poster_path
    return None


def _imdb_url(movie: Movie) -> str:
    """Build the IMDb title URL, falling back to a search for rows without an id."""
    if movie.imdb_const:
        return f"https://www.imdb.com/title/{quote(movie.imdb_const, safe='')}/"
    query = quote(f"{movie.title or ''} {movie.year or ''}".strip(), safe="")
    return f"https://www.imdb.com/find/?q={query}"


def movie_card(movie: Movie, html_dir: Path) -> str:
    title = escape(movie.title or "", quote=True)
    year = f" ({movie.year})" if movie.year else ""
    imdb_url = escape(_imdb_url(movie), quote=True)
    heading = (
        f'<a href="{imdb_url}" target="_blank" rel="noopener noreferrer">'
        f"{title}{year}</a>"
    )
    lines = ['    <article class="card">', f"      <h3>{heading}</h3>"]

    poster = poster_src(movie, html_dir)
    if poster:
        lines.append(
            f'      <a href="{imdb_url}" target="_blank" rel="noopener noreferrer">'
            f'<img class="poster" src="{escape(poster, quote=True)}" '
            f'alt="{title} poster" loading="lazy" decoding="async"> </a>'
        )
    else:
        lines.append('      <div class="poster poster--empty" aria-hidden="true">no poster</div>')

    rating = format_number(movie.rating)
    if rating:
        lines.append(f"      <p><b>My rating:</b> {rating} / 10</p>")
    imdb = format_number(movie.imdb_rating)
    if imdb:
        lines.append(f"      <p><b>IMDb:</b> {imdb} / 10</p>")
    if movie.title_type:
        lines.append(f'      <p class="muted">{escape(movie.title_type, quote=True)}</p>')
    if movie.genres:
        lines.append(f'      <p class="muted">{escape(movie.genres, quote=True)}</p>')

    lines.append("    </article>")
    return "\n".join(lines)


def music_card(track: Music, html_dir: Path) -> str:
    title = escape(track.title or "", quote=True)
    lines = ['    <article class="card card--music">', f"      <h3>{title}</h3>"]

    poster = poster_src(track, html_dir)
    if poster:
        lines.append(
            f'      <img class="poster" src="{escape(poster, quote=True)}" '
            f'alt="{title} cover" loading="lazy" decoding="async">'
        )
    else:
        lines.append('      <div class="poster poster--empty" aria-hidden="true">no cover</div>')

    if track.artist:
        lines.append(f'      <p><b>Artist:</b> {escape(track.artist, quote=True)}</p>')
    if track.album:
        lines.append(f'      <p><b>Album:</b> {escape(track.album, quote=True)}</p>')
    rating = format_number(track.rating)
    if rating:
        lines.append(f"      <p><b>Rating:</b> {rating} / 5</p>")

    lines.append("    </article>")
    return "\n".join(lines)


def collection_card(record: Any, html_dir: Path, subtitle: str | None = None) -> str:
    """Render a game/anime/manga card (title, poster, rating)."""
    title = escape(record.title or "", quote=True)
    lines = ['    <article class="card">', f"      <h3>{title}</h3>"]

    poster = poster_src(record, html_dir)
    if poster:
        lines.append(
            f'      <img class="poster" src="{escape(poster, quote=True)}" '
            f'alt="{title} poster" loading="lazy" decoding="async">'
        )
    else:
        lines.append('      <div class="poster poster--empty" aria-hidden="true">no poster</div>')

    rating = format_number(record.rating)
    if rating:
        lines.append(f"      <p><b>My rating:</b> {rating} / 10</p>")
    if subtitle:
        lines.append(f'      <p class="muted">{escape(subtitle, quote=True)}</p>')

    lines.append("    </article>")
    return "\n".join(lines)


def anime_subtitle(record: Anime) -> str | None:
    parts = [record.title_type or ""]
    if record.episodes:
        parts.append(f"{record.episodes} episodes")
    return " · ".join(part for part in parts if part) or None


def manga_subtitle(record: Manga) -> str | None:
    parts = [record.title_type or ""]
    if record.chapters:
        parts.append(f"{record.chapters} chapters")
    return " · ".join(part for part in parts if part) or None
