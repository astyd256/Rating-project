"""Render the collection as a static HTML page.

Movie posters are referenced through their on-disk path (``images/movies/<file>``
relative to the site folder); music cover art is embedded as a data URI because
several tracks usually share the same album image.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from lib.db.crud import retrieve_records_by_column
from lib.db.models import Anime, Game, Manga, Movie, Music
from lib.db.session import get_session
from lib.render_cards import (
    anime_subtitle,
    collection_card,
    manga_subtitle,
    movie_card,
    music_card,
)

_STYLE = """
:root {
    color-scheme: light;
    --bg: #f5f5f5;
    --surface: #ffffff;
    --text: #1c1c1c;
    --muted: #666666;
    --border: #e2e2e2;
    --border-strong: #cccccc;
    --poster-bg: #eeeeee;
    --shadow: 0 6px 20px rgba(0, 0, 0, .1);
    --accent-bg: #1c1c1c;
    --accent-text: #ffffff;
    --now-playing: #1a7f37;
}
html[data-theme="dark"] {
    color-scheme: dark;
    --bg: #141414;
    --surface: #1e1e1e;
    --text: #f2f2f2;
    --muted: #a3a3a3;
    --border: #333333;
    --border-strong: #444444;
    --poster-bg: #2a2a2a;
    --shadow: 0 6px 20px rgba(0, 0, 0, .5);
    --accent-bg: #f2f2f2;
    --accent-text: #141414;
    --now-playing: #4ade80;
}
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
    margin: 0;
    padding: 24px;
    background: var(--bg);
    color: var(--text);
    transition: background-color .2s ease, color .2s ease;
}
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 16px;
}
.page-header h1 { margin: 0; font-size: 28px; }
.toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 20px;
}
.toolbar .tabs { margin-bottom: 0; }
.theme-toggle {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    padding: 0;
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
}
.theme-toggle:hover { border-color: var(--text); }
.theme-toggle:focus-visible { outline: 2px solid var(--text); outline-offset: 2px; }
.theme-toggle .icon { width: 18px; height: 18px; display: block; }
.theme-toggle .icon-sun { display: none; }
html[data-theme="dark"] .theme-toggle .icon-sun { display: block; }
html[data-theme="dark"] .theme-toggle .icon-moon { display: none; }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.tab-btn {
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid var(--border-strong);
    background: var(--surface);
    color: var(--text);
    cursor: pointer;
    font-size: 14px;
}
.tab-btn.active { background: var(--accent-bg); border-color: var(--accent-bg); color: var(--accent-text); }
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
    background: var(--surface);
    border: 1px solid var(--border);
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
    background: var(--poster-bg);
    display: block;
}
.card--music .poster { aspect-ratio: 1 / 1; }
.poster--empty {
    display: flex;
    align-items: center;
    justify-content: center;
    border: 1px dashed var(--border-strong);
    color: var(--muted);
    font-size: 12px;
}
.card h3 a { color: inherit; text-decoration: none; }
.card h3 a:hover { text-decoration: underline; }
.card p { margin: 0; font-size: 13px; }
.muted { color: var(--muted); }
@media (max-width: 760px) {
    .toolbar { align-items: stretch; }
    .toolbar .tabs { width: 100%; }
}
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

_THEME_INIT = """
(function () {
    try {
        var stored = localStorage.getItem('theme');
        var theme = stored === 'dark' || stored === 'light'
            ? stored
            : (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
                ? 'dark'
                : 'light');
        document.documentElement.dataset.theme = theme;
    } catch (error) {
        // Storage may be unavailable; the page then uses the light theme.
    }
})();
"""

_THEME_BUTTON = """<button class="theme-toggle" id="theme-toggle" type="button"
        aria-label="Switch to dark theme" aria-pressed="false" title="Switch to dark theme">
  <svg class="icon icon-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>
  </svg>
  <svg class="icon icon-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor"
       stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="4"/>
    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
  </svg>
</button>"""

_THEME_SCRIPT = """
(function () {
    const root = document.documentElement;
    const button = document.getElementById('theme-toggle');
    if (!button) {
        return;
    }
    const labels = {
        light: 'Switch to dark theme',
        dark: 'Switch to light theme'
    };

    function apply(theme) {
        root.dataset.theme = theme;
        const label = labels[theme] || labels.light;
        button.setAttribute('aria-label', label);
        button.setAttribute('title', label);
        button.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
    }

    apply(root.dataset.theme === 'dark' ? 'dark' : 'light');
    button.addEventListener('click', function () {
        const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        apply(next);
        try {
            localStorage.setItem('theme', next);
        } catch (error) {
            // The theme still applies for this page view.
        }
    });
})();
"""

_LASTFM_STYLE = """
.lastfm-widget {
    display: flex;
    align-items: center;
    gap: 10px;
    width: min(300px, 100%);
    padding: 10px 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    box-shadow: var(--shadow);
    color: var(--text);
    text-decoration: none;
}
.lastfm-widget[hidden] { display: none; }
.lastfm-cover {
    width: 48px;
    height: 48px;
    border-radius: 6px;
    object-fit: cover;
    background: var(--poster-bg);
    flex: 0 0 auto;
}
.lastfm-cover[hidden] { display: none; }
.lastfm-meta {
    display: flex;
    flex-direction: column;
    min-width: 0;
    line-height: 1.25;
}
.lastfm-track {
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.lastfm-artist {
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.lastfm-state { font-size: 11px; color: var(--now-playing); margin-top: 2px; }
.lastfm-state--idle { color: var(--muted); }
@media (max-width: 760px) {
    .lastfm-widget {
        width: 100%;
        box-shadow: none;
    }
}
"""

_LASTFM_SCRIPT = """
(function () {
    const cfg = __LASTFM_CONFIG__;
    const widget = document.getElementById('lastfm-widget');
    if (!widget) {
        return;
    }
    const cover = document.getElementById('lastfm-cover');
    const trackElement = document.getElementById('lastfm-track');
    const artistElement = document.getElementById('lastfm-artist');
    const stateElement = document.getElementById('lastfm-state');
    const PLACEHOLDER = '2a96cbd8b46e442fc41c2b86b821562f';
    const profileUrl = 'https://www.last.fm/user/' + encodeURIComponent(cfg.user);
    let delay = Math.max(30, cfg.refresh) * 1000;
    let timer = null;
    let busy = false;

    function pickImage(images) {
        if (!Array.isArray(images)) {
            return null;
        }
        const sizes = ['extralarge', 'large', 'medium', 'small'];
        for (const size of sizes) {
            const match = images.find((image) => image.size === size
                && image['#text']
                && image['#text'].indexOf(PLACEHOLDER) === -1);
            if (match) {
                return match['#text'];
            }
        }
        return null;
    }

    function formatAge(uts) {
        const seconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(uts));
        if (!Number.isFinite(seconds)) {
            return '';
        }
        if (seconds < 60) {
            return 'just now';
        }
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) {
            return minutes + ' min ago';
        }
        const hours = Math.floor(minutes / 60);
        if (hours < 24) {
            return hours + ' h ago';
        }
        return Math.floor(hours / 24) + ' d ago';
    }

    function render(track) {
        const nowPlaying = track['@attr'] && track['@attr'].nowplaying === 'true';
        const artist = track.artist && (track.artist['#text'] || track.artist);
        trackElement.textContent = track.name || 'Unknown track';
        artistElement.textContent = artist || '';
        if (nowPlaying) {
            stateElement.textContent = 'now playing';
            stateElement.className = 'lastfm-state';
        } else {
            const uts = track.date && track.date.uts;
            stateElement.textContent = uts ? 'last played ' + formatAge(uts) : 'last played';
            stateElement.className = 'lastfm-state lastfm-state--idle';
        }

        const image = pickImage(track.image);
        if (image && /^https?:\\/\\//i.test(image)) {
            cover.src = image;
            cover.hidden = false;
        } else {
            cover.removeAttribute('src');
            cover.hidden = true;
        }

        widget.href = profileUrl;
        widget.hidden = false;
    }

    async function update() {
        if (busy) {
            return;
        }
        busy = true;
        try {
            const params = new URLSearchParams({
                method: 'user.getrecenttracks',
                user: cfg.user,
                api_key: cfg.key,
                format: 'json',
                limit: '1'
            });
            const response = await fetch(
                'https://ws.audioscrobbler.com/2.0/?' + params.toString(),
                { cache: 'no-store' }
            );
            if (!response.ok) {
                throw new Error('lastfm http ' + response.status);
            }
            const data = await response.json();
            const raw = data && data.recenttracks && data.recenttracks.track;
            const track = Array.isArray(raw) ? raw[0] : raw;
            if (!track) {
                throw new Error('lastfm empty response');
            }
            render(track);
            delay = Math.max(30, cfg.refresh) * 1000;
        } catch (error) {
            // Keep the last successful state and retry with a backoff.
            delay = Math.min(Math.max(delay, 30000) * 2, 300000);
        } finally {
            busy = false;
            schedule();
        }
    }

    function schedule() {
        window.clearTimeout(timer);
        if (document.visibilityState === 'visible') {
            timer = window.setTimeout(update, delay);
        }
    }

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'visible') {
            update();
        } else {
            window.clearTimeout(timer);
        }
    });

    update();
})();
"""


_EXCLUDED_MANGA_TYPES = {"doujin", "light_novel"}


def _lastfm_widget(user: str, api_key: str, refresh_seconds: int) -> tuple[str, str]:
    """Return the widget markup and its script for the given Last.fm account."""
    profile_url = f"https://www.last.fm/user/{quote(user, safe='')}"
    config = json.dumps(
        {
            "user": user,
            "key": api_key,
            "refresh": max(30, int(refresh_seconds)),
        },
        ensure_ascii=True,
    ).replace("</", "<\\/")

    markup = (
        f'<a class="lastfm-widget" id="lastfm-widget" href="{profile_url}" '
        'target="_blank" rel="noopener noreferrer" hidden>\n'
        '  <img class="lastfm-cover" id="lastfm-cover" alt="" width="48" height="48" '
        'loading="lazy" decoding="async">\n'
        '  <span class="lastfm-meta">\n'
        '    <span class="lastfm-track" id="lastfm-track"></span>\n'
        '    <span class="lastfm-artist" id="lastfm-artist"></span>\n'
        '    <span class="lastfm-state lastfm-state--idle" id="lastfm-state">Last.fm</span>\n'
        "  </span>\n"
        "</a>"
    )
    script = _LASTFM_SCRIPT.replace("__LASTFM_CONFIG__", config)
    return markup, script


def main(
    html_name: str,
    db_path: str,
    top_n: int = 30,
    *,
    lastfm_user: str | None = None,
    lastfm_api_key: str | None = None,
    lastfm_refresh: int = 60,
    include_manga_types: set[str] | None = None,
) -> dict[str, Any]:
    """Write the HTML page and return a small report about the generated content."""
    output = Path(html_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    html_dir = output.resolve().parent

    with get_session(db_path) as session:
        movie_rows = retrieve_records_by_column(session, Movie, "rating", None, descending=True)
        music_rows = retrieve_records_by_column(session, Music, "rating", None, descending=True)
        game_rows = retrieve_records_by_column(session, Game, "rating", None, descending=True)
        anime_rows = retrieve_records_by_column(session, Anime, "rating", None, descending=True)
        manga_rows = retrieve_records_by_column(session, Manga, "rating", None, descending=True)

        included = {value.lower() for value in (include_manga_types or set())}
        excluded = set() if "all" in included else _EXCLUDED_MANGA_TYPES - included
        if excluded:
            manga_rows = [
                manga
                for manga in manga_rows
                if (manga.title_type or "").lower() not in excluded
            ]

        if top_n and top_n > 0:
            movie_rows = movie_rows[:top_n]
            music_rows = music_rows[:top_n]
            game_rows = game_rows[:top_n]
            anime_rows = anime_rows[:top_n]
            manga_rows = manga_rows[:top_n]

        movie_cards = [movie_card(movie, html_dir) for movie in movie_rows]
        music_cards = [music_card(track, html_dir) for track in music_rows]
        game_cards = [collection_card(game, html_dir) for game in game_rows]
        anime_cards = [
            collection_card(anime, html_dir, anime_subtitle(anime)) for anime in anime_rows
        ]
        manga_cards = [
            collection_card(manga, html_dir, manga_subtitle(manga)) for manga in manga_rows
        ]

    widget_markup = ""
    widget_script = ""
    if lastfm_user and lastfm_api_key:
        widget_markup, widget_script = _lastfm_widget(
            lastfm_user,
            lastfm_api_key,
            lastfm_refresh,
        )
    style = _STYLE + (_LASTFM_STYLE if widget_markup else "")

    collections = [
        ("movies", "Movies", movie_cards),
        ("music", "Music", music_cards),
        ("games", "Games", game_cards),
        ("anime", "Anime", anime_cards),
        ("manga", "Manga", manga_cards),
    ]
    tab_parts: list[str] = []
    section_parts: list[str] = []
    for index, (key, label, cards) in enumerate(collections):
        active = " active" if index == 0 else ""
        tab_parts.append(
            f'  <button class="tab-btn{active}" type="button" data-target="{key}">'
            f'{label} <span class="count">{len(cards)}</span></button>'
        )
        section_parts.extend(
            [
                f'<section id="{key}" class="section{active}">',
                '  <div class="container">',
                "\n".join(cards),
                "  </div>",
                "</section>",
            ]
        )

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>My Collection</title>",
        f"<script>{_THEME_INIT}</script>",
        f"<style>{style}</style>",
        "</head>",
        "<body>",
        '<header class="page-header">',
        "  <h1>My Collection</h1>",
        _THEME_BUTTON,
        "</header>",
        '<div class="toolbar">',
        '<div class="tabs">',
        *tab_parts,
        "</div>",
        widget_markup,
        "</div>",
        *section_parts,
        f"<script>{_SCRIPT}</script>",
        f"<script>{_THEME_SCRIPT}</script>",
        f"<script>{widget_script}</script>" if widget_script else "",
        "</body>",
        "</html>",
    ]

    output.write_text("\n".join(parts), encoding="utf-8")
    return {
        "path": str(output),
        "movies": len(movie_cards),
        "music": len(music_cards),
        "games": len(game_cards),
        "anime": len(anime_cards),
        "manga": len(manga_cards),
        "bytes": output.stat().st_size,
        "lastfm": bool(widget_markup),
    }
