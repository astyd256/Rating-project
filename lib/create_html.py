"""Render the collection as a static HTML page.

Movie posters are referenced through their on-disk path (``images/movies/<file>``
relative to the site folder); music cover art is embedded as a data URI because
several tracks usually share the same album image.
"""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path
from typing import Any

from lib.db.crud import retrieve_records_by_column
from lib.db.models import Movie, Music
from lib.db.session import get_session
from lib.media import guess_image_mime

_STYLE = """
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
    margin: 0;
    padding: 24px;
    background: #f5f5f5;
    color: #1c1c1c;
}
h1 { margin: 0 0 20px; font-size: 28px; }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.tab-btn {
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid #ccc;
    background: #fff;
    cursor: pointer;
    font-size: 14px;
}
.tab-btn.active { background: #1c1c1c; border-color: #1c1c1c; color: #fff; }
.count { opacity: .65; font-size: 12px; margin-left: 4px; }
.section { display: none; }
.section.active { display: block; }
.container {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 20px;
}
.card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 12px;
    background: #fff;
    border: 1px solid #e2e2e2;
    border-radius: 10px;
}
.card h3 {
    margin: 0;
    font-size: 15px;
    line-height: 1.25;
    height: 2.5em;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
}
.poster {
    width: 100%;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 6px;
    background: #eee;
    display: block;
}
.card--music .poster { aspect-ratio: 1 / 1; }
.poster--empty {
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px dashed #d0d0d0;
    color: #999;
    font-size: 12px;
}
.card p { margin: 0; font-size: 13px; }
.muted { color: #666; }
@media (max-width: 520px) {
    .container { grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
    body { padding: 16px; }
}
"""

_SCRIPT = """
document.querySelectorAll('.tab-btn').forEach((button) => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach((item) => item.classList.remove('active'));
        document.querySelectorAll('.section').forEach((section) => section.classList.remove('active'));
        button.classList.add('active');
        const target = document.getElementById(button.dataset.target);
        if (target) {
            target.classList.add('active');
        }
    });
});
"""


def _format_number(value: Any) -> str | None:
    if value is None:
        return None
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _data_uri(blob: bytes | None) -> str | None:
    if not blob:
        return None
    mime = guess_image_mime(blob)
    if mime is None:
        return None
    encoded = base64.b64encode(blob).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _poster_src(movie: Movie, html_dir: Path) -> str | None:
    """Return the poster path if the file exists next to the generated page."""
    if not movie.poster_path:
        return None
    relative = Path(movie.poster_path)
    if relative.is_absolute():
        return None
    if (html_dir / relative).is_file():
        return movie.poster_path
    return None


def _movie_card(movie: Movie, html_dir: Path) -> str:
    title = escape(movie.title or "", quote=True)
    year = f" ({movie.year})" if movie.year else ""
    lines = ["    <article class=\"card\">", f"      <h3>{title}{year}</h3>"]

    poster = _poster_src(movie, html_dir)
    if poster:
        lines.append(
            f'      <img class="poster" src="{escape(poster, quote=True)}" '
            f'alt="{title} poster" loading="lazy" decoding="async">'
        )
    else:
        lines.append('      <div class="poster poster--empty" aria-hidden="true">no poster</div>')

    rating = _format_number(movie.rating)
    if rating:
        lines.append(f"      <p><b>My rating:</b> {rating} / 10</p>")
    imdb = _format_number(movie.imdb_rating)
    if imdb:
        lines.append(f"      <p><b>IMDb:</b> {imdb} / 10</p>")
    if movie.title_type:
        lines.append(f'      <p class="muted">{escape(movie.title_type, quote=True)}</p>')
    if movie.genres:
        lines.append(f'      <p class="muted">{escape(movie.genres, quote=True)}</p>')

    lines.append("    </article>")
    return "\n".join(lines)


def _music_card(track: Music) -> str:
    title = escape(track.title or "", quote=True)
    lines = ['    <article class="card card--music">', f"      <h3>{title}</h3>"]

    art = _data_uri(track.album_art)
    if art:
        lines.append(
            f'      <img class="poster" src="{art}" alt="{title} cover" '
            f'loading="lazy" decoding="async">'
        )
    else:
        lines.append('      <div class="poster poster--empty" aria-hidden="true">no cover</div>')

    if track.artist:
        lines.append(f'      <p><b>Artist:</b> {escape(track.artist, quote=True)}</p>')
    if track.album:
        lines.append(f'      <p><b>Album:</b> {escape(track.album, quote=True)}</p>')
    rating = _format_number(track.rating)
    if rating:
        lines.append(f"      <p><b>Rating:</b> {rating} / 5</p>")

    lines.append("    </article>")
    return "\n".join(lines)


def main(html_name: str, db_path: str, top_n: int = 50) -> dict[str, Any]:
    """Write the HTML page and return a small report about the generated content."""
    output = Path(html_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_dir = output.resolve().parent

    with get_session(db_path) as session:
        movie_rows = retrieve_records_by_column(session, Movie, "rating", None, descending=True)
        music_rows = retrieve_records_by_column(session, Music, "rating", None, descending=True)

        if top_n and top_n > 0:
            movie_rows = movie_rows[:top_n]
            music_rows = music_rows[:top_n]

        movie_cards = [_movie_card(movie, html_dir) for movie in movie_rows]
        music_cards = [_music_card(track) for track in music_rows]

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>My Collection</title>",
        f"<style>{_STYLE}</style>",
        "</head>",
        "<body>",
        "<h1>My Collection</h1>",
        '<div class="tabs">',
        (
            '  <button class="tab-btn active" type="button" data-target="movies">'
            f'Movies <span class="count">{len(movie_cards)}</span></button>'
        ),
        (
            '  <button class="tab-btn" type="button" data-target="music">'
            f'Music <span class="count">{len(music_cards)}</span></button>'
        ),
        "</div>",
        '<section id="movies" class="section active">',
        '  <div class="container">',
        "\n".join(movie_cards),
        "  </div>",
        "</section>",
        '<section id="music" class="section">',
        '  <div class="container">',
        "\n".join(music_cards),
        "  </div>",
        "</section>",
        f"<script>{_SCRIPT}</script>",
        "</body>",
        "</html>",
    ]

    output.write_text("\n".join(parts), encoding="utf-8")
    return {
        "path": str(output),
        "movies": len(movie_cards),
        "music": len(music_cards),
        "bytes": output.stat().st_size,
    }
